import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, or_, select
from sse_starlette.sse import EventSourceResponse

from . import pipeline, sources
from .auth import current_user
from .config import THUMBS_DIR, UPLOADS_DIR
from .db import Asset, Project, Run, RunEvent, Style, User, engine, get_session, now
from .media import MediaError, kind_for, make_thumbnail, probe
from .timeline import ASPECTS, Timeline

router = APIRouter(prefix="/api", tags=["studio"])

MAX_UPLOAD_BYTES = 4 * 1024**3
Aspect = Literal["16:9", "9:16", "1:1", "4:5"]


# ---------------------------------------------------------------------------
# Schemas


class AssetOut(BaseModel):
    id: str
    kind: str
    role: str
    name: str
    duration: Optional[float]
    width: Optional[int]
    height: Optional[int]
    has_audio: bool
    note: str
    has_thumb: bool
    source: str
    source_url: str
    credit: str
    license: str
    created_at: datetime


class RunOut(BaseModel):
    id: str
    project_id: str
    instruction: str
    mode: str
    status: str
    error: Optional[str]
    has_video: bool
    duration: Optional[float]
    cost_usd: Optional[float]
    created_at: datetime
    finished_at: Optional[datetime]


class ProjectSummary(BaseModel):
    id: str
    name: str
    emoji: str
    aspect: str
    target_seconds: int
    style_id: Optional[str]
    cover_asset_id: Optional[str]
    latest_status: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummary):
    prompt: str
    script: str
    timeline: Optional[dict]
    assets: list[AssetOut]
    latest_run: Optional[RunOut]


class StyleOut(BaseModel):
    id: str
    name: str
    emoji: str
    description: str
    pacing_seconds: float
    caption_position: str
    caption_color: str
    caption_box: bool
    transition: str
    brightness: float
    contrast: float
    saturation: float
    builtin: bool


def asset_out(a: Asset) -> AssetOut:
    return AssetOut(id=a.id, kind=a.kind, role=a.role, name=a.name, duration=a.duration,
                    width=a.width, height=a.height, has_audio=a.has_audio, note=a.note,
                    has_thumb=bool(a.thumb_path), source=a.source, source_url=a.source_url,
                    credit=a.credit, license=a.license, created_at=a.created_at)


def run_out(r: Run) -> RunOut:
    return RunOut(id=r.id, project_id=r.project_id, instruction=r.instruction, mode=r.mode,
                  status=r.status, error=r.error, has_video=pipeline.output_file(r) is not None,
                  duration=r.duration, cost_usd=r.cost_usd, created_at=r.created_at,
                  finished_at=r.finished_at)


def style_out(s: Style) -> StyleOut:
    return StyleOut(**s.model_dump(exclude={"user_id", "created_at"}), builtin=s.user_id is None)


def _assets(db: Session, project_id: str) -> list[Asset]:
    return list(db.exec(select(Asset).where(Asset.project_id == project_id)
                        .order_by(col(Asset.created_at))).all())


def _summary(db: Session, p: Project) -> dict:
    cover = db.exec(select(Asset).where(Asset.project_id == p.id, Asset.thumb_path.is_not(None))
                    .order_by(col(Asset.created_at))).first()
    run = db.get(Run, p.latest_run_id) if p.latest_run_id else None
    return dict(id=p.id, name=p.name, emoji=p.emoji, aspect=p.aspect,
                target_seconds=p.target_seconds, style_id=p.style_id,
                cover_asset_id=cover.id if cover else None,
                latest_status=run.status if run else None, created_at=p.created_at,
                updated_at=p.updated_at)


def project_out(db: Session, p: Project) -> ProjectOut:
    run = db.get(Run, p.latest_run_id) if p.latest_run_id else None
    return ProjectOut(
        **_summary(db, p), prompt=p.prompt, script=p.script,
        timeline=json.loads(p.timeline_json) if p.timeline_json else None,
        assets=[asset_out(a) for a in _assets(db, p.id)],
        latest_run=run_out(run) if run else None,
    )


def own_project(project_id: str, user: User, db: Session) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return p


def own_asset(asset_id: str, user: User, db: Session) -> Asset:
    a = db.get(Asset, asset_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Asset not found")
    return a


def own_run(run_id: str, user: User, db: Session) -> Run:
    r = db.get(Run, run_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Run not found")
    return r


# ---------------------------------------------------------------------------
# Projects


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled video", max_length=120)
    prompt: str = Field(default="", max_length=20000)
    target_seconds: int = Field(default=60, ge=5, le=3600)
    aspect: Aspect = "16:9"
    style_id: Optional[str] = "sty_explainer"


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    emoji: Optional[str] = Field(default=None, max_length=8)
    prompt: Optional[str] = Field(default=None, max_length=20000)
    target_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    aspect: Optional[Aspect] = None
    style_id: Optional[str] = None
    script: Optional[str] = Field(default=None, max_length=200000)


def _check_style(style_id: Optional[str], user: User, db: Session) -> None:
    if style_id:
        s = db.get(Style, style_id)
        if not s or (s.user_id and s.user_id != user.id):
            raise HTTPException(400, "Unknown style")


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_session)):
    rows = db.exec(select(Project).where(Project.user_id == user.id)
                   .order_by(col(Project.updated_at).desc())).all()
    return [ProjectSummary(**_summary(db, p)) for p in rows]


@router.post("/projects", response_model=ProjectOut)
def create_project(body: ProjectCreate, user: User = Depends(current_user),
                   db: Session = Depends(get_session)):
    _check_style(body.style_id, user, db)
    p = Project(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return project_out(db, p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    return project_out(db, own_project(project_id, user, db))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, user: User = Depends(current_user),
                   db: Session = Depends(get_session)):
    p = own_project(project_id, user, db)
    data = body.model_dump(exclude_unset=True)
    if "style_id" in data:
        _check_style(data["style_id"], user, db)
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = now()
    db.add(p)
    db.commit()
    db.refresh(p)
    return project_out(db, p)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    p = own_project(project_id, user, db)
    runs = db.exec(select(Run).where(Run.project_id == p.id)).all()
    for r in runs:
        pipeline.cancel(r.id)
        for e in db.exec(select(RunEvent).where(RunEvent.run_id == r.id)).all():
            db.delete(e)
        if f := pipeline.output_file(r):
            f.unlink(missing_ok=True)
        db.delete(r)
    for a in _assets(db, p.id):
        _delete_asset_files(a)
        db.delete(a)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Assets


def _delete_asset_files(a: Asset) -> None:
    Path(a.path).unlink(missing_ok=True)
    if a.thumb_path:
        Path(a.thumb_path).unlink(missing_ok=True)


@router.post("/projects/{project_id}/assets", response_model=list[AssetOut])
async def upload_assets(project_id: str, files: list[UploadFile] = File(...),
                        user: User = Depends(current_user), db: Session = Depends(get_session)):
    p = own_project(project_id, user, db)
    created: list[Asset] = []
    for upload in files:
        name = Path(upload.filename or "upload").name
        kind = kind_for(name, upload.content_type)
        if not kind:
            raise HTTPException(400, f"{name}: only video, image and audio files are supported")
        asset = Asset(project_id=p.id, user_id=user.id, kind=kind, name=name, path="",
                      role="music" if kind == "audio" else "footage")
        dest_dir = UPLOADS_DIR / user.id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{asset.id}{Path(name).suffix.lower()}"
        size = 0
        with dest.open("wb") as fh:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} is larger than 4 GB")
                fh.write(chunk)
        try:
            info = await probe(dest)
            asset.thumb_path = str(await make_thumbnail(dest, kind, info.duration,
                                                        THUMBS_DIR / f"{asset.id}.jpg") or "") or None
        except MediaError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, f"{name}: {exc}") from exc
        asset.path = str(dest)
        asset.duration = info.duration if kind != "image" else None
        asset.width, asset.height, asset.has_audio = info.width, info.height, info.has_audio
        db.add(asset)
        created.append(asset)
    p.updated_at = now()
    db.add(p)
    db.commit()
    for a in created:
        db.refresh(a)
    return [asset_out(a) for a in created]


class AssetUpdate(BaseModel):
    role: Optional[Literal["footage", "reference", "music"]] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    name: Optional[str] = Field(default=None, max_length=200)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: str, body: AssetUpdate, user: User = Depends(current_user),
                 db: Session = Depends(get_session)):
    a = own_asset(asset_id, user, db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.add(a)
    db.commit()
    db.refresh(a)
    return asset_out(a)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    a = own_asset(asset_id, user, db)
    _delete_asset_files(a)
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    a = own_asset(asset_id, user, db)
    return FileResponse(a.path, filename=a.name, content_disposition_type="inline")


@router.get("/assets/{asset_id}/thumb")
def asset_thumb(asset_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    a = own_asset(asset_id, user, db)
    if not a.thumb_path:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(a.thumb_path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------------------
# Styles


class StyleIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    emoji: str = Field(default="🎨", max_length=8)
    description: str = Field(min_length=1, max_length=2000)
    pacing_seconds: float = Field(default=3.5, ge=0.5, le=30)
    caption_position: Literal["top", "center", "bottom", "lower_third"] = "bottom"
    caption_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    caption_box: bool = True
    transition: Literal["cut", "fade"] = "cut"
    brightness: float = Field(default=0.0, ge=-0.3, le=0.3)
    contrast: float = Field(default=1.0, ge=0.5, le=1.6)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)


@router.get("/styles", response_model=list[StyleOut])
def list_styles(user: User = Depends(current_user), db: Session = Depends(get_session)):
    rows = db.exec(select(Style).where(or_(Style.user_id == None, Style.user_id == user.id))  # noqa: E711
                   .order_by(col(Style.user_id).is_not(None), col(Style.created_at))).all()
    return [style_out(s) for s in rows]


@router.post("/styles", response_model=StyleOut)
def create_style(body: StyleIn, user: User = Depends(current_user), db: Session = Depends(get_session)):
    s = Style(user_id=user.id, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return style_out(s)


def own_style(style_id: str, user: User, db: Session) -> Style:
    s = db.get(Style, style_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Style not found (built-in styles can't be edited)")
    return s


@router.put("/styles/{style_id}", response_model=StyleOut)
def update_style(style_id: str, body: StyleIn, user: User = Depends(current_user),
                 db: Session = Depends(get_session)):
    s = own_style(style_id, user, db)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.add(s)
    db.commit()
    db.refresh(s)
    return style_out(s)


@router.delete("/styles/{style_id}")
def delete_style(style_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    s = own_style(style_id, user, db)
    for p in db.exec(select(Project).where(Project.style_id == s.id)).all():
        p.style_id = "sty_explainer"
        db.add(p)
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Runs


class RunCreate(BaseModel):
    instruction: str = Field(default="", max_length=8000)
    mode: Literal["agent", "render"] = "agent"


@router.post("/projects/{project_id}/runs", response_model=RunOut)
async def create_run(project_id: str, body: RunCreate, user: User = Depends(current_user),
               db: Session = Depends(get_session)):
    p = own_project(project_id, user, db)
    if not user.token_enc:
        raise HTTPException(401, "Reconnect your Claude account first")
    if p.latest_run_id:
        last = db.get(Run, p.latest_run_id)
        if last and last.status not in pipeline.TERMINAL:
            raise HTTPException(409, "This video is already being made")
    if body.mode == "render" and not p.timeline_json:
        raise HTTPException(400, "There is no timeline to render yet")
    if body.mode == "agent" and not p.prompt.strip() and not body.instruction.strip():
        raise HTTPException(400, "Describe the video you want first")
    run = Run(project_id=p.id, user_id=user.id, instruction=body.instruction.strip(), mode=body.mode)
    db.add(run)
    p.latest_run_id = run.id
    p.updated_at = now()
    db.add(p)
    db.commit()
    db.refresh(run)
    pipeline.emit_sync(run.id, "status", {"status": "queued"})
    pipeline.start(run.id)
    return run_out(run)


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
def list_runs(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    p = own_project(project_id, user, db)
    rows = db.exec(select(Run).where(Run.project_id == p.id).order_by(col(Run.created_at).desc())).all()
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    return run_out(own_run(run_id, user, db))


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_session)):
    r = own_run(run_id, user, db)
    pipeline.cancel(r.id)
    db.refresh(r)
    return run_out(r)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = 0,
                     user: User = Depends(current_user), db: Session = Depends(get_session)):
    own_run(run_id, user, db)

    async def stream():
        last = after
        while True:
            if await request.is_disconnected():
                return
            with Session(engine) as s:
                events = s.exec(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > last)
                                .order_by(col(RunEvent.id))).all()
                status = s.get(Run, run_id).status
            for e in events:
                last = e.id
                yield {"id": str(e.id), "event": e.type,
                       "data": json.dumps({"id": e.id, "type": e.type, "at": e.created_at.isoformat(),
                                           **json.loads(e.data)})}
            if status in pipeline.TERMINAL and not events:
                yield {"event": "end", "data": "{}"}
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(stream(), ping=15)


@router.get("/runs/{run_id}/video")
def run_video(run_id: str, download: bool = False, user: User = Depends(current_user),
              db: Session = Depends(get_session)):
    r = own_run(run_id, user, db)
    f = pipeline.output_file(r)
    if not f:
        raise HTTPException(404, "No video for this run")
    p = db.get(Project, r.project_id)
    safe = "".join(ch for ch in (p.name if p else "video") if ch.isalnum() or ch in " -_").strip() or "video"
    return FileResponse(f, media_type="video/mp4", filename=f"{safe}.mp4",
                        content_disposition_type="attachment" if download else "inline")


@router.get("/sources")
def footage_sources(user: User = Depends(current_user)):
    """Which footage libraries the editor can search right now."""
    return sources.provider_status()


@router.get("/meta")
def meta():
    return {"aspects": list(ASPECTS), "timeline_schema": Timeline.model_json_schema()}
