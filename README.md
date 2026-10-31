# ArchFlow AI

A local web platform for designing software before you code it. You describe an idea, and a team of AI agents turns it into
requirements, flow diagrams, an architecture, and a build plan. You can also draw flows and architectures by hand.
The result is exported as clean, structured `.md` files that you (or an AI coding assistant) can start coding from.

## Agents

| # | Stage | Agent | Output |
|---|---|---|---|
| 1 | Business Requirements | **Business Needs Agent** | Goals, personas, `REQ-xxx` functional and `NFR-xxx` quality requirements with acceptance criteria |
| 2 | Requirements Review | **System Software Architect** | Gaps, risks, missing requirements, stakeholder questions, which flows to draw |
| 3 | Flows & Diagrams | **Flow Agent** | Mermaid flow diagrams with step-by-step descriptions mapped to requirement IDs |
| 4 | Architecture | **Architecture Agent** | Components, tech stack, data model, APIs, deployment, ADRs, risks, improvements |
| 5 | Architecture Review & Build Plan | **System Software Architect** | Review, coverage gaps, milestone plan, coding guide |

You can run each stage, read the result, write feedback, and re-run it. When an earlier stage changes, later stages are marked
**stale**. You can also edit any stage's JSON by hand.

### Deep agents (LangChain + LangGraph)

By default every agent runs as a **deep agent** built with [`deepagents`](https://github.com/langchain-ai/deepagents) on LangGraph. A deep agent:

- **plans** its work with a to-do list (`write_todos`)
- reads the project context from a virtual file system (`/context/requirements.json`, `/context/flows.json`, and so on), which its subagents share
- **delegates** focused analysis to specialist subagents:

  | Agent | Subagents |
  |---|---|
  | Business Needs | `domain-analyst`, `nfr-analyst` |
  | System Software Architect | `security-reviewer`, `scalability-reviewer`, `delivery-planner` |
  | Flow | `flow-designer`, `edge-case-analyst` |
  | Architecture | `data-modeler`, `api-designer`, `infra-designer` |
  | Diagram (canvas) | none, so it stays fast |

- **checks its own work** with project tools: `validate_mermaid`, `check_requirement_coverage`, `list_requirements` and `get_stage_output`

All prompts are Markdown files in `app/agents/prompts/`. Edit one and the next agent run uses the new text, with no restart needed.
To add a subagent, drop a new `.md` file into `prompts/<agent>/subagents/` that starts with a `name:` and `description:` header.

A deep agent makes several model calls per run, so it is slower and uses more quota than a single call.
To change this per agent, set the **Mode** column in Settings to **⚡ Fast**, which uses one model call.
The pipeline shows a `🧠 deep · N steps` badge on each stage. Hover over it to see which tools and subagents were used.

## Bring your own credentials, any provider

Under **⚙ Providers & Agents** you can add as many providers as you like and assign a provider and model to each agent:

- **Anthropic (Claude)**, through the official SDK (e.g. `claude-opus-5-5`, `claude-sonnet-5-5`). Refusal fallbacks are enabled on models that support them.
- **OpenAI**
- **Azure OpenAI** (deployment name used as the model)
- **Google Gemini**
- **OpenAI-compatible**: OpenRouter, Groq, DeepSeek, Mistral, Together, xAI, LM Studio, and others
- **Ollama**, for local models without a key

For example, you can run the Architect on Claude Opus and the Flow Agent on a local Ollama model.
Use **Extra request params** (JSON) to pass provider-specific options such as `{"max_tokens": 16000}`.

Keys are stored only on your machine, in `data/settings.json` (git-ignored), and are never sent back to the browser.
The server listens on `127.0.0.1` only.

## Manual mode: draw it yourself

The **Canvas** tab is a diagram editor with these shapes: start/end, process, decision, actor, service, database, queue, external system and note.

- Drag shapes to move them. Drag the ● handle onto another shape to connect them. Double-click to edit labels.
- Each drawing is saved as Mermaid code automatically. You can also paste Mermaid to import it.
- Click **✎ Edit in canvas** on any AI-generated flowchart to copy it to the canvas and refine it by hand.
- **Ask Architect to review** returns issues, suggestions, and an improved diagram you can apply.
- Hand-drawn diagrams are given to the agents as your intent, and they are included in the exported docs.

## Output

On the **Docs** tab, click **Save .md files to disk** (writes to `data/projects/<project>/docs/`) or **Download ZIP**:

```
docs/
├── README.md                    index + generation status
├── 01-requirements.md
├── 02-requirements-review.md
├── 03-flows.md                  AI flows + your hand-drawn flows (Mermaid)
├── 04-architecture.md
├── 05-data-model.md             entities + ER diagram
├── 06-api.md
├── 07-decisions.md              ADRs
├── 08-architecture-review.md
├── 09-implementation-plan.md    milestones with task checklists
└── AGENTS.md                    coding brief for developers / AI coding assistants
```

Copy the `docs/` folder into your new repository and point your coding assistant at `AGENTS.md`.

## Run

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app                   # http://127.0.0.1:8000
```

On Windows you can double-click `run.bat` instead.
Environment overrides: `DA_PORT`, `DA_HOST`, `DA_DATA_DIR`.

## Project layout

```
app/
  main.py          FastAPI routes
  providers.py     provider adapters (Anthropic SDK, OpenAI, Azure, Gemini, OpenAI-compatible, Ollama)
  agents/          the AI agents (LangChain + LangGraph deep agents)
    prompts/       ALL prompt text as Markdown: <agent>/<task>.md, <agent>/subagents/<name>.md, shared/*.md
    business_agent.py, architect_agent.py, flow_agent.py,
    architecture_agent.py, diagram_agent.py   one file per agent: name, description, tasks
    loader.py      reads the prompt .md files (front matter, {{include shared/...}})
    stages.py      pipeline order and dependencies
    context.py     JSON output contracts and project context builders
    tools.py       tools the agents call (validate_mermaid, check_requirement_coverage, ...)
    llm.py         LangChain chat model from your provider credentials
    runner.py      runs a task as a deep agent or as a single fast call
  pipeline.py      runs stages, stores results, marks downstream stages stale
  docs_writer.py   JSON + diagrams -> Markdown docs
  storage.py       settings + projects as JSON files under data/
static/
  index.html, css/, js/  (main.js UI, canvas.js diagram editor, markdown.js Markdown + Mermaid rendering)
```
