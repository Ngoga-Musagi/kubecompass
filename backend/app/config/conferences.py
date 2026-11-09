"""Loads conference definitions from deployment/configuration/conferences/*.yaml."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator

from app.config.settings import get_settings


class SourceConfig(BaseModel):
    adapter: str
    event_code: str
    sessions_url: str
    speakers_url: str
    local_sessions_file: str
    local_speakers_file: str
    schedule_url: str | None = None


class CategoryConfig(BaseModel):
    track: str
    audience_level: str | None = None
    subtopic: str | None = None
    projects: str | None = None
    flags: dict[str, str] = Field(default_factory=dict)


class QuestionConfig(BaseModel):
    speaker_company: str | None = None
    speaker_company_override: str | None = None
    speaker_title: str | None = None
    session_slides: str | None = None
    session_repository: str | None = None
    session_demo: str | None = None
    session_website: str | None = None
    session_location_map: str | None = None


class TitleRule(BaseModel):
    pattern: str
    format: str

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        re.compile(v)
        return v


class ConferenceConfig(BaseModel):
    id: str
    name: str
    short_name: str
    city: str
    timezone: str
    website: str | None = None
    source: SourceConfig
    categories: CategoryConfig
    questions: QuestionConfig
    format_by_track: dict[str, str] = Field(default_factory=dict)
    format_by_subtopic: dict[str, str] = Field(default_factory=dict)
    format_by_title_without_speakers: list[TitleRule] = Field(default_factory=list)
    non_content_formats: list[str] = Field(default_factory=list)
    non_organization_values: list[str] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        ZoneInfo(v)  # raises for unknown IANA identifiers
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class UnknownConferenceError(KeyError):
    pass


@lru_cache
def load_conferences(directory: Path | None = None) -> dict[str, ConferenceConfig]:
    directory = directory or get_settings().conferences_dir
    confs: dict[str, ConferenceConfig] = {}
    for path in sorted(directory.glob("*.yaml")):
        conf = ConferenceConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        confs[conf.id] = conf
    return confs


def get_conference(conference_id: str) -> ConferenceConfig:
    confs = load_conferences()
    if conference_id not in confs:
        raise UnknownConferenceError(conference_id)
    return confs[conference_id]
