"""Diagram Agent: the canvas assistant that draws and edits flow and architecture diagrams from instructions.

Prompts:   prompts/diagram/diagram_edit.md
Subagents: none (the canvas assistant is interactive, so it stays lean); add files under
           prompts/diagram/subagents/ to give it some.
"""

KEY = "diagram"
NAME = "Diagram Agent"
DESCRIPTION = "Canvas assistant: draws and edits flows and architecture diagrams from your instructions."
DEFAULT_EFFORT = "medium"
TASKS = ("diagram_edit",)
