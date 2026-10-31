export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let toastTimer;
export function toast(msg, { error = false, ms = 3500 } = {}) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.toggle('error', error);
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), error ? Math.max(ms, 7000) : ms);
}

/** Small modal form. fields: [{name, label, type: 'text'|'textarea'|'select', value, options: [[value,label]]}] */
export function promptForm(title, fields) {
  const dlg = $('#prompt-dialog');
  $('#prompt-title').textContent = title;
  $('#prompt-fields').innerHTML = fields.map(f => {
    const id = `pq-${f.name}`;
    let input;
    if (f.type === 'textarea') input = `<textarea id="${id}" name="${f.name}" rows="${f.rows || 4}">${esc(f.value)}</textarea>`;
    else if (f.type === 'select') input = `<select id="${id}" name="${f.name}">${f.options.map(([v, l]) =>
      `<option value="${esc(v)}" ${v === f.value ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    else input = `<input id="${id}" name="${f.name}" value="${esc(f.value)}" ${f.required ? 'required' : ''}>`;
    return `<label>${esc(f.label)}${input}</label>`;
  }).join('');
  return new Promise(resolve => {
    dlg.onclose = () => {
      if (dlg.returnValue !== 'ok') return resolve(null);
      const out = {};
      for (const f of fields) out[f.name] = $(`#pq-${f.name}`).value;
      resolve(out);
    };
    dlg.returnValue = '';
    dlg.showModal();
    $('#prompt-fields input, #prompt-fields textarea')?.focus();
  });
}
