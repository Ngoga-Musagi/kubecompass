"""Pydantic models for the *raw* Sessionize payloads.

Derived from the actual responses of /view/All and /view/Speakers (inspected
2026-11-09). Unknown extra fields are allowed so additive source changes do not
break ingestion; missing required fields fail validation loudly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Raw(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RawCategoryItem(_Raw):
    id: int
    name: str
    sort: int | None = None


class RawCategory(_Raw):
    id: int
    title: str
    items: list[RawCategoryItem]
    type: str | None = None


class RawRoom(_Raw):
    id: int
    name: str
    sort: int | None = None


class RawQuestion(_Raw):
    id: int
    question: str
    questionType: str | None = None


class RawSessionAnswer(_Raw):
    questionId: int
    answerValue: str | None = None


class RawSession(_Raw):
    id: str
    title: str
    description: str | None = None
    startsAt: str | None = None
    endsAt: str | None = None
    isServiceSession: bool = False
    isPlenumSession: bool = False
    speakers: list[str] = Field(default_factory=list)
    categoryItems: list[int] = Field(default_factory=list)
    questionAnswers: list[RawSessionAnswer] = Field(default_factory=list)
    roomId: int | None = None
    liveUrl: str | None = None
    recordingUrl: str | None = None
    status: str | None = None


class RawLink(_Raw):
    title: str | None = None
    url: str
    linkType: str | None = None


class RawAllSpeaker(_Raw):
    """Speaker as embedded in /view/All (answers reference questionId)."""

    id: str
    firstName: str | None = None
    lastName: str | None = None
    fullName: str
    bio: str | None = None
    tagLine: str | None = None
    profilePicture: str | None = None
    isTopSpeaker: bool = False
    links: list[RawLink] = Field(default_factory=list)
    sessions: list[int] = Field(default_factory=list)
    questionAnswers: list[RawSessionAnswer] = Field(default_factory=list)


class RawSpeakerAnswer(_Raw):
    id: int
    question: str
    answer: str | None = None


class RawSpeakerSessionRef(_Raw):
    id: int
    name: str


class RawSpeaker(_Raw):
    """Speaker from /view/Speakers (answers carry the question text inline)."""

    id: str
    fullName: str
    bio: str | None = None
    tagLine: str | None = None
    profilePicture: str | None = None
    isTopSpeaker: bool = False
    links: list[RawLink] = Field(default_factory=list)
    sessions: list[RawSpeakerSessionRef] = Field(default_factory=list)
    questionAnswers: list[RawSpeakerAnswer] = Field(default_factory=list)


class RawAllView(_Raw):
    sessions: list[RawSession]
    speakers: list[RawAllSpeaker]
    questions: list[RawQuestion]
    categories: list[RawCategory]
    rooms: list[RawRoom]
