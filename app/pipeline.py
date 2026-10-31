"""Runs agents for pipeline stages and stores their results on the project."""

import logging
import re

from . import agents, storage
from .agents import runner
from .agents.runner import parse_json  # noqa: F401  (re-exported)
from .providers import LLMError

log = logging.getLogger("digital_architect")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


class PipelineError(Exception):
    pass


def _agent_runtime(agent_key: str) -> tuple[dict, dict]:
    settings = storage.load_settings()
    cfg = settings["agents"].get(agent_key) or {}
    name = agents.AGENTS[agent_key]["name"]
    if not cfg.get("provider_id"):
        raise PipelineError(f"No provider assigned to the {name}. Open Settings → Agents.")
    provider = storage.get_provider(cfg["provider_id"])
    if not provider:
        raise PipelineError(f"The provider assigned to the {name} no longer exists. Open Settings → Agents.")
    return provider, cfg


async def call_agent(agent_key: str, task: str, user_prompt: str, project: dict | None = None) -> tuple[dict, dict]:
    """Run a task on the agent's configured provider (deep agent or fast mode, per Settings)."""
    provider, cfg = _agent_runtime(agent_key)
    return await runner.run(agent_key, task, user_prompt, provider, cfg, project)


async def run_stage(project_id: str, stage_key: str, feedback: str = "",
                    context_from: list[str] | None = None) -> dict:
    """Run a stage's agent. `context_from` feeds other stages' output in as suggestions to apply
    (e.g. send the architecture review back to the Flow Agent)."""
    stage = agents.stage_def(stage_key)
    sources = tuple(k for k in (context_from or []) if k in agents.STAGE_KEYS and k != stage_key)
    project = storage.get_project(project_id)
    missing = [d for d in stage["depends"] if not (project["stages"].get(d) or {}).get("data")]
    if missing:
        titles = ", ".join(agents.stage_def(m)["title"] for m in missing)
        raise PipelineError(f"Run these stages first: {titles}.")

    user_prompt = agents.build_user_prompt(stage_key, project, feedback, sources)
    data, meta = await call_agent(stage["agent"], stage_key, user_prompt, project)

    # Reload: the user may have edited diagrams while the agent was running.
    project = storage.get_project(project_id)
    prev = project["stages"].get(stage_key) or {}
    history = prev.get("history", [])
    history.append({"at": storage.now(), "feedback": feedback, "applied_from": list(sources), **meta})
    project["stages"][stage_key] = {
        "status": "done",
        "data": data,
        "updated": storage.now(),
        **meta,
        "history": history[-20:],
    }
    _mark_stale(project, stage_key)
    return storage.save_project(project)


def _mark_stale(project: dict, stage_key: str) -> None:
    for key in agents.downstream(stage_key):
        s = project["stages"].get(key)
        if s and s.get("data"):
            s["status"] = "stale"


def set_stage_data(project_id: str, stage_key: str, data: dict) -> dict:
    agents.stage_def(stage_key)
    project = storage.get_project(project_id)
    prev = project["stages"].get(stage_key) or {}
    project["stages"][stage_key] = {**prev, "status": "edited", "data": data, "updated": storage.now()}
    _mark_stale(project, stage_key)
    return storage.save_project(project)


def approve_stage(project_id: str, stage_key: str) -> dict:
    project = storage.get_project(project_id)
    s = project["stages"].get(stage_key)
    if not s or not s.get("data"):
        raise PipelineError("Nothing to approve yet: run this stage first.")
    s["status"] = "approved"
    return storage.save_project(project)


async def assist_diagram(project_id: str, diagram_id: str, instruction: str, current_mermaid: str,
                         descriptions: dict | None = None) -> dict:
    """Diagram Agent: draw or modify a canvas diagram (and its node descriptions) from an instruction."""
    if not instruction.strip():
        raise PipelineError("Type an instruction for the Diagram Agent.")
    project = storage.get_project(project_id)
    diagram = next((d for d in project["diagrams"] if d["id"] == diagram_id), None)
    if not diagram:
        raise KeyError(diagram_id)
    prompt = agents.build_diagram_edit_prompt(project, diagram, instruction, current_mermaid or "",
                                              descriptions if isinstance(descriptions, dict) else None)
    data, meta = await call_agent("diagram", "diagram_edit", prompt, project)
    if not re.match(r"\s*(flowchart|graph)\b", data.get("mermaid") or ""):
        raise LLMError("The Diagram Agent did not return a flowchart. Try rephrasing the instruction.")
    nd = data.get("node_descriptions")
    data["node_descriptions"] = {str(k): str(v) for k, v in nd.items() if v} if isinstance(nd, dict) else {}

    project = storage.get_project(project_id)
    for d in project["diagrams"]:
        if d["id"] == diagram_id:
            chat = d.setdefault("chat", [])
            chat.append({"role": "user", "text": instruction, "at": storage.now()})
            chat.append({"role": "agent", "text": data.get("summary") or "Done.", "at": storage.now(), **meta})
            d["chat"] = chat[-30:]
            storage.save_project(project)
            return {"result": data, "chat": d["chat"]}
    raise KeyError(diagram_id)


async def review_diagram(project_id: str, diagram_id: str) -> dict:
    project = storage.get_project(project_id)
    diagram = next((d for d in project["diagrams"] if d["id"] == diagram_id), None)
    if not diagram:
        raise KeyError(diagram_id)
    if not diagram.get("mermaid"):
        raise PipelineError("The diagram is empty: draw something first.")
    data, meta = await call_agent("architect", "diagram_review",
                                  agents.build_diagram_review_prompt(project, diagram), project)
    project = storage.get_project(project_id)
    for d in project["diagrams"]:
        if d["id"] == diagram_id:
            d["review"] = {"data": data, "updated": storage.now(), **meta}
    return storage.save_project(project)
