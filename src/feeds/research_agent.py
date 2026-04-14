"""Research agent for gathering verified evidence before drafting."""

from __future__ import annotations

import asyncio
import logging

from copilot import CopilotClient, define_tool
from pydantic import BaseModel, Field

from src.feeds.research_tools import (
    check_terraform_resource,
    fetch_article,
    search_microsoft_learn,
)

logger = logging.getLogger(__name__)


class FetchParams(BaseModel):
    url: str = Field(description="HTTPS URL to fetch article content from")


class LearnSearchParams(BaseModel):
    query: str = Field(description="Search query for Microsoft Learn documentation")


class TerraformCheckParams(BaseModel):
    provider: str = Field(description="Terraform provider name (e.g. azurerm)")
    resource_type: str = Field(description="Resource type to verify (e.g. kubernetes_cluster)")


@define_tool(description="Fetch article content from a URL for fact verification", skip_permission=True)
async def tool_fetch_article(params: FetchParams) -> str:
    return fetch_article(params.url)


@define_tool(description="Search Microsoft Learn documentation", skip_permission=True)
async def tool_search_learn(params: LearnSearchParams) -> str:
    return search_microsoft_learn(params.query)


@define_tool(description="Verify a Terraform resource exists in the registry", skip_permission=True)
async def tool_check_terraform(params: TerraformCheckParams) -> str:
    return check_terraform_resource(params.provider, params.resource_type)


async def gather_evidence(
    title: str,
    summary: str,
    source_url: str,
    model: str = "claude-opus-4.6",
) -> dict:
    """Run the research agent to gather verified evidence.

    Returns a dict with:
    - article_summary: fetched source text
    - learn_results: Microsoft Learn verification
    - verified_claims: list of verified facts
    - unverified_claims: list of claims that couldn't be verified
    """
    try:
        return await asyncio.wait_for(
            _run_research_session(title, summary, source_url, model),
            timeout=120,
        )
    except TimeoutError:
        logger.warning("Research agent timed out")
    except Exception:
        logger.warning("Research agent failed", exc_info=True)

    # Tool-free fallback: fetch the source article directly
    try:
        logger.info("Attempting tool-free fallback via fetch_article")
        article_text = fetch_article(source_url)
        if article_text and not article_text.startswith(("Blocked:", "Fetch failed:")):
            return {
                "article_summary": article_text,
                "verified_claims": [],
                "unverified_claims": [],
                "key_facts": [],
                "source_url": source_url,
            }
    except Exception:
        logger.warning("Tool-free fallback also failed", exc_info=True)

    return {
        "article_summary": summary,
        "verified_claims": [],
        "unverified_claims": [],
        "key_facts": [],
        "source_url": source_url,
    }


async def _run_research_session(
    title: str, summary: str, source_url: str, model: str
) -> dict:
    """Internal: run the full research SDK session."""
    system_prompt = """You are a research agent. Your job is to gather and verify facts
for a LinkedIn post about an Azure/cloud technology update.

INSTRUCTIONS:
1. Fetch the source article using fetch_article
2. If the article mentions specific Azure features, verify them with search_learn
3. If Terraform resources are mentioned, verify with check_terraform
4. Return a JSON summary of your findings

OUTPUT FORMAT (JSON only):
{
    "article_summary": "2-3 sentence summary of the source article",
    "verified_claims": ["claim 1 (verified via Learn)", "claim 2 (in source article)"],
    "unverified_claims": ["claim that could not be confirmed"],
    "key_facts": ["specific fact 1", "specific fact 2"],
    "source_url": "the original URL"
}

Use at most 5 tool calls. Be efficient."""

    user_prompt = f"""Research this Azure update for a LinkedIn post:

Title: {title}
Summary: {summary}
Source URL: {source_url}

Fetch the source article first, then verify any specific Azure feature claims."""

    async with CopilotClient() as client:
        async with await client.create_session(
            model=model,
            system_message={"mode": "replace", "content": system_prompt},
            tools=[tool_fetch_article, tool_search_learn, tool_check_terraform],
            on_permission_request=lambda _: True,
        ) as session:
            messages: list[str] = []
            current_turn: list[str] = []
            done = asyncio.Event()

            def on_event(event):
                nonlocal current_turn
                etype = event.type.value
                if etype == "assistant.turn_start":
                    current_turn = []
                elif etype == "assistant.message":
                    content = getattr(event.data, "content", "")
                    if content:
                        current_turn.append(content)
                elif etype == "assistant.turn_end":
                    if current_turn:
                        messages.append("".join(current_turn))
                elif etype == "session.idle":
                    done.set()

            session.on(on_event)
            await session.send(user_prompt)
            await done.wait()

            if messages:
                raw = messages[-1]
                from src.drafts.drafter import _parse_llm_json
                return _parse_llm_json(raw)

    return {
        "article_summary": summary,
        "verified_claims": [],
        "unverified_claims": [],
        "key_facts": [],
        "source_url": source_url,
    }


def gather_evidence_sync(
    title: str, summary: str, source_url: str, model: str = "claude-opus-4.6",
) -> dict:
    """Sync wrapper for gather_evidence."""
    return asyncio.run(gather_evidence(title, summary, source_url, model))
