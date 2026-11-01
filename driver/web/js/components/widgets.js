/* widgets.js — 通用 UI 小部件（滑块 / 分段控件 / 等级选择 / 进度条 / 统计 / 列表） */
import { icon } from './icons.js';
import { h, clamp } from './util.js';

export function badge(text, kind = '', extra = {}) {
  return h('span', { class: `badge ${kind}`.trim(), ...extra }, text);
}

export function sectionTitle(title, hint = '') {
  return h('div', { class: 'section-title' },
    h('h2', {}, title),
    hint ? h('span', { class: 'hint' }, hint) : null,
  );
}

export function kvList(rows) {
  return h('div', { class: 'kv' }, rows.map(([k, v]) => h('div', { class: 'kv-row' },
    h('div', { class: 'k' }, k),
    h('div', { class: `v${typeof v === 'string' && /^[0-9A-F ]{11,}$/.test(v) ? ' mono' : ''}` }, v),
  )));
}

export function statGrid(items) {
  return h('div', { class: 'stat-grid' }, items.map((it) => h('div', { class: `stat${it.accent ? ' accent' : ''}` },
    h('div', { class: 'stat-label' }, it.label),
    h('div', { class: 'stat-value' }, String(it.value), it.unit ? h('small', {}, it.unit) : null),
  )));
}

export function emptyState(iconName, text, hint = '') {
  return h('div', { class: 'empty' },
    h('div', { html: icon(iconName, { size: 28 }) }),
    h('div', {}, text),
    hint ? h('div', { class: 'tiny' }, hint) : null,
  );
}

/* ---------------------------------------------------------------- slider */
export function createSlider({ label, min = 0, max = 100, value = 50, step = 1, format = (v) => v, onInput, onChange }) {
  const input = h('input', { type: 'range', min: String(min), max: String(max), step: String(step), value: String(value) });
  const valueEl = h('span', { class: 'value' }, format(value));
  const labelEl = h('span', { class: 'label' }, label);
  const wrap = h('div', { class: 'slider-wrap' },
    h('div', { class: 'slider-top' }, labelEl, valueEl),
    input,
  );
  const paint = () => {
    const pct = ((Number(input.value) - min) / (max - min)) * 100;
    input.style.setProperty('--fill', `${pct}%`);
  };
  paint();
  input.addEventListener('input', () => {
    valueEl.textContent = format(Number(input.value));
    paint();
    onInput?.(Number(input.value));
  });
  input.addEventListener('change', () => onChange?.(Number(input.value)));
  return {
    el: wrap,
    get value() { return Number(input.value); },
    set(v, silent = true) {
      input.value = String(v);
      valueEl.textContent = format(Number(input.value));
      paint();
      if (!silent) onInput?.(Number(input.value));
    },
    setLabel(t) { labelEl.textContent = t; },
  };
}

/* ---------------------------------------------------------------- segmented control */
export function createSegmented({ options, value, onChange, full = false, small = false }) {
  const el = h('div', { class: `segmented${full ? ' full' : ''}${small ? ' small' : ''}` });
  let current = value;
  const buttons = options.map((opt) => {
    const btn = h('button', {
      type: 'button',
      class: opt.value === current ? 'active' : '',
      onclick: () => {
        if (opt.value === current) return;
        current = opt.value;
        buttons.forEach((b, i) => b.classList.toggle('active', options[i].value === current));
        onChange?.(current, opt);
      },
    }, opt.label);
    el.append(btn);
    return btn;
  });
  return {
    el,
    get value() { return current; },
    set(v) {
      current = v;
      buttons.forEach((b, i) => b.classList.toggle('active', options[i].value === current));
    },
    setOptions(next) {
      options = next;
      el.innerHTML = '';
      buttons.length = 0;
      next.forEach((opt) => {
        const btn = h('button', {
          type: 'button',
          class: opt.value === current ? 'active' : '',
          onclick: () => { current = opt.value; setActive(); onChange?.(current, opt); },
        }, opt.label);
        el.append(btn);
        buttons.push(btn);
      });
    },
  };
  function setActive() {
    buttons.forEach((b, i) => b.classList.toggle('active', options[i].value === current));
  }
}

/* ---------------------------------------------------------------- level stepper (1..6) */
export function createStepper({ min = 1, max = 6, value = 3, onChange }) {
  const el = h('div', { class: 'stepper' });
  const buttons = [];
  let current = value;
  for (let i = min; i <= max; i++) {
    const b = h('button', {
      type: 'button',
      class: i === current ? 'active' : '',
      title: String(i),
      onclick: () => {
        if (i === current) return;
        current = i;
        buttons.forEach((btn, idx) => btn.classList.toggle('active', idx + min === current));
        onChange?.(current);
      },
    }, String(i));
    el.append(b);
    buttons.push(b);
  }
  return {
    el,
    get value() { return current; },
    set(v) {
      current = clamp(v, min, max);
      buttons.forEach((btn, idx) => btn.classList.toggle('active', idx + min === current));
    },
  };
}

/* ---------------------------------------------------------------- progress */
export function createProgress({ label = '', thin = false } = {}) {
  const labelEl = h('span', {}, label);
  const pctEl = h('strong', {}, '0%');
  const bar = h('div', { class: `progress-bar${thin ? ' thin' : ''}` }, h('i'));
  const el = h('div', { class: 'progress' },
    h('div', { class: 'progress-top' }, labelEl, pctEl),
    bar,
  );
  return {
    el,
    set(pct, text) {
      const p = clamp(Math.round(pct), 0, 100);
      bar.style.setProperty('--pct', `${p}%`);
      pctEl.textContent = `${p}%`;
      el.classList.remove('done', 'error', 'indeterminate');
      if (text !== undefined) labelEl.textContent = text;
    },
    indeterminate(text) {
      bar.style.setProperty('--pct', '100%');
      el.classList.add('indeterminate');
      el.classList.remove('done', 'error');
      pctEl.textContent = '';
      if (text !== undefined) labelEl.textContent = text;
    },
    done(text) {
      bar.style.setProperty('--pct', '100%');
      el.classList.add('done');
      el.classList.remove('indeterminate', 'error');
      pctEl.textContent = '100%';
      if (text !== undefined) labelEl.textContent = text;
    },
    error(text) {
      el.classList.add('error');
      el.classList.remove('indeterminate', 'done');
      pctEl.textContent = '!';
      if (text !== undefined) labelEl.textContent = text;
    },
    reset(text) {
      bar.style.setProperty('--pct', '0%');
      el.classList.remove('done', 'error', 'indeterminate');
      pctEl.textContent = '0%';
      if (text !== undefined) labelEl.textContent = text;
    },
  };
}

/* ---------------------------------------------------------------- tabs */
export function createTabs({ tabs, active, onChange, counts = {} }) {
  const el = h('div', { class: 'tabs', role: 'tablist' });
  let current = active ?? tabs[0].id;
  const buttons = tabs.map((t) => {
    const btn = h('button', {
      type: 'button', role: 'tab',
      class: t.id === current ? 'active' : '',
      'data-id': t.id,
      onclick: () => {
        if (t.id === current) return;
        current = t.id;
        buttons.forEach((b) => b.classList.toggle('active', b.dataset.id === current));
        onChange?.(current);
      },
    }, t.icon ? h('span', { html: icon(t.icon, { size: 14 }) }) : null, t.label,
    counts[t.id] !== undefined ? h('span', { class: 'count' }, String(counts[t.id])) : null);
    el.append(btn);
    return btn;
  });
  return {
    el,
    get value() { return current; },
    set(v) {
      current = v;
      buttons.forEach((b) => b.classList.toggle('active', b.dataset.id === current));
    },
  };
}

/* ---------------------------------------------------------------- misc layout */
export function fieldRow(label, control, hint = '') {
  return h('div', { class: 'field' },
    h('div', { class: 'field-label' }, label),
    control,
    hint ? h('div', { class: 'field-hint' }, hint) : null,
  );
}

export function card({ title = '', desc = '', actions = null, body = null, className = '', flush = false }) {
  const head = title || actions ? h('div', { class: 'card-head' },
    h('div', {},
      title ? h('div', { class: 'card-title' }, title) : null,
      desc ? h('div', { class: 'card-desc' }, desc) : null,
    ),
    h('div', { class: 'spacer' }),
    actions || null,
  ) : null;
  const bodyNode = h('div', { class: `card-body${flush ? ' flush' : ''}` });
  if (body instanceof Node) bodyNode.append(body);
  return h('section', { class: `card ${className}`.trim() }, head, bodyNode);
}

/** 带搜索框的列表 */
export function searchBox({ placeholder = '搜索…', onInput }) {
  const input = h('input', { class: 'input sm', placeholder });
  const wrap = h('div', { class: 'search-box' },
    h('div', { html: icon('search', { size: 15 }) }),
    input,
  );
  input.addEventListener('input', () => onInput?.(input.value.trim()));
  return { el: wrap, get value() { return input.value; }, focus: () => input.focus() };
}
