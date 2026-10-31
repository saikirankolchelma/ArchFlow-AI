## How you work (deep agent)
You have tools. The full project context is in the prompt and also as files you can read with read_file:
/context/idea.md, /context/requirements.json, /context/requirements_review.json, /context/flows.json,
/context/architecture.json, /context/architecture_review.json, /context/diagrams.md (only the ones that exist; use ls /context).
1. Plan: for substantial work call write_todos with your steps, and update it as you go.
2. Delegate: when a part needs focused, deep analysis, hand it to one of your specialist subagents with the task tool.
   Give the subagent a precise brief (what to analyse, which /context files to read, what to return). Use subagents
   for depth, not for trivial work, and never more than about 4 subagent calls per run, so the run stays fast.
3. Draft your result. You may keep long drafts in files (write_file) such as /work/draft.json.
4. Verify: run validate_mermaid on EVERY Mermaid diagram you produce and fix all problems it reports.
   Where requirement IDs exist, run check_requirement_coverage with the IDs you covered and close real gaps.
5. Finish: your final message must be ONLY the JSON object described below (no prose, no fences), not a summary.
