/* Manual diagram editor (SVG) with Mermaid import/export. */

const NS = 'http://www.w3.org/2000/svg';
const GRID = 10;

export const SHAPES = {
  process: { label: 'Process', w: 150, h: 60, mm: ['[', ']'] },
  decision: { label: 'Decision?', w: 150, h: 90, mm: ['{', '}'] },
  terminal: { label: 'Start', w: 140, h: 50, mm: ['([', '])'] },
  database: { label: 'Database', w: 130, h: 80, mm: ['[(', ')]'] },
  service: { label: 'Service', w: 150, h: 60, mm: ['[[', ']]'] },
  actor: { label: 'User', w: 90, h: 90, mm: ['((', '))'] },
  external: { label: 'External system', w: 150, h: 60, mm: ['>', ']'] },
  queue: { label: 'Queue', w: 150, h: 56, mm: ['[/', '/]'] },
  note: { label: 'Note', w: 170, h: 70, mm: ['[', ']'] },
};

const ICONS = { process: '⚙', service: '▥', database: '⛁', queue: '✉', external: '⇄', note: '✎' };

/** Mermaid colours per shape type (explicit fills so docs look the same on GitHub light and dark). */
export const MERMAID_CLASSES = {
  terminal: 'fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d',
  process: 'fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a',
  decision: 'fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f',
  actor: 'fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95',
  service: 'fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px,color:#312e81',
  database: 'fill:#ccfbf1,stroke:#0d9488,stroke-width:2px,color:#134e4a',
  queue: 'fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#7c2d12',
  external: 'fill:#f1f5f9,stroke:#64748b,stroke-width:2px,stroke-dasharray:5 4,color:#1e293b',
  note: 'fill:#fef9c3,stroke:#ca8a04,stroke-width:1px,color:#713f12',
};

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

const snap = v => Math.round(v / GRID) * GRID;
const clone = o => JSON.parse(JSON.stringify(o));

function wrapText(label, maxChars) {
  const lines = [];
  for (const para of String(label || '').split('\n')) {
    let line = '';
    for (const word of para.split(/\s+/)) {
      if (!word) continue;
      if (line && (line + ' ' + word).length > maxChars) { lines.push(line); line = word; }
      else line = line ? line + ' ' + word : word;
    }
    lines.push(line);
  }
  return lines;
}

export class DiagramEditor {
  constructor(svg, { onChange, onSelect } = {}) {
    this.svg = svg;
    this.onChange = onChange || (() => {});
    this.onSelect = onSelect || (() => {});
    this._selSig = '';
    this.graph = { direction: 'TD', nodes: [], edges: [] };
    this.view = { x: 40, y: 40, k: 1 };
    this.selected = null;
    this.drag = null;
    this.enabled = false;
    this.history = [];
    this._build();
    this._bind();
  }

  _build() {
    this.svg.innerHTML = '';
    const defs = el('defs', {}, this.svg);
    const marker = el('marker', { id: 'arrow', viewBox: '0 0 10 10', refX: 10, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto-start-reverse' }, defs);
    el('path', { d: 'M0,0 L10,5 L0,10 z' }, marker);
    const shadow = el('filter', { id: 'shadow', x: '-20%', y: '-20%', width: '140%', height: '150%' }, defs);
    el('feDropShadow', { dx: 0, dy: 2, stdDeviation: 2.5, 'flood-color': '#101828', 'flood-opacity': 0.18 }, shadow);
    const pat = el('pattern', { id: 'grid', width: 20, height: 20, patternUnits: 'userSpaceOnUse' }, defs);
    el('path', { d: 'M20 0 L0 0 0 20', fill: 'none', style: 'stroke: var(--grid)' }, pat);
    this.world = el('g', {}, this.svg);
    el('rect', { x: -10000, y: -10000, width: 20000, height: 20000, fill: 'url(#grid)' }, this.world);
    this.edgeLayer = el('g', {}, this.world);
    this.nodeLayer = el('g', {}, this.world);
    this.tempLayer = el('g', {}, this.world);
    this._applyView();
  }

  _bind() {
    this.svg.addEventListener('pointerdown', e => this._down(e));
    window.addEventListener('pointermove', e => this._move(e));
    window.addEventListener('pointerup', e => this._up(e));
    this.svg.addEventListener('dblclick', e => this._dbl(e));
    this.svg.addEventListener('wheel', e => this._wheel(e), { passive: false });
    this.svg.addEventListener('keydown', e => {
      if (!this.enabled) return;
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); this.deleteSelected(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); this.undo(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); this.duplicateSelected(); }
    });
  }

  // ------------------------------------------------------------ public API

  setEnabled(on) { this.enabled = on; this.svg.style.visibility = on ? 'visible' : 'hidden'; }

  load(graph) {
    this.graph = Object.assign({ direction: 'TD', nodes: [], edges: [] }, clone(graph || {}));
    this.selected = null;
    this.history = [clone(this.graph)];
    this.render();
    requestAnimationFrame(() => this.fit());
  }

  getGraph() { return clone(this.graph); }

  setDirection(dir) { this.graph.direction = dir; this._changed(); }

  addNode(type, at) {
    const s = SHAPES[type] || SHAPES.process;
    const r = this.svg.getBoundingClientRect();
    const c = at || {
      x: (r.width / 2 - this.view.x) / this.view.k + (Math.random() * 60 - 30),
      y: (r.height / 2 - this.view.y) / this.view.k + (Math.random() * 60 - 30),
    };
    const n = { id: this._nextId('n', this.graph.nodes), type, label: s.label, x: snap(c.x - s.w / 2), y: snap(c.y - s.h / 2), w: s.w, h: s.h };
    this.graph.nodes.push(n);
    this.selected = { kind: 'node', id: n.id };
    this._changed();
    return n;
  }

  deleteSelected() {
    const sel = this.selected;
    if (!sel) return;
    if (sel.kind === 'node') {
      this.graph.nodes = this.graph.nodes.filter(n => n.id !== sel.id);
      this.graph.edges = this.graph.edges.filter(e => e.from !== sel.id && e.to !== sel.id);
    } else {
      this.graph.edges = this.graph.edges.filter(e => e.id !== sel.id);
    }
    this.selected = null;
    this._changed();
  }

  selectedNode() {
    return this.selected?.kind === 'node' ? this._node(this.selected.id) || null : null;
  }

  /** Edit a node's label/type/description. Pass record=false while typing, then call commit() once. */
  updateNode(id, patch, record = true) {
    const n = this._node(id);
    if (!n) return;
    if (patch.type && patch.type !== n.type && SHAPES[patch.type]) {
      n.w = SHAPES[patch.type].w; n.h = SHAPES[patch.type].h;
    }
    Object.assign(n, patch);
    this._changed(record);
  }

  commit() { this._record(); }

  duplicateSelected() {
    const n = this.selectedNode();
    if (!n) return;
    const copy = { ...clone(n), id: this._nextId('n', this.graph.nodes), x: n.x + 30, y: n.y + 30 };
    this.graph.nodes.push(copy);
    this.selected = { kind: 'node', id: copy.id };
    this._changed();
  }

  /** {nodeId: description} for nodes that have one. */
  getDescriptions() {
    return Object.fromEntries(this.graph.nodes.filter(n => n.description).map(n => [n.id, n.description]));
  }

  /** Standalone SVG of the diagram with resolved colours (for download). */
  exportSVG() {
    const ns = this.graph.nodes;
    if (!ns.length) return '';
    const pad = 30;
    const minX = Math.min(...ns.map(n => n.x)) - pad, minY = Math.min(...ns.map(n => n.y)) - pad;
    const maxX = Math.max(...ns.map(n => n.x + n.w)) + pad, maxY = Math.max(...ns.map(n => n.y + n.h)) + pad;
    const prevSel = this.selected;
    this.selected = null;
    this.render();
    const out = this.svg.cloneNode(true);
    const src = this.svg.querySelectorAll('*'), dst = out.querySelectorAll('*');
    const props = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-size', 'font-weight', 'font-family'];
    src.forEach((s, i) => {
      const cs = getComputedStyle(s);
      dst[i].setAttribute('style', props.map(p => `${p}:${cs.getPropertyValue(p)}`).join(';'));
    });
    out.querySelectorAll('.handle').forEach(h => h.remove());
    out.querySelector('rect[fill="url(#grid)"]')?.remove();
    out.querySelector('g').removeAttribute('transform');
    out.setAttribute('xmlns', NS);
    out.setAttribute('viewBox', `${minX} ${minY} ${maxX - minX} ${maxY - minY}`);
    out.setAttribute('width', maxX - minX);
    out.setAttribute('height', maxY - minY);
    out.style.background = getComputedStyle(this.svg.parentElement).backgroundColor;
    this.selected = prevSel;
    this.render();
    return new XMLSerializer().serializeToString(out);
  }

  layout() { autoLayout(this.graph); this._changed(); this.fit(); }

  zoom(factor) {
    const r = this.svg.getBoundingClientRect();
    this._zoomAt(r.width / 2, r.height / 2, factor);
  }

  fit() {
    const r = this.svg.getBoundingClientRect();
    const ns = this.graph.nodes;
    if (!ns.length || !r.width) { this.view = { x: 40, y: 40, k: 1 }; return this._applyView(); }
    const minX = Math.min(...ns.map(n => n.x)), minY = Math.min(...ns.map(n => n.y));
    const maxX = Math.max(...ns.map(n => n.x + n.w)), maxY = Math.max(...ns.map(n => n.y + n.h));
    const pad = 50;
    const k = Math.min(1.4, (r.width - pad * 2) / (maxX - minX), (r.height - pad * 2) / (maxY - minY));
    this.view = { k, x: (r.width - (maxX - minX) * k) / 2 - minX * k, y: (r.height - (maxY - minY) * k) / 2 - minY * k };
    this._applyView();
  }

  toMermaid() { return graphToMermaid(this.graph); }

  importMermaid(text) {
    const g = mermaidToGraph(text);
    this._carryDescriptions(g, {});
    this.graph = g;
    this.selected = null;
    this._changed();
    this.fit();
  }

  /** Apply an updated diagram (e.g. from the Diagram Agent) while keeping positions of nodes that still exist.
   *  `descriptions` ({id: text}) adds or replaces per-node descriptions; others are kept. */
  applyMermaid(text, descriptions = {}) {
    const g = mermaidToGraph(text);
    const old = new Map(this.graph.nodes.map(n => [n.id, n]));
    if ([...old.keys()].some(id => g.nodes.some(n => n.id === id))) placeNewNodes(g, old);
    this._carryDescriptions(g, descriptions);
    this.graph = g;
    this.selected = null;
    this._changed();
    this.fit();
  }

  _carryDescriptions(g, descriptions) {
    const old = new Map(this.graph.nodes.map(n => [n.id, n.description]));
    for (const n of g.nodes) {
      const d = descriptions?.[n.id] ?? old.get(n.id);
      if (d) n.description = String(d);
    }
  }

  canUndo() { return this.history.length > 1; }

  undo() {
    if (!this.canUndo()) return;
    this.history.pop();
    this.graph = clone(this.history[this.history.length - 1]);
    this.selected = null;
    this.render();
    this.onChange();
  }

  _notifySelection() {
    const n = this.selectedNode();
    const sig = n ? `${n.id}|${n.label}|${n.type}|${n.description || ''}` : '';
    if (sig !== this._selSig) { this._selSig = sig; this.onSelect(n); }
  }

  _record() {
    this.history.push(clone(this.graph));
    if (this.history.length > 50) this.history.shift();
  }

  // ------------------------------------------------------------ rendering

  render() {
    this.edgeLayer.innerHTML = '';
    this.nodeLayer.innerHTML = '';
    for (const e of this.graph.edges) this._renderEdge(e);
    for (const n of this.graph.nodes) this._renderNode(n);
    this._notifySelection();
  }

  _renderNode(n) {
    const sel = this.selected?.kind === 'node' && this.selected.id === n.id;
    const g = el('g', { class: `node ${n.type}${sel ? ' selected' : ''}`, transform: `translate(${n.x},${n.y})`, 'data-node': n.id }, this.nodeLayer);
    const { w, h } = n;
    const cls = { class: 'shape' };
    switch (n.type) {
      case 'decision': el('polygon', { ...cls, points: `${w / 2},0 ${w},${h / 2} ${w / 2},${h} 0,${h / 2}` }, g); break;
      case 'terminal': el('rect', { ...cls, width: w, height: h, rx: h / 2 }, g); break;
      case 'actor': el('circle', { ...cls, cx: w / 2, cy: h / 2, r: Math.min(w, h) / 2 }, g); break;
      case 'queue': { const s = 16; el('polygon', { ...cls, points: `${s},0 ${w},0 ${w - s},${h} 0,${h}` }, g); break; }
      case 'database': {
        const e = 10;
        el('path', { ...cls, d: `M0,${e} L0,${h - e} A${w / 2},${e} 0 0 0 ${w},${h - e} L${w},${e} A${w / 2},${e} 0 0 0 0,${e} Z` }, g);
        el('ellipse', { ...cls, cx: w / 2, cy: e, rx: w / 2, ry: e }, g);
        break;
      }
      case 'service':
        el('rect', { ...cls, width: w, height: h, rx: 4 }, g);
        el('line', { class: 'shape', x1: 10, y1: 0, x2: 10, y2: h }, g);
        el('line', { class: 'shape', x1: w - 10, y1: 0, x2: w - 10, y2: h }, g);
        break;
      case 'note': el('path', { ...cls, d: `M0,0 L${w - 14},0 L${w},14 L${w},${h} L0,${h} Z` }, g); break;
      default: el('rect', { ...cls, width: w, height: h, rx: 6 }, g);
    }
    const inner = n.type === 'decision' ? w * 0.6 : n.type === 'actor' ? w * 0.8 : w - 20;
    const lines = wrapText(n.label, Math.max(6, Math.floor(inner / 7.2)));
    const t = el('text', { x: w / 2, 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, g);
    lines.forEach((line, i) => {
      const ts = el('tspan', { x: w / 2, y: h / 2 + (i - (lines.length - 1) / 2) * 16 }, t);
      ts.textContent = line;
    });
    if (n.description) {
      el('title', {}, g).textContent = `${n.label}\n\n${n.description}`;
      el('circle', { class: 'info-dot', cx: w - 4, cy: 4, r: 8 }, g);
      el('text', { class: 'info-i', x: w - 4, y: 4, 'text-anchor': 'middle', 'dominant-baseline': 'central' }, g).textContent = 'i';
    }
    const icon = ICONS[n.type];
    if (icon && !['decision', 'actor', 'terminal'].includes(n.type)) {
      el('text', { class: 'icon', x: n.type === 'queue' ? 20 : 8, y: n.type === 'database' ? 32 : 15 }, g).textContent = icon;
    }
    el('circle', { class: 'handle', cx: w, cy: h / 2, r: 6, 'data-handle': n.id }, g);
    el('circle', { class: 'handle', cx: w / 2, cy: h, r: 6, 'data-handle': n.id }, g);
  }

  _renderEdge(e) {
    const a = this._node(e.from), b = this._node(e.to);
    if (!a || !b || a === b) return;
    const p1 = boundary(a, center(b)), p2 = boundary(b, center(a));
    const sel = this.selected?.kind === 'edge' && this.selected.id === e.id;
    const g = el('g', { class: `edge${sel ? ' selected' : ''}`, 'data-edge': e.id }, this.edgeLayer);
    const d = `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
    el('path', { class: 'hit', d }, g);
    el('path', { class: 'line', d, 'marker-end': 'url(#arrow)' }, g);
    if (e.label) {
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
      const bg = el('rect', { class: 'label-bg', rx: 3 }, g);
      const t = el('text', { x: mx, y: my, 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, g);
      t.textContent = e.label;
      const bb = t.getBBox();
      Object.entries({ x: bb.x - 4, y: bb.y - 2, width: bb.width + 8, height: bb.height + 4 }).forEach(([k, v]) => bg.setAttribute(k, v));
    }
  }

  _applyView() {
    this.world.setAttribute('transform', `translate(${this.view.x},${this.view.y}) scale(${this.view.k})`);
  }

  // ------------------------------------------------------------ interaction

  _node(id) { return this.graph.nodes.find(n => n.id === id); }

  _nextId(prefix, list) {
    let max = 0;
    for (const x of list) { const m = new RegExp(`^${prefix}(\\d+)$`).exec(x.id); if (m) max = Math.max(max, +m[1]); }
    let id = `${prefix}${max + 1}`;
    while (list.some(x => x.id === id)) id += '_';
    return id;
  }

  _world(e) {
    const r = this.svg.getBoundingClientRect();
    return { x: (e.clientX - r.left - this.view.x) / this.view.k, y: (e.clientY - r.top - this.view.y) / this.view.k };
  }

  _changed(record = true) { if (record) this._record(); this.render(); this.onChange(); }

  _down(e) {
    if (!this.enabled || e.button !== 0) return;
    this.svg.focus();
    const handle = e.target.closest('[data-handle]');
    if (handle) { this.drag = { mode: 'connect', from: handle.dataset.handle }; e.preventDefault(); return; }
    const nodeEl = e.target.closest('[data-node]');
    if (nodeEl) {
      const n = this._node(nodeEl.dataset.node);
      const p = this._world(e);
      this.selected = { kind: 'node', id: n.id };
      this.drag = { mode: 'move', id: n.id, dx: p.x - n.x, dy: p.y - n.y, moved: false };
      this.render();
      return;
    }
    const edgeEl = e.target.closest('[data-edge]');
    if (edgeEl) { this.selected = { kind: 'edge', id: edgeEl.dataset.edge }; this.render(); return; }
    this.selected = null;
    this.drag = { mode: 'pan', sx: e.clientX, sy: e.clientY, vx: this.view.x, vy: this.view.y };
    this.render();
  }

  _move(e) {
    const d = this.drag;
    if (!d) return;
    if (d.mode === 'pan') {
      this.view.x = d.vx + e.clientX - d.sx;
      this.view.y = d.vy + e.clientY - d.sy;
      this._applyView();
    } else if (d.mode === 'move') {
      const n = this._node(d.id);
      const p = this._world(e);
      n.x = snap(p.x - d.dx); n.y = snap(p.y - d.dy);
      d.moved = true;
      this.render();
    } else if (d.mode === 'connect') {
      const a = center(this._node(d.from));
      const p = this._world(e);
      this.tempLayer.innerHTML = '';
      el('line', { class: 'temp-line', x1: a.x, y1: a.y, x2: p.x, y2: p.y, 'marker-end': 'url(#arrow)' }, this.tempLayer);
    }
  }

  _up(e) {
    const d = this.drag;
    if (!d) return;
    this.drag = null;
    if (d.mode === 'connect') {
      this.tempLayer.innerHTML = '';
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-node]');
      const to = target?.dataset.node;
      if (to && to !== d.from && !this.graph.edges.some(x => x.from === d.from && x.to === to)) {
        const edge = { id: this._nextId('e', this.graph.edges), from: d.from, to, label: '' };
        this.graph.edges.push(edge);
        this.selected = { kind: 'edge', id: edge.id };
        this._changed();
      }
    } else if (d.mode === 'move' && d.moved) {
      this._record();
      this.onChange();
    }
  }

  _dbl(e) {
    if (!this.enabled) return;
    const nodeEl = e.target.closest('[data-node]');
    const edgeEl = e.target.closest('[data-edge]');
    if (nodeEl) {
      const n = this._node(nodeEl.dataset.node);
      const label = window.prompt('Shape label (use \\n for a new line):', n.label.replace(/\n/g, '\\n'));
      if (label !== null) { n.label = label.replace(/\\n/g, '\n'); this._changed(); }
    } else if (edgeEl) {
      const ed = this.graph.edges.find(x => x.id === edgeEl.dataset.edge);
      const label = window.prompt('Arrow label (leave empty for none):', ed.label || '');
      if (label !== null) { ed.label = label; this._changed(); }
    } else {
      const n = this.addNode('process', this._world(e));
      const label = window.prompt('Step label:', n.label);
      if (label !== null) { n.label = label; this._changed(); }
    }
  }

  _wheel(e) {
    if (!this.enabled) return;
    e.preventDefault();
    const r = this.svg.getBoundingClientRect();
    this._zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.1 : 1 / 1.1);
  }

  _zoomAt(mx, my, factor) {
    const k2 = Math.min(3, Math.max(0.2, this.view.k * factor));
    this.view.x = mx - (mx - this.view.x) * (k2 / this.view.k);
    this.view.y = my - (my - this.view.y) * (k2 / this.view.k);
    this.view.k = k2;
    this._applyView();
  }
}

function center(n) { return { x: n.x + n.w / 2, y: n.y + n.h / 2 }; }

/** Point on the node outline in the direction of `target`. */
function boundary(n, target) {
  const c = center(n);
  const dx = target.x - c.x, dy = target.y - c.y;
  if (!dx && !dy) return c;
  let s;
  if (n.type === 'decision') s = 1 / (Math.abs(dx) / (n.w / 2) + Math.abs(dy) / (n.h / 2));
  else if (n.type === 'actor') s = (Math.min(n.w, n.h) / 2) / Math.hypot(dx, dy);
  else s = 1 / Math.max(Math.abs(dx) / (n.w / 2), Math.abs(dy) / (n.h / 2));
  return { x: c.x + dx * s, y: c.y + dy * s };
}

// ------------------------------------------------------------ layout

export function autoLayout(graph) {
  const ids = graph.nodes.map(n => n.id);
  const out = new Map(ids.map(i => [i, []]));
  const indeg = new Map(ids.map(i => [i, 0]));
  for (const e of graph.edges) {
    if (out.has(e.from) && indeg.has(e.to)) { out.get(e.from).push(e.to); indeg.set(e.to, indeg.get(e.to) + 1); }
  }
  const layer = new Map();
  const bfs = roots => {
    const q = [...roots];
    roots.forEach(r => layer.set(r, 0));
    for (let i = 0; i < q.length; i++) {
      for (const v of out.get(q[i])) if (!layer.has(v)) { layer.set(v, layer.get(q[i]) + 1); q.push(v); }
    }
  };
  bfs(ids.filter(i => indeg.get(i) === 0));
  for (const id of ids) if (!layer.has(id)) bfs([id]);

  const layers = [];
  for (const id of ids) (layers[layer.get(id)] ||= []).push(id);
  const LR = graph.direction === 'LR';
  const mainGap = LR ? 230 : 140, crossGap = LR ? 120 : 200;
  const maxCount = Math.max(1, ...layers.map(l => (l || []).length));
  layers.forEach((items, L) => {
    (items || []).forEach((id, idx) => {
      const n = graph.nodes.find(x => x.id === id);
      const cross = 100 + ((maxCount - 1) / 2 + idx - (items.length - 1) / 2) * crossGap;
      const main = 80 + L * mainGap;
      const cx = LR ? main : cross, cy = LR ? cross : main;
      n.x = snap(cx - n.w / 2); n.y = snap(cy - n.h / 2);
    });
  });
}

/** Keep positions of nodes found in `old`; place new nodes next to an already-placed neighbour without overlapping. */
export function placeNewNodes(g, old) {
  const LR = g.direction === 'LR';
  const placed = [];
  const placedIds = new Set();
  for (const n of g.nodes) {
    const o = old.get(n.id);
    if (o) { n.x = o.x; n.y = o.y; placed.push(n); placedIds.add(n.id); }
  }
  const overlaps = (x, y, n) => placed.some(p =>
    x < p.x + p.w + 30 && x + n.w + 30 > p.x && y < p.y + p.h + 30 && y + n.h + 30 > p.y);
  let pending = g.nodes.filter(n => !placedIds.has(n.id));
  while (pending.length) {
    let n = null, edge = null;
    for (const cand of pending) {
      edge = g.edges.find(e => (e.to === cand.id && placedIds.has(e.from)) || (e.from === cand.id && placedIds.has(e.to)));
      if (edge) { n = cand; break; }
    }
    let x, y;
    if (n) {
      const a = placed.find(p => p.id === (edge.to === n.id ? edge.from : edge.to));
      const after = edge.from === a.id ? 1 : -1;
      x = LR ? a.x + after * 230 : a.x + (a.w - n.w) / 2;
      y = LR ? a.y + (a.h - n.h) / 2 : a.y + after * 140;
    } else {
      n = pending[0];
      x = LR ? Math.max(...placed.map(p => p.x + p.w)) + 80 : Math.min(...placed.map(p => p.x));
      y = LR ? Math.min(...placed.map(p => p.y)) : Math.max(...placed.map(p => p.y + p.h)) + 80;
    }
    for (let guard = 0; overlaps(x, y, n) && guard < 60; guard++) {
      if (LR) y += n.h + 40; else x += n.w + 40;
    }
    n.x = snap(x); n.y = snap(y);
    placed.push(n); placedIds.add(n.id);
    pending = pending.filter(p => p !== n);
  }
}

// ------------------------------------------------------------ Mermaid <-> graph

const quote = s => `"${String(s ?? '').replace(/"/g, '#quot;').replace(/\n/g, '<br/>')}"`;

export function graphToMermaid(graph) {
  if (!graph.nodes.length) return '';
  const lines = [`flowchart ${graph.direction || 'TD'}`];
  for (const n of graph.nodes) {
    const [o, c] = (SHAPES[n.type] || SHAPES.process).mm;
    lines.push(`  ${n.id}${o}${quote(n.label)}${c}`);
  }
  for (const e of graph.edges) lines.push(`  ${e.from} -->${e.label ? `|${quote(e.label)}|` : ''} ${e.to}`);
  const byType = {};
  for (const n of graph.nodes) (byType[n.type] ||= []).push(n.id);
  for (const [type, ids] of Object.entries(byType)) {
    if (!MERMAID_CLASSES[type]) continue;
    lines.push(`  classDef ${type} ${MERMAID_CLASSES[type]}`);
    lines.push(`  class ${ids.join(',')} ${type}`);
  }
  return lines.join('\n');
}

const OPENERS = [
  ['([', ['])'], 'terminal'], ['[(', [')]'], 'database'], ['[[', [']]'], 'service'], ['((', ['))'], 'actor'],
  ['[/', ['/]', '\\]'], 'queue'], ['[\\', ['\\]', '/]'], 'queue'], ['{{', ['}}'], 'decision'], ['{', ['}'], 'decision'],
  ['>', [']'], 'external'], ['[', [']'], 'process'], ['(', [')'], 'process'],
];

const unquote = s => String(s).trim().replace(/^"(.*)"$/s, '$1').replace(/#quot;/g, '"').replace(/<br\s*\/?>/gi, '\n').trim();

function parseNode(s, i) {
  const m = /^\s*([A-Za-z0-9_]\w*)/.exec(s.slice(i));
  if (!m) return null;
  let pos = i + m[0].length;
  let type = null, label = null;
  for (const [open, closes, t] of OPENERS) {
    if (!s.startsWith(open, pos)) continue;
    let p = pos + open.length;
    if (s[p] === '"') {
      const q = s.indexOf('"', p + 1);
      if (q < 0) continue;
      const after = s.slice(q + 1);
      const ws = after.length - after.trimStart().length;
      const c = closes.find(c => after.trimStart().startsWith(c));
      if (!c) continue;
      label = s.slice(p + 1, q);
      pos = q + 1 + ws + c.length;
    } else {
      let best = -1, bc = null;
      for (const c of closes) { const k = s.indexOf(c, p); if (k >= 0 && (best < 0 || k < best)) { best = k; bc = c; } }
      if (best < 0) continue;
      label = s.slice(p, best);
      pos = best + bc.length;
    }
    type = t;
    break;
  }
  let cls = null;
  const cm = /^:::([\w-]+)/.exec(s.slice(pos));
  if (cm) { cls = cm[1]; pos += cm[0].length; }
  return { id: m[1], type, label: label === null ? null : unquote(label), cls, pos };
}

const EDGE_PATTERNS = [
  /^\s*--\s+(.+?)\s+-{2,}[>ox]?/,
  /^\s*==\s+(.+?)\s+={2,}[>ox]?/,
  /^\s*-\.\s+(.+?)\s+\.-+[>ox]?/,
  /^\s*<?(?:-\.+-|-{2,}|={2,}|~~~)[>ox]?\s*(?:\|([^|]*)\|)?/,
];

function parseEdge(s, i) {
  const rest = s.slice(i);
  for (const re of EDGE_PATTERNS) {
    const m = re.exec(rest);
    if (m) return { label: m[1] ? unquote(m[1]) : '', len: m[0].length };
  }
  return null;
}

export function mermaidToGraph(text) {
  const raw = String(text || '').split('\n').map(l => l.trim().replace(/;$/, '')).filter(l => l && !l.startsWith('%%'));
  if (!raw.length) throw new Error('Mermaid code is empty.');
  const header = /^(flowchart|graph)\b\s*(TD|TB|LR|RL|BT)?/i.exec(raw[0]);
  if (!header) throw new Error('Only Mermaid flowcharts (flowchart / graph) can be opened in the canvas.');
  const dirRaw = (header[2] || 'TD').toUpperCase();
  const direction = dirRaw === 'LR' || dirRaw === 'RL' ? 'LR' : 'TD';

  const nodes = new Map();
  const edges = [];
  const noteIds = new Set();
  const upsert = r => {
    const n = nodes.get(r.id);
    const type = r.cls === 'note' ? 'note' : r.type;
    if (n) {
      if (type) n.type = type;
      if (r.label !== null) n.label = r.label;
    } else {
      nodes.set(r.id, { id: r.id, type: type || 'process', label: r.label ?? r.id });
    }
  };

  for (const line of raw.slice(1)) {
    if (/^(subgraph|end$|end\s|classDef|style|linkStyle|click|direction)\b/.test(line)) continue;
    const cm = /^class\s+([\w,\s]+?)\s+([\w-]+)$/.exec(line);
    if (cm) { if (cm[2] === 'note') cm[1].split(',').forEach(id => noteIds.add(id.trim())); continue; }

    let i = 0, prev = null, label = '';
    while (i < line.length) {
      const group = [];
      const first = parseNode(line, i);
      if (!first) break;
      group.push(first); i = first.pos;
      for (;;) {
        const amp = /^\s*&\s*/.exec(line.slice(i));
        if (!amp) break;
        const r = parseNode(line, i + amp[0].length);
        if (!r) break;
        group.push(r); i = r.pos;
      }
      group.forEach(upsert);
      if (prev) for (const a of prev) for (const b of group) edges.push({ from: a.id, to: b.id, label });
      const em = parseEdge(line, i);
      if (!em) break;
      prev = group; label = em.label; i += em.len;
    }
  }

  const graph = { direction, nodes: [], edges: [] };
  for (const n of nodes.values()) {
    if (noteIds.has(n.id)) n.type = 'note';
    const s = SHAPES[n.type];
    graph.nodes.push({ ...n, x: 0, y: 0, w: s.w, h: s.h });
  }
  edges.forEach((e, k) => graph.edges.push({ id: `e${k + 1}`, ...e }));
  if (!graph.nodes.length) throw new Error('No nodes found in the Mermaid code.');
  autoLayout(graph);
  return graph;
}
