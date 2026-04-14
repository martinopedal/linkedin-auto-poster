"""Configuration loader with pydantic validation."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FeedConfig(BaseModel):
    """Single RSS feed source with URL and display name."""

    url: str
    name: str


class FilterConfig(BaseModel):
    """Keyword filters and scoring thresholds for news item selection."""

    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    min_significance_score: int = 3
    max_posts_per_run: int = 5
    standalone_threshold: int = 7


class LLMConfig(BaseModel):
    """LLM provider and generation parameters for draft creation."""

    provider: str = "azure_openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 500


class LinkedInConfig(BaseModel):
    """LinkedIn post visibility and length constraints."""

    visibility: str = "PUBLIC"
    max_post_length: int = 1500


class PublishConfig(BaseModel):
    """Publishing controls including staleness threshold and dry-run mode."""

    max_age_days: int = 7
    dry_run: bool = False


class AppConfig(BaseModel):
    """Top-level application configuration aggregating all sub-configs."""

    feeds: list[FeedConfig] = Field(default_factory=list)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    linkedin: LinkedInConfig = Field(default_factory=LinkedInConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate configuration from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return AppConfig.model_validate(raw or {})
