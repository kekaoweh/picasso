"""The editing agent: Claude plans the video through a small set of studio tools.

Each run executes on the signed-in user's own Claude credential (a `claude setup-token`
OAuth token or an API key) via the Claude Agent SDK. The only built-in Claude Code tool
allowed is WebSearch (read-only research). Everything else happens through the studio
tools below: the agent finds licensed footage on the web, studies it, writes and cuts.
"""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from pydantic import ValidationError
from sqlmodel import Session, select

from . import sources
from .config import AGENT_MAX_TURNS, CLAUDE_HOMES_DIR, MODEL, THUMBS_DIR, UPLOADS_DIR, WORK_DIR, fernet
from .db import Asset, Project, Style, User, engine, now
from .media import MediaError, contact_sheet, make_thumbnail, probe
from .timeline import ASPECTS, Timeline, validate_timeline

BUILTIN_TOOLS = [
    "Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "NotebookEdit",
    "WebFetch", "Task", "Agent", "TodoWrite", "Skill",
]
MAX_IMPORTS_PER_RUN = 60
IMPORT_WAIT_SECONDS = 40

SYSTEM_PROMPT = """You are Picasso, an AI film editor with a strong eye. From a creator's brief and a \
style you make a finished, beautiful video on your own: you research the subject, find footage on the \
web, study it, write the piece and cut it. The app renders your timeline with ffmpeg when you finish.

The creator may upload nothing at all. Footage you don't have, you find with search_footage, which \
searches licensed libraries (Pexels, Pixabay, Wikimedia Commons, NASA, the Prelinger archive; only the \
ones that are switched on respond). Everything they return is cleared for reuse, which is why you \
source footage only through these tools and never from other websites. Pexels and Pixabay hold the \
most polished modern, cinematic footage (often 4K) and should be your first choice for most subjects; \
Wikimedia Commons suits real places, nature and history, NASA space and Earth, Prelinger vintage film.

How to work:
1. Read the brief. If it involves facts, people, places or events you're unsure of, use WebSearch to \
get them right. Then call list_assets: use what the creator uploaded first. "reference" assets show a \
look or pace to match; use them in the cut only if the brief asks.
2. Plan a shot list: the beats of the piece and the image each one needs.
3. For each beat, call search_footage with a concrete visual query: subject + shot + light/mood \
("aerial pine forest in fog at dawn", "close up hands kneading dough, warm light", "city street at \
night, rain, neon reflections"). You see a numbered contact sheet of results; look at it. Search again \
with better words when nothing is right. Use kind="image" for stills (they get slow camera moves) \
and kind="audio" to look for a music bed when the creator gave none.
4. Call import_footage with the ids you'll actually use (a few spares are fine; at most \
60 per run). Then view_asset to choose exact in-points.
5. write_script (markdown: hook, beats, on-screen words), then set_timeline. Fix any errors it returns \
and submit again until accepted.
6. Finish with two or three sentences on your creative choices. Don't ask questions; decide.

The look, which matters as much as the content:
- Choose footage that belongs together: the same light, color temperature, pace and quality. A \
cohesive, cinematic film beats a literal one. Prefer clean, well-composed, stable, high-resolution \
shots (1080p+), matching the project's orientation where possible.
- Reject clips with watermarks, logos, burned-in text or subtitles, visible UI, heavy compression, \
or cheap stock clichés (thumbs-up, handshakes, people pointing at screens). Also reject effect plates \
(smoke, fog, light leaks or particles on a black or plain background, green screen): on their own \
they read as an empty frame. View a clip before using it if the preview looked mostly blank.
- Vary shot scale (wide, medium, close), let striking images breathe, and cut on motion.
- Keep on-screen words few, short and purposeful; leave many shots without text.
- Open with the strongest image. End deliberately (a held final shot or a title card).

Editing rules:
- Hit the target duration within about 10%. Total duration is the sum of clip durations.
- Follow the style's pacing (average shot length) and caption placement; vary shot lengths around \
it so the rhythm feels human.
- Title cards sparingly: an opening title and chapter breaks in long videos. Give them a background \
color that suits the footage (deep, muted tones), never pure black by default.
- Video clips: pick in-points (source_start) at good moments you saw, never past the end of the \
source. Images always get motion (zoom_in, zoom_out, pan_left, pan_right).
- If the footage you have can't fill the length, search for more rather than padding with title cards.
- Music: put a music asset under the whole video with timeline.music (~0.25 volume under clips with \
their own sound, ~0.8 otherwise). Set keep_audio=false on clips whose sound would clash. Without music \
or usable sound, prefer clips' natural ambience.
- When you used footage from the libraries, end with a short credits title card such as "Footage: \
Pexels, Wikimedia Commons, NASA" (the app keeps the full per-clip credits).
- Use each clip's `note` field to say briefly why it is there; the creator sees these notes."""


def credential_env(user: User) -> dict[str, str]:
    token = fernet.decrypt(user.token_enc.encode()).decode()
    return credential_env_for(token, user.token_kind, user.id)


def credential_env_for(token: str, kind: str, user_id: str) -> dict[str, str]:
    # A per-user config dir keeps the bundled Claude Code from picking up any login
    # stored for the server's own OS account.
    home = CLAUDE_HOMES_DIR / user_id
    home.mkdir(parents=True, exist_ok=True)
    env = {"CLAUDE_CONFIG_DIR": str(home)}
    if kind == "oauth":
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    else:
        env["ANTHROPIC_API_KEY"] = token
    return env


def base_options(env: dict[str, str], cwd: Path, web_search: bool = False, **kwargs: Any) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODEL,
        env=env,
        cwd=str(cwd),
        tools=["WebSearch"] if web_search else [],
        disallowed_tools=BUILTIN_TOOLS + ([] if web_search else ["WebSearch"]),
        permission_mode="dontAsk",
        setting_sources=[],
        **kwargs,
    )


async def verify_credential(token: str, kind: str, user_id: str) -> None:
    """Make one tiny request so a bad token fails at sign-in, not mid-edit."""
    cwd = WORK_DIR / "verify"
    cwd.mkdir(exist_ok=True)
    options = base_options(credential_env_for(token, kind, user_id), cwd, max_turns=1,
                           system_prompt="Reply with exactly: OK")
    error = None
    async for message in query(prompt="ping", options=options):
        if isinstance(message, ResultMessage) and message.is_error:
            error = message.result or "Claude rejected this credential"
    if error:
        raise RuntimeError(error)


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _load_assets(project_id: str) -> dict[str, Asset]:
    with Session(engine) as s:
        return {a.id: a for a in s.exec(select(Asset).where(Asset.project_id == project_id)).all()}


def build_studio_server(project_id: str, user_id: str, orientation: str):
    candidates: dict[str, sources.Candidate] = {}
    downloads: dict[str, asyncio.Task] = {}  # candidate id -> import task
    download_slots = asyncio.Semaphore(4)

    @tool("list_assets", "List every media asset in this project: the creator's uploads and footage you imported.", {})
    async def list_assets(args: dict[str, Any]) -> dict[str, Any]:
        assets = _load_assets(project_id)
        if not assets:
            return _ok("No assets yet. Find footage with search_footage, or build from title cards.")
        rows = [
            {
                "asset_id": a.id, "kind": a.kind, "role": a.role, "name": a.name,
                "duration_s": round(a.duration, 2) if a.duration and a.kind != "image" else None,
                "size": f"{a.width}x{a.height}" if a.width else None,
                "has_audio": a.has_audio, "creator_note": a.note or None,
                "source": a.source if a.source != "upload" else "uploaded by the creator",
            }
            for a in assets.values()
        ]
        return _ok(json.dumps(rows, indent=1))

    @tool(
        "view_asset",
        "See frames from an image or video asset as a labelled contact sheet. For videos you can "
        "focus on a time range and choose how many frames (1-12) to sample.",
        {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "start": {"type": "number", "description": "Range start in seconds (video only)"},
                "end": {"type": "number", "description": "Range end in seconds (video only)"},
                "frames": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "required": ["asset_id"],
        },
    )
    async def view_asset(args: dict[str, Any]) -> dict[str, Any]:
        asset = _load_assets(project_id).get(args.get("asset_id", ""))
        if not asset:
            return _err(f"Unknown asset_id {args.get('asset_id')!r}; call list_assets.")
        if asset.kind == "audio":
            return _ok(f"{asset.name} is audio ({asset.duration or 0:.1f}s); it has no frames.")
        try:
            jpeg = await contact_sheet(asset, int(args.get("frames") or 6),
                                       float(args.get("start") or 0), args.get("end"))
        except Exception as exc:  # noqa: BLE001 - surface media errors to the agent
            return _err(f"Could not read frames: {exc}")
        return {
            "content": [
                {"type": "image", "data": base64.b64encode(jpeg).decode(), "mimeType": "image/jpeg"},
                {"type": "text", "text": f"{asset.name} ({asset.kind}). Labels are source timestamps."},
            ]
        }

    @tool(
        "write_script",
        "Save the script / edit plan (markdown) for this video. The creator sees it in the editor.",
        {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]},
    )
    async def write_script(args: dict[str, Any]) -> dict[str, Any]:
        with Session(engine) as s:
            project = s.get(Project, project_id)
            project.script = args.get("script", "")
            project.updated_at = now()
            s.add(project)
            s.commit()
        return _ok("Script saved.")

    @tool(
        "set_timeline",
        "Submit the full edit. Clips play back-to-back in order. Returns validation errors to fix, "
        "or a summary once accepted. Schema: " + json.dumps(Timeline.model_json_schema()),
        {"type": "object", "properties": {"timeline": {"type": "object"}}, "required": ["timeline"]},
    )
    async def set_timeline(args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("timeline")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                return _err(f"timeline is not valid JSON: {exc}")
        try:
            timeline = Timeline.model_validate(raw)
        except ValidationError as exc:
            return _err(f"Timeline does not match the schema:\n{exc}")
        errors = validate_timeline(timeline, _load_assets(project_id))
        if errors:
            return _err("Fix these and resubmit:\n- " + "\n- ".join(errors[:40]))
        with Session(engine) as s:
            project = s.get(Project, project_id)
            project.timeline_json = timeline.model_dump_json()
            project.updated_at = now()
            s.add(project)
            s.commit()
            target = project.target_seconds
        total = timeline.total_duration
        drift = ""
        if abs(total - target) > target * 0.1:
            drift = f" That is {total - target:+.1f}s off the {target}s target; adjust if you can."
        return _ok(f"Timeline accepted: {len(timeline.clips)} clips, {total:.1f}s total.{drift}")

    @tool(
        "search_footage",
        "Search licensed footage libraries on the web (Pexels, Pixabay, Wikimedia Commons, NASA, Prelinger "
        "archive; whichever are enabled). Returns a numbered contact sheet of previews plus details "
        "(duration, resolution, license). Write concrete visual queries: subject, shot, light, mood.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What should be on screen, e.g. 'aerial coastline at golden hour'"},
                "kind": {"type": "string", "enum": ["video", "image", "audio"], "description": "Default video"},
                "providers": {"type": "array", "items": {"type": "string"},
                              "description": "Optional: limit to some libraries, e.g. ['NASA']"},
                "per_library": {"type": "integer", "minimum": 2, "maximum": 10, "description": "Default 5"},
            },
            "required": ["query"],
        },
    )
    async def search_footage(args: dict[str, Any]) -> dict[str, Any]:
        query = (args.get("query") or "").strip()
        if not query:
            return _err("Give a query.")
        kind = args.get("kind") or "video"
        found, notes = await sources.search_all(query, kind, orientation, int(args.get("per_library") or 5),
                                                args.get("providers"))
        if not found:
            hint = " (" + "; ".join(notes) + ")" if notes else ""
            return _ok(f"No {kind} results for “{query}”{hint}. Try different, more general words.")
        for c in found:
            c.id = f"f{len(candidates) + 1}"
            candidates[c.id] = c
        text = "\n".join(c.describe() for c in found)
        if notes:
            text += "\nNote: " + "; ".join(notes)
        content: list[dict[str, Any]] = []
        sheet = await sources.preview_sheet(found)
        if sheet:
            content.append({"type": "image", "data": base64.b64encode(sheet).decode(), "mimeType": "image/jpeg"})
        content.append({"type": "text", "text": f"Results for “{query}” ({kind}):\n{text}\n"
                        "Import the ones you'll use with import_footage."})
        return {"content": content}

    @tool(
        "import_footage",
        "Download chosen search results into the project so they can be viewed and cut. Pass the ids "
        "from search_footage (e.g. ['f3', 'f7']). Returns the new asset ids.",
        {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}, "required": ["ids"]},
    )
    async def import_footage(args: dict[str, Any]) -> dict[str, Any]:
        ids = list(dict.fromkeys(args.get("ids") or []))
        unknown = [i for i in ids if i not in candidates]
        new = [i for i in ids if i in candidates and i not in downloads]
        if len(downloads) + len(new) > MAX_IMPORTS_PER_RUN:
            return _err(f"That would exceed {MAX_IMPORTS_PER_RUN} imports this run; "
                        f"you have room for {MAX_IMPORTS_PER_RUN - len(downloads)}.")
        for cid in new:
            # Downloads run as tasks so a slow file never blocks the tool call, and a repeated
            # request for the same id reuses the same download instead of fetching it twice.
            downloads[cid] = asyncio.create_task(_import_one(cid))
        wanted = [i for i in ids if i in downloads]
        await asyncio.wait([downloads[i] for i in wanted], timeout=IMPORT_WAIT_SECONDS)
        lines, pending = [], []
        for cid in wanted:
            task = downloads[cid]
            if not task.done():
                pending.append(cid)
            elif task.exception():
                lines.append(f"{cid}: failed ({task.exception()}); choose another result")
            else:
                lines.append(task.result())
        if pending:
            lines.append(f"Still downloading: {', '.join(pending)}. Call import_footage with these ids "
                         "again to collect them (they will not be downloaded twice).")
        lines += [f"{i}: unknown id" for i in unknown]
        return _ok("\n".join(lines) or "Nothing to import.")

    async def _import_one(cid: str) -> str:
        c = candidates[cid]
        async with download_slots:
            asset = Asset(project_id=project_id, user_id=user_id, kind=c.kind, name=c.title[:120], path="",
                          role="music" if c.kind == "audio" else "footage", source=c.provider,
                          source_url=c.page_url, credit=c.author[:200], license=c.license[:120])
            dest_dir = UPLOADS_DIR / user_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            path = await sources.download(c, dest_dir / asset.id)
            try:
                info = await probe(path)
                thumb = await make_thumbnail(path, c.kind, info.duration, THUMBS_DIR / f"{asset.id}.jpg")
            except MediaError:
                path.unlink(missing_ok=True)
                raise
            asset.path, asset.thumb_path = str(path), str(thumb) if thumb else None
            asset.duration = info.duration if c.kind != "image" else None
            asset.width, asset.height, asset.has_audio = info.width, info.height, info.has_audio
            asset_id = asset.id  # read before commit; the instance is detached afterwards
            with Session(engine) as s:
                s.add(asset)
                s.commit()
        dur = f"{info.duration:.1f}s" if info.duration and c.kind != "image" else "still"
        return f"{cid} -> asset_id {asset_id} ({c.kind}, {dur}, {info.width}x{info.height})"

    tools = [list_assets, view_asset, search_footage, import_footage, write_script, set_timeline]
    server = create_sdk_mcp_server(name="studio", version="1.0.0", tools=tools)

    def cancel_downloads() -> None:
        for task in downloads.values():
            task.cancel()

    return server, [f"mcp__studio__{t.name}" for t in tools], cancel_downloads


TOOL_LABELS = {
    "list_assets": "Looking through your media",
    "search_footage": "Searching for footage",
    "import_footage": "Collecting footage",
    "WebSearch": "Researching",
    "view_asset": "Watching footage",
    "write_script": "Writing the script",
    "set_timeline": "Cutting the timeline",
}

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


def build_prompt(project: Project, style: Style | None, instruction: str) -> str:
    width, height = ASPECTS.get(project.aspect, ASPECTS["16:9"])
    minutes, seconds = divmod(project.target_seconds, 60)
    length = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    parts = [
        f"# Project: {project.name}",
        f"Target duration: {length} ({project.target_seconds}s). Aspect: {project.aspect} ({width}x{height}).",
        "## Brief",
        project.prompt.strip() or "(No brief given. Make the best video you can from the media.)",
    ]
    if style:
        parts += [
            f"## Style: {style.name}",
            style.description,
            f"Average shot length ~{style.pacing_seconds}s. Default caption position: "
            f"{style.caption_position}. Default transition: {style.transition}.",
        ]
    if project.timeline_json and instruction:
        parts += [
            "## Current edit (revise this rather than starting over unless asked)",
            f"Script:\n{project.script}",
            f"Timeline JSON:\n{project.timeline_json}",
            "## Revision request",
            instruction,
        ]
    elif instruction:
        parts += ["## Extra direction", instruction]
    return "\n\n".join(parts)


async def run_agent(user: User, project: Project, style: Style | None, instruction: str,
                    emit: Emit) -> float | None:
    orientation = {"9:16": "portrait", "4:5": "portrait", "1:1": "square"}.get(project.aspect, "landscape")
    server, tool_names, cancel_downloads = build_studio_server(project.id, user.id, orientation)
    cwd = WORK_DIR / project.id
    cwd.mkdir(parents=True, exist_ok=True)
    options = base_options(
        credential_env(user), cwd, web_search=True,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"studio": server},
        allowed_tools=tool_names + ["WebSearch"],
        max_turns=AGENT_MAX_TURNS,
        effort="high",
    )
    cost = None
    error = None
    try:
        cost, error = await _drive(query(prompt=build_prompt(project, style, instruction), options=options), emit)
    finally:
        cancel_downloads()
    # Raise only after the stream is drained; leaving the SDK's generator early
    # breaks its cleanup.
    if error:
        raise RuntimeError(error)
    return cost


async def _drive(stream, emit: Emit) -> tuple[float | None, str | None]:
    cost = None
    error = None
    async for message in stream:
        if isinstance(message, AssistantMessage):
            if message.error:
                # API failures arrive as synthetic assistant text; the run error covers them.
                continue
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    await emit("message", {"text": block.text.strip()})
                elif isinstance(block, ToolUseBlock):
                    name = block.name.removeprefix("mcp__studio__")
                    await emit("tool", {"name": name, "label": TOOL_LABELS.get(name, name),
                                        "input": _summarise_input(name, block.input)})
        elif isinstance(message, ResultMessage):
            cost = message.total_cost_usd
            if message.is_error:
                error = message.result or f"Agent stopped: {message.subtype}"
    return cost, error


def _summarise_input(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "view_asset":
        return {k: data[k] for k in ("asset_id", "start", "end") if k in data}
    if name == "set_timeline":
        clips = (data.get("timeline") or {}).get("clips") if isinstance(data.get("timeline"), dict) else None
        return {"clips": len(clips) if isinstance(clips, list) else None}
    if name == "search_footage":
        return {"query": str(data.get("query", ""))[:120], "kind": data.get("kind") or "video"}
    if name == "import_footage":
        return {"count": len(data.get("ids") or [])}
    if name == "WebSearch":
        return {"query": str(data.get("query", ""))[:120]}
    return {}
