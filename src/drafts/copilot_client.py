"""GitHub Copilot SDK wrapper for draft generation.

This module handles all AI interactions through the Copilot SDK.
Two modes of operation:

1. Raw text generation (generate_with_copilot / generate_with_fallback):
   - Uses deny_all permissions to prevent tool/skill invocation
   - system_message mode="replace" overrides the SDK's default system prompt
     so only our voice profile and rules apply
   - Used for both drafting and critique steps

2. JSON generation (generate_json_with_fallback):
   - Same as raw, but parses the response as JSON
   - Falls back to the next model if JSON parsing fails

Fallback chain:
   Draft: Claude Opus → Claude Sonnet → GPT-4.1
   Critic: GPT-5.4 → GPT-4.1
   Each model is retried once on transient errors (timeout, 429, 5xx).

The run_draft_pipeline function orchestrates the full draft+critique flow
using a single CopilotClient with separate sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging

from copilot import CopilotClient

logger = logging.getLogger(__name__)

_RETRYABLE_PATTERNS = ["timeout", "429", "500", "502", "503", "504", "connection", "eof", "empty response"]


def _is_retryable_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(p in err_str for p in _RETRYABLE_PATTERNS)

# Models configuration
DEFAULT_DRAFT_MODEL = "claude-opus-4.6"
DEFAULT_CRITIC_MODEL = "gpt-5.4"
FALLBACK_MODELS = ["claude-sonnet-4.6", "gpt-4.1"]


async def _send_and_collect(session, message: str) -> str:
    """Send a message and collect the final assistant response text.

    The SDK is agentic and may produce multiple turns (reasoning,
    tool calls, skill invocations). We only want the last
    assistant.message content from the final turn.
    """
    messages = []
    current_turn_messages = []
    done = asyncio.Event()

    def on_event(event):
        nonlocal current_turn_messages
        etype = event.type.value
        if etype == "assistant.turn_start":
            current_turn_messages = []
        elif etype == "assistant.message":
            content = getattr(event.data, "content", "")
            if content:
                current_turn_messages.append(content)
        elif etype == "assistant.turn_end":
            if current_turn_messages:
                messages.append("".join(current_turn_messages))
        elif etype == "session.idle":
            done.set()

    session.on(on_event)
    await session.send(message)
    await done.wait()

    # Return the last turn's message (the final answer)
    if messages:
        return messages[-1]
    logger.warning("SDK session produced no assistant.message events")
    return ""


async def generate_with_copilot(
    system_prompt: str,
    user_prompt: str,
    model: str,
    client: CopilotClient,
    temperature: float = 0.7,
) -> str:
    """Generate text using a Copilot SDK session. Returns raw response text.

    Uses deny_all permissions to prevent the agent from invoking
    tools/skills - we want raw text generation only.
    """
    try:
        result = await asyncio.wait_for(
            _generate_session(system_prompt, user_prompt, model, client),
            timeout=120,
        )
        if not result.strip():
            raise RuntimeError(f"Empty response from {model}")
        return result
    except TimeoutError:
        logger.warning("SDK session timed out for %s", model)
        raise RuntimeError(f"SDK session timed out for {model}")


async def _generate_session(
    system_prompt: str, user_prompt: str, model: str, client: CopilotClient
) -> str:
    """Internal: create session, send, collect response."""
    def deny_all(request):
        return False

    async with await client.create_session(
        model=model,
        system_message={"mode": "replace", "content": system_prompt},
        on_permission_request=deny_all,
    ) as session:
        return await _send_and_collect(session, user_prompt)


async def generate_with_fallback(
    system_prompt: str,
    user_prompt: str,
    models: list[str],
    client: CopilotClient,
    temperature: float = 0.7,
) -> str:
    """Try models in order, fall back on failure."""
    last_error = None
    for model in models:
        for retry in range(2):
            try:
                result = await generate_with_copilot(
                    system_prompt, user_prompt, model, client, temperature
                )
                logger.info("Generated with %s (attempt %d)", model, retry + 1)
                return result
            except Exception as e:
                last_error = e
                if retry == 0 and _is_retryable_error(e):
                    logger.warning("%s retry: %s", model, str(e)[:100])
                    await asyncio.sleep(1)
                    continue
                logger.warning("%s failed, next model: %s", model, str(e)[:100])
                break

    raise RuntimeError(f"All models failed. Last: {last_error}")


async def generate_json_with_fallback(
    system_prompt: str,
    user_prompt: str,
    models: list[str],
    client: CopilotClient,
    temperature: float = 0.7,
) -> dict:
    """Generate and parse JSON, falling back to next model on parse failure."""
    from src.drafts.drafter import _parse_llm_json

    last_error = None
    for model in models:
        for retry in range(2):
            try:
                raw = await generate_with_copilot(
                    system_prompt, user_prompt, model, client, temperature
                )
                parsed = _parse_llm_json(raw)
                logger.info("Generated valid JSON with %s", model)
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                if retry == 0:
                    logger.warning("%s returned invalid JSON, retrying: %s", model, str(e)[:80])
                    await asyncio.sleep(0.5)
                    continue
                logger.warning("%s JSON failed twice, next model: %s", model, str(e)[:80])
                break
            except Exception as e:
                last_error = e
                if retry == 0 and _is_retryable_error(e):
                    logger.warning("%s transient error, retrying: %s", model, str(e)[:80])
                    await asyncio.sleep(1)
                    continue
                logger.warning("%s failed, next model: %s", model, str(e)[:80])
                break

    raise RuntimeError(f"All models failed. Last: {last_error}")


async def run_draft_pipeline(
    system_prompt: str,
    user_prompt: str,
    critic_prompt: str | None,
    critic_input: str | None,
    config: dict,
) -> tuple[dict, str | None]:
    """Run full draft + critique pipeline.

    Returns (parsed_draft_dict, critique_rewrite_or_none).
    Uses one CopilotClient with separate sessions.
    """
    draft_model = config.get("draft_model", DEFAULT_DRAFT_MODEL)
    critic_model = config.get("critic_model", DEFAULT_CRITIC_MODEL)
    draft_models = [draft_model] + FALLBACK_MODELS
    critic_models = [critic_model, "gpt-4.1"]

    async with CopilotClient() as client:
        # Step 1: Draft (JSON parsed via model fallback chain)
        draft_parsed = await generate_json_with_fallback(
            system_prompt, user_prompt, draft_models, client
        )

        # Step 2: Critique (raw text, if prompt provided)
        critique_text = None
        if critic_prompt and critic_input:
            try:
                draft_body = draft_parsed.get("body", "")
                full_critic_input = f"{critic_input}\n\n{draft_body}"
                critique_text = await generate_with_fallback(
                    critic_prompt, full_critic_input, critic_models, client
                )
            except Exception:
                logger.warning("Critique failed, using draft as-is", exc_info=True)

        return draft_parsed, critique_text


def run_pipeline_sync(
    system_prompt: str,
    user_prompt: str,
    critic_prompt: str | None = None,
    critic_input: str | None = None,
    config: dict | None = None,
) -> tuple[dict, str | None]:
    """Sync wrapper for the async pipeline. Call from click commands."""
    return asyncio.run(
        run_draft_pipeline(
            system_prompt, user_prompt, critic_prompt, critic_input, config or {}
        )
    )
