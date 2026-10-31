"""Flow Agent: user, system and integration flow diagrams with a description for every step.

Prompts:   prompts/flow/flows.md
Subagents: prompts/flow/subagents/*.md  (flow-designer, edge-case-analyst)
"""

KEY = "flow"
NAME = "Flow Agent"
DESCRIPTION = "Creates user/system flow diagrams (Mermaid) with a description for every step."
DEFAULT_EFFORT = "medium"
TASKS = ("flows",)
