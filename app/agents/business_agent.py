"""Business Needs Agent: turns raw ideas and business notes into structured, testable requirements.

Prompts:   prompts/business/requirements.md
Subagents: prompts/business/subagents/*.md  (domain-analyst, nfr-analyst)
"""

KEY = "business"
NAME = "Business Needs Agent"
DESCRIPTION = "Turns raw ideas and business requirements into structured, testable requirements."
DEFAULT_EFFORT = "medium"
TASKS = ("requirements",)
