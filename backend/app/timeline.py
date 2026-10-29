"""The edit decision list the agent writes and the renderer consumes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .db import Asset

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
FPS = 30


class TextOverlay(BaseModel):
    text: str = Field(max_length=280)
    position: Literal["top", "center", "bottom", "lower_third"] | None = None
    style: Literal["caption", "title", "subtitle"] = "caption"


class Clip(BaseModel):
    kind: Literal["asset", "title_card"]
    asset_id: Optional[str] = None
    source_start: float = Field(default=0.0, ge=0)
    duration: float = Field(gt=0.2, le=600)
    text: Optional[TextOverlay] = None
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "none"
    background: str = Field(default="#111111", pattern=r"^#[0-9a-fA-F]{6}$")
    transition: Literal["cut", "fade"] | None = None
    keep_audio: bool = True
    note: str = ""


class Music(BaseModel):
    asset_id: str
    volume: float = Field(default=0.3, ge=0, le=1.5)
    start_at: float = Field(default=0.0, ge=0)


class Timeline(BaseModel):
    title: str = ""
    clips: list[Clip] = Field(min_length=1, max_length=3000)
    music: Optional[Music] = None

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)


def validate_timeline(timeline: Timeline, assets: dict[str, Asset]) -> list[str]:
    errors: list[str] = []
    for i, clip in enumerate(timeline.clips):
        where = f"clips[{i}]"
        if clip.kind == "title_card":
            if clip.asset_id:
                errors.append(f"{where}: title_card must not set asset_id")
            continue
        asset = assets.get(clip.asset_id or "")
        if not asset:
            errors.append(f"{where}: unknown asset_id {clip.asset_id!r}")
            continue
        if asset.kind == "audio":
            errors.append(f"{where}: {asset.id} is audio; use it as timeline.music instead")
        elif asset.kind == "image":
            if clip.source_start:
                errors.append(f"{where}: source_start must be 0 for images")
        elif asset.kind == "video":
            if clip.motion != "none":
                errors.append(f"{where}: motion is only supported on images")
            if asset.duration is not None and clip.source_start + clip.duration > asset.duration + 0.05:
                errors.append(
                    f"{where}: source_start {clip.source_start:.2f} + duration {clip.duration:.2f} "
                    f"exceeds {asset.id} length {asset.duration:.2f}s"
                )
    if timeline.music:
        music = assets.get(timeline.music.asset_id)
        if not music:
            errors.append(f"music: unknown asset_id {timeline.music.asset_id!r}")
        elif music.kind not in ("audio", "video"):
            errors.append(f"music: {music.id} has no audio")
    return errors
