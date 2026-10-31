"""Pipeline stages: which agent runs each step, and what each step depends on."""

STAGES = [
    {"key": "requirements", "agent": "business", "title": "Business Requirements", "depends": []},
    {"key": "requirements_review", "agent": "architect", "title": "Requirements Review", "depends": ["requirements"]},
    {"key": "flows", "agent": "flow", "title": "Flows & Diagrams", "depends": ["requirements"]},
    {"key": "architecture", "agent": "architecture", "title": "Architecture", "depends": ["requirements", "flows"]},
    {"key": "architecture_review", "agent": "architect", "title": "Architecture Review & Build Plan", "depends": ["architecture"]},
]
STAGE_KEYS = [s["key"] for s in STAGES]


def stage_def(key: str) -> dict:
    for s in STAGES:
        if s["key"] == key:
            return s
    raise KeyError(key)


def downstream(key: str) -> list[str]:
    """Stages that (transitively) depend on `key`."""
    out: list[str] = []
    for s in STAGES:
        if key in s["depends"] or any(d in out for d in s["depends"]):
            out.append(s["key"])
    return out
