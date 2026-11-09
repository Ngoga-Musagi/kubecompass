"""Per-embedding-model similarity thresholds.

Source: deployment/configuration/embedding-calibration.yaml
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.config.settings import get_settings


class Calibration(BaseModel):
    query_floor: float
    query_ceiling: float
    coverage_min: float
    related_floor: float
    related_ceiling: float
    alternative_min: float


@lru_cache
def _load(path: Path) -> tuple[dict[str, Calibration], str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    models = {name: Calibration.model_validate(v) for name, v in raw["models"].items()}
    return models, raw["default"]


def calibration_for(model_name: str, path: Path | None = None) -> Calibration:
    """Thresholds for an embedding model; unknown models fall back to the default entry."""
    models, default = _load(
        path
        or get_settings().repo_root / "deployment" / "configuration" / "embedding-calibration.yaml"
    )
    return models.get(model_name, models[default])
