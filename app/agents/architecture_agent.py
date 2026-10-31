"""Architecture Agent: solution architecture, data model, APIs, deployment, decisions and improvements.

Prompts:   prompts/architecture/architecture.md
Subagents: prompts/architecture/subagents/*.md  (data-modeler, api-designer, infra-designer)
"""

KEY = "architecture"
NAME = "Architecture Agent"
DESCRIPTION = "Designs and improves the solution architecture, data model, APIs and decisions."
DEFAULT_EFFORT = "high"
TASKS = ("architecture",)
