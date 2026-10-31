"""LangChain tools the deep agents (and their subagents) can call while they work."""

import re

from langchain_core.tools import tool

from .context import dump, stage_data
from .stages import STAGE_KEYS

_HEADERS = ("flowchart", "graph", "sequenceDiagram", "erDiagram", "classDiagram", "stateDiagram", "journey", "gantt", "mindmap")
_CANVAS_FORBIDDEN = re.compile(r"^\s*(subgraph|end\b|style\b|classDef\b|linkStyle\b|click\b)")
_PAIRS = {"[": "]", "(": ")", "{": "}"}
_NODE_ID = re.compile(r"(?:^|-->|---|-\.->|==>|&)\s*\|?[^|]*\|?\s*([A-Za-z0-9_]+)\s*[\[\(\{>]")


def check_mermaid(code: str, canvas: bool = False) -> list[str]:
    """Static checks for the mistakes that most often break Mermaid rendering. Returns a list of problems."""
    lines = [l for l in (code or "").replace("\r", "").split("\n")]
    body = [(i + 1, l) for i, l in enumerate(lines) if l.strip() and not l.strip().startswith("%%")]
    if not body:
        return ["The diagram is empty."]
    problems = []
    header = body[0][1].strip()
    if not header.startswith(_HEADERS):
        problems.append(f"line {body[0][0]}: must start with a diagram type such as `flowchart TD`, got `{header[:40]}`.")
    is_flow = header.startswith(("flowchart", "graph"))
    if canvas and not is_flow:
        problems.append("The canvas only supports `flowchart` diagrams.")
    if not is_flow:
        return problems

    for n, line in body[1:]:
        s = line.strip()
        if canvas and _CANVAS_FORBIDDEN.match(s):
            problems.append(f"line {n}: `{s.split()[0]}` is not supported on the canvas; remove it.")
            continue
        if s.startswith(("subgraph", "end", "classDef", "class ", "style ", "linkStyle", "click ", "direction ")):
            continue
        if s.count('"') % 2:
            problems.append(f"line {n}: unbalanced double quotes: `{s[:80]}`.")
            continue
        # Bracket balance outside quoted text.
        outside = re.sub(r'"[^"]*"', '""', s)
        outside = re.sub(r"\|[^|]*\|", "||", outside)  # edge labels
        outside = re.sub(r'>""\]', "", outside)  # asymmetric shape id>"text"]
        stack = []
        for ch in outside:
            if ch in _PAIRS:
                stack.append(_PAIRS[ch])
            elif ch in _PAIRS.values():
                if not stack or stack.pop() != ch:
                    stack = ["!"]
                    break
        if stack:
            problems.append(f"line {n}: brackets are not balanced: `{s[:80]}`.")
            continue
        # Unquoted labels that contain characters Mermaid chokes on.
        for m in re.finditer(r"[A-Za-z0-9_]+\s*(\[\[|\[\(|\(\(|\(\[|\[/|\[|\(|\{|>)([^\"\]\)\}]*?)(\]\]|\)\]|\)\)|\]\)|/\]|\]|\)|\})", outside):
            label = m.group(2).strip()
            if label and label != '""':
                problems.append(f"line {n}: label `{label[:40]}` should be quoted, e.g. id[\"{label[:30]}\"].")
                break
        edge_label = re.search(r"\|([^|\"]*[()\[\]{}][^|\"]*)\|", s)
        if edge_label:
            problems.append(f"line {n}: edge label `{edge_label.group(1)}` contains brackets; quote it: |\"...\"|.")
    return problems


def build_tools(project: dict) -> list:
    """Tools bound to one project snapshot. Subagents inherit them from their parent agent."""
    req = stage_data(project, "requirements") or {}
    req_ids = [r.get("id") for r in req.get("functional_requirements", []) if r.get("id")]
    nfr_ids = [r.get("id") for r in req.get("non_functional_requirements", []) if r.get("id")]

    @tool
    def validate_mermaid(code: str, canvas: bool = False) -> str:
        """Check a Mermaid diagram for syntax problems that break rendering (missing header, unquoted labels,
        unbalanced brackets or quotes). Set canvas=true for diagrams that must open in the visual canvas editor.
        Returns "OK" or a list of problems to fix."""
        problems = check_mermaid(code, canvas)
        if problems:
            return "Problems found:\n- " + "\n- ".join(problems[:20])
        nodes = len(set(_NODE_ID.findall(code)))
        edges = len(re.findall(r"-->|---|-\.->|==>", code))
        return f"OK ({nodes} labelled nodes, {edges} edges)."

    @tool
    def check_requirement_coverage(covered_ids: list[str]) -> str:
        """Compare the requirement IDs your output covers (e.g. ["REQ-001", "NFR-002"]) with the full
        requirements specification. Returns which functional and non-functional requirements are still uncovered."""
        if not req_ids and not nfr_ids:
            return "No requirements specification exists yet, so coverage cannot be checked."
        covered = {c.strip().upper() for c in covered_ids}
        missing_req = [i for i in req_ids if i.upper() not in covered]
        missing_nfr = [i for i in nfr_ids if i.upper() not in covered]
        titles = {r.get("id"): r.get("title") for r in req.get("functional_requirements", [])}
        lines = [f"Covered {len(req_ids) - len(missing_req)}/{len(req_ids)} functional and "
                 f"{len(nfr_ids) - len(missing_nfr)}/{len(nfr_ids)} non-functional requirements."]
        if missing_req:
            lines.append("Uncovered functional: " + "; ".join(f"{i} {titles.get(i) or ''}".strip() for i in missing_req))
        if missing_nfr:
            lines.append("Uncovered non-functional: " + ", ".join(missing_nfr))
        return "\n".join(lines)

    @tool
    def list_requirements() -> str:
        """List all requirement IDs with their titles and priority (short form of the requirements specification)."""
        if not req:
            return "No requirements specification exists yet."
        out = [f"{r.get('id')} [{r.get('priority')}] {r.get('title')}" for r in req.get("functional_requirements", [])]
        out += [f"{r.get('id')} [{r.get('category')}] {r.get('description')}" for r in req.get("non_functional_requirements", [])]
        return "\n".join(out)

    @tool
    def get_stage_output(stage: str) -> str:
        """Return the full JSON output of a pipeline stage. stage is one of: requirements, requirements_review,
        flows, architecture, architecture_review."""
        if stage not in STAGE_KEYS:
            return f"Unknown stage '{stage}'. Use one of: {', '.join(STAGE_KEYS)}."
        data = stage_data(project, stage)
        return dump(data) if data else f"The {stage} stage has no output yet."

    return [validate_mermaid, check_requirement_coverage, list_requirements, get_stage_output]
