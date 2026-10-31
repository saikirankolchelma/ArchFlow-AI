"""Collects the agent modules: their public info, the tasks they own, and their subagents."""

from . import architect_agent, architecture_agent, business_agent, diagram_agent, flow_agent, loader

MODULES = [business_agent, architect_agent, flow_agent, architecture_agent, diagram_agent]


def agents_info() -> dict:
    """Public info sent to the UI (/api/meta). Subagent names come from the prompt files."""
    return {
        m.KEY: {
            "name": m.NAME,
            "description": m.DESCRIPTION,
            "default_effort": m.DEFAULT_EFFORT,
            "subagents": [s["name"] for s in loader.subagents(m.KEY)],
        }
        for m in MODULES
    }


AGENTS = agents_info()

# task -> agent key, e.g. "flows" -> "flow", "diagram_review" -> "architect"
TASK_AGENT = {task: m.KEY for m in MODULES for task in m.TASKS}


def task_prompt(task: str) -> str:
    return loader.task_prompt(TASK_AGENT[task], task)


def subagents_for(agent_key: str) -> list[dict]:
    return loader.subagents(agent_key)
