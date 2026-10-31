"""File-based storage for settings (provider credentials, agent assignments) and projects."""

import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROJECTS_DIR, SETTINGS_FILE

_lock = threading.RLock()
MASK = "••••••••"

AGENT_KEYS = ("business", "architect", "flow", "architecture", "diagram")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------- settings

def _default_settings() -> dict:
    return {
        "providers": [],
        "agents": {k: {"provider_id": "", "model": "", "effort": "", "max_tokens": 32000, "engine": "deep"}
                   for k in AGENT_KEYS},
    }


def load_settings() -> dict:
    with _lock:
        settings = _read_json(SETTINGS_FILE, None) or _default_settings()
        for k, v in _default_settings()["agents"].items():
            settings.setdefault("agents", {}).setdefault(k, v)
        return settings


def save_settings(settings: dict) -> None:
    with _lock:
        _write_json(SETTINGS_FILE, settings)


def mask_key(key: str) -> str:
    if not key:
        return ""
    return MASK + key[-4:] if len(key) > 8 else MASK


def public_settings() -> dict:
    """Settings safe to send to the browser: API keys are masked."""
    s = load_settings()
    providers = []
    for p in s["providers"]:
        q = dict(p)
        q["api_key"] = mask_key(p.get("api_key", ""))
        q["has_key"] = bool(p.get("api_key"))
        providers.append(q)
    return {"providers": providers, "agents": s["agents"]}


def get_provider(provider_id: str) -> dict | None:
    return next((p for p in load_settings()["providers"] if p["id"] == provider_id), None)


def upsert_provider(data: dict) -> dict:
    with _lock:
        s = load_settings()
        existing = next((p for p in s["providers"] if p["id"] == data.get("id")), None)
        key = data.get("api_key") or ""
        if existing and (not key or key.startswith(MASK)):
            key = existing.get("api_key", "")  # unchanged masked value: keep stored key
        provider = {
            "id": existing["id"] if existing else "p_" + uuid.uuid4().hex[:8],
            "type": data["type"],
            "label": data.get("label") or data["type"],
            "api_key": key,
            "base_url": (data.get("base_url") or "").rstrip("/"),
            "api_version": data.get("api_version") or "",
            "default_model": data.get("default_model") or "",
            "extra_params": data.get("extra_params") or {},
        }
        if existing:
            s["providers"] = [provider if p["id"] == existing["id"] else p for p in s["providers"]]
        else:
            s["providers"].append(provider)
        save_settings(s)
        return provider


def delete_provider(provider_id: str) -> None:
    with _lock:
        s = load_settings()
        s["providers"] = [p for p in s["providers"] if p["id"] != provider_id]
        for a in s["agents"].values():
            if a.get("provider_id") == provider_id:
                a["provider_id"] = ""
        save_settings(s)


def update_agents(agents: dict) -> dict:
    with _lock:
        s = load_settings()
        for k in AGENT_KEYS:
            if k in agents:
                a = agents[k]
                s["agents"][k] = {
                    "provider_id": a.get("provider_id") or "",
                    "model": a.get("model") or "",
                    "effort": a.get("effort") or "",
                    "max_tokens": int(a.get("max_tokens") or 32000),
                    "engine": a.get("engine") if a.get("engine") in ("deep", "direct") else "deep",
                }
        save_settings(s)
        return s["agents"]


# ---------------------------------------------------------------- projects

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "project"


def _project_file(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9\-]+", project_id):
        raise KeyError(project_id)
    return PROJECTS_DIR / project_id / "project.json"


def docs_dir(project_id: str) -> Path:
    return _project_file(project_id).parent / "docs"


def list_projects() -> list[dict]:
    if not PROJECTS_DIR.exists():
        return []
    out = []
    for f in PROJECTS_DIR.glob("*/project.json"):
        p = _read_json(f, None)
        if p:
            out.append({"id": p["id"], "name": p["name"], "updated": p.get("updated", "")})
    return sorted(out, key=lambda p: p["updated"], reverse=True)


def create_project(name: str, idea: str) -> dict:
    with _lock:
        pid = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
        project = {
            "id": pid,
            "name": name,
            "idea": idea,
            "created": now(),
            "updated": now(),
            "stages": {},
            "diagrams": [],
        }
        _write_json(_project_file(pid), project)
        return project


def get_project(project_id: str) -> dict:
    p = _read_json(_project_file(project_id), None)
    if p is None:
        raise KeyError(project_id)
    p.setdefault("stages", {})
    p.setdefault("diagrams", [])
    return p


def save_project(project: dict) -> dict:
    with _lock:
        project["updated"] = now()
        _write_json(_project_file(project["id"]), project)
        return project


def delete_project(project_id: str) -> None:
    with _lock:
        folder = _project_file(project_id).parent
        if folder.exists():
            shutil.rmtree(folder)


DATA_DIR.mkdir(parents=True, exist_ok=True)
