"""System Software Architect: reviews requirements, architecture and hand-drawn diagrams, and writes the build plan.

Prompts:   prompts/architect/requirements_review.md, architecture_review.md, diagram_review.md
Subagents: prompts/architect/subagents/*.md  (security-reviewer, scalability-reviewer, delivery-planner)
"""

KEY = "architect"
NAME = "System Software Architect"
DESCRIPTION = "Critically reviews requirements, flows and architecture; produces the build plan."
DEFAULT_EFFORT = "high"
TASKS = ("requirements_review", "architecture_review", "diagram_review")
