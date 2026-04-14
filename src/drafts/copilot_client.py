"""GitHub Copilot SDK wrapper for draft generation."""

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


def _create_client() -> CopilotClient:
    """Create a CopilotClient with auth from environment.

    Auth priority (per SDK docs):
    1. COPILOT_GITHUB_TOKEN env var (recommended)
    2. GH_TOKEN env var
    3. GITHUB_TOKEN env var
    4. Stored OAuth credentials (from 'copilot' CLI login)
    5. gh CLI auth

    Supported token types: gho_, ghu_, github_pat_
    NOT supported: ghs_ (GitHub Actions installation tokens)

    For CI, set a PAT with copilot scope as COPILOT_GITHUB_TOKEN secret.
    """
    return CopilotClient()


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
    event_types_seen = []
    session_error = None

    def on_event(event):
        nonlocal current_turn_messages, session_error
        etype = event.type.value
        event_types_seen.append(etype)
        if etype == "assistant.turn_start":
            current_turn_messages = []
        elif etype == "assistant.message":
            content = getattr(event.data, "content", "")
            if content:
                current_turn_messages.append(content)
        elif etype == "assistant.message_delta":
            content = getattr(event.data, "content", "") or getattr(event.data, "delta", "")
            if content:
                current_turn_messages.append(content)
        elif etype == "assistant.turn_end":
            if current_turn_messages:
                messages.append("".join(current_turn_messages))
        elif etype == "session.error":
            error_msg = getattr(event.data, "message", "") or getattr(event.data, "error", "") or str(event.data)
            session_error = error_msg
            logger.error("SDK session error: %s", error_msg)
            done.set()
        elif etype == "session.idle":
            done.set()

    session.on(on_event)
    await session.send(message)
    await done.wait()

    if session_error:
        raise RuntimeError(f"SDK session error: {session_error}")

    # Return the last turn's message (the final answer)
    if messages:
        return messages[-1]
    logger.warning(
        "SDK session produced no content. Events: %s",
        ", ".join(event_types_seen) or "none",
    )
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
    """Internal: create session, send, collect response.

    Uses mode:"replace" to override system prompt and disables
    all tool/skill permissions for raw text generation.
    """
    def deny_all(*args, **kwargs):
        """Deny all permission requests - accepts any signature."""
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
) -> tuple[str, str]:
    """Try models in order with exponential backoff.

    Returns (generated_text, model_name_used).
    """
    last_error = None
    for model_idx, model in enumerate(models):
        for retry in range(3):
            try:
                result = await generate_with_copilot(
                    system_prompt, user_prompt, model, client, temperature
                )
                logger.info("Generated with %s (attempt %d)", model, retry + 1)
                return result, model
            except Exception as e:
                last_error = e
                if _is_retryable_error(e):
                    wait = 3 * (3 ** retry)
                    logger.warning("%s attempt %d failed, waiting %ds: %s",
                                   model, retry + 1, wait, str(e)[:100])
                    await asyncio.sleep(wait)
                    continue
                logger.warning("%s non-retryable failure: %s", model, str(e)[:100])
                break
        if model_idx < len(models) - 1:
            logger.info("Switching to next model, waiting 5s...")
            await asyncio.sleep(5)

    raise RuntimeError(f"All models failed. Last: {last_error}")


async def generate_json_with_fallback(
    system_prompt: str,
    user_prompt: str,
    models: list[str],
    client: CopilotClient,
    temperature: float = 0.7,
) -> tuple[dict, str]:
    """Generate and parse JSON, falling back to next model on parse failure.

    Returns (parsed_dict, model_name_used).
    """
    from src.drafts.drafter import _parse_llm_json

    last_error = None
    for model_idx, model in enumerate(models):
        for retry in range(3):
            try:
                raw = await generate_with_copilot(
                    system_prompt, user_prompt, model, client, temperature
                )
                parsed = _parse_llm_json(raw)
                logger.info("Generated valid JSON with %s", model)
                return parsed, model
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                wait = 3 * (3 ** retry)
                logger.warning("%s returned invalid JSON (attempt %d), waiting %ds: %s",
                               model, retry + 1, wait, str(e)[:80])
                await asyncio.sleep(wait)
                continue
            except Exception as e:
                last_error = e
                if _is_retryable_error(e):
                    wait = 3 * (3 ** retry)
                    logger.warning("%s attempt %d failed, waiting %ds: %s",
                                   model, retry + 1, wait, str(e)[:80])
                    await asyncio.sleep(wait)
                    continue
                logger.warning("%s non-retryable failure: %s", model, str(e)[:80])
                break
        if model_idx < len(models) - 1:
            logger.info("Switching to next model, waiting 5s...")
            await asyncio.sleep(5)

    raise RuntimeError(f"All models failed. Last: {last_error}")


async def run_draft_pipeline(
    system_prompt: str,
    user_prompt: str,
    critic_prompt: str | None,
    critic_input: str | None,
    config: dict,
) -> tuple[dict, str | None, dict]:
    """Run full draft + critique pipeline.

    Returns (parsed_draft_dict, critique_rewrite_or_none, metadata).
    Uses one CopilotClient with separate sessions.
    """
    draft_model = config.get("draft_model", DEFAULT_DRAFT_MODEL)
    critic_model = config.get("critic_model", DEFAULT_CRITIC_MODEL)
    draft_models = [draft_model] + FALLBACK_MODELS
    critic_models = [critic_model, "gpt-4.1"]

    draft_model_used = None
    critic_model_used = None

    async with _create_client() as client:
        # Verify auth before spending time on model calls
        try:
            auth = await client.get_auth_status()
            if not auth.isAuthenticated:
                raise RuntimeError(
                    f"Copilot auth failed (type={auth.authType}, "
                    f"msg={auth.statusMessage}). "
                    "In CI, add a COPILOT_GITHUB_TOKEN repo secret "
                    "(classic PAT with 'copilot' scope)."
                )
            logger.info("Copilot authenticated as %s (type=%s)", auth.login, auth.authType)
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning("Could not verify auth status: %s", e)

        # Step 1: Draft (JSON parsed via model fallback chain)
        draft_parsed, draft_model_used = await generate_json_with_fallback(
            system_prompt, user_prompt, draft_models, client
        )

        # Step 2: Critique (raw text, if prompt provided)
        critique_text = None
        if critic_prompt and critic_input:
            try:
                draft_body = draft_parsed.get("body", "")
                full_critic_input = f"{critic_input}\n\n{draft_body}"
                critique_text, critic_model_used = await generate_with_fallback(
                    critic_prompt, full_critic_input, critic_models, client
                )
            except Exception:
                logger.warning("Critique failed, using draft as-is", exc_info=True)

        metadata = {
            "draft_model": draft_model_used,
            "critic_model": critic_model_used,
        }
        return draft_parsed, critique_text, metadata


def run_pipeline_sync(
    system_prompt: str,
    user_prompt: str,
    critic_prompt: str | None = None,
    critic_input: str | None = None,
    config: dict | None = None,
) -> tuple[dict, str | None, dict]:
    """Sync wrapper for the async pipeline. Call from click commands."""
    return asyncio.run(
        run_draft_pipeline(
            system_prompt, user_prompt, critic_prompt, critic_input, config or {}
        )
    )
