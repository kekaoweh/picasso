import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    token_kind: str  # "oauth" (claude setup-token) or "api_key"
    token_enc: str
    token_hint: str
    created_at: datetime = Field(default_factory=now)


class AuthSession(SQLModel, table=True):
    id: str = Field(primary_key=True)  # sha256 of the cookie value
    user_id: str = Field(index=True, foreign_key="user.id")
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime


class Style(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("sty"), primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)  # None = built-in preset
    name: str
    emoji: str = "🎬"
    description: str
    pacing_seconds: float = 4.0
    caption_position: str = "bottom"
    caption_color: str = "#FFFFFF"
    caption_box: bool = True
    transition: str = "cut"
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    created_at: datetime = Field(default_factory=now)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("prj"), primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    name: str = "Untitled video"
    emoji: str = "🎞️"
    prompt: str = ""
    target_seconds: int = 60
    aspect: str = "16:9"
    style_id: Optional[str] = None
    script: str = ""
    timeline_json: str = ""
    latest_run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Asset(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("ast"), primary_key=True)
    project_id: str = Field(index=True, foreign_key="project.id")
    user_id: str = Field(index=True)
    kind: str  # video | image | audio
    role: str = "footage"  # footage | reference | music
    name: str
    path: str
    thumb_path: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    has_audio: bool = False
    note: str = ""
    created_at: datetime = Field(default_factory=now)


class Run(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("run"), primary_key=True)
    project_id: str = Field(index=True, foreign_key="project.id")
    user_id: str = Field(index=True)
    instruction: str = ""
    mode: str = "agent"  # agent = plan + render, render = re-render the current timeline
    status: str = "queued"  # queued | planning | rendering | done | error | cancelled
    error: Optional[str] = None
    output_path: Optional[str] = None
    duration: Optional[float] = None
    cost_usd: Optional[float] = None
    created_at: datetime = Field(default_factory=now)
    finished_at: Optional[datetime] = None


class RunEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, foreign_key="run.id")
    type: str  # status | message | tool | progress | error | done
    data: str  # JSON
    created_at: datetime = Field(default_factory=now)


PRESET_STYLES = [
    dict(
        id="sty_documentary", emoji="🎙️", name="Documentary",
        description="Calm, considered pacing. Let shots breathe, use lower-third captions to "
        "introduce ideas, title cards between chapters, gentle fades between sections.",
        pacing_seconds=6.0, caption_position="lower_third", transition="fade",
        contrast=1.05, saturation=0.95,
    ),
    dict(
        id="sty_kinetic", emoji="⚡", name="Kinetic",
        description="Fast, punchy, social-first. Quick cuts on every beat, bold centered captions "
        "with a few words each, hook in the first two seconds, no dead air.",
        pacing_seconds=1.8, caption_position="center", transition="cut",
        contrast=1.12, saturation=1.2,
    ),
    dict(
        id="sty_cinematic", emoji="🎥", name="Cinematic",
        description="Moody and deliberate. Wide establishing shots, slow push-ins on stills, "
        "minimal text, fades to black between scenes, slightly desaturated grade.",
        pacing_seconds=5.0, caption_position="bottom", caption_box=False, transition="fade",
        brightness=-0.03, contrast=1.15, saturation=0.85,
    ),
    dict(
        id="sty_explainer", emoji="💡", name="Explainer",
        description="Clear and structured like a video essay. Title card per section, captions "
        "that state the key point of each shot, steady medium pacing.",
        pacing_seconds=3.5, caption_position="bottom", transition="cut",
    ),
    dict(
        id="sty_minimal", emoji="◻️", name="Minimal",
        description="Clean and quiet. Few, well-chosen shots, almost no text, plain cuts, "
        "natural color.",
        pacing_seconds=4.5, caption_position="bottom", caption_box=False, transition="cut",
    ),
]


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for preset in PRESET_STYLES:
            if not session.get(Style, preset["id"]):
                session.add(Style(**preset))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session


__all__ = [
    "engine", "now", "new_id", "init_db", "get_session", "select", "Session",
    "User", "AuthSession", "Style", "Project", "Asset", "Run", "RunEvent",
]
