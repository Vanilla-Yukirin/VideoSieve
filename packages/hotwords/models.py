"""Typed models for hotwords generation output."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts.models import SCHEMA_VERSION


class HotwordItem(BaseModel):
    """One extracted hotword candidate."""

    model_config = ConfigDict(extra="forbid")

    text: str
    lang: str
    weight: int = Field(ge=1, le=10)
    aliases: list[str] = Field(default_factory=list)


class HotwordsDocument(BaseModel):
    """Canonical `hotwords/hotwords.json` payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    project_id: str
    job_id: str
    generated_at: datetime
    items: list[HotwordItem] = Field(default_factory=list)


class HotwordsResult(BaseModel):
    """Result payload with output location and parsed document."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    job_id: str
    hotwords_path: str
    hotwords: HotwordsDocument
