"""Runs an agent task, either as a LangGraph deep agent or as a single fast model call.

Deep mode (default): `deepagents.create_deep_agent` on LangGraph, with
  - planning (write_todos),
  - a virtual file system holding the project context (/context/*.md|json) that subagents share,
  - the agent's specialist subagents (task tool),
  - project tools: validate_mermaid, check_requirement_coverage, list_requirements, get_stage_output.
Fast mode: one prompt, one JSON answer (no tools), through app.providers.
"""

import asyncio
import json
import logging
import re
import time
from collections import Counter

from ..providers import LLMError, complete
from . import context, loader
from .registry import AGENTS, task_prompt

log = logging.getLogger("digital_architect")

DEEP_TIMEOUT = 900  # seconds for a whole deep-agent run, including subagents
RECURSION_LIMIT = 80  # LangGraph steps; bounds runaway tool loops


def parse_json(text: str) -> dict:
    """Extract a JSON object from a model reply (tolerates fences and surrounding prose)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the reply.")
    candidate = t[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", candidate))  # trailing commas


def system_prompt(task: str, deep: bool) -> str:
    """Role prompt (prompts/<agent>/<task>.md) + deep-agent workflow + JSON output contract."""
    try:
        parts = [task_prompt(task)]
        if deep:
            parts.append(loader.read("shared/deep-workflow.md"))
        parts.append(context.output_contract(task))
    except loader.PromptFileError as e:
        raise LLMError(str(e))
    return "\n\n".join(parts)


async def run(agent_key: str, task: str, user_prompt: str, provider: dict, cfg: dict,
              project: dict | None = None) -> tuple[dict, dict]:
    """Run one task and return (parsed JSON result, run metadata)."""
    engine = cfg.get("engine") or "deep"
    model = cfg.get("model") or provider.get("default_model") or ""
    effort = cfg.get("effort") or AGENTS[agent_key]["default_effort"]
    max_tokens = int(cfg.get("max_tokens") or 32000)
    label = f"{AGENTS[agent_key]['name']} / {task} [{engine}] on {provider.get('label')} · {model}"
    started = time.monotonic()
    log.info("%s: started", label)

    if engine == "deep":
        data, extra = await _run_deep(agent_key, task, user_prompt, provider, model, effort, max_tokens, project or {}, label)
    else:
        data, extra = await _run_direct(task, user_prompt, provider, model, effort, max_tokens)

    duration = round(time.monotonic() - started, 1)
    log.info("%s: done in %.1fs", label, duration)
    meta = {"agent": agent_key, "engine": engine, "provider": provider.get("label"),
            "model": model or provider.get("default_model"), "duration_s": duration, **extra}
    return data, meta


# ---------------------------------------------------------------- fast mode

async def _run_direct(task, user_prompt, provider, model, effort, max_tokens) -> tuple[dict, dict]:
    system = system_prompt(task, deep=False)
    text = await complete(provider, model, system, user_prompt, max_tokens=max_tokens, effort=effort)
    try:
        return parse_json(text), {}
    except ValueError as e:
        repair = (f"{user_prompt}\n\n## Note\nYour previous reply was not valid JSON ({e}). "
                  "Return ONLY the JSON object, with no text before or after it.")
        text = await complete(provider, model, system, repair, max_tokens=max_tokens, effort=effort)
        try:
            return parse_json(text), {}
        except ValueError as e2:
            raise LLMError(f"The agent did not return valid JSON twice: {e2}")


# ---------------------------------------------------------------- deep mode

def build_deep_agent(agent_key: str, task: str, provider: dict, model: str, effort: str, max_tokens: int, project: dict):
    from deepagents import create_deep_agent
    from langchain.agents.middleware import TodoListMiddleware

    from .llm import chat_model
    from .registry import subagents_for
    from .tools import build_tools

    return create_deep_agent(
        model=chat_model(provider, model, effort=effort, max_tokens=max_tokens),
        tools=build_tools(project),
        system_prompt=system_prompt(task, deep=True),
        subagents=subagents_for(agent_key),
        middleware=[TodoListMiddleware()],
        name=agent_key,
    )


async def _run_deep(agent_key, task, user_prompt, provider, model, effort, max_tokens, project, label) -> tuple[dict, dict]:
    from deepagents.backends.utils import create_file_data
    from langchain_core.messages import HumanMessage

    try:
        agent = build_deep_agent(agent_key, task, provider, model, effort, max_tokens, project)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Could not create the deep agent: {_explain(e, provider)}")

    state = {
        "messages": [HumanMessage(user_prompt)],
        "files": {path: create_file_data(text) for path, text in context.context_files(project).items()},
    }
    config = {"recursion_limit": RECURSION_LIMIT}
    steps: list[str] = []

    final = await _stream(agent, state, config, steps, label, provider)
    text = _final_text(final)
    try:
        data = parse_json(text)
    except ValueError:
        # Ask the same agent (same conversation) to emit only the JSON object.
        final["messages"].append(HumanMessage("Your last message was not the final JSON object. Reply now with ONLY "
                                              "the complete JSON object described in your instructions, nothing else."))
        final = await _stream(agent, final, config, steps, label, provider)
        try:
            data = parse_json(_final_text(final))
        except ValueError as e:
            raise LLMError(f"The deep agent did not finish with valid JSON: {e}")

    counts = Counter(steps)
    return data, {"steps": len(steps), "tools_used": dict(counts.most_common())}


async def _stream(agent, state, config, steps: list[str], label: str, provider: dict) -> dict:
    """Run the graph, logging every tool call (plans, subagent delegations, validations) as it happens."""
    final = None
    seen = len(state.get("messages", []))  # on a repair turn, earlier steps are already counted
    try:
        async with asyncio.timeout(DEEP_TIMEOUT):
            async for snapshot in agent.astream(state, config=config, stream_mode="values"):
                final = snapshot
                messages = snapshot.get("messages", [])
                for msg in messages[seen:]:
                    for call in getattr(msg, "tool_calls", None) or []:
                        name = call.get("name")
                        if name == "task":
                            name = f"task→{(call.get('args') or {}).get('subagent_type', '?')}"
                        steps.append(name)
                        log.info("%s:   step %d · %s", label, len(steps), name)
                seen = len(messages)
    except TimeoutError:
        raise LLMError(f"The deep agent did not finish within {DEEP_TIMEOUT // 60} minutes. "
                       "Retry, use a faster model, or switch this agent to Fast mode in Settings.")
    except LLMError:
        raise
    except Exception as e:
        if "recursion" in str(e).lower():
            raise LLMError("The deep agent took too many steps without finishing. Retry or switch it to Fast mode.")
        raise LLMError(_explain(e, provider))
    if not final:
        raise LLMError("The deep agent returned nothing.")
    return final


def _final_text(state: dict) -> str:
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "type", "") == "ai" and not getattr(msg, "tool_calls", None):
            text = msg.text if isinstance(getattr(msg, "text", None), str) else str(msg.content)
            if text.strip():
                return text
    return ""


def _explain(e: Exception, provider: dict) -> str:
    """Turn SDK exceptions from any provider into a short, actionable message."""
    label = provider.get("label") or provider.get("type")
    msg = str(e)
    low = msg.lower()
    if any(s in low for s in ("401", "403", "api key", "api_key", "unauthorized", "permission_denied", "authentication")):
        return f"{label} rejected the API key. Check it in Settings."
    if "429" in low or "quota" in low or "rate limit" in low or "resource_exhausted" in low:
        if "perday" in low or "per day" in low:
            limit = re.search(r"limit: (\d+)", msg)
            return (f"{label}: daily quota used up{f' ({limit.group(1)} requests/day)' if limit else ''}. "
                    "A deep agent makes many model calls per run, so free tiers run out fast. Enable billing, "
                    "assign another provider in Settings, or switch this agent to ⚡ Fast mode.")
        return f"{label}: rate limit or quota exceeded. Wait a minute and retry, or check your plan."
    if "503" in low or "overloaded" in low or "unavailable" in low:
        return f"{label}: the model is overloaded right now. Try again shortly or pick another model in Settings."
    if "404" in low or "not found" in low:
        return f"{label}: model not found. Check the model id in Settings."
    if "timed out" in low or "timeout" in low:
        return f"{label}: the request timed out. Retry, or pick a faster model in Settings."
    return f"{label}: {type(e).__name__}: {msg[:400]}"
