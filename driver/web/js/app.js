/* app.js — 应用入口：路由 / 主题 / 语言 / 设备状态栏 / 页面挂载 */
import { Api } from './api.js';
import { I18n } from './i18n.js';
import { icon, brandLogo } from './icons.js';
import { toast, toastError, toastSuccess, toastWarn, toastInfo } from './components/toast.js';
import { confirmDialog, alertDialog, openDialog } from './components/dialog.js';
import { store, h, clear, fmtDateTime } from './util.js';
import { enableAutoTranslate, disableAutoTranslate } from './i18n-dom.js';

/* ---------------------------------------------------------------- 页面注册表 */
const PAGES = [
  { id: 'lighting', group: 'lighting', icon: 'sun', titleKey: 'nav.lighting', subKey: 'page.lighting.sub', loader: () => import('./pages/lighting.js') },
  { id: 'perkey', group: 'lighting', icon: 'palette', titleKey: 'nav.perkey', subKey: 'page.perkey.sub', loader: () => import('./pages/perkey.js') },
  { id: 'screen', group: 'display', icon: 'monitor', titleKey: 'nav.screen', subKey: 'page.screen.sub', loader: () => import('./pages/screen.js') },
  { id: 'music', group: 'display', icon: 'music', titleKey: 'nav.music', subKey: 'page.music.sub', loader: () => import('./pages/music.js') },
  { id: 'keymap', group: 'keys', icon: 'keyboard', titleKey: 'nav.keymap', subKey: 'page.keymap.sub', loader: () => import('./pages/keymap.js') },
  { id: 'macro', group: 'keys', icon: 'macro', titleKey: 'nav.macro', subKey: 'page.macro.sub', loader: () => import('./pages/macro.js') },
  { id: 'wireless', group: 'device', icon: 'wifi', titleKey: 'nav.wireless', subKey: 'page.wireless.sub', loader: () => import('./pages/wireless.js') },
  { id: 'keytest', group: 'device', icon: 'activity', titleKey: 'nav.keytest', subKey: 'page.keytest.sub', loader: () => import('./pages/keytest.js') },
  { id: 'device', group: 'device', icon: 'chip', titleKey: 'nav.device', subKey: 'page.device.sub', loader: () => import('./pages/device.js') },
  { id: 'backup', group: 'device', icon: 'archive', titleKey: 'nav.backup', subKey: 'page.backup.sub', loader: () => import('./pages/backup.js') },
  { id: 'settings', group: 'system', icon: 'settings', titleKey: 'nav.settings', subKey: 'page.settings.sub', loader: () => import('./pages/settings.js') },
];
const NAV_GROUPS = [
  { labelKey: 'nav.group.lighting', ids: ['lighting', 'perkey'] },
  { labelKey: 'nav.group.display', ids: ['screen', 'music'] },
  { labelKey: 'nav.group.keys', ids: ['keymap', 'macro'] },
  { labelKey: 'nav.group.device', ids: ['wireless', 'keytest', 'device', 'backup'] },
  { labelKey: 'nav.group.system', ids: ['settings'] },
];
const THEME_KEY = 'mk87.theme';
const LANG_KEY = 'mk87.lang';
const MOCK_BANNER_KEY = 'mk87.mockBannerDismissed';
const TRAY_BANNER_KEY = 'mk87.trayBannerDismissed';
// v0.1.8.6：Windows 图标在溢出区的一次性提示（与「托盘不可用」分开记，避免互相影响）
const TRAY_OVERFLOW_HINT_KEY = 'mk87.trayOverflowHintDismissed.v1';
// v0.1.8.6：GNOME 缺 AppIndicator 扩展时的一次性引导（记住已关闭；换 key 让老用户也能看到一次）
const TRAY_INSTALL_BANNER_KEY = 'mk87.trayInstallBannerDismissed.v1';
const TRAY_RELOGIN_BANNER_KEY = 'mk87.trayReloginBannerDismissed.v1';

/* ---------------------------------------------------------------- 全局状态 */
const api = new Api();
const i18n = new I18n(store.get(LANG_KEY, 'zh'));
const t = (key, vars) => i18n.t(key, vars);
const state = {
  status: null,
  wsState: 'closed',
  mode: 'detecting',
  themePref: store.get(THEME_KEY, 'auto'),
  currentId: null,
  cleanup: null,
  navigating: false,
  booted: false,
  trayDetail: null,
  trayDetailLoading: false,
};

let statusPoll = null;

const $ = (sel) => document.querySelector(sel);
const pageRoot = $('#page-root');
const navEl = $('#nav');
const statusGroup = $('#status-group');
const themeToggle = $('#theme-toggle');
const banners = $('#banners');

/* ---------------------------------------------------------------- 主题 */
const mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
function resolvedTheme() {
  if (state.themePref === 'auto') return mq?.matches ? 'dark' : 'light';
  return state.themePref === 'light' ? 'light' : 'dark';
}
function applyTheme() {
  const theme = resolvedTheme();
  document.documentElement.dataset.theme = theme;
  // 同步浏览器 UI 颜色
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) meta.setAttribute('content', theme);
  renderThemeToggle();
}
function setTheme(pref, { persist = true, sync = true } = {}) {
  state.themePref = pref === 'light' || pref === 'dark' ? pref : 'auto';
  if (persist) store.set(THEME_KEY, state.themePref);
  applyTheme();
  if (sync) syncServerSettings();
}
mq?.addEventListener?.('change', () => { if (state.themePref === 'auto') applyTheme(); });

function renderThemeToggle() {
  if (!themeToggle) return;
  const items = [
    { pref: 'light', icon: 'sun', label: t('theme.light') },
    { pref: 'dark', icon: 'moon', label: t('theme.dark') },
    { pref: 'auto', icon: 'auto', label: t('theme.auto') },
  ];
  clear(themeToggle);
  for (const it of items) {
    const btn = h('button', {
      type: 'button',
      class: state.themePref === it.pref ? 'active' : '',
      title: it.label,
      'aria-label': it.label,
      'aria-pressed': String(state.themePref === it.pref),
      html: icon(it.icon, { size: 15 }),
      onclick: () => setTheme(it.pref),
    });
    themeToggle.append(btn);
  }
}

/* ---------------------------------------------------------------- 语言 */
i18n.onChange(() => {
  store.set(LANG_KEY, i18n.lang);
  document.documentElement.lang = i18n.lang === 'en' ? 'en' : 'zh-CN';
  applyLanguageToDom();
  renderNav();
  renderThemeToggle();
  updatePageHead();
  renderBanners();
  renderStatusBar();
  renderSidebarDevice();
  syncServerSettings();
  renderRoute(true);
});

/** English 时对整页 DOM 应用翻译层；中文时停用（页面重挂载即恢复中文原文） */
function applyLanguageToDom() {
  // 页面模块会读 <html lang> 决定动态文案的语言（如音乐模式名），这里保证首屏也同步
  document.documentElement.lang = i18n.lang === 'en' ? 'en' : 'zh-CN';
  if (i18n.lang === 'en') enableAutoTranslate(document.body);
  else disableAutoTranslate();
}

/* ---------------------------------------------------------------- 设置同步 */
let syncTimer = null;
function syncServerSettings() {
  clearTimeout(syncTimer);
  syncTimer = setTimeout(async () => {
    try {
      await api.put('/api/settings', { theme: state.themePref, language: i18n.lang });
    } catch { /* 后端不可用 / 未实现时忽略 */ }
  }, 500);
}

/* ---------------------------------------------------------------- 导航 */
function renderNav() {
  clear(navEl);
  for (const group of NAV_GROUPS) {
    const wrap = h('div', { class: 'nav-group' }, h('div', { class: 'nav-label' }, t(group.labelKey)));
    for (const id of group.ids) {
      const page = PAGES.find((p) => p.id === id);
      if (!page) continue;
      const btn = h('button', {
        type: 'button',
        class: `nav-item${state.currentId === id ? ' active' : ''}`,
        'data-page': id,
        title: t(page.titleKey),
        onclick: () => navigate(id),
      },
        h('span', { html: icon(page.icon, { size: 18 }) }),
        h('span', { class: 'nav-text' }, t(page.titleKey)),
      );
      wrap.append(btn);
    }
    navEl.append(wrap);
  }
}

function updatePageHead() {
  const page = PAGES.find((p) => p.id === (state.currentId || routeId()));
  if (!page) return;
  $('#page-title').textContent = t(page.titleKey);
  $('#page-sub').textContent = t(page.subKey);
  document.title = `${t(page.titleKey)} · MK87 Studio`;
}

function navigate(id) {
  if (!PAGES.some((p) => p.id === id)) id = 'lighting';
  if (location.hash !== `#/${id}`) location.hash = `#/${id}`;
  else renderRoute(true);
}

function routeId() {
  const raw = (location.hash || '').replace(/^#\/?/, '').split(/[?&]/)[0];
  return PAGES.some((p) => p.id === raw) ? raw : 'lighting';
}

window.addEventListener('hashchange', () => renderRoute());

async function renderRoute(force = false) {
  const id = routeId();
  if (state.navigating) return;
  if (!force && state.currentId === id && state.booted) return;
  state.navigating = true;
  const page = PAGES.find((p) => p.id === id) || PAGES[0];

  // 卸载旧页面
  try { state.cleanup?.(); } catch (e) { console.error('[page cleanup]', e); }
  state.cleanup = null;
  state.currentId = id;
  renderNav();
  updatePageHead();

  clear(pageRoot);
  const container = h('div', { class: 'page' });
  pageRoot.append(container);

  try {
    const mod = await page.loader();
    const pageObj = mod.default || mod.page || mod;
    if (!pageObj || typeof pageObj.mount !== 'function') throw new Error(`页面模块 ${id} 缺少 mount()`);
    const cleanup = await pageObj.mount(container, ctx);
    state.cleanup = typeof cleanup === 'function'
      ? cleanup
      : (typeof pageObj.unmount === 'function' ? () => pageObj.unmount() : null);
    state.booted = true;
    if (i18n.lang === 'en') enableAutoTranslate(document.body);
  } catch (e) {
    console.error('[page]', id, e);
    clear(container);
    container.append(h('div', { class: 'card', style: { padding: '28px' } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' } },
        h('span', { html: icon('alert-triangle', { size: 20 }), style: { color: 'var(--danger)' } }),
        h('strong', {}, `页面加载失败：${page.id}`),
      ),
      h('pre', { class: 'code-block' }, String(e?.stack || e)),
      h('div', { class: 'row mt-12' },
        h('button', { class: 'btn primary', onclick: () => renderRoute(true) }, '重试'),
      ),
    ));
  } finally {
    state.navigating = false;
    pageRoot.scrollTop = 0;
    $('#page-root').scrollTop = 0;
  }
}

/* ---------------------------------------------------------------- 设备状态 */
function setStatus(status) {
  if (!status) return;
  state.status = status;
  renderStatusBar();
  renderSidebarDevice();
  renderBanners();
  refreshTrayDetail();
}

/** 仅原生外壳模式 + 托盘不可用时，读一次完整托盘环境（GNOME 扩展一键安装引导用）。 */
async function refreshTrayDetail() {
  if (state.trayDetailLoading || api.mode !== 'live') return;
  const st = state.status;
  if (!st || st.shell !== true) return;
  if (st.tray?.available === true) {
    state.trayDetail = null;
    return;
  }
  if (state.trayDetail) return; // 轮询/状态事件频繁触发，探测结果只在首次加载
  state.trayDetailLoading = true;
  try {
    state.trayDetail = await api.get('/api/tray/status');
  } catch (e) {
    console.warn('[tray] 读取托盘环境失败', e?.message || e);
    state.trayDetail = null;
  } finally {
    state.trayDetailLoading = false;
    renderBanners();
  }
}

function chip({ iconName, html, cls = '', title = '', onclick }) {
  const node = h('div', {
    class: `chip ${cls}`.trim(),
    title,
    role: onclick ? 'button' : null,
    tabindex: onclick ? '0' : null,
    onclick,
    onkeydown: onclick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onclick(e); } } : null,
  });
  if (iconName) node.insertAdjacentHTML('beforeend', icon(iconName, { size: 15 }));
  if (html) node.insertAdjacentHTML('beforeend', html);
  return node;
}

function renderStatusBar() {
  if (!statusGroup) return;
  clear(statusGroup);
  const st = state.status;

  if (state.mode === 'mock') {
    statusGroup.append(chip({
      cls: 'mock',
      title: t('mock.title'),
      html: `<span class="chip-dot" style="background:var(--violet);box-shadow:none"></span><span>${t('status.mock')}</span>`,
      onclick: () => navigate('settings'),
    }));
  }

  const online = !!st?.connected;
  const transport = st?.transport || 'none';
  const transportLabel = transport === 'usb' ? 'USB' : transport === '2.4g' ? '2.4G' : t('status.transport.none');
  statusGroup.append(chip({
    cls: online ? 'online clickable' : 'offline clickable',
    title: online ? `${t('status.device')}：${st.device?.product || 'MK87'}（${transportLabel}）` : t('banner.disconnected'),
    html: `<span class="chip-dot"></span><span>${online ? transportLabel : t('status.disconnected')}</span>`,
    onclick: () => navigate('device'),
  }));

  if (online && st?.battery && typeof st.battery.percent === 'number') {
    statusGroup.append(chip({
      cls: 'battery',
      iconName: 'battery',
      title: `${t('status.battery')} ${st.battery.percent}%${st.battery.charging ? ' · ' + t('status.charging') : ''}`,
      html: `<span>${st.battery.percent}%</span>${st.battery.charging ? `<span style="color:var(--ok);display:inline-flex">${icon('zap', { size: 13 })}</span>` : ''}`,
    }));
  }

  if (online && st?.device?.firmware) {
    statusGroup.append(chip({
      iconName: 'chip',
      title: t('status.firmware'),
      html: `<span class="muted tiny" style="margin-right:2px">FW</span><strong>${st.device.firmware}</strong>`,
    }));
  }

  const reconnect = h('button', {
    class: 'btn sm icon',
    title: t('status.reconnect'),
    'aria-label': t('status.reconnect'),
    html: icon('refresh-cw', { size: 15 }),
    onclick: scanDevice,
  });
  statusGroup.append(reconnect);
}

function renderSidebarDevice() {
  const st = state.status;
  const mini = $('#device-mini');
  const name = $('#mini-name');
  const meta = $('#mini-meta');
  const hint = $('#mini-hint');
  if (!mini) return;
  const online = !!st?.connected;
  mini.classList.toggle('online', online);
  mini.classList.toggle('offline', !!st && !online);
  if (online) {
    name.textContent = st.device?.product || 'AJAZZ KEYBOARD';
    const tr = st.transport === '2.4g' ? '2.4G 无线' : 'USB 有线';
    const bat = st.battery?.percent !== undefined ? ` · ${st.battery.percent}%${st.battery.charging ? ' ⚡' : ''}` : '';
    meta.textContent = `${tr}${bat}`;
  } else if (st) {
    name.textContent = t('status.disconnected');
    meta.textContent = t('status.reconnect');
  }
  if (hint) {
    hint.textContent = state.mode === 'mock'
      ? `${t('common.demo')} · 数据仅保存在浏览器`
      : t('app.offline');
  }
}

function renderBanners() {
  if (!banners) return;
  clear(banners);
  const st = state.status;
  const online = !!st?.connected;

  if (st && !online) {
    banners.append(bannerEl({
      kind: 'danger', iconName: 'plug',
      text: t('banner.disconnected'),
      action: { label: t('status.reconnect'), kind: 'primary', onClick: scanDevice },
    }));
  } else if (state.wsState === 'closed' && state.mode === 'live' && st?.connected) {
    banners.append(bannerEl({ kind: 'warn', iconName: 'refresh', text: t('banner.reconnecting') }));
  }

  // 冲突提示：优先结构化 conflictItems（后端已按语言提供 zh/en），旧版回退 conflicts 字符串数组
  const conflictItems = Array.isArray(st?.conflictItems) ? st.conflictItems : null;
  if (conflictItems && conflictItems.length) {
    for (const item of conflictItems) {
      const msg = i18n.lang === 'en'
        ? (item?.en || item?.zh || item?.code || '')
        : (item?.zh || item?.en || item?.code || '');
      if (msg) banners.append(bannerEl({ kind: 'warn', iconName: 'alert-triangle', text: msg }));
    }
  } else if (st?.conflicts?.length) {
    for (const msg of st.conflicts) {
      banners.append(bannerEl({ kind: 'warn', iconName: 'alert-triangle', text: t('banner.conflict', { msg }) }));
    }
  }

  // 托盘不可用（v0.1.8）：没有托盘宿主时关闭窗口会直接退出程序，必须让用户知道。
  // v0.1.8.6：GNOME 缺 AppIndicator 扩展时给一次性的「去设置一键安装」引导（可关闭且记住，
  // 换用独立 store key 让以前关过旧横幅的用户也能看到一次）。
  const trayStatus = st?.tray || null;
  const trayDetail = state.trayDetail;
  const trayCode = trayDetail?.advice?.code || '';
  const isGnome = trayCode.startsWith('gnome-') || trayDetail?.gnome?.detected === true;
  // GNOME 专用引导由上面的 banner 负责：即使这次已被用户关闭，也不要再降级成通用「托盘不可用」横幅打扰
  const gnomeTrayGuidance = !!trayDetail && trayCode.startsWith('gnome-');
  let trayBannerShown = false;
  if (trayDetail && trayDetail.shellMode !== false && trayStatus?.available !== true) {
    if ((trayCode === 'gnome-missing-extension' || trayCode === 'gnome-extension-disabled')
        && !store.get(TRAY_INSTALL_BANNER_KEY, false)) {
      const missing = trayCode === 'gnome-missing-extension';
      const textZh = missing
        ? 'GNOME 默认不显示托盘图标：还差一个 AppIndicator 扩展。到「设置 → 系统托盘」点一次「一键安装」（只需输入一次管理员密码）即可，装完注销重新登录。'
        : 'AppIndicator 扩展已安装但还没启用。到「设置 → 系统托盘」点「启用扩展」（无需管理员密码），再注销重新登录。';
      const textEn = missing
        ? 'GNOME does not show tray icons by default: the AppIndicator extension is missing. Open Settings → System tray and click "Install" once (one admin password); log out and back in afterwards.'
        : 'The AppIndicator extension is installed but not enabled yet. Open Settings → System tray and click "Enable extension" (no admin password), then log out and back in.';
      banners.append(bannerEl({
        kind: 'warn', iconName: 'alert-triangle',
        text: i18n.lang === 'en' ? textEn : textZh,
        dismissKey: TRAY_INSTALL_BANNER_KEY,
        action: { label: t('nav.settings'), kind: 'primary', onClick: () => navigate('settings') },
      }));
      trayBannerShown = true;
    } else if (trayCode === 'gnome-needs-relogin' && !store.get(TRAY_RELOGIN_BANNER_KEY, false)) {
      const textZh = 'AppIndicator 扩展已安装并启用。注销重新登录（Wayland）或按 Alt+F2 → r（X11）后托盘图标就会出现。';
      const textEn = 'The AppIndicator extension is installed and enabled. Log out and back in (Wayland) or press Alt+F2 → r (X11) and the tray icon will appear.';
      banners.append(bannerEl({
        kind: 'info', iconName: 'info',
        text: i18n.lang === 'en' ? textEn : textZh,
        dismissKey: TRAY_RELOGIN_BANNER_KEY,
        action: { label: t('nav.settings'), kind: '', onClick: () => navigate('settings') },
      }));
      trayBannerShown = true;
    }
  }
  if (!trayBannerShown && !gnomeTrayGuidance && trayStatus && trayStatus.available === false
      && !store.get(TRAY_BANNER_KEY, false)) {
    const windowsTray = /^windows-/.test(trayCode) || trayDetail?.platform === 'windows';
    const trayMsg = windowsTray
      ? (i18n.lang === 'en'
        ? 'The Windows tray icon is temporarily unavailable; the app keeps trying to restore it in the background. Closing the window only minimizes it to the taskbar instead of hiding it. See Settings → System tray for details.'
        : 'Windows 托盘图标暂时不可用，程序正在后台自动恢复。这期间关闭窗口只会最小化到任务栏（不会隐身）。详情见「设置 → 系统托盘」。')
      : (isGnome && trayDetail
        ? (i18n.lang === 'en'
          ? 'System tray unavailable: closing the window will quit the app. Install the AppIndicator extension in Settings → System tray (one admin password).'
          : '系统托盘不可用：关闭窗口将直接退出程序。请到「设置 → 系统托盘」一键安装 AppIndicator 扩展（只需一次管理员密码）。')
        : (i18n.lang === 'en'
          ? 'System tray unavailable: closing the window will quit the app. See Settings → System tray for details.'
          : '系统托盘不可用：关闭窗口将直接退出程序。详情见「设置 → 系统托盘」。'));
    banners.append(bannerEl({
      kind: 'warn', iconName: 'alert-triangle',
      text: trayMsg,
      dismissKey: TRAY_BANNER_KEY,
      action: { label: t('nav.settings'), kind: 'primary', onClick: () => navigate('settings') },
    }));
  }

  // v0.1.8.6：Windows 托盘图标已注册但被收进「显示隐藏的图标」溢出区时，给一次性提示
  //（这是「托盘消失」最常见的用户感知：其实只是图标进了 ^ 里）。
  if (!trayBannerShown && trayStatus?.available === true && trayStatus?.iconState === 'hidden'
      && !store.get(TRAY_OVERFLOW_HINT_KEY, false)) {
    banners.append(bannerEl({
      kind: 'info', iconName: 'info',
      text: i18n.lang === 'en'
        ? 'The MK87 Studio tray icon is in the taskbar overflow (“Show hidden icons”, the ^ button near the clock). Click ^ and drag the icon onto the taskbar to keep it visible.'
        : 'MK87 Studio 的托盘图标在任务栏「显示隐藏的图标」（时钟旁的 ^）溢出区里。点开 ^ 把图标拖到任务栏即可常驻显示。',
      dismissKey: TRAY_OVERFLOW_HINT_KEY,
    }));
  }

  if (state.mode === 'mock' && !store.get(MOCK_BANNER_KEY, false)) {
    banners.append(bannerEl({
      kind: 'info', iconName: 'info',
      text: `${t('common.demo')}：${t('mock.desc')}`,
      dismissKey: MOCK_BANNER_KEY,
      action: { label: t('nav.settings'), kind: '', onClick: () => navigate('settings') },
    }));
  }
}

function bannerEl({ kind = 'warn', iconName = 'info', text, action = null, dismissKey = null }) {
  const node = h('div', { class: `banner${kind === 'danger' ? ' danger' : ''}${kind === 'info' ? '' : ''}` });
  node.append(h('div', { class: 'banner-icon', html: icon(iconName, { size: 17 }) }));
  node.append(h('div', { style: { minWidth: 0 } }, text));
  node.append(h('div', { class: 'spacer' }));
  if (action) node.append(h('button', { class: `btn sm ${action.kind === 'primary' ? 'primary' : ''}`, onclick: action.onClick }, action.label));
  if (dismissKey) {
    node.append(h('button', {
      class: 'btn sm icon ghost', title: t('common.close'),
      html: icon('x', { size: 14 }),
      onclick: () => { store.set(dismissKey, true); node.remove(); },
    }));
  }
  return node;
}

async function scanDevice() {
  const btn = statusGroup.querySelector('button.icon');
  btn?.setAttribute('disabled', 'disabled');
  try {
    const st = await api.post('/api/device/scan');
    setStatus(st || await api.get('/api/status'));
    toastSuccess(state.mode === 'mock' ? '已重新连接（mock 演示）' : '设备已重新连接');
  } catch (e) {
    toastError(`连接失败：${e.message || e}`);
    renderBanners();
  } finally {
    btn?.removeAttribute('disabled');
  }
}

/* ---------------------------------------------------------------- 页面上下文 */
const ctx = {
  api,
  i18n,
  t,
  store,
  get status() { return state.status; },
  get isMock() { return state.mode === 'mock'; },
  get mockServer() { return api.mock; },
  go: navigate,
  toast,
  toastSuccess,
  toastError,
  toastWarn,
  toastInfo,
  openDialog,
  confirmDialog,
  alertDialog,
  onStatus(fn) {
    const off = api.on('ws:status', fn);
    if (state.status) fn(state.status);
    return off;
  },
  onEvent(type, fn) { return api.on(`ws:${type}`, fn); },
  async refreshStatus() {
    try {
      const st = await api.get('/api/status');
      setStatus(st);
      return st;
    } catch (e) {
      console.warn('[api] refreshStatus 失败', e);
      return state.status;
    }
  },
  setTheme,
  getTheme: () => state.themePref,
  reloadPage: () => renderRoute(true),
  async simulateDisconnect() {
    if (api.mock) await api.mock.simulateDisconnect();
  },
  async simulateReconnect() {
    if (api.mock) await api.mock.simulateReconnect();
  },
  async setTransport(tr) {
    if (api.mock) await api.mock.setTransport(tr);
  },
};

/* ---------------------------------------------------------------- 全局 WS 事件 */
api.on('mode', (mode) => {
  state.mode = mode;
  renderStatusBar();
  renderSidebarDevice();
  renderBanners();
});
api.on('ws:state', (s) => {
  state.wsState = s;
  renderBanners();
});
api.on('ws:status', (st) => setStatus(st));
api.on('ws:battery', (b) => {
  if (state.status) {
    state.status.battery = { ...(state.status.battery || {}), ...b };
    renderStatusBar();
  }
});
api.on('ws:toast', (data) => {
  if (!data?.message) return;
  toast(data.message, { type: data.level === 'error' ? 'error' : data.level === 'warn' ? 'warn' : 'info' });
});

/* ---------------------------------------------------------------- 启动 */
function updateClockInFooter() { /* 预留：侧边栏可显示时钟 */ }

async function boot() {
  // 品牌图标
  $('#brand-mark').innerHTML = brandLogo(22);
  const bootMark = $('#boot-mark');
  if (bootMark) bootMark.innerHTML = brandLogo(26);
  applyTheme();
  renderNav();
  updatePageHead();
  renderThemeToggle();

  let status = null;
  try {
    status = await api.init();
  } catch (e) {
    console.error('[boot] api.init 失败', e);
  }
  state.mode = api.mode;

  // 服务端设置（首次运行时采纳）
  try {
    const serverSettings = await api.get('/api/settings');
    if (serverSettings) {
      if (!store.get(THEME_KEY, null) && serverSettings.theme) setTheme(serverSettings.theme, { persist: true, sync: false });
      if (!store.get(LANG_KEY, null) && serverSettings.language && serverSettings.language !== i18n.lang) {
        store.set(LANG_KEY, serverSettings.language);
        i18n.setLang(serverSettings.language);
      }
    }
  } catch { /* mock 或无后端时忽略 */ }
  // 把本地设置推给服务端，保持两端一致
  syncServerSettings();

  setStatus(status || state.status);
  api.connect();
  state.wsState = api.wsState;

  // 实时模式：低频轮询兜底（WS 为主）
  if (api.mode === 'live') {
    statusPoll = setInterval(async () => {
      if (document.hidden) return;
      try { setStatus(await api.get('/api/status')); } catch { /* WS 会处理 */ }
    }, 10000);
  }

  // 初始路由
  if (!location.hash) history.replaceState(null, '', `#/${routeId()}`);
  applyLanguageToDom();
  await renderRoute(true);
  document.getElementById('boot-screen')?.remove();
}

boot().catch((e) => {
  console.error('[boot] 致命错误', e);
  const root = $('#page-root');
  if (root) root.innerHTML = `<div class="card" style="padding:28px;margin:auto"><strong>启动失败</strong><p class="muted small mt-8">${String(e?.message || e)}</p></div>`;
});

window.addEventListener('beforeunload', () => {
  clearInterval(statusPoll);
  try { state.cleanup?.(); } catch { /* ignore */ }
  api.mock?.dispose?.();
});
