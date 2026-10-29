import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .agent import run_agent
from .config import RENDERS_DIR, WORK_DIR
from .db import Asset, Project, Run, RunEvent, Style, User, engine, now
from .media import render_timeline
from .timeline import Timeline, validate_timeline

log = logging.getLogger("picasso.pipeline")

TERMINAL = {"done", "error", "cancelled"}
_tasks: dict[str, asyncio.Task] = {}


def emit_sync(run_id: str, type_: str, data: dict[str, Any]) -> None:
    with Session(engine) as s:
        s.add(RunEvent(run_id=run_id, type=type_, data=json.dumps(data)))
        s.commit()


async def emit(run_id: str, type_: str, data: dict[str, Any]) -> None:
    emit_sync(run_id, type_, data)


def _set(run_id: str, **fields: Any) -> None:
    with Session(engine) as s:
        run = s.get(Run, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        s.add(run)
        s.commit()


async def _status(run_id: str, status: str, **fields: Any) -> None:
    _set(run_id, status=status, **fields)
    await emit(run_id, "status", {"status": status, **{k: v for k, v in fields.items() if k == "error"}})


async def _execute(run_id: str) -> None:
    with Session(engine) as s:
        run = s.get(Run, run_id)
        project = s.get(Project, run.project_id)
        user = s.get(User, run.user_id)
        style = s.get(Style, project.style_id) if project.style_id else None
        for obj in (run, project, user, style):
            if obj is not None:
                s.expunge(obj)

    try:
        if run.mode == "agent":
            await _status(run_id, "planning")
            cost = await run_agent(user, project, style, run.instruction,
                                   lambda t, d: emit(run_id, t, d))
            _set(run_id, cost_usd=cost)

        with Session(engine) as s:
            project = s.get(Project, run.project_id)
            assets = {a.id: a for a in s.exec(select(Asset).where(Asset.project_id == project.id)).all()}
            style = s.get(Style, project.style_id) if project.style_id else s.get(Style, "sty_explainer")
            s.expunge_all()
        if not project.timeline_json:
            raise RuntimeError("The agent finished without producing a timeline.")
        timeline = Timeline.model_validate_json(project.timeline_json)
        if errors := validate_timeline(timeline, assets):
            raise RuntimeError("Timeline references missing media: " + "; ".join(errors[:5]))

        await _status(run_id, "rendering")
        out = RENDERS_DIR / f"{run_id}.mp4"

        async def progress(done: int, total: int) -> None:
            await emit(run_id, "progress", {"done": done, "total": total})

        duration = await render_timeline(timeline, assets, style, project.aspect, out,
                                         WORK_DIR / run_id, progress)
        _set(run_id, output_path=str(out), duration=duration, finished_at=now())
        await _status(run_id, "done")
    except asyncio.CancelledError:
        _set(run_id, finished_at=now())
        emit_sync(run_id, "status", {"status": "cancelled"})
        _set(run_id, status="cancelled")
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        _set(run_id, finished_at=now())
        await _status(run_id, "error", error=friendly_error(str(exc)))
    finally:
        _tasks.pop(run_id, None)


def friendly_error(message: str) -> str:
    lowered = message.lower()
    if "authenticate" in lowered or "401" in message or "invalid api key" in lowered:
        return ("Claude rejected your token (it may have expired or been revoked). Sign out, run "
                "`claude setup-token` again and sign in with the new token.")
    if "429" in message or "rate limit" in lowered or "usage limit" in lowered:
        return "You've hit your Claude usage limit. Try again once it resets."
    return message[:2000]


def start(run_id: str) -> None:
    _tasks[run_id] = asyncio.create_task(_execute(run_id))


def cancel(run_id: str) -> bool:
    task = _tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


def recover_interrupted_runs() -> None:
    with Session(engine) as s:
        for run in s.exec(select(Run).where(Run.status.not_in(TERMINAL))).all():
            run.status = "error"
            run.error = "Interrupted because the server restarted. Start it again."
            run.finished_at = now()
            s.add(run)
        s.commit()


def output_file(run: Run) -> Path | None:
    if run.output_path and Path(run.output_path).exists():
        return Path(run.output_path)
    return None
