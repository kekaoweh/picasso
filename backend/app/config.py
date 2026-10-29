import os
import shutil
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PICASSO_DATA_DIR", BACKEND_DIR / "data")).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
THUMBS_DIR = DATA_DIR / "thumbs"
RENDERS_DIR = DATA_DIR / "renders"
WORK_DIR = DATA_DIR / "work"
CLAUDE_HOMES_DIR = DATA_DIR / "claude-homes"

for d in (DATA_DIR, UPLOADS_DIR, THUMBS_DIR, RENDERS_DIR, WORK_DIR, CLAUDE_HOMES_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("PICASSO_DATABASE_URL", f"sqlite:///{DATA_DIR / 'picasso.db'}")
MODEL = os.environ.get("PICASSO_MODEL", "claude-opus-5-5")
AGENT_MAX_TURNS = int(os.environ.get("PICASSO_AGENT_MAX_TURNS", "80"))
SESSION_DAYS = 30
COOKIE_NAME = "picasso_session"
COOKIE_SECURE = os.environ.get("PICASSO_COOKIE_SECURE", "false").lower() == "true"
FRONTEND_ORIGIN = os.environ.get("PICASSO_FRONTEND_ORIGIN", "http://localhost:3100")

# Each user's agents must run on that user's own Claude credential, never on
# whatever happens to be configured for the server process.
for _var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(_var, None)


def _load_fernet() -> Fernet:
    key = os.environ.get("PICASSO_SECRET_KEY")
    if not key:
        key_file = DATA_DIR / "secret.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            key_file.chmod(0o600)
        key = key_file.read_text().strip()
    return Fernet(key)


fernet = _load_fernet()


def ffmpeg_path() -> str:
    explicit = os.environ.get("PICASSO_FFMPEG")
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


FONT_CANDIDATES = [
    os.environ.get("PICASSO_FONT", ""),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def font_path() -> str:
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("No usable font found for captions; set PICASSO_FONT to a .ttf file")
