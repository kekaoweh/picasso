"""The editing agent: Claude plans the video through a small set of studio tools.

Each run executes on the signed-in user's own Claude credential (a `claude setup-token`
OAuth token or an API key) via the Claude Agent SDK. Built-in Claude Code tools are
disabled; the agent can only touch this project's media through the tools below.
"""

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

from .config import AGENT_MAX_TURNS, CLAUDE_HOMES_DIR, MODEL, WORK_DIR, fernet
from .db import Asset, Project, Style, User, engine, now
from .media import contact_sheet
from .timeline import ASPECTS, Timeline, validate_timeline

BUILTIN_TOOLS = [
    "Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "NotebookEdit",
    "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "Skill",
]

SYSTEM_PROMPT = """You are Picasso, an AI video editor. You turn a creator's brief, their uploaded \
media and a style into a finished edit. You do the whole job yourself: watch the footage, write \
the script, then cut the timeline. The app renders your timeline with ffmpeg once you are done.

How to work:
1. Call list_assets, then view_asset on the footage you might use (and on any "reference" assets, \
which show the look, tone or pacing the creator wants; references are inspiration, only use them in \
the cut if the brief says so). For long videos, view specific time ranges to find the best moments.
2. Call write_script with a short markdown plan: a hook, the sections/beats, and the on-screen text \
for each beat. Keep it tight and specific to the footage you actually saw.
3. Call set_timeline with the full edit. If it returns errors, fix them and call it again until it \
is accepted.
4. Finish with two or three sentences on the creative choices you made. Do not ask questions; \
make sensible decisions and note any assumptions.

Editing rules:
- Hit the target duration within about 10%. Total duration is the sum of clip durations.
- Follow the style's pacing (average shot length) and caption placement; vary shot lengths around \
it so the rhythm feels human.
- Open with a strong hook. Use title cards sparingly (opening title, chapter breaks in long videos).
- Captions should be short (one idea, usually under 12 words) and must match what's on screen.
- Video clips: pick in-points (source_start) at good moments you saw, and never run past the end \
of the source. Images: give them motion (zoom_in, zoom_out, pan_left, pan_right) so they don't \
feel static.
- When there is not enough footage for the target length, reuse different moments of clips and \
stills with different motion rather than padding with title cards.
- If there is an audio asset with role "music", put it under the whole video with timeline.music \
(volume ~0.25 when clips have their own sound, ~0.8 when they don't). Set keep_audio=false on clips \
whose sound would clash.
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


def base_options(env: dict[str, str], cwd: Path, **kwargs: Any) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODEL,
        env=env,
        cwd=str(cwd),
        tools=[],
        disallowed_tools=BUILTIN_TOOLS,
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


def build_studio_server(project_id: str):
    @tool("list_assets", "List every media asset uploaded to this project.", {})
    async def list_assets(args: dict[str, Any]) -> dict[str, Any]:
        assets = _load_assets(project_id)
        if not assets:
            return _ok("No assets uploaded. Build the video from title cards only.")
        rows = [
            {
                "asset_id": a.id, "kind": a.kind, "role": a.role, "name": a.name,
                "duration_s": round(a.duration, 2) if a.duration and a.kind != "image" else None,
                "size": f"{a.width}x{a.height}" if a.width else None,
                "has_audio": a.has_audio, "creator_note": a.note or None,
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

    tools = [list_assets, view_asset, write_script, set_timeline]
    server = create_sdk_mcp_server(name="studio", version="1.0.0", tools=tools)
    return server, [f"mcp__studio__{t.name}" for t in tools]


TOOL_LABELS = {
    "list_assets": "Looking through your media",
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
    server, tool_names = build_studio_server(project.id)
    cwd = WORK_DIR / project.id
    cwd.mkdir(parents=True, exist_ok=True)
    options = base_options(
        credential_env(user), cwd,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"studio": server},
        allowed_tools=tool_names,
        max_turns=AGENT_MAX_TURNS,
        effort="high",
    )
    cost = None
    error = None
    async for message in query(prompt=build_prompt(project, style, instruction), options=options):
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
    # Raise only after the stream is drained; leaving the SDK's generator early
    # breaks its cleanup.
    if error:
        raise RuntimeError(error)
    return cost


def _summarise_input(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "view_asset":
        return {k: data[k] for k in ("asset_id", "start", "end") if k in data}
    if name == "set_timeline":
        clips = (data.get("timeline") or {}).get("clips") if isinstance(data.get("timeline"), dict) else None
        return {"clips": len(clips) if isinstance(clips, list) else None}
    return {}
