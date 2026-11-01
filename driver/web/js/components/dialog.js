/* dialog.js — 二次确认 / 信息对话框（Promise 风格） */
import { icon } from './icons.js';
import { h } from './util.js';

let active = null;

/**
 * 通用对话框
 * @returns {Promise<any>} 点击按钮返回 value，关闭返回 null
 */
export function openDialog({
  title,
  sub = '',
  iconName = 'info',
  iconKind = '',          // '' | 'danger' | 'warn'
  body = null,            // Node | string(HTML) | null
  buttons = [{ label: '确定', value: true, kind: 'primary' }],
  wide = false,
  dismissible = true,
} = {}) {
  return new Promise((resolve) => {
    const rootEl = document.getElementById('dialog-root');
    const prevFocus = document.activeElement;

    const bodyNode = h('div', { class: 'dialog-body' });
    if (body instanceof Node) bodyNode.append(body);
    else if (typeof body === 'string') bodyNode.innerHTML = body;

    const foot = h('div', { class: 'dialog-foot' });
    const btnNodes = buttons.map((b) => {
      const cls = ['btn', b.kind === 'primary' ? 'primary' : b.kind === 'danger' ? 'danger' : ''].filter(Boolean).join(' ');
      const node = h('button', { class: cls, onclick: () => finish(b.value) }, b.label);
      foot.append(node);
      return node;
    });

    const dialog = h('div', {
      class: `dialog${wide ? ' wide' : ''}`,
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': title,
    },
      h('div', { class: 'dialog-head' },
        h('div', { class: `dialog-icon ${iconKind}`, html: icon(iconName, { size: 19 }) }),
        h('div', {},
          h('div', { class: 'dialog-title' }, title),
          sub ? h('div', { class: 'dialog-sub' }, sub) : null,
        ),
      ),
      bodyNode,
      foot,
    );

    const backdrop = h('div', { class: 'dialog-backdrop' }, dialog);

    function finish(value) {
      if (active !== backdrop) return;
      active = null;
      document.removeEventListener('keydown', onKey, true);
      backdrop.remove();
      if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
      resolve(value);
    }

    function onKey(e) {
      if (e.key === 'Escape' && dismissible) {
        e.stopPropagation();
        finish(null);
      } else if (e.key === 'Enter' && buttons.length) {
        const primary = buttons.findIndex((b) => b.kind === 'primary');
        const idx = primary >= 0 ? primary : buttons.length - 1;
        e.preventDefault();
        finish(buttons[idx].value);
      }
    }

    if (buttons.length === 0) {
      const closeBtn = h('button', { class: 'btn ghost dialog-close', html: icon('x', { size: 15 }), title: '关闭', onclick: () => finish(null) });
      dialog.querySelector('.dialog-head').append(closeBtn);
    }

    backdrop.addEventListener('pointerdown', (e) => {
      if (e.target === backdrop && dismissible) finish(null);
    });
    document.addEventListener('keydown', onKey, true);
    rootEl.append(backdrop);
    active = backdrop;
    requestAnimationFrame(() => {
      const first = foot.querySelector('.btn.primary, .btn.danger, .btn');
      first?.focus();
    });
  });
}

/** 危险/确认对话框 → Promise<boolean> */
export function confirmDialog({
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = true,
  iconName = danger ? 'alert-triangle' : 'info',
  extra = '',
}) {
  return openDialog({
    title,
    iconName,
    iconKind: danger ? 'danger' : 'warn',
    body: `<p>${escapeHtml(message)}</p>${extra ? `<p>${extra}</p>` : ''}`,
    buttons: [
      { label: cancelText, value: false },
      { label: confirmText, value: true, kind: danger ? 'danger' : 'primary' },
    ],
  }).then((v) => v === true);
}

/** 信息对话框 → Promise<void> */
export function alertDialog({ title = '提示', message = '', iconName = 'info', iconKind = '', okText = '知道了' }) {
  return openDialog({
    title, iconName, iconKind,
    body: `<p>${escapeHtml(message)}</p>`,
    buttons: [{ label: okText, value: true, kind: 'primary' }],
  });
}

/** 带一个输入框的对话框 → Promise<string|null> */
export function promptDialog({ title, label = '名称', value = '', placeholder = '', maxLength = 40, confirmText = '保存' }) {
  const input = h('input', { class: 'input', value, placeholder, maxlength: String(maxLength) });
  const body = h('div', { class: 'field', style: { gap: '8px' } },
    h('label', { class: 'field-label' }, label),
    input,
  );
  return openDialog({
    title,
    iconName: 'edit',
    body,
    buttons: [
      { label: '取消', value: null },
      { label: confirmText, value: 'ok', kind: 'primary' },
    ],
  }).then((v) => {
    if (v !== 'ok') return null;
    return input.value.trim();
  });
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
