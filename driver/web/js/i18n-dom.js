/* i18n-dom.js — 页面级英文翻译层。
   中文是源语言：所有页面文案直接写在 DOM 里；切换到 English 时，
   本模块对整棵 DOM 的文本节点与常见属性做「中文短语 → 英文」替换，
   并监听后续动态插入的节点（toast / 日志 / 计数等），保证即时生效。
   字典在 i18n-en-dom.js（键 = 渲染后的中文原文，含插值的用 PATTERNS 正则）。 */
import { EN_TEXT, EN_PATTERNS } from './i18n-en-dom.js';

const CJK = /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/;
const CJK_IDEO = /[\u4e00-\u9fff]/;
/* 全角标点 → 半角（用于中英混排字符串，如 "Device：AJAZZ（USB）"） */
const PUNCT_MAP = [
  [/：/g, ': '], [/（/g, ' ('],
  [/）/g, ')'], [/、/g, ', '], [/，/g, ', '], [/。/g, '. '],
  [/；/g, '; '], [/！/g, '!'], [/？/g, '?'], [/「/g, '"'], [/」/g, '"'],
  [/『/g, '"'], [/』/g, '"'], [/～/g, '~'], [/　/g, ' '],
];
function cleanPunctuation(str) {
  let out = str;
  for (const [re, rep] of PUNCT_MAP) out = out.replace(re, rep);
  return out.replace(/ \)/g, ')').replace(/\( /g, ' (').replace(/ {2,}/g, ' ').trim();
}
const ATTRS = ['placeholder', 'title', 'aria-label'];
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE']);

let observer = null;
let writing = false;
let enabled = false;

function preserveWhitespace(original, translated) {
  const lead = original.match(/^\s*/)[0];
  const trail = original.match(/\s*$/)[0];
  return lead + translated + trail;
}

/** 将一段中文文本翻译成英文；无可翻译内容返回 null */
export function translateText(text) {
  if (!text || !CJK.test(text)) return null;
  const core = text.trim();
  if (!core) return null;

  let out = EN_TEXT[core];
  if (out !== undefined) return preserveWhitespace(text, out);

  for (const [re, rep] of EN_PATTERNS) {
    if (re.test(core)) return preserveWhitespace(text, core.replace(re, rep));
  }
  if (!CJK_IDEO.test(core)) {
    const cleaned = cleanPunctuation(core);
    if (cleaned !== core) return preserveWhitespace(text, cleaned);
  }
  return null;
}

function translateAttributeValue(value) {
  if (!value || !CJK.test(value)) return null;
  const core = value.trim();
  let out = EN_TEXT[core];
  if (out !== undefined) return value.replace(core, out);
  for (const [re, rep] of EN_PATTERNS) {
    if (re.test(core)) return value.replace(core, core.replace(re, rep));
  }
  if (!CJK_IDEO.test(core)) {
    const cleaned = cleanPunctuation(core);
    if (cleaned !== core) return value.replace(core, cleaned);
  }
  return null;
}

function shouldSkip(node) {
  const p = node.parentElement;
  return p && SKIP_TAGS.has(p.tagName);
}

function translateTextNode(node) {
  const next = translateText(node.data);
  if (next === null || next === node.data) return;
  writing = true;
  node.data = next;
  writing = false;
}

function translateElementAttrs(el) {
  for (const attr of ATTRS) {
    const value = el.getAttribute?.(attr);
    if (!value) continue;
    const next = translateAttributeValue(value);
    if (next === null || next === value) continue;
    writing = true;
    el.setAttribute(attr, next);
    writing = false;
  }
  if (el.tagName === 'META') return;
  if (el.getAttribute?.('content') && (el.getAttribute('name') === 'description')) {
    const next = translateAttributeValue(el.getAttribute('content'));
    if (next) el.setAttribute('content', next);
  }
}

/** 翻译一棵子树（幂等：已翻译过的英文文本不再变化） */
export function translateTree(root) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    if (!shouldSkip(root)) translateTextNode(root);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
  if (root.nodeType === Node.ELEMENT_NODE) {
    translateElementAttrs(root);
    if (SKIP_TAGS.has(root.tagName)) return;
  }
  if (root.nodeType === Node.ELEMENT_NODE && root.querySelectorAll) {
    for (const el of root.querySelectorAll('*')) translateElementAttrs(el);
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (!shouldSkip(node)) translateTextNode(node);
    node = walker.nextNode();
  }
}

function handleMutations(mutations) {
  if (writing) return;
  for (const m of mutations) {
    if (m.type === 'characterData') {
      if (!shouldSkip(m.target)) translateTextNode(m.target);
    } else if (m.type === 'childList') {
      for (const node of m.addedNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          if (!shouldSkip(node)) translateTextNode(node);
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          translateTree(node);
        }
      }
    } else if (m.type === 'attributes') {
      if (m.target?.getAttribute) translateElementAttrs(m.target);
    }
  }
}

/** 开启英文模式：翻译整页并监听后续 DOM 变化 */
export function enableAutoTranslate(root) {
  enabled = true;
  translateTree(root || document.body);
  if (!observer) {
    observer = new MutationObserver(handleMutations);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS,
    });
  }
}

/** 关闭英文模式（切回中文时由页面重挂载恢复中文，这里只停监听） */
export function disableAutoTranslate() {
  enabled = false;
  if (observer) { observer.disconnect(); observer = null; }
}

export function isAutoTranslateEnabled() { return enabled; }
