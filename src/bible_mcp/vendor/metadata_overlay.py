import json
from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_OVERLAY_PATH = Path(__file__).resolve().parent / "theographic_overlay.json"


class OverlayRecord(BaseModel):
    canonical_slug: str
    display_name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)


class MetadataOverlay(BaseModel):
    people: dict[str, OverlayRecord] = Field(default_factory=dict)
    places: dict[str, OverlayRecord] = Field(default_factory=dict)


def load_metadata_overlay(path: Path = DEFAULT_OVERLAY_PATH) -> MetadataOverlay:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MetadataOverlay.model_validate(payload)
