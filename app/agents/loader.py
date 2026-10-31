"""Loads agent prompts from the Markdown files in app/agents/prompts/.

    prompts/<agent>/<task>.md                 the agent's instructions for one task
    prompts/<agent>/subagents/<name>.md       a specialist subagent (front matter: name, description)
    prompts/shared/*.md                       pieces reused via {{include shared/<file>.md}}

Files are read on every run, so edits take effect on the next agent run without restarting the server.
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_INCLUDE = re.compile(r"\{\{\s*include\s+([\w./-]+)\s*\}\}")
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


class PromptFileError(Exception):
    pass


def _path(rel: str) -> Path:
    path = (PROMPTS_DIR / rel).resolve()
    if PROMPTS_DIR not in path.parents:
        raise PromptFileError(f"Prompt path outside the prompts folder: {rel}")
    if not path.is_file():
        raise PromptFileError(f"Missing prompt file: app/agents/prompts/{rel}")
    return path


def parse(text: str) -> tuple[dict, str]:
    """Split optional `key: value` front matter from the Markdown body."""
    meta: dict[str, str] = {}
    m = _FRONT.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        text = text[m.end():]
    return meta, text


def _expand(body: str, depth: int) -> str:
    if depth > 5:
        raise PromptFileError("Prompt includes are nested too deeply.")
    return _INCLUDE.sub(lambda m: read(m.group(1), depth + 1), body)


def read(rel: str, depth: int = 0) -> str:
    """A prompt file's body with includes expanded (front matter removed)."""
    _, body = parse(_path(rel).read_text(encoding="utf-8"))
    return _expand(body, depth).strip()


def task_prompt(agent_key: str, task: str) -> str:
    return read(f"{agent_key}/{task}.md")


def subagents(agent_key: str) -> list[dict]:
    """Subagent specs for deepagents, one per prompts/<agent>/subagents/*.md file."""
    folder = PROMPTS_DIR / agent_key / "subagents"
    specs = []
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        meta, body = parse(f.read_text(encoding="utf-8"))
        specs.append({
            "name": meta.get("name") or f.stem,
            "description": meta.get("description") or f"Specialist: {f.stem}",
            "system_prompt": _expand(body, 0).strip(),
        })
    return specs
