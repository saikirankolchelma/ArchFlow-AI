import { api } from './api.js';
import { $, $$, esc, toast, promptForm } from './ui.js';
import { renderMarkdown } from './markdown.js';
import { DiagramEditor, mermaidToGraph } from './canvas.js';

const state = {
  meta: null,
  settings: null,
  project: null,
  previews: {},
  diagramReviews: {},
  running: null,
  feedback: {},
  editing: {},
  collapsed: {},
  diagramId: null,
  docs: null,
  docFile: null,
  tab: 'pipeline',
};

const DONE = new Set(['done', 'approved', 'edited']);
const PRESETS = [
  ['', 'Custom URL'],
  ['https://openrouter.ai/api/v1', 'OpenRouter'],
  ['https://api.groq.com/openai/v1', 'Groq'],
  ['https://api.deepseek.com/v1', 'DeepSeek'],
  ['https://api.mistral.ai/v1', 'Mistral'],
  ['https://api.together.xyz/v1', 'Together AI'],
  ['https://api.x.ai/v1', 'xAI'],
  ['http://localhost:1234/v1', 'LM Studio (local)'],
];

const lsGet = k => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

// ============================================================ projects

async function loadProjects(selectId) {
  const list = await api('/projects');
  const sel = $('#project-select');
  sel.innerHTML = list.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  const hasProjects = list.length > 0;
  $('#empty-state').classList.toggle('hidden', hasProjects);
  $('#tabs').classList.toggle('hidden', !hasProjects);
  $$('.tab').forEach(t => t.classList.toggle('hidden', !hasProjects || t.id !== `tab-${state.tab}`));
  $('#btn-delete-project').classList.toggle('hidden', !hasProjects);
  if (!hasProjects) { state.project = null; return; }
  const wanted = selectId || lsGet('da-project');
  const id = list.some(p => p.id === wanted) ? wanted : list[0].id;
  sel.value = id;
  await openProject(id);
}

async function openProject(id) {
  await flushDiagramSave();
  state.diagramId = null;
  state.docs = null;
  applyView(await api(`/projects/${id}`));
  lsSet('da-project', id);
  $('#project-name').value = state.project.name;
  $('#project-idea').value = state.project.idea || '';
  $('#btn-zip').href = `/api/projects/${id}/docs.zip`;
  selectDiagram(null);
  if (state.tab === 'docs') loadDocs();
}

function applyView(view) {
  state.project = view.project;
  state.previews = view.previews || {};
  state.diagramReviews = view.diagram_reviews || {};
  renderPipeline();
  renderDiagramList();
}

async function newProject() {
  const v = await promptForm('New project', [
    { name: 'name', label: 'Project name', value: '', required: true },
    { name: 'idea', label: 'Idea / business requirements (you can edit later)', type: 'textarea', rows: 6, value: '' },
  ]);
  if (!v || !v.name.trim()) return;
  const view = await api('/projects', { method: 'POST', body: v });
  await loadProjects(view.project.id);
}

// ============================================================ pipeline

function agentLabel(agentKey) {
  const cfg = state.settings.agents[agentKey] || {};
  const p = state.settings.providers.find(x => x.id === cfg.provider_id);
  if (!p) return '<span style="color:var(--danger)">no provider assigned</span>';
  return `${esc(p.label)} · ${esc(cfg.model || p.default_model || '?')}`;
}

/** "🧠 deep · 7 steps" chip; the tooltip lists the tools and subagents the last run used. */
function deepBadge(st) {
  if (st.engine !== 'deep') return '';
  const used = Object.entries(st.tools_used || {}).map(([k, n]) => `${k} ×${n}`).join('\n');
  return ` <span class="badge deep" title="${esc(used || 'No tool calls')}">🧠 deep · ${st.steps || 0} steps</span>`;
}

function renderPipeline() {
  const root = $('#stages');
  if (!state.project) { root.innerHTML = ''; return; }
  root.innerHTML = state.meta.stages.map((s, i) => {
    const st = state.project.stages[s.key] || {};
    const status = state.running === s.key ? 'running' : (st.status || 'not run');
    const has = !!st.data;
    const agent = state.meta.agents[s.agent];
    const busy = !!state.running;
    return `
    <div class="card stage ${esc(st.status || '')} ${state.collapsed[s.key] ? 'collapsed' : ''}" data-stage="${s.key}">
      <div class="stage-head">
        <div class="stage-num">${i + 1}</div>
        <h3>${esc(s.title)}</h3>
        <span class="badge ${esc(status)}">${state.running === s.key ? '<span class="spinner"></span> running' : esc(status)}</span>
        <span class="small"><span class="stage-agent">${esc(agent.name)}</span> <span class="muted">· ${agentLabel(s.agent)}${st.duration_s ? ` · ${st.duration_s}s` : ''}</span>${deepBadge(st)}</span>
        <span class="spacer"></span>
        <button class="btn small" data-act="run" ${busy ? 'disabled' : ''}>${has ? '↻ Re-run' : '▶ Run'}</button>
        <button class="btn small" data-act="approve" ${!has || busy || st.status === 'approved' ? 'disabled' : ''}>✓ Approve</button>
        <button class="btn small" data-act="edit" ${!has || busy ? 'disabled' : ''}>{ } Edit</button>
        <button class="btn small" data-act="copy" ${!has ? 'disabled' : ''} title="Copy this result as Markdown">📋 Copy</button>
        <button class="btn small ghost" data-act="toggle">${state.collapsed[s.key] ? '▸' : '▾'}</button>
      </div>
      ${has ? `<div class="apply-row">
        <span class="small muted">Use this result elsewhere:</span>
        <select class="apply-select" ${busy ? 'disabled' : ''}>${applyOptions(s.key)}</select>
      </div>` : ''}
      <div class="stage-body">
        <textarea class="feedback" rows="2" placeholder="${has ? 'Feedback for the agent: what to change on re-run (optional)' : 'Extra instructions for the agent (optional)'}">${esc(state.feedback[s.key] || '')}</textarea>
        ${st.status === 'stale' ? '<p class="small" style="color:var(--warn)">An earlier stage changed after this was generated. Re-run to update.</p>' : ''}
        ${state.editing[s.key]
          ? `<textarea class="json mono" spellcheck="false">${esc(JSON.stringify(st.data, null, 2))}</textarea>
             <div class="row"><button class="btn primary small" data-act="save-json">Save JSON</button><button class="btn small ghost" data-act="cancel-json">Cancel</button></div>`
          : `<div class="md preview">${has ? '' : `<p class="muted">${esc(agent.description)}</p>`}</div>`}
      </div>
    </div>`;
  }).join('');

  for (const card of $$('.stage', root)) {
    const key = card.dataset.stage;
    const preview = $('.preview', card);
    if (preview && state.previews[key]) {
      const kind = key === 'flows' ? 'flow' : 'architecture';
      renderMarkdown(preview, state.previews[key], { onOpenInCanvas: src => openInCanvas(src, kind) });
    }
    $('.feedback', card).addEventListener('input', e => { state.feedback[key] = e.target.value; });
  }
}

// ------------------------------------------------------------ cross-agent: send one stage's suggestions elsewhere

const TARGET_STAGES = ['requirements', 'flows', 'architecture'];

function applyOptions(sourceKey) {
  const stageOpts = state.meta.stages
    .filter(s => TARGET_STAGES.includes(s.key) && s.key !== sourceKey)
    .map(s => `<option value="stage:${s.key}">${esc(s.title)} (${esc(state.meta.agents[s.agent].name)}): re-run applying it</option>`);
  const diagramOpts = (state.project.diagrams || [])
    .map(d => `<option value="diagram:${esc(d.id)}">${esc(d.name)} (${esc(d.kind)})</option>`);
  return `<option value="">➜ Apply suggestions to…</option>
    <optgroup label="Agent stages">${stageOpts.join('')}</optgroup>
    <optgroup label="Canvas diagrams (Diagram Agent)">${diagramOpts.join('')}<option value="diagram:new">+ New canvas diagram</option></optgroup>`;
}

/** Plain-text list of the actionable suggestions in a stage's output. */
function suggestionsText(key) {
  const d = state.project.stages[key]?.data || {};
  const out = [];
  const add = (prefix, items, fmt) => (items || []).forEach(x => out.push(`- ${prefix}${fmt(x)}`));
  add('', d.issues, i => `[${i.severity || ''}] ${i.description || ''}${i.suggestion ? ` → ${i.suggestion}` : ''}`);
  add('Missing: ', d.missing_requirements, m => `${m.title}${m.why ? ` (${m.why})` : ''}`);
  add('Flow to add: ', d.flow_suggestions, f => `${f.name}${f.why ? ` (${f.why})` : ''}`);
  add('Coverage gap ', d.coverage_gaps, g => `${g.requirement}: ${g.gap}`);
  add('Improvement: ', d.improvements, i => `${i.title}: ${i.description || ''}`);
  add('Risk: ', d.risks, r => `${r.risk} → ${r.mitigation || ''}`);
  add('', d.suggestions, s => s);
  if (key === 'architecture' && d.components) {
    out.push('', 'Architecture components to reflect:');
    add('', d.components, c => `${c.name} (${c.type}, ${c.technology || ''}): ${c.responsibility || ''}`);
  }
  const text = out.join('\n');
  return text.length > 6000 ? text.slice(0, 6000) + '\n…' : text;
}

async function applyTo(sourceKey, target) {
  const source = state.meta.stages.find(s => s.key === sourceKey);
  const [kind, id] = target.split(':');
  const list = suggestionsText(sourceKey);
  if (kind === 'stage') {
    const t = state.meta.stages.find(s => s.key === id);
    if (!confirm(`Send the "${source.title}" result to the ${state.meta.agents[t.agent].name} and re-run "${t.title}"?\n\nStages after it will be marked stale.`)) return;
    const extra = (state.feedback[id] || '').trim();
    state.feedback[id] = `Apply the relevant suggestions from the "${source.title}" stage.${list ? `\n${list}` : ''}${extra ? `\n\nAlso: ${extra}` : ''}`;
    state.collapsed[id] = false;
    await runStage(id, { context_from: [sourceKey] });
    document.querySelector(`[data-stage="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    const instruction = `Update this diagram by applying these suggestions from the "${source.title}" stage. `
      + `Keep what is still correct, and update node descriptions where they change.\n${list || '(use the stage output in the project context)'}`;
    await flushDiagramSave();
    if (id === 'new') {
      const name = sourceKey === 'architecture' || sourceKey === 'architecture_review' ? 'Architecture (from AI)' : 'Flow (from AI)';
      await createDiagram({ name, kind: name.startsWith('Architecture') ? 'architecture' : 'flow' });
    } else {
      switchTab('canvas');
      selectDiagram(id);
    }
    await sendAssist(instruction);
  }
}

async function runStage(key, extra = {}) {
  state.running = key;
  renderPipeline();
  try {
    applyView(await api(`/projects/${state.project.id}/stages/${key}/run`, {
      method: 'POST', body: { feedback: state.feedback[key] || '', ...extra },
    }));
    state.feedback[key] = '';
    state.docs = null;
    toast(`${state.meta.stages.find(s => s.key === key).title}: done`);
    return true;
  } catch (err) {
    toast(err.message, { error: true });
    return false;
  } finally {
    state.running = null;
    renderPipeline();
  }
}

async function runRemaining() {
  await saveIdea(true);
  for (const s of state.meta.stages) {
    const st = state.project.stages[s.key];
    if (st && DONE.has(st.status)) continue;
    if (!(await runStage(s.key))) return;
  }
  toast('Pipeline complete. Open the Docs tab to export.');
}

async function onStageClick(e) {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const key = btn.closest('[data-stage]').dataset.stage;
  const act = btn.dataset.act;
  const pid = state.project.id;
  try {
    if (act === 'run') { await saveIdea(true); await runStage(key); }
    else if (act === 'approve') applyView(await api(`/projects/${pid}/stages/${key}/approve`, { method: 'POST' }));
    else if (act === 'toggle') { state.collapsed[key] = !state.collapsed[key]; renderPipeline(); }
    else if (act === 'edit') { state.editing[key] = true; renderPipeline(); }
    else if (act === 'copy') copyText(state.previews[key] || '', 'Copied as Markdown: paste it anywhere');
    else if (act === 'cancel-json') { state.editing[key] = false; renderPipeline(); }
    else if (act === 'save-json') {
      const text = $('textarea.json', btn.closest('[data-stage]')).value;
      let data;
      try { data = JSON.parse(text); } catch (err) { return toast(`Invalid JSON: ${err.message}`, { error: true }); }
      state.editing[key] = false;
      applyView(await api(`/projects/${pid}/stages/${key}`, { method: 'PUT', body: { data } }));
      state.docs = null;
      toast('Saved your edits');
    }
  } catch (err) {
    toast(err.message, { error: true });
  }
}

async function saveIdea(silent = false) {
  if (!state.project) return;
  const name = $('#project-name').value.trim() || state.project.name;
  const idea = $('#project-idea').value;
  if (name === state.project.name && idea === (state.project.idea || '')) return;
  applyView(await api(`/projects/${state.project.id}`, { method: 'PATCH', body: { name, idea } }));
  const opt = $(`#project-select option[value="${state.project.id}"]`);
  if (opt) opt.textContent = name;
  if (!silent) toast('Saved');
}

// ============================================================ canvas

let editor;
let saveTimer = null;

function currentDiagram() {
  return state.project?.diagrams.find(d => d.id === state.diagramId) || null;
}

function renderDiagramList() {
  const list = $('#diagram-list');
  const ds = state.project?.diagrams || [];
  list.innerHTML = ds.length
    ? ds.map(d => `<li data-id="${esc(d.id)}" class="${d.id === state.diagramId ? 'active' : ''}">
        <span class="name">${esc(d.name)}<br><span class="kind">${esc(d.kind)}</span></span>
        <span class="item-actions">
          <button data-li="rename" title="Rename">✎</button>
          <button data-li="duplicate" title="Duplicate">⧉</button>
          <button data-li="delete" title="Delete">🗑</button>
        </span></li>`).join('')
    : '<li class="muted">No diagrams yet. Click + New</li>';
}

async function deleteDiagram(id) {
  const d = state.project.diagrams.find(x => x.id === id);
  if (!d || !confirm(`Delete diagram "${d.name}"? This cannot be undone.`)) return;
  if (id === state.diagramId) { clearTimeout(saveTimer); saveTimer = null; }
  applyView(await api(`/projects/${state.project.id}/diagrams/${id}`, { method: 'DELETE' }));
  if (id === state.diagramId) selectDiagram(null);
  toast('Diagram deleted');
}

async function renameDiagram(id) {
  const d = state.project.diagrams.find(x => x.id === id);
  const v = await promptForm('Rename diagram', [{ name: 'name', label: 'Name', value: d.name, required: true }]);
  if (!v || !v.name.trim()) return;
  if (id === state.diagramId) { $('#diagram-name').value = v.name.trim(); await saveDiagram(); return; }
  await api(`/projects/${state.project.id}/diagrams/${id}`, { method: 'PUT', body: { name: v.name.trim() } });
  d.name = v.name.trim();
  renderDiagramList();
}

async function duplicateDiagram(id) {
  await flushDiagramSave();
  const d = state.project.diagrams.find(x => x.id === id);
  await createDiagram({ name: `${d.name} (copy)`, kind: d.kind, graph: d.graph, mermaid: d.mermaid, description: d.description });
  toast('Diagram duplicated');
}

// ------------------------------------------------------------ selected shape panel

function fillNodePanel(n) {
  $('#node-panel').classList.toggle('hidden', !n);
  if (!n) return;
  const set = (sel, v) => { const f = $(sel); if (document.activeElement !== f) f.value = v; };
  set('#node-label', n.label || '');
  set('#node-type', n.type);
  set('#node-desc', n.description || '');
}

function bindNodePanel() {
  const sel = () => editor.selectedNode();
  $('#node-label').addEventListener('input', e => { const n = sel(); if (n) editor.updateNode(n.id, { label: e.target.value }, false); });
  $('#node-desc').addEventListener('input', e => { const n = sel(); if (n) editor.updateNode(n.id, { description: e.target.value }, false); });
  for (const f of ['#node-label', '#node-desc']) $(f).addEventListener('change', () => editor.commit());
  $('#node-type').addEventListener('change', e => { const n = sel(); if (n) editor.updateNode(n.id, { type: e.target.value }); });
  $('#node-delete').onclick = () => editor.deleteSelected();
  $('#node-close').onclick = () => { editor.selected = null; editor.render(); };
  $('#node-ai-desc').onclick = () => {
    const n = sel();
    if (!n) return;
    sendAssist(`Write a detailed description for node ${n.id} "${n.label}" (what happens, who or what is responsible, `
      + `data in/out, rules, error handling). Only update that node's description; keep the diagram unchanged.`);
  };
}

// ------------------------------------------------------------ export

function download(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

const fileSafe = s => (s || 'diagram').replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-') || 'diagram';

function exportDiagram(format) {
  const d = currentDiagram();
  const svg = d && editor.exportSVG();
  if (!svg) return toast('Nothing to export: the diagram is empty.');
  if (format === 'svg') return download(`${fileSafe(d.name)}.svg`, new Blob([svg], { type: 'image/svg+xml' }));
  const img = new Image();
  img.onload = () => {
    const scale = 2;
    const c = document.createElement('canvas');
    c.width = img.width * scale; c.height = img.height * scale;
    const ctx = c.getContext('2d');
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    c.toBlob(b => download(`${fileSafe(d.name)}.png`, b), 'image/png');
  };
  img.onerror = () => toast('PNG export failed; try SVG.', { error: true });
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function copyText(text, msg = 'Copied') {
  const done = () => toast(msg);
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text).then(done, () => fallback());
  fallback();
  function fallback() {
    const t = document.createElement('textarea');
    t.value = text; document.body.appendChild(t); t.select();
    try { document.execCommand('copy'); done(); } catch { toast('Copy failed', { error: true }); }
    t.remove();
  }
}

function selectDiagram(id) {
  state.diagramId = id;
  const d = currentDiagram();
  renderDiagramList();
  $('#canvas-empty').classList.toggle('hidden', !!d);
  editor.setEnabled(!!d);
  for (const sel of ['#diagram-name', '#diagram-kind', '#diagram-desc', '#diagram-mermaid', '#btn-review-diagram',
    '#btn-delete-diagram', '#assist-input', '#btn-assist']) $(sel).disabled = !d;
  renderAssistant();
  if (!d) {
    editor.load({ nodes: [], edges: [] });
    $('#diagram-name').value = ''; $('#diagram-desc').value = ''; $('#diagram-mermaid').value = '';
    $('#diagram-review').innerHTML = '';
    return;
  }
  editor.load(d.graph);
  $('#canvas-direction').value = d.graph?.direction || 'TD';
  $('#diagram-name').value = d.name;
  $('#diagram-kind').value = d.kind;
  $('#diagram-desc').value = d.description || '';
  $('#diagram-mermaid').value = d.mermaid || editor.toMermaid();
  renderDiagramReview();
}

function renderDiagramReview() {
  const md = state.diagramReviews[state.diagramId];
  const box = $('#diagram-review');
  if (!md) { box.innerHTML = ''; return; }
  renderMarkdown(box, '### Architect review\n\n' + md, {
    onOpenInCanvas: src => {
      if (!confirm('Replace the current drawing with the improved diagram?')) return;
      try { editor.importMermaid(src); } catch (err) { toast(err.message, { error: true }); }
    },
  });
}

function renderAssistant() {
  $('#assist-model').innerHTML = state.settings ? agentLabel('diagram') : '';
  const d = currentDiagram();
  const log = $('#assist-log');
  log.innerHTML = (d?.chat || []).map(m => `<div class="msg ${m.role === 'user' ? 'user' : 'agent'}">${esc(m.text)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}

let assisting = false;
async function sendAssist(text) {
  const instruction = (text ?? $('#assist-input').value).trim();
  const d = currentDiagram();
  if (!d) return toast('Create or select a diagram first.');
  if (!instruction || assisting) return;
  assisting = true;
  await flushDiagramSave();
  const btn = $('#btn-assist');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Drawing…';
  const log = $('#assist-log');
  log.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(instruction)}</div><div class="msg agent muted">Working on it…</div>`);
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api(`/projects/${state.project.id}/diagrams/${d.id}/assist`, {
      method: 'POST', body: { instruction, mermaid: editor.toMermaid(), descriptions: editor.getDescriptions() },
    });
    d.chat = r.chat;
    $('#assist-input').value = '';
    if (r.result.description && !$('#diagram-desc').value.trim()) $('#diagram-desc').value = r.result.description;
    if (r.result.diagram_name && /^(untitled|ai diagram|new diagram)/i.test($('#diagram-name').value.trim())) {
      $('#diagram-name').value = r.result.diagram_name;
    }
    try {
      editor.applyMermaid(r.result.mermaid, r.result.node_descriptions || {});  // triggers autosave
    } catch (err) {
      toast(`The agent's diagram could not be drawn: ${err.message}`, { error: true });
    }
  } catch (err) {
    toast(err.message, { error: true });
  } finally {
    assisting = false;
    btn.disabled = !currentDiagram();
    btn.textContent = 'Send (Ctrl+Enter)';
    renderAssistant();
  }
}

function scheduleSave() {
  if (!currentDiagram()) return;
  $('#save-status').textContent = 'Unsaved changes…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDiagram, 700);
}

async function flushDiagramSave() {
  if (saveTimer) { clearTimeout(saveTimer); await saveDiagram(); }
}

async function saveDiagram() {
  saveTimer = null;
  const d = currentDiagram();
  if (!d) return;
  const body = {
    name: $('#diagram-name').value.trim() || 'Untitled diagram',
    kind: $('#diagram-kind').value,
    description: $('#diagram-desc').value,
    graph: editor.getGraph(),
    mermaid: editor.toMermaid(),
  };
  try {
    await api(`/projects/${state.project.id}/diagrams/${d.id}`, { method: 'PUT', body });
    Object.assign(d, body);
    state.docs = null;
    renderDiagramList();
    $('#save-status').textContent = 'Saved';
  } catch (err) {
    $('#save-status').textContent = 'Save failed';
    toast(err.message, { error: true });
  }
}

async function createDiagram(init = {}) {
  const view = await api(`/projects/${state.project.id}/diagrams`, { method: 'POST', body: init });
  applyView(view);
  switchTab('canvas');
  selectDiagram(view.diagram_id);
}

async function newDiagram() {
  if (!state.project) return;
  const v = await promptForm('New diagram', [
    { name: 'name', label: 'Name', value: '', required: true },
    { name: 'kind', label: 'Type', type: 'select', value: 'flow', options: [['flow', 'Flow'], ['architecture', 'Architecture'], ['other', 'Other']] },
    { name: 'ai', label: 'What should the Diagram Agent draw? (optional: leave empty to draw it yourself)', type: 'textarea', rows: 3, value: '' },
  ]);
  if (!v) return;
  await flushDiagramSave();
  await createDiagram({ name: v.name || 'Untitled diagram', kind: v.kind });
  if (v.ai.trim()) await sendAssist(v.ai);
}

async function openInCanvas(src, kind) {
  let graph;
  try { graph = mermaidToGraph(src); } catch (err) { return toast(err.message, { error: true }); }
  const v = await promptForm('Copy diagram to canvas for manual editing', [
    { name: 'name', label: 'Name', value: kind === 'flow' ? 'Edited flow' : 'Edited architecture', required: true },
  ]);
  if (!v) return;
  await flushDiagramSave();
  await createDiagram({ name: v.name, kind, graph, mermaid: src });
}

async function reviewDiagram() {
  const d = currentDiagram();
  if (!d) return;
  await flushDiagramSave();
  const btn = $('#btn-review-diagram');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Reviewing…';
  try {
    applyView(await api(`/projects/${state.project.id}/diagrams/${d.id}/review`, { method: 'POST' }));
    renderDiagramReview();
  } catch (err) {
    toast(err.message, { error: true });
  } finally {
    btn.disabled = false;
    btn.textContent = 'Ask Architect to review';
  }
}

function bindCanvas() {
  editor = new DiagramEditor($('#canvas'), {
    onChange: () => { $('#diagram-mermaid').value = editor.toMermaid(); scheduleSave(); },
    onSelect: fillNodePanel,
  });
  bindNodePanel();
  $('#diagram-list').addEventListener('click', async e => {
    const li = e.target.closest('li[data-id]');
    if (!li) return;
    const action = e.target.closest('[data-li]')?.dataset.li;
    try {
      if (action === 'delete') return await deleteDiagram(li.dataset.id);
      if (action === 'rename') return await renameDiagram(li.dataset.id);
      if (action === 'duplicate') return await duplicateDiagram(li.dataset.id);
      await flushDiagramSave();
      selectDiagram(li.dataset.id);
    } catch (err) { toast(err.message, { error: true }); }
  });
  $('#btn-duplicate-sel').onclick = () => editor.duplicateSelected();
  $('#btn-export-svg').onclick = () => exportDiagram('svg');
  $('#btn-export-png').onclick = () => exportDiagram('png');
  $('#btn-new-diagram').onclick = () => newDiagram().catch(err => toast(err.message, { error: true }));
  $$('#canvas-toolbar [data-shape]').forEach(b => b.onclick = () => {
    if (!currentDiagram()) return toast('Create or select a diagram first.');
    editor.addNode(b.dataset.shape);
  });
  $('#btn-delete-sel').onclick = () => editor.deleteSelected();
  $('#btn-undo').onclick = () => editor.undo();
  $('#btn-assist').onclick = () => sendAssist();
  $('#assist-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendAssist(); }
  });
  $$('.chip[data-suggest]').forEach(c => c.onclick = () => {
    if (!currentDiagram()) return toast('Create or select a diagram first.');
    sendAssist(c.dataset.suggest);
  });
  $('#btn-layout').onclick = () => editor.layout();
  $('#btn-zoom-in').onclick = () => editor.zoom(1.2);
  $('#btn-zoom-out').onclick = () => editor.zoom(1 / 1.2);
  $('#btn-fit').onclick = () => editor.fit();
  $('#canvas-direction').onchange = e => editor.setDirection(e.target.value);
  for (const sel of ['#diagram-name', '#diagram-desc']) $(sel).addEventListener('input', scheduleSave);
  $('#diagram-kind').addEventListener('change', scheduleSave);
  $('#btn-import-mermaid').onclick = () => {
    try { editor.importMermaid($('#diagram-mermaid').value); toast('Imported'); }
    catch (err) { toast(err.message, { error: true }); }
  };
  $('#btn-copy-mermaid').onclick = () => copyText($('#diagram-mermaid').value);
  $('#btn-review-diagram').onclick = reviewDiagram;
  $('#btn-delete-diagram').onclick = () => {
    const d = currentDiagram();
    if (d) deleteDiagram(d.id).catch(err => toast(err.message, { error: true }));
  };
}

// ============================================================ docs

async function loadDocs() {
  if (!state.project) return;
  await flushDiagramSave();
  const { files } = await api(`/projects/${state.project.id}/docs`);
  state.docs = files;
  if (!files[state.docFile]) state.docFile = 'README.md';
  $('#docs-list').innerHTML = Object.keys(files).map(n =>
    `<li data-file="${esc(n)}" class="${n === state.docFile ? 'active' : ''}">${esc(n)}</li>`).join('');
  renderDoc();
}

function renderDoc() {
  const md = state.docs?.[state.docFile] || '';
  const view = $('#docs-view');
  if ($('#docs-raw').checked) view.innerHTML = `<pre>${esc(md)}</pre>`;
  else renderMarkdown(view, md);
}

function bindDocs() {
  $('#docs-list').addEventListener('click', e => {
    const li = e.target.closest('li[data-file]');
    if (!li) return;
    state.docFile = li.dataset.file;
    $$('#docs-list li').forEach(x => x.classList.toggle('active', x === li));
    renderDoc();
  });
  $('#docs-raw').onchange = renderDoc;
  $('#btn-copy-doc').onclick = () => state.docs && copyText(state.docs[state.docFile] || '', `Copied ${state.docFile}`);
  $('#btn-download-doc').onclick = () => state.docs
    && download(state.docFile, new Blob([state.docs[state.docFile] || ''], { type: 'text/markdown' }));
  $('#btn-export').onclick = async () => {
    try {
      await flushDiagramSave();
      const r = await api(`/projects/${state.project.id}/export`, { method: 'POST' });
      $('#export-status').textContent = `Saved ${r.files.length} files to ${r.path}`;
      toast('Docs saved to disk');
    } catch (err) { toast(err.message, { error: true }); }
  };
}

// ============================================================ settings

function renderSettings() {
  const types = state.meta.provider_types;
  const ps = state.settings.providers;
  $('#provider-list').innerHTML = ps.length ? ps.map(p => `
    <div class="provider" data-id="${esc(p.id)}">
      <div class="info"><b>${esc(p.label)}</b><br>
        <span class="muted small">${esc(types[p.type]?.label || p.type)} · ${esc(p.base_url || 'default URL')} · key: ${p.has_key ? esc(p.api_key) : 'none'}</span></div>
      <input class="test-model" placeholder="model to test" value="${esc(p.default_model)}">
      <button class="btn small" data-act="test">Test</button>
      <button class="btn small" data-act="edit">Edit</button>
      <button class="btn small ghost" data-act="delete">Delete</button>
    </div>`).join('') : '<p class="muted">No providers yet. Add one below.</p>';

  const providerOpts = ['<option value="">(none)</option>', ...ps.map(p => `<option value="${esc(p.id)}">${esc(p.label)}</option>`)].join('');
  $('#agent-rows').innerHTML = Object.entries(state.meta.agents).map(([key, a]) => {
    const cfg = state.settings.agents[key] || {};
    const prov = ps.find(p => p.id === cfg.provider_id);
    const hint = prov ? (prov.default_model || types[prov.type]?.model_hint || '') : '';
    const efforts = ['', 'low', 'medium', 'high', 'xhigh', 'max'];
    return `<tr data-agent="${key}">
      <td><b>${esc(a.name)}</b><br><span class="muted small">${esc(a.description)}</span>
        ${a.subagents?.length ? `<br><span class="muted small">Subagents: ${a.subagents.map(esc).join(', ')}</span>` : ''}</td>
      <td><select class="a-engine">${Object.entries(state.meta.engines || {}).map(([k, l]) =>
        `<option value="${k}" title="${esc(l)}" ${k === (cfg.engine || 'deep') ? 'selected' : ''}>${k === 'deep' ? '🧠 Deep' : '⚡ Fast'}</option>`).join('')}</select></td>
      <td><select class="a-provider">${providerOpts}</select></td>
      <td><input class="a-model" value="${esc(cfg.model)}" placeholder="${esc(hint || 'model id')}"></td>
      <td><select class="a-effort">${efforts.map(e => `<option value="${e}" ${e === (cfg.effort || '') ? 'selected' : ''}>${e || `default (${a.default_effort})`}</option>`).join('')}</select></td>
      <td><input class="a-max" type="number" min="1000" step="1000" value="${esc(cfg.max_tokens || 32000)}" style="width:100px"></td>
    </tr>`;
  }).join('');
  $$('#agent-rows tr').forEach(tr => { $('.a-provider', tr).value = state.settings.agents[tr.dataset.agent]?.provider_id || ''; });
}

function onTypeChange() {
  const type = $('#pf-type').value;
  const t = state.meta.provider_types[type];
  const form = $('#provider-form');
  form.base_url.placeholder = t.base_url || 'https://…/v1';
  form.default_model.placeholder = t.model_hint;
  form.api_key.placeholder = t.needs_key ? 'API key' : 'not required';
  $('#pf-version-wrap').classList.toggle('hidden', type !== 'azure_openai');
  $('#pf-preset-wrap').classList.toggle('hidden', type !== 'openai_compatible');
}

function resetProviderForm() {
  const form = $('#provider-form');
  form.reset();
  form.provider_id.value = '';
  onTypeChange();
}

function editProvider(p) {
  const form = $('#provider-form');
  form.provider_id.value = p.id;
  form.type.value = p.type;
  onTypeChange();
  form.label.value = p.label;
  form.api_key.value = p.api_key;
  form.base_url.value = p.base_url;
  form.api_version.value = p.api_version || '';
  form.default_model.value = p.default_model;
  form.extra_params.value = p.extra_params && Object.keys(p.extra_params).length ? JSON.stringify(p.extra_params) : '';
  $('#provider-form-wrap').open = true;
}

function bindSettings() {
  const dlg = $('#settings-dialog');
  $('#btn-settings').onclick = () => { renderSettings(); dlg.showModal(); };
  $('[data-close]', dlg).onclick = () => dlg.close();
  dlg.addEventListener('close', () => { renderPipeline(); renderAssistant(); });

  $('#pf-type').innerHTML = Object.entries(state.meta.provider_types).map(([k, t]) => `<option value="${k}">${esc(t.label)}</option>`).join('');
  $('#pf-preset').innerHTML = PRESETS.map(([u, l]) => `<option value="${esc(u)}">${esc(l)}</option>`).join('');
  $('#pf-type').onchange = onTypeChange;
  $('#pf-preset').onchange = e => {
    const form = $('#provider-form');
    form.base_url.value = e.target.value;
    if (!form.label.value && e.target.value) form.label.value = e.target.selectedOptions[0].textContent;
  };
  $('#pf-cancel').onclick = () => { resetProviderForm(); $('#provider-form-wrap').open = false; };
  onTypeChange();

  $('#provider-form').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    let extra = {};
    if (f.extra_params.value.trim()) {
      try { extra = JSON.parse(f.extra_params.value); } catch (err) { return toast(`Extra params: ${err.message}`, { error: true }); }
    }
    try {
      state.settings = await api('/providers', {
        method: 'POST',
        body: {
          id: f.provider_id.value || undefined, type: f.type.value, label: f.label.value, api_key: f.api_key.value,
          base_url: f.base_url.value, api_version: f.api_version.value, default_model: f.default_model.value, extra_params: extra,
        },
      });
      resetProviderForm();
      $('#provider-form-wrap').open = false;
      renderSettings();
      toast('Provider saved');
    } catch (err) { toast(err.message, { error: true }); }
  });

  $('#provider-list').addEventListener('click', async e => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const row = btn.closest('[data-id]');
    const p = state.settings.providers.find(x => x.id === row.dataset.id);
    try {
      if (btn.dataset.act === 'edit') editProvider(p);
      else if (btn.dataset.act === 'delete') {
        if (!confirm(`Delete provider "${p.label}"?`)) return;
        state.settings = await api(`/providers/${p.id}`, { method: 'DELETE' });
        renderSettings();
      } else if (btn.dataset.act === 'test') {
        btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
        const r = await api(`/providers/${p.id}/test`, { method: 'POST', body: { model: $('.test-model', row).value } });
        toast(`✓ ${p.label} works: ${r.reply}`);
      }
    } catch (err) {
      toast(err.message, { error: true });
    } finally {
      if (btn.dataset.act === 'test') { btn.disabled = false; btn.textContent = 'Test'; }
    }
  });

  $('#btn-save-agents').onclick = async () => {
    const body = {};
    for (const tr of $$('#agent-rows tr')) {
      body[tr.dataset.agent] = {
        provider_id: $('.a-provider', tr).value,
        model: $('.a-model', tr).value.trim(),
        effort: $('.a-effort', tr).value,
        max_tokens: +$('.a-max', tr).value || 32000,
        engine: $('.a-engine', tr).value,
      };
    }
    try {
      state.settings = await api('/agents', { method: 'PUT', body });
      renderSettings();
      toast('Agent assignments saved');
    } catch (err) { toast(err.message, { error: true }); }
  };
}

// ============================================================ shell

function switchTab(tab) {
  state.tab = tab;
  $$('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.tab').forEach(t => t.classList.toggle('hidden', t.id !== `tab-${tab}`));
  if (tab === 'canvas') requestAnimationFrame(() => editor.fit());
  if (tab === 'docs') loadDocs().catch(err => toast(err.message, { error: true }));
}

async function init() {
  [state.meta, state.settings] = await Promise.all([api('/meta'), api('/settings')]);
  bindSettings();
  bindCanvas();
  bindDocs();
  $('#tabs').addEventListener('click', e => { const b = e.target.closest('button[data-tab]'); if (b) switchTab(b.dataset.tab); });
  $('#stages').addEventListener('click', onStageClick);
  $('#stages').addEventListener('change', e => {
    const sel = e.target.closest('.apply-select');
    if (!sel || !sel.value) return;
    const target = sel.value;
    sel.value = '';
    applyTo(sel.closest('[data-stage]').dataset.stage, target).catch(err => toast(err.message, { error: true }));
  });
  $('#project-select').onchange = e => openProject(e.target.value).catch(err => toast(err.message, { error: true }));
  $('#btn-new-project').onclick = $('#btn-empty-new').onclick = () => newProject().catch(err => toast(err.message, { error: true }));
  $('#btn-delete-project').onclick = async () => {
    if (!state.project || !confirm(`Delete project "${state.project.name}" and all its data?`)) return;
    await api(`/projects/${state.project.id}`, { method: 'DELETE' });
    await loadProjects();
  };
  $('#btn-save-idea').onclick = () => saveIdea().catch(err => toast(err.message, { error: true }));
  $('#btn-run-all').onclick = () => runRemaining().catch(err => toast(err.message, { error: true }));
  window.addEventListener('beforeunload', () => { if (saveTimer) saveDiagram(); });

  await loadProjects();
  if (!state.settings.providers.length) toast('Start by adding a provider under ⚙ Providers & Agents.', { ms: 6000 });
}

init().catch(err => toast(`Failed to start: ${err.message}`, { error: true }));
