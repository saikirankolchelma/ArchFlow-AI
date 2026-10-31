"""HTTP API + static web UI."""

import uuid

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import agents, docs_writer, pipeline, storage
from .config import STATIC_DIR
from .providers import PROVIDER_TYPES, LLMError, test_provider

app = FastAPI(title="Digital Architect")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(KeyError)
async def _not_found(_: Request, exc: KeyError):
    return JSONResponse({"detail": f"Not found: {exc}"}, status_code=404)


@app.exception_handler(LLMError)
async def _llm_error(_: Request, exc: LLMError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.exception_handler(pipeline.PipelineError)
async def _pipeline_error(_: Request, exc: pipeline.PipelineError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/meta")
def meta():
    return {"provider_types": PROVIDER_TYPES, "agents": agents.agents_info(), "stages": agents.STAGES,
            "engines": agents.ENGINES}


# ---------------------------------------------------------------- settings

@app.get("/api/settings")
def get_settings():
    return storage.public_settings()


@app.post("/api/providers")
def save_provider(data: dict = Body(...)):
    if data.get("type") not in PROVIDER_TYPES:
        raise HTTPException(400, "Unknown provider type.")
    if not isinstance(data.get("extra_params") or {}, dict):
        raise HTTPException(400, "Extra params must be a JSON object.")
    storage.upsert_provider(data)
    return storage.public_settings()


@app.delete("/api/providers/{provider_id}")
def remove_provider(provider_id: str):
    storage.delete_provider(provider_id)
    return storage.public_settings()


@app.post("/api/providers/{provider_id}/test")
async def check_provider(provider_id: str, data: dict = Body(default={})):
    provider = storage.get_provider(provider_id)
    if not provider:
        raise KeyError(provider_id)
    reply = await test_provider(provider, data.get("model") or "")
    return {"ok": True, "reply": reply[:300]}


@app.put("/api/agents")
def save_agents(data: dict = Body(...)):
    storage.update_agents(data)
    return storage.public_settings()


# ---------------------------------------------------------------- projects

def _view(project: dict) -> dict:
    return {"project": project, "previews": docs_writer.stage_previews(project),
            "diagram_reviews": {d["id"]: docs_writer.render_diagram_review(d.get("review"))
                                for d in project.get("diagrams", [])}}


@app.get("/api/projects")
def projects():
    return storage.list_projects()


@app.post("/api/projects")
def new_project(data: dict = Body(...)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Project name is required.")
    return _view(storage.create_project(name, data.get("idea") or ""))


@app.get("/api/projects/{project_id}")
def project(project_id: str):
    return _view(storage.get_project(project_id))


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, data: dict = Body(...)):
    p = storage.get_project(project_id)
    for field in ("name", "idea"):
        if field in data:
            p[field] = data[field]
    return _view(storage.save_project(p))


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: str):
    storage.delete_project(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/stages/{stage_key}/run")
async def run_stage(project_id: str, stage_key: str, data: dict = Body(default={})):
    p = await pipeline.run_stage(project_id, stage_key, data.get("feedback") or "", data.get("context_from") or [])
    return _view(p)


@app.put("/api/projects/{project_id}/stages/{stage_key}")
def edit_stage(project_id: str, stage_key: str, data: dict = Body(...)):
    if not isinstance(data.get("data"), dict):
        raise HTTPException(400, "Stage data must be a JSON object.")
    return _view(pipeline.set_stage_data(project_id, stage_key, data["data"]))


@app.post("/api/projects/{project_id}/stages/{stage_key}/approve")
def approve_stage(project_id: str, stage_key: str):
    return _view(pipeline.approve_stage(project_id, stage_key))


# ---------------------------------------------------------------- manual diagrams

@app.post("/api/projects/{project_id}/diagrams")
def new_diagram(project_id: str, data: dict = Body(...)):
    p = storage.get_project(project_id)
    diagram = {
        "id": "d_" + uuid.uuid4().hex[:8],
        "name": data.get("name") or "Untitled diagram",
        "kind": data.get("kind") or "flow",
        "description": data.get("description") or "",
        "graph": data.get("graph") or {"direction": "TD", "nodes": [], "edges": []},
        "mermaid": data.get("mermaid") or "",
        "updated": storage.now(),
    }
    p["diagrams"].append(diagram)
    return {**_view(storage.save_project(p)), "diagram_id": diagram["id"]}


@app.put("/api/projects/{project_id}/diagrams/{diagram_id}")
def save_diagram(project_id: str, diagram_id: str, data: dict = Body(...)):
    p = storage.get_project(project_id)
    d = next((x for x in p["diagrams"] if x["id"] == diagram_id), None)
    if not d:
        raise KeyError(diagram_id)
    for field in ("name", "kind", "description", "graph", "mermaid"):
        if field in data:
            d[field] = data[field]
    d["updated"] = storage.now()
    storage.save_project(p)
    return {"ok": True, "updated": d["updated"]}


@app.delete("/api/projects/{project_id}/diagrams/{diagram_id}")
def remove_diagram(project_id: str, diagram_id: str):
    p = storage.get_project(project_id)
    p["diagrams"] = [d for d in p["diagrams"] if d["id"] != diagram_id]
    return _view(storage.save_project(p))


@app.post("/api/projects/{project_id}/diagrams/{diagram_id}/assist")
async def assist_diagram(project_id: str, diagram_id: str, data: dict = Body(...)):
    return await pipeline.assist_diagram(project_id, diagram_id, data.get("instruction") or "",
                                         data.get("mermaid") or "", data.get("descriptions") or {})


@app.post("/api/projects/{project_id}/diagrams/{diagram_id}/review")
async def review_diagram(project_id: str, diagram_id: str):
    return _view(await pipeline.review_diagram(project_id, diagram_id))


# ---------------------------------------------------------------- docs

@app.get("/api/projects/{project_id}/docs")
def docs(project_id: str):
    return {"files": docs_writer.render_docs(storage.get_project(project_id))}


@app.post("/api/projects/{project_id}/export")
def export_docs(project_id: str):
    folder, files = docs_writer.write_docs(storage.get_project(project_id))
    return {"path": folder, "files": files}


@app.get("/api/projects/{project_id}/docs.zip")
def docs_zip(project_id: str):
    p = storage.get_project(project_id)
    return Response(docs_writer.zip_docs(p), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{p["id"]}-docs.zip"'})
