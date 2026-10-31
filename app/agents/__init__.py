"""The AI agents of Digital Architect.

    prompts/               ALL prompt text, as Markdown files (edit these to change how an agent thinks)
      shared/              pieces reused by several prompts: mermaid-rules, canvas-syntax, deep-workflow, json-rules
      business/            requirements.md                + subagents/domain-analyst.md, nfr-analyst.md
      architect/           requirements_review.md, architecture_review.md, diagram_review.md
                           + subagents/security-reviewer.md, scalability-reviewer.md, delivery-planner.md
      flow/                flows.md                       + subagents/flow-designer.md, edge-case-analyst.md
      architecture/        architecture.md                + subagents/data-modeler.md, api-designer.md, infra-designer.md
      diagram/             diagram_edit.md

    business_agent.py, architect_agent.py, flow_agent.py, architecture_agent.py, diagram_agent.py
                 one file per agent: name, description, default effort, tasks it owns
    loader.py    reads the prompt .md files (front matter, {{include ...}})
    stages.py    pipeline order and dependencies
    context.py   JSON output contracts and the project context given to agents
    tools.py     LangChain tools the agents call (validate_mermaid, check_requirement_coverage, ...)
    llm.py       LangChain chat model from the user's provider credentials
    runner.py    runs a task as a LangGraph deep agent (default) or a single fast call
"""

from .context import (build_diagram_edit_prompt, build_diagram_review_prompt, build_user_prompt,
                      node_descriptions)
from .registry import AGENTS, TASK_AGENT, agents_info
from .stages import STAGE_KEYS, STAGES, downstream, stage_def

ENGINES = {
    "deep": "Deep agent (LangGraph: planning, subagents, tools)",
    "direct": "Fast (single model call)",
}
