import { marked } from 'https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.esm.js';
import DOMPurify from 'https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.es.mjs';
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs';
import { esc } from './ui.js';

const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  flowchart: { curve: 'basis', padding: 14 },
  themeVariables: dark
    ? { primaryColor: '#1e3a5f', primaryBorderColor: '#60a5fa', primaryTextColor: '#e6e9ef', lineColor: '#94a3b8',
        secondaryColor: '#3b2770', tertiaryColor: '#1b1f27', background: '#1b1f27', mainBkg: '#1e3a5f',
        edgeLabelBackground: '#232833', clusterBkg: '#232833', fontFamily: 'system-ui, Segoe UI, sans-serif' }
    : { primaryColor: '#dbeafe', primaryBorderColor: '#2563eb', primaryTextColor: '#1e3a8a', lineColor: '#64748b',
        secondaryColor: '#ede9fe', tertiaryColor: '#f8fafc', edgeLabelBackground: '#ffffff', clusterBkg: '#f8fafc',
        fontFamily: 'system-ui, Segoe UI, sans-serif' },
});

let counter = 0;

/** Render Markdown (LLM output is sanitized) and turn ```mermaid blocks into diagrams. */
export async function renderMarkdown(el, md, opts = {}) {
  el.innerHTML = DOMPurify.sanitize(marked.parse(md || ''));
  for (const code of el.querySelectorAll('pre > code.language-mermaid')) {
    const wrap = document.createElement('div');
    wrap.className = 'mermaid-wrap';
    code.parentElement.replaceWith(wrap);
    await renderMermaid(wrap, code.textContent, opts);
  }
}

export async function renderMermaid(wrap, src, { onOpenInCanvas } = {}) {
  const id = `mmd-${++counter}`;
  try {
    const { svg } = await mermaid.render(id, src);
    wrap.innerHTML = svg;
  } catch (err) {
    document.getElementById('d' + id)?.remove();
    document.getElementById(id)?.remove();
    wrap.innerHTML = `<div class="mermaid-error">Diagram could not be rendered: ${esc(err.message || err)}</div><pre>${esc(src)}</pre>`;
  }
  const actions = document.createElement('div');
  actions.className = 'mermaid-actions';
  const copy = document.createElement('button');
  copy.className = 'btn small';
  copy.textContent = '📋 Copy code';
  copy.title = 'Copy the Mermaid code of this diagram';
  copy.onclick = () => navigator.clipboard.writeText(src).then(() => { copy.textContent = '✓ Copied'; setTimeout(() => { copy.textContent = '📋 Copy code'; }, 1500); });
  actions.appendChild(copy);
  if (onOpenInCanvas && /^\s*(flowchart|graph)\b/.test(src)) {
    const btn = document.createElement('button');
    btn.className = 'btn small';
    btn.textContent = '✎ Edit in canvas';
    btn.onclick = () => onOpenInCanvas(src);
    actions.appendChild(btn);
  }
  wrap.appendChild(actions);
}
