# Picasso

Created and maintained by **Keka Oweh** ([github.com/kekaoweh](https://github.com/kekaoweh)).

An AI video editor where an agent makes the whole video. You describe what you want, add footage,
references and music, and pick a style. Claude watches the media, writes a script, cuts a timeline,
and the backend renders an MP4. Ask for changes in plain language to get a new version.

- **Frontend:** Next.js 15 (App Router, Tailwind v4), Notion-style UI, `frontend/`
- **Backend:** FastAPI + SQLite + ffmpeg, `backend/`
- **Agent:** Claude Agent SDK (`claude-opus-5-5`), running on each user's own Claude credential

## Run it

Requirements: Node 20+, [uv](https://docs.astral.sh/uv/). Python and ffmpeg are installed
automatically: uv fetches Python, and a static ffmpeg build comes from `imageio-ffmpeg` (a
system `ffmpeg` on `PATH` is used instead when one exists).

```bash
./dev.sh            # backend on :8000, frontend on http://localhost:3100
```

## Signing in

Users sign in with their Claude account:

1. Run `claude setup-token` in a terminal (it opens the browser for Claude login).
2. Paste the `sk-ant-oat…` token on the Picasso sign-in page.

The token is checked with one tiny request, encrypted (Fernet) and stored, then passed to the agent as
`CLAUDE_CODE_OAUTH_TOKEN` for that user's runs only. Each user gets an isolated `CLAUDE_CONFIG_DIR`, and
the server strips any `ANTHROPIC_*` credentials from its own environment. A run can never fall back
to a different account. Anthropic API keys (`sk-ant-api…`) are accepted at the same screen.

> **Before you launch publicly:** Anthropic's Agent SDK terms say third-party products may not offer
> claude.ai login or subscription rate limits to their users unless Anthropic has approved it
> ([docs](https://code.claude.com/docs/en/agent-sdk/overview)). Using your own token yourself is fine.
> For other users, get approval first, or switch them to API keys (already supported).

## How a video gets made

```
brief + media + style ──▶ agent (Claude, studio tools only) ──▶ timeline JSON ──▶ ffmpeg ──▶ MP4
```

The agent has no shell or file access. Built-in Claude Code tools are disabled, and it only gets four
tools scoped to the project (`backend/app/agent.py`):

| Tool | What it does |
| --- | --- |
| `list_assets` | Lists the project's clips, photos and audio, with the user's notes and roles |
| `view_asset` | Returns a labelled contact sheet of frames (optionally for a time range) |
| `write_script` | Saves the markdown script shown in the editor |
| `set_timeline` | Validates the edit (schema, asset ids, trims within source length) and saves it |

The timeline (`backend/app/timeline.py`) is a list of clips, either media or title cards. Each clip
has trims, captions, Ken Burns motion for stills and a transition, plus an optional music bed.
`backend/app/media.py` renders each clip to a normalized segment (style grade, captions, fades),
concatenates the segments and mixes in the music. Supported formats: 16:9, 9:16, 1:1 and 4:5.

**Asset roles:** *Footage* is cut into the video. *Reference* shows the agent a look or pacing to
match. *Music* becomes the soundtrack.

**Styles** combine editing direction for the agent (pacing, tone, caption usage) with render
settings (caption position, color and box, transitions, brightness, contrast, saturation). There are
five built-in styles, and users can create their own on the Styles page.

## Configuration (env vars)

| Var | Default | |
| --- | --- | --- |
| `PICASSO_MODEL` | `claude-opus-5-5` | Model the agent uses |
| `PICASSO_DATA_DIR` | `backend/data` | DB, uploads, renders |
| `PICASSO_SECRET_KEY` | auto-generated in data dir | Fernet key for stored tokens |
| `PICASSO_AGENT_MAX_TURNS` | `80` | |
| `PICASSO_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `PICASSO_FFMPEG` / `PICASSO_FONT` | auto | Override the ffmpeg binary / caption font |
| `PICASSO_BACKEND_URL` (frontend) | `http://127.0.0.1:8000` | Where Next proxies `/api` |

## Not built yet

- Generating new footage with an AI video model. The agent currently edits only what you upload;
  `set_timeline` / `render_timeline` are the place to add a "generate shot" clip type.
- Voiceover / TTS and auto-captions from speech.
- A background job queue. Runs are asyncio tasks in the API process, so use a single worker, or add
  Redis/Celery to scale out.

## Author

**Keka Oweh** ([github.com/kekaoweh](https://github.com/kekaoweh)). Picasso is designed, built and owned by
Keka Oweh.
