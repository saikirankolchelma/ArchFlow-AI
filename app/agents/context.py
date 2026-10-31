"""Output contracts (JSON shapes) and the project context each agent receives.

The prompt text itself lives in Markdown files under prompts/ (see loader.py).
Every agent returns a single JSON object. The docs writer turns that JSON into Markdown,
so the output shapes below are the contract between agents and documentation.
"""

import json

from . import loader
from .stages import stage_def

SHAPES = {
    "requirements": {
        "project_name": "Short product name",
        "summary": "2-3 sentence summary of the product",
        "problem_statement": "The business problem being solved",
        "goals": ["Measurable business goal"],
        "out_of_scope": ["Explicitly excluded item"],
        "personas": [{"name": "Persona", "description": "Who they are", "needs": ["What they need"]}],
        "functional_requirements": [{
            "id": "REQ-001", "title": "Short title", "description": "What the system must do",
            "priority": "must | should | could", "acceptance_criteria": ["Given/When/Then style criterion"],
        }],
        "non_functional_requirements": [{
            "id": "NFR-001", "category": "performance | security | availability | scalability | usability | compliance | maintainability",
            "description": "Quality requirement", "metric": "How it is measured",
        }],
        "constraints": ["Budget, timeline, technology or regulatory constraint"],
        "assumptions": ["Assumption made"],
        "open_questions": ["Question the business must answer"],
        "glossary": [{"term": "Domain term", "definition": "Meaning"}],
    },
    "requirements_review": {
        "verdict": "approve | revise",
        "score": 7,
        "summary": "Overall assessment",
        "strengths": ["What is good"],
        "issues": [{
            "severity": "high | medium | low", "area": "e.g. scope, security, data",
            "description": "The problem", "suggestion": "Concrete fix", "related": ["REQ-001"],
        }],
        "missing_requirements": [{"title": "Missing capability", "why": "Why it matters"}],
        "questions_for_stakeholders": ["Question"],
        "flow_suggestions": [{"name": "Flow that should be diagrammed", "why": "Reason", "related": ["REQ-001"]}],
    },
    "flows": {
        "flows": [{
            "id": "FLOW-01", "name": "Flow name", "type": "user | system | data | integration",
            "description": "What this flow achieves", "actors": ["Actor"], "trigger": "What starts it",
            "mermaid": "flowchart TD\n  start([\"Start\"]) --> a[\"Step\"]",
            "steps": [{"n": 1, "actor": "Who", "action": "What happens", "details": "Rules, validation, data", "covers": ["REQ-001"]}],
            "edge_cases": ["Error or alternative path and how it is handled"],
        }],
        "coverage_notes": "Which requirements are covered by which flows, and any not covered",
    },
    "architecture": {
        "style": "e.g. modular monolith, microservices, serverless, event-driven",
        "summary": "Why this architecture fits the requirements",
        "diagram_mermaid": "flowchart LR\n  web[\"Web App\"] --> api[\"API\"]",
        "components": [{
            "name": "Component", "type": "frontend | gateway | service | worker | database | cache | queue | storage | external",
            "responsibility": "What it does", "technology": "Concrete tech choice",
            "interfaces": ["Exposes / consumes"], "covers": ["REQ-001"],
        }],
        "tech_stack": [{"layer": "Frontend | Backend | Database | Infra | ...", "choice": "Tech", "reason": "Why", "alternatives": ["Alt"]}],
        "data_model": {
            "entities": [{"name": "Entity", "description": "Meaning", "fields": [{"name": "id", "type": "uuid", "notes": "PK"}]}],
            "er_mermaid": "erDiagram\n  USER ||--o{ ORDER : places",
        },
        "api": [{"method": "POST", "path": "/api/orders", "description": "Purpose", "request": "Body summary", "response": "Response summary", "auth": "Who can call"}],
        "nfr_strategies": [{"concern": "e.g. security", "approach": "How the design meets it", "related": ["NFR-001"]}],
        "deployment": {"description": "Hosting and environments", "environments": ["dev", "prod"], "diagram_mermaid": "flowchart LR\n  ..."},
        "decisions": [{"id": "ADR-001", "title": "Decision", "context": "Situation", "decision": "What was decided", "alternatives": ["Option rejected"], "consequences": "Trade-offs"}],
        "improvements": [{"title": "Suggested improvement", "description": "Detail", "impact": "high | medium | low", "effort": "high | medium | low"}],
        "risks": [{"risk": "Technical risk", "mitigation": "How to reduce it"}],
    },
    "architecture_review": {
        "verdict": "approve | revise",
        "score": 7,
        "summary": "Overall assessment",
        "issues": [{
            "severity": "high | medium | low", "area": "e.g. scalability, security, cost",
            "description": "The problem", "suggestion": "Concrete fix", "related": ["REQ-001"],
        }],
        "coverage_gaps": [{"requirement": "REQ-001", "gap": "What the architecture does not cover"}],
        "implementation_plan": [{
            "milestone": "M1 - Name", "goal": "Outcome", "tasks": ["Concrete engineering task"],
            "covers": ["REQ-001"], "done_when": "Exit criteria",
        }],
        "coding_guide": {
            "folder_structure": "Text tree of the recommended repository layout",
            "conventions": ["Coding convention"],
            "getting_started": ["First setup step"],
            "testing_strategy": "How to test",
        },
    },
    "diagram_edit": {
        "summary": "1-3 sentences: what you drew or changed",
        "diagram_name": "Short diagram name",
        "description": "2-4 sentences describing what the diagram shows",
        "mermaid": "flowchart TD\n  n1([\"Start\"]) --> n2[\"Step\"]",
        "node_descriptions": {"n2": "What happens in this step: who/what performs it, inputs and outputs, business rules, errors"},
    },
    "diagram_review": {
        "summary": "Assessment of the diagram",
        "issues": [{"severity": "high | medium | low", "description": "Problem", "suggestion": "Fix"}],
        "suggestions": ["Improvement idea"],
        "improved_mermaid": "flowchart TD\n  ... improved version of the diagram ...",
    },
}


def output_contract(task: str) -> str:
    return f"{loader.read('shared/json-rules.md')}\n{json.dumps(SHAPES[task], indent=2)}"


# ---------------------------------------------------------------- project context

def stage_data(project: dict, key: str):
    return (project.get("stages", {}).get(key) or {}).get("data")


def dump(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False)


def node_descriptions(diagram: dict) -> str:
    nodes = (diagram.get("graph") or {}).get("nodes") or []
    lines = [f"- {n.get('id')} \"{n.get('label')}\": {n['description']}" for n in nodes if n.get("description")]
    return "Node descriptions:\n" + "\n".join(lines) if lines else ""


def manual_diagrams(project: dict, kinds: tuple[str, ...]) -> str:
    parts = []
    for d in project.get("diagrams", []):
        if d.get("kind") in kinds and d.get("mermaid"):
            parts.append(f"### {d.get('name')} ({d.get('kind')})\n{d.get('description') or ''}\n"
                         f"```mermaid\n{d['mermaid']}\n```\n{node_descriptions(d)}")
    return "\n\n".join(parts)


def context_files(project: dict) -> dict[str, str]:
    """Project context as virtual files for a deep agent and its subagents (/context/...)."""
    files = {"/context/idea.md": f"# {project.get('name')}\n\n{project.get('idea') or '(no idea text given)'}\n"}
    for key in ("requirements", "requirements_review", "flows", "architecture", "architecture_review"):
        data = stage_data(project, key)
        if data:
            files[f"/context/{key}.json"] = dump(data)
    diagrams = manual_diagrams(project, ("flow", "architecture", "other"))
    if diagrams:
        files["/context/diagrams.md"] = "# Diagrams drawn by the stakeholder\n\n" + diagrams
    return files


def build_user_prompt(stage_key: str, project: dict, feedback: str = "",
                      context_from: tuple[str, ...] = ()) -> str:
    sections = [f"# Project: {project.get('name')}\n\n## Stakeholder idea / business requirements\n{project.get('idea') or '(none given)'}"]

    req = stage_data(project, "requirements")
    req_review = stage_data(project, "requirements_review")
    flows = stage_data(project, "flows")
    arch = stage_data(project, "architecture")

    if stage_key != "requirements" and req:
        sections.append("## Requirements specification\n" + dump(req))
    if stage_key == "requirements" and req_review:
        sections.append("## Architect's review of the previous requirements (address these issues)\n" + dump(req_review))
    if stage_key in ("flows", "architecture") and req_review:
        sections.append("## Architect's requirements review\n" + dump(req_review))
    if stage_key in ("architecture", "architecture_review") and flows:
        sections.append("## Flows\n" + dump(flows))
    if stage_key == "architecture_review" and arch:
        sections.append("## Architecture\n" + dump(arch))
    if stage_key == "architecture":
        prev_review = stage_data(project, "architecture_review")
        if prev_review:
            sections.append("## Architect's review of the previous architecture (address these issues)\n" + dump(prev_review))

    kinds = {"flows": ("flow", "other"), "architecture": ("architecture", "other"),
             "architecture_review": ("architecture", "flow", "other"), "requirements_review": ("flow", "architecture", "other")}
    manual = manual_diagrams(project, kinds.get(stage_key, ()))
    if manual:
        sections.append("## Diagrams drawn by the stakeholder\n" + manual)

    for src in context_from:
        data = stage_data(project, src)
        if data and src != stage_key:
            sections.append(f"## Output of the {stage_def(src)['title']} stage: apply its relevant suggestions, "
                            f"improvements and decisions to your output\n" + dump(data))

    previous = stage_data(project, stage_key)
    if previous and (feedback or context_from):
        sections.append("## Your previous output for this stage (revise it; keep IDs stable)\n" + dump(previous))
    if feedback:
        sections.append("## Feedback / instructions from the user (highest priority)\n" + feedback)

    sections.append(f"Now produce the {stage_def(stage_key)['title']} as the JSON object described in your instructions.")
    return "\n\n".join(sections)


def build_diagram_edit_prompt(project: dict, diagram: dict, instruction: str, current_mermaid: str,
                              descriptions: dict | None = None) -> str:
    parts = [f"# Project: {project.get('name')}\n\n## Idea\n{project.get('idea') or '(none)'}"]
    req = stage_data(project, "requirements")
    if req:
        reqs = [f"{r.get('id')}: {r.get('title')}" for r in req.get("functional_requirements", [])]
        parts.append("## Requirements\n" + "\n".join(reqs))
    arch = stage_data(project, "architecture")
    if arch and diagram.get("kind") == "architecture":
        comps = [f"{c.get('name')} ({c.get('type')}, {c.get('technology')})" for c in arch.get("components", [])]
        parts.append(f"## Current AI architecture ({arch.get('style')})\n" + "\n".join(comps))
    flows = stage_data(project, "flows")
    if flows and diagram.get("kind") == "flow":
        parts.append("## Existing flows\n" + "\n".join(f"- {f.get('name')}: {f.get('description')}" for f in flows.get("flows", [])))
    history = [m for m in diagram.get("chat", [])][-6:]
    if history:
        parts.append("## Conversation so far\n" + "\n".join(f"{m['role']}: {m['text']}" for m in history))
    parts.append(f"## Diagram: {diagram.get('name')} (type: {diagram.get('kind')})\n"
                 f"Description: {diagram.get('description') or '(none)'}\n"
                 + (f"Current canvas:\n```mermaid\n{current_mermaid}\n```" if current_mermaid.strip() else "The canvas is empty."))
    if descriptions:
        parts.append("## Current node descriptions\n" + "\n".join(f"- {k}: {v}" for k, v in descriptions.items()))
    parts.append(f"## User instruction\n{instruction}")
    return "\n\n".join(parts)


def build_diagram_review_prompt(project: dict, diagram: dict) -> str:
    parts = [f"# Project: {project.get('name')}\n\n## Idea\n{project.get('idea') or ''}"]
    req = stage_data(project, "requirements")
    if req:
        parts.append("## Requirements\n" + dump(req))
    parts.append(f"## Diagram to review: {diagram.get('name')} ({diagram.get('kind')})\n"
                 f"Author's description: {diagram.get('description') or '(none)'}\n```mermaid\n{diagram.get('mermaid')}\n```\n"
                 f"{node_descriptions(diagram)}")
    parts.append("Review this diagram and return the JSON object described in your instructions.")
    return "\n\n".join(parts)
