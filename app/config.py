import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# On Vercel the deployed files are read-only; only /tmp is writable (and it is not shared or permanent).
ON_VERCEL = bool(os.environ.get("VERCEL"))
DATA_DIR = Path(os.environ.get("DA_DATA_DIR") or ("/tmp/archflow-data" if ON_VERCEL else ROOT / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATIC_DIR = ROOT / "static"

HOST = os.environ.get("DA_HOST", "127.0.0.1")
PORT = int(os.environ.get("DA_PORT", "8000"))
