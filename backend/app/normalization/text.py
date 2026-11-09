"""Small, dependency-free text normalization helpers."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"[ \t\f\v]+")
_MULTI_NL = re.compile(r"\n{3,}")
_SLUG = re.compile(r"[^a-z0-9]+")


def clean_text(value: str | None) -> str | None:
    """Normalize line endings/whitespace while preserving paragraph structure."""
    if value is None:
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(_WS.sub(" ", line).strip() for line in text.split("\n"))
    text = _MULTI_NL.sub("\n\n", text).strip()
    return text or None


def strip_emoji(value: str) -> str:
    """Remove leading pictographs used as decoration in category names (e.g. '⚡ Lightning')."""
    chars = [c for c in value if unicodedata.category(c) not in {"So", "Sk", "Cs"} and c != "️"]
    return "".join(chars).strip()


def slugify(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return _SLUG.sub("-", norm).strip("-")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]
