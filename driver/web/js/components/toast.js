/* toast.js — 右上角浮层提示 */
import { icon } from './icons.js';
import { h } from './util.js';

let root = null;
const ICONS = { success: 'check-circle', info: 'info', warn: 'alert-triangle', error: 'alert-circle' };

function ensureRoot() {
  if (!root) root = document.getElementById('toast-root');
  return root;
}

export function toast(message, { title = '', type = 'info', timeout = 3600 } = {}) {
  const host = ensureRoot();
  if (!host) return { close() {} };
  const level = ICONS[type] ? type : 'info';
  const node = h('div', { class: `toast ${level}`, role: 'status' },
    h('div', { class: 'toast-icon', html: icon(ICONS[level], { size: 15 }) }),
    h('div', { class: 'toast-body' },
      title ? h('div', { class: 'toast-title' }, title) : null,
      h('div', { class: 'toast-msg' }, message),
    ),
    h('button', { class: 'toast-close', title: '关闭', html: icon('x', { size: 14 }), onclick: close }),
  );
  let timer = null;
  function close() {
    if (!node.isConnected) return;
    clearTimeout(timer);
    node.classList.add('leaving');
    setTimeout(() => node.remove(), 220);
  }
  host.append(node);
  if (timeout > 0) timer = setTimeout(close, timeout);
  return { close };
}

export const toastSuccess = (msg, opts = {}) => toast(msg, { type: 'success', ...opts });
export const toastError = (msg, opts = {}) => toast(msg, { type: 'error', ...opts });
export const toastWarn = (msg, opts = {}) => toast(msg, { type: 'warn', ...opts });
export const toastInfo = (msg, opts = {}) => toast(msg, { type: 'info', ...opts });
