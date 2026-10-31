"""Renders project data (agent JSON + hand-drawn diagrams) into structured Markdown docs."""

import io
import re
import zipfile

from . import storage


# ---------------------------------------------------------------- helpers

def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_s(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_s(x)}" for k, x in v.items())
    return str(v)


def _cell(v) -> str:
    return _s(v).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return "_None._\n"
    head = "| " + " | ".join(label for _, label in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(_cell(r.get(key) if isinstance(r, dict) else r) for key, _ in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body]) + "\n"


def bullets(items, empty: str = "_None._") -> str:
    items = [i for i in (items or []) if i]
    if not items:
        return empty + "\n"
    return "\n".join(f"- {_s(i)}" for i in items) + "\n"


MERMAID_CLASSES = {
    "terminal": "fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d",
    "process": "fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a",
    "decision": "fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f",
    "actor": "fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95",
    "service": "fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px,color:#312e81",
    "database": "fill:#ccfbf1,stroke:#0d9488,stroke-width:2px,color:#134e4a",
    "queue": "fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#7c2d12",
    "external": "fill:#f1f5f9,stroke:#64748b,stroke-width:2px,stroke-dasharray:5 4,color:#1e293b",
}
# opener -> shape type (longest openers first)
_OPENERS = [("([", "terminal"), ("[(", "database"), ("[[", "service"), ("((", "actor"), ("[/", "queue"),
            ("[\\", "queue"), ("{{", "decision"), ("{", "decision"), (">", "external"), ("[", "process"), ("(", "process")]
_NODE_RE = re.compile(r"(?<![\w-])([A-Za-z_]\w*)(" + "|".join(re.escape(o) for o, _ in _OPENERS) + ")")
_RESERVED = {"flowchart", "graph", "subgraph", "end", "class", "classDef", "style", "linkStyle", "click", "direction"}


def colorize(code: str) -> str:
    """Give flowchart nodes a colour per shape type, unless the diagram already styles itself."""
    if not re.match(r"\s*(flowchart|graph)\b", code) or re.search(r"\b(classDef|style)\b", code):
        return code
    stripped = re.sub(r'"[^"]*"', '""', code)
    stripped = re.sub(r"\|[^|]*\|", "", stripped)
    types: dict[str, list[str]] = {}
    seen = set()
    for line in stripped.splitlines()[1:]:
        for node_id, opener in _NODE_RE.findall(line):
            if node_id in _RESERVED or node_id in seen:
                continue
            seen.add(node_id)
            types.setdefault(dict(_OPENERS)[opener], []).append(node_id)
    if not types:
        return code
    extra = []
    for t, ids in types.items():
        extra.append(f"  classDef {t} {MERMAID_CLASSES[t]}")
        extra.append(f"  class {','.join(ids)} {t}")
    return code.rstrip() + "\n" + "\n".join(extra)


def mermaid(code: str) -> str:
    code = (code or "").strip()
    return f"```mermaid\n{colorize(code)}\n```\n" if code else ""


def _data(project: dict, key: str) -> dict:
    return (project.get("stages", {}).get(key) or {}).get("data") or {}


def _diagrams(project: dict, kind: str) -> list[dict]:
    return [d for d in project.get("diagrams", []) if d.get("kind") == kind and d.get("mermaid")]


def _manual_section(project: dict, kind: str, title: str) -> str:
    ds = _diagrams(project, kind)
    if not ds:
        return ""
    out = [f"## {title}\n"]
    for d in ds:
        out.append(f"### {d.get('name')}\n")
        if d.get("description"):
            out.append(d["description"].strip() + "\n")
        out.append(mermaid(d["mermaid"]))
        nodes = [n for n in (d.get("graph") or {}).get("nodes", []) if n.get("description")]
        if nodes:
            heading = "Components" if d.get("kind") == "architecture" else "Step details"
            out.append(f"**{heading}**\n")
            out.append(table([{"label": n.get("label"), "type": SHAPE_NAMES.get(n.get("type"), n.get("type")),
                               "description": n.get("description")} for n in nodes],
                             [("label", "Name"), ("type", "Type"), ("description", "Description")]))
    return "\n".join(out)


SHAPE_NAMES = {"terminal": "Start/End", "process": "Process", "decision": "Decision", "actor": "Actor",
               "service": "Service", "database": "Database", "queue": "Queue", "external": "External system",
               "note": "Note"}


# ---------------------------------------------------------------- stage renderers

def render_requirements(project: dict) -> str:
    r = _data(project, "requirements")
    if not r:
        return ""
    out = [f"# Requirements: {r.get('project_name') or project.get('name')}\n"]
    out.append(f"{r.get('summary', '')}\n")
    out.append(f"## Problem statement\n\n{r.get('problem_statement', '')}\n")
    out.append("## Goals\n\n" + bullets(r.get("goals")))
    out.append("## Out of scope\n\n" + bullets(r.get("out_of_scope")))
    out.append("## Personas\n")
    for p in r.get("personas", []):
        out.append(f"### {p.get('name')}\n\n{p.get('description', '')}\n\n**Needs:**\n\n" + bullets(p.get("needs")))
    out.append("## Functional requirements\n")
    out.append(table(r.get("functional_requirements", []),
                     [("id", "ID"), ("title", "Title"), ("priority", "Priority"), ("description", "Description")]))
    out.append("### Acceptance criteria\n")
    for fr in r.get("functional_requirements", []):
        if fr.get("acceptance_criteria"):
            out.append(f"**{fr.get('id')} – {fr.get('title')}**\n\n" + bullets(fr["acceptance_criteria"]))
    out.append("## Non-functional requirements\n")
    out.append(table(r.get("non_functional_requirements", []),
                     [("id", "ID"), ("category", "Category"), ("description", "Description"), ("metric", "Metric")]))
    out.append("## Constraints\n\n" + bullets(r.get("constraints")))
    out.append("## Assumptions\n\n" + bullets(r.get("assumptions")))
    out.append("## Open questions\n\n" + bullets(r.get("open_questions")))
    if r.get("glossary"):
        out.append("## Glossary\n\n" + table(r["glossary"], [("term", "Term"), ("definition", "Definition")]))
    return "\n".join(out)


def _issues(issues: list) -> str:
    return table(issues or [], [("severity", "Severity"), ("area", "Area"), ("description", "Issue"),
                                ("suggestion", "Suggestion"), ("related", "Related")])


def render_requirements_review(project: dict) -> str:
    r = _data(project, "requirements_review")
    if not r:
        return ""
    out = ["# Requirements Review (System Architect)\n",
           f"**Verdict:** {r.get('verdict', '')} &nbsp; **Score:** {r.get('score', '')}/10\n",
           f"{r.get('summary', '')}\n",
           "## Strengths\n\n" + bullets(r.get("strengths")),
           "## Issues\n\n" + _issues(r.get("issues")),
           "## Missing requirements\n\n" + table(r.get("missing_requirements", []), [("title", "Capability"), ("why", "Why")]),
           "## Questions for stakeholders\n\n" + bullets(r.get("questions_for_stakeholders")),
           "## Suggested flows\n\n" + table(r.get("flow_suggestions", []), [("name", "Flow"), ("why", "Why"), ("related", "Related")])]
    return "\n".join(out)


def render_flows(project: dict, include_manual: bool = True) -> str:
    r = _data(project, "flows")
    manual = _manual_section(project, "flow", "Hand-drawn flows") if include_manual else ""
    if not r and not manual:
        return ""
    out = ["# Flows\n"]
    flows = r.get("flows", []) if r else []
    if flows:
        out.append("| ID | Flow | Type | Trigger |\n|---|---|---|---|")
        out.extend(f"| {_cell(f.get('id'))} | {_cell(f.get('name'))} | {_cell(f.get('type'))} | {_cell(f.get('trigger'))} |" for f in flows)
        out.append("")
    for f in flows:
        out.append(f"## {f.get('id', '')} {f.get('name', '')}\n")
        out.append(f"{f.get('description', '')}\n")
        out.append(f"**Actors:** {_s(f.get('actors'))}  \n**Trigger:** {f.get('trigger', '')}\n")
        out.append(mermaid(f.get("mermaid", "")))
        out.append("### Steps\n")
        out.append(table(f.get("steps", []), [("n", "#"), ("actor", "Actor"), ("action", "Action"),
                                              ("details", "Details"), ("covers", "Covers")]))
        if f.get("edge_cases"):
            out.append("### Edge cases\n\n" + bullets(f["edge_cases"]))
    if r and r.get("coverage_notes"):
        out.append(f"## Coverage notes\n\n{r['coverage_notes']}\n")
    if manual:
        out.append(manual)
    return "\n".join(out)


def render_architecture(project: dict, include_manual: bool = True) -> str:
    a = _data(project, "architecture")
    manual = _manual_section(project, "architecture", "Hand-drawn architecture diagrams") if include_manual else ""
    if not a and not manual:
        return ""
    out = ["# Architecture\n"]
    if a:
        out.append(f"**Style:** {a.get('style', '')}\n\n{a.get('summary', '')}\n")
        out.append("## System diagram\n\n" + mermaid(a.get("diagram_mermaid", "")))
        out.append("## Components\n\n" + table(a.get("components", []), [
            ("name", "Component"), ("type", "Type"), ("responsibility", "Responsibility"),
            ("technology", "Technology"), ("interfaces", "Interfaces"), ("covers", "Covers")]))
        out.append("## Tech stack\n\n" + table(a.get("tech_stack", []), [
            ("layer", "Layer"), ("choice", "Choice"), ("reason", "Reason"), ("alternatives", "Alternatives")]))
        out.append("## Non-functional strategies\n\n" + table(a.get("nfr_strategies", []), [
            ("concern", "Concern"), ("approach", "Approach"), ("related", "Related")]))
        dep = a.get("deployment") or {}
        if dep:
            out.append(f"## Deployment\n\n{dep.get('description', '')}\n\n**Environments:** {_s(dep.get('environments'))}\n")
            out.append(mermaid(dep.get("diagram_mermaid", "")))
        out.append("## Suggested improvements\n\n" + table(a.get("improvements", []), [
            ("title", "Improvement"), ("description", "Description"), ("impact", "Impact"), ("effort", "Effort")]))
        out.append("## Risks\n\n" + table(a.get("risks", []), [("risk", "Risk"), ("mitigation", "Mitigation")]))
        out.append("See also: [Data model](05-data-model.md) · [API](06-api.md) · [Decisions](07-decisions.md)\n")
    if manual:
        out.append(manual)
    return "\n".join(out)


def render_data_model(project: dict) -> str:
    dm = _data(project, "architecture").get("data_model") or {}
    if not dm:
        return ""
    out = ["# Data Model\n", mermaid(dm.get("er_mermaid", ""))]
    for e in dm.get("entities", []):
        out.append(f"## {e.get('name')}\n\n{e.get('description', '')}\n")
        out.append(table(e.get("fields", []), [("name", "Field"), ("type", "Type"), ("notes", "Notes")]))
    return "\n".join(out)


def render_api(project: dict) -> str:
    api = _data(project, "architecture").get("api") or []
    if not api:
        return ""
    return "# API\n\n" + table(api, [("method", "Method"), ("path", "Path"), ("description", "Description"),
                                     ("request", "Request"), ("response", "Response"), ("auth", "Auth")])


def render_decisions(project: dict) -> str:
    decisions = _data(project, "architecture").get("decisions") or []
    if not decisions:
        return ""
    out = ["# Architecture Decision Records\n"]
    for d in decisions:
        out.append(f"## {d.get('id', '')}: {d.get('title', '')}\n")
        out.append(f"**Context:** {d.get('context', '')}\n\n**Decision:** {d.get('decision', '')}\n")
        out.append("**Alternatives considered:**\n\n" + bullets(d.get("alternatives")))
        out.append(f"**Consequences:** {d.get('consequences', '')}\n")
    return "\n".join(out)


def render_architecture_review(project: dict) -> str:
    r = _data(project, "architecture_review")
    if not r:
        return ""
    return "\n".join([
        "# Architecture Review (System Architect)\n",
        f"**Verdict:** {r.get('verdict', '')} &nbsp; **Score:** {r.get('score', '')}/10\n",
        f"{r.get('summary', '')}\n",
        "## Issues\n\n" + _issues(r.get("issues")),
        "## Requirement coverage gaps\n\n" + table(r.get("coverage_gaps", []), [("requirement", "Requirement"), ("gap", "Gap")]),
    ])


def render_plan(project: dict) -> str:
    r = _data(project, "architecture_review")
    plan = r.get("implementation_plan") or []
    if not plan:
        return ""
    out = ["# Implementation Plan\n"]
    for m in plan:
        out.append(f"## {m.get('milestone', '')}\n\n**Goal:** {m.get('goal', '')}\n")
        out.append("**Tasks:**\n\n" + "\n".join(f"- [ ] {_s(t)}" for t in m.get("tasks", [])) + "\n")
        out.append(f"**Covers:** {_s(m.get('covers'))}  \n**Done when:** {m.get('done_when', '')}\n")
    return "\n".join(out)


def render_agents_md(project: dict) -> str:
    req = _data(project, "requirements")
    arch = _data(project, "architecture")
    review = _data(project, "architecture_review")
    guide = review.get("coding_guide") or {}
    if not (req or arch):
        return ""
    out = [f"# AGENTS.md: coding brief for {project.get('name')}\n",
           "This file is the entry point for developers and AI coding assistants. "
           "Read it first, then the linked docs. Reference requirement IDs (REQ-xxx / NFR-xxx) in commits, PRs and tests.\n",
           f"## What we are building\n\n{req.get('summary', '')}\n"]
    if arch:
        out.append(f"## Architecture\n\n**Style:** {arch.get('style', '')}. Details in [04-architecture.md](04-architecture.md).\n")
        out.append("## Tech stack\n\n" + table(arch.get("tech_stack", []), [("layer", "Layer"), ("choice", "Choice")]))
    if guide.get("folder_structure"):
        out.append(f"## Repository layout\n\n```text\n{guide['folder_structure']}\n```\n")
    if guide.get("getting_started"):
        out.append("## Getting started\n\n" + "\n".join(f"{i}. {_s(s)}" for i, s in enumerate(guide["getting_started"], 1)) + "\n")
    if guide.get("conventions"):
        out.append("## Conventions\n\n" + bullets(guide["conventions"]))
    if guide.get("testing_strategy"):
        out.append(f"## Testing\n\n{guide['testing_strategy']}\n")
    if review.get("implementation_plan"):
        out.append("## Build order\n\n" + "\n".join(
            f"{i}. **{m.get('milestone', '')}**: {m.get('goal', '')}" for i, m in enumerate(review["implementation_plan"], 1)
        ) + "\n\nFull task list: [09-implementation-plan.md](09-implementation-plan.md).\n")
    out.append("## Docs index\n\nSee [README.md](README.md).\n")
    return "\n".join(out)


FILES = [
    ("01-requirements.md", "Requirements", render_requirements),
    ("02-requirements-review.md", "Requirements review", render_requirements_review),
    ("03-flows.md", "Flows", render_flows),
    ("04-architecture.md", "Architecture", render_architecture),
    ("05-data-model.md", "Data model", render_data_model),
    ("06-api.md", "API", render_api),
    ("07-decisions.md", "Decisions (ADRs)", render_decisions),
    ("08-architecture-review.md", "Architecture review", render_architecture_review),
    ("09-implementation-plan.md", "Implementation plan", render_plan),
    ("AGENTS.md", "Coding brief for developers / AI assistants", render_agents_md),
]


def _other_diagrams(project: dict) -> str:
    return _manual_section(project, "other", "Diagrams")


def render_docs(project: dict) -> dict[str, str]:
    files: dict[str, str] = {}
    for name, _, fn in FILES:
        content = fn(project)
        if content.strip():
            files[name] = content
    other = _other_diagrams(project)
    if other:
        files["10-other-diagrams.md"] = "# Other Diagrams\n\n" + other

    req = _data(project, "requirements")
    index = [f"# {project.get('name')}\n"]
    if req:
        index.append(f"{req.get('summary', '')}\n")
        index.append("## Goals\n\n" + bullets(req.get("goals")))
    else:
        index.append(f"{project.get('idea', '')}\n")
    index.append("## Documents\n")
    titles = {n: t for n, t, _ in FILES}
    titles["10-other-diagrams.md"] = "Other diagrams"
    index.extend(f"- [{titles.get(n, n)}]({n})" for n in files)
    status = [f"| {k} | {v.get('status', '')} | {v.get('provider', '')} / {v.get('model', '')} | {v.get('updated', '')} |"
              for k, v in project.get("stages", {}).items()]
    if status:
        index.append("\n## Generation status\n\n| Stage | Status | Provider / model | Updated |\n|---|---|---|---|")
        index.extend(status)
    index.append(f"\n_Generated by Digital Architect on {storage.now()}._\n")
    return {"README.md": "\n".join(index), **files}


STAGE_PREVIEW = {
    "requirements": render_requirements,
    "requirements_review": render_requirements_review,
    "flows": lambda p: render_flows(p, include_manual=False),
    "architecture": lambda p: "\n\n".join(x for x in (
        render_architecture(p, include_manual=False), render_data_model(p), render_api(p), render_decisions(p)) if x),
    "architecture_review": lambda p: "\n\n".join(x for x in (render_architecture_review(p), render_plan(p)) if x),
}


def stage_previews(project: dict) -> dict[str, str]:
    return {k: fn(project) for k, fn in STAGE_PREVIEW.items()}


def render_diagram_review(review: dict) -> str:
    r = (review or {}).get("data") or {}
    if not r:
        return ""
    return "\n".join([
        f"{r.get('summary', '')}\n",
        "**Issues**\n\n" + table(r.get("issues", []), [("severity", "Severity"), ("description", "Issue"), ("suggestion", "Suggestion")]),
        "**Suggestions**\n\n" + bullets(r.get("suggestions")),
        "**Improved diagram**\n\n" + mermaid(r.get("improved_mermaid", "")),
    ])


def write_docs(project: dict) -> tuple[str, list[str]]:
    folder = storage.docs_dir(project["id"])
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.md"):
        old.unlink()
    files = render_docs(project)
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return str(folder), list(files)


def zip_docs(project: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in render_docs(project).items():
            z.writestr(f"docs/{name}", content)
    return buf.getvalue()
