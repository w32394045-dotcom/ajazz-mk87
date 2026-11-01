/* pages/settings.js — 设置：主题（浅色/深色/跟随系统）、语言、关于、演示模式控制 */
import { icon, brandLogo } from '../icons.js';
import { h } from '../util.js';
import { badge, kvList } from '../components/widgets.js';
import { confirmDialog } from '../components/dialog.js';

const THEMES = [
  { id: 'light', label: '浅色', desc: '白色底 / 深色文字', icon: 'sun', preview: 'light-preview' },
  { id: 'dark', label: '深色', desc: '黑灰底 / 浅色文字', icon: 'moon', preview: 'dark-preview' },
  { id: 'auto', label: '跟随系统', desc: '随 prefers-color-scheme 自动切换', icon: 'auto', preview: '' },
];

const LANGS = [
  { id: 'zh', label: '简体中文', flag: '中', desc: '默认界面语言' },
  { id: 'en', label: 'English', flag: 'EN', desc: '预留翻译层（部分页面仍为中文）' },
];

export default {
  id: 'settings',
  async mount(root, ctx) {
    const { api, i18n } = ctx;
    const status = ctx.status;
    let currentTheme = ctx.getTheme();

    /* ---------------- 主题卡片 ---------------- */
    const themeCards = new Map();
    const themeGrid = h('div', { class: 'theme-cards' });
    for (const th of THEMES) {
      const card = h('button', {
        type: 'button',
        class: `theme-card${currentTheme === th.id ? ' active' : ''}`,
        onclick: () => {
          currentTheme = th.id;
          ctx.setTheme(th.id);
          themeCards.forEach((node, id) => node.classList.toggle('active', id === currentTheme));
          ctx.toast(`主题已切换为「${th.label}」`, { timeout: 1600 });
        },
      },
        h('div', { class: 'theme-preview ' + th.preview },
          h('div', { class: 'tp-side' }, h('i'), h('i'), h('i'), h('i')),
          h('div', { class: 'tp-main' }, h('i'), h('i'), h('i')),
        ),
        h('div', { class: 'tlabel' }, h('span', { html: icon(th.icon, { size: 15 }) }), h('span', {}, th.label),
          h('span', { class: 'spacer' }),
          currentTheme === th.id ? h('span', { style: { color: 'var(--accent)' }, html: icon('check-circle', { size: 15 }) }) : null,
        ),
        h('div', { class: 'tiny muted' }, th.desc),
      );
      themeCards.set(th.id, card);
      themeGrid.append(card);
    }

    /* ---------------- 语言卡片 ---------------- */
    const langCards = new Map();
    const langGrid = h('div', { class: 'lang-cards' });
    for (const lang of LANGS) {
      const card = h('div', {
        class: `lang-card${i18n.lang === lang.id ? ' active' : ''}`,
        role: 'button', tabindex: '0',
        onclick: () => {
          if (i18n.lang === lang.id) return;
          i18n.setLang(lang.id);
          ctx.toast(lang.id === 'zh' ? '界面语言：简体中文' : 'Language: English (partial translation)', { timeout: 2400 });
        },
        onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); } },
      },
        h('span', { class: 'flag' }, lang.flag),
        h('div', {},
          h('div', { style: { fontWeight: '600' } }, lang.label),
          h('div', { class: 'tiny muted' }, lang.desc),
        ),
        i18n.lang === lang.id ? h('span', { style: { marginLeft: 'auto', color: 'var(--accent)' }, html: icon('check-circle', { size: 16 }) }) : null,
      );
      langCards.set(lang.id, card);
      langGrid.append(card);
    }

    /* ---------------- 退出程序（仅原生外壳模式） ---------------- */
    const quitRow = h('div', { class: 'row mt-12', style: { display: 'none' } });
    const quitBtn = h('button', {
      class: 'btn sm danger', html: `${icon('power', { size: 14 })}<span>退出 MK87 Studio</span>`,
      onclick: quitApp,
    });
    quitRow.append(quitBtn, h('span', { class: 'tiny muted' }, '关闭本地服务与程序窗口（浏览器模式无此按钮）'));
    function updateQuitVisibility() {
      quitRow.style.display = ctx.status?.shell === true ? '' : 'none';
    }
    function showQuitOverlay() {
      document.getElementById('quit-overlay')?.remove();
      const overlay = h('div', {
        id: 'quit-overlay',
        style: {
          position: 'fixed', inset: '0', zIndex: '300', display: 'grid', placeItems: 'center',
          background: 'color-mix(in srgb, #04060b 62%, transparent)', backdropFilter: 'blur(6px)',
        },
      }, h('div', { class: 'card', style: { padding: '30px 34px', textAlign: 'center', maxWidth: '380px' } },
        h('div', { class: 'brand-mark', style: { margin: '0 auto 14px', width: '46px', height: '46px' }, html: brandLogo(26) }),
        h('div', { style: { fontSize: '16px', fontWeight: '700' } }, '程序即将退出'),
        h('div', { class: 'tiny muted mt-8' }, '正在关闭本地服务与程序窗口；服务停止后可以直接关闭此页面。'),
      ));
      document.body.append(overlay);
    }
    async function quitApp() {
      const ok = await confirmDialog({
        title: '退出 MK87 Studio',
        message: '将关闭本地服务与程序窗口，当前页面会断开连接。未保存的修改将丢失。',
        confirmText: '退出程序',
      });
      if (!ok) return;
      quitBtn.disabled = true;
      try {
        const resp = await api.post('/api/quit');
        if (resp && resp.ok) showQuitOverlay();
        else ctx.toastWarn(resp?.message || '浏览器模式请直接关闭服务进程');
      } catch (e) {
        ctx.toastError(`退出失败：${e.message || e}`);
      } finally {
        quitBtn.disabled = false;
      }
    }

    /* ---------------- 关于 ---------------- */
    const aboutCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '关于')),
      h('div', { class: 'card-body' },
        h('div', { class: 'about-hero' },
          h('div', { class: 'logo', html: brandLogo(30) }),
          h('div', {},
            h('h3', {}, 'MK87 Studio'),
            h('div', { class: 'ver' }, '跨平台键盘配置工具 · v1.0.0 · 接口契约 v1'),
            h('div', { class: 'row mt-8' },
              badge('原生 HTML/CSS/JS', 'accent'),
              badge('零构建 · 零 CDN · 离线可用', 'ok'),
              badge('浅色 / 深色双主题', 'violet'),
            ),
          ),
        ),
        h('div', { class: 'section-title', style: { marginTop: '20px' } }, h('h2', {}, '运行信息')),
        kvList([
          ['前端形态', '本地 Web UI（FastAPI 静态托管，也可用 python -m http.server）'],
          ['数据来源', ctx.isMock ? '内置 mock（未连接后端）' : '本地 Python 后端 + HID 设备'],
          ['当前连接', status?.connected ? `${status.transport === '2.4g' ? '2.4G 无线' : 'USB 有线'} · ${status.device?.product || 'MK87'}` : '未连接'],
          ['固件', status?.device?.firmware || '—'],
          ['主题与语言', 'localStorage + PUT /api/settings 双写'],
        ]),
        quitRow,
        h('div', { class: 'section-title' }, h('h2', {}, '技术栈')),
        kvList([
          ['后端', 'Python 3.10+ · FastAPI · hidapi · Pillow / numpy'],
          ['前端', '原生 ES Modules · 手写 CSS 变量主题 · 内联 SVG 图标'],
          ['设备', 'AJAZZ MK87 · VID 0x0C45 / PID 0x8047（USB）· 0xFEFE（2.4G）'],
          ['协议', 'AA/55 帧 · 0xFF68 主协议 · 0xFF67 TFT · 0xFF60 2.4G'],
        ]),
        h('div', { class: 'tiny muted mt-16', style: { lineHeight: '1.8' } },
          h('p', {}, '本项目是基于真机逆向结论实现的第三方配置工具，与 AJAZZ 官方无关。所有操作在本地完成，不会上传任何数据，也不会访问外网。'),
          h('p', {}, '已知不支持：磁轴高级键、灯效 GIF 动画、屏幕内置页切换、屏幕壁纸页、系统信息页、板载多 Profile、音乐律动 2.4G。详见「设备信息 → 能力矩阵」。'),
        ),
      ),
    );

    /* ---------------- 开机自启 ---------------- */
    const autostartBadge = badge('读取中…', '');
    const autostartSwitch = h('input', { type: 'checkbox' });
    const autostartHint = h('div', { class: 'tiny muted' }, '正在读取开机自启状态…');
    const autostartDetail = h('div', { class: 'mt-12' });
    const autostartRetry = h('button', {
      class: 'btn sm ghost', html: `${icon('refresh', { size: 13 })}<span>重试</span>`,
      onclick: () => loadAutostart(),
    });
    const autostartState = { supported: null, enabled: false, loading: true };

    function renderAutostart() {
      const st = autostartState;
      autostartSwitch.checked = !!st.enabled;
      autostartSwitch.disabled = st.loading || st.supported === false;
      autostartBadge.className = 'badge';
      if (st.loading) {
        autostartBadge.textContent = '读取中…';
      } else if (st.supported === false) {
        autostartBadge.textContent = '当前平台不支持';
        autostartBadge.classList.add('danger');
      } else if (st.supported === null) {
        autostartBadge.textContent = '读取失败';
        autostartBadge.classList.add('warn');
      } else if (st.enabled) {
        autostartBadge.textContent = '已开启';
        autostartBadge.classList.add('ok');
      } else {
        autostartBadge.textContent = '已关闭';
      }
      autostartDetail.innerHTML = '';
      if (st.supported && (st.command || st.location)) {
        autostartDetail.append(kvList([
          ['平台', st.platform || '—'],
          ['命令', st.command || '—'],
          ['启动项位置', st.location || '—'],
        ]));
      }
      autostartHint.textContent = st.supported === false
        ? '当前平台（或当前运行方式）不支持开机自启；Linux/macOS 由安装包写入用户级 autostart / LaunchAgent。'
        : st.supported === null
          ? '无法读取开机自启状态，请确认后端已实现 GET /api/autostart。'
          : '开机自启由后端写入系统启动项（Windows：注册表 Run 项；Linux：~/.config/autostart）。';
    }

    async function loadAutostart() {
      autostartState.loading = true;
      renderAutostart();
      try {
        const st = await api.get('/api/autostart');
        autostartState.loading = false;
        autostartState.supported = st?.supported !== false;
        autostartState.enabled = !!st?.enabled;
        autostartState.platform = st?.platform;
        autostartState.command = st?.command;
        autostartState.location = st?.location;
      } catch (e) {
        autostartState.loading = false;
        autostartState.supported = null;
        ctx.toastError(`读取开机自启失败：${e.message || e}`);
      }
      renderAutostart();
    }

    autostartSwitch.addEventListener('change', async () => {
      if (autostartState.supported !== true) { autostartSwitch.checked = !!autostartState.enabled; return; }
      const want = autostartSwitch.checked;
      autostartSwitch.disabled = true;
      try {
        const st = await api.put('/api/autostart', { enabled: want });
        autostartState.enabled = st?.enabled !== undefined ? !!st.enabled : want;
        autostartState.supported = st?.supported !== false;
        autostartState.command = st?.command || autostartState.command;
        autostartState.location = st?.location || autostartState.location;
        autostartState.platform = st?.platform || autostartState.platform;
        renderAutostart();
        ctx.toastSuccess(autostartState.enabled ? '已开启开机自启' : '已关闭开机自启');
      } catch (e) {
        autostartState.enabled = !want;
        renderAutostart();
        ctx.toastError(`设置开机自启失败：${e.message || e}`);
      } finally {
        autostartSwitch.disabled = autostartState.supported !== true;
      }
    });

    const autostartCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '开机自启'),
          h('div', { class: 'card-desc' }, '随系统启动 MK87 Studio（写入当前用户的启动项，无需管理员权限）')),
        h('div', { class: 'spacer' }),
        autostartBadge,
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'row between' },
          h('label', { class: 'check' }, autostartSwitch, h('span', {}, '登录系统后自动启动 MK87 Studio')),
          h('div', { class: 'row' }, autostartRetry),
        ),
        autostartHint,
        autostartDetail,
      ),
    );

    /* ---------------- 偏好与演示 ---------------- */
    const prefCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '界面设置'),
          h('div', { class: 'card-desc' }, '主题与语言会同时保存到浏览器 localStorage 和服务端 /api/settings')),
        h('div', { class: 'spacer' }),
        badge('即时生效', 'ok'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'field' }, h('div', { class: 'field-label' }, '界面主题'), themeGrid),
        h('div', { class: 'field mt-20' }, h('div', { class: 'field-label' }, '语言'), langGrid),
        h('div', { class: 'row mt-20' },
          h('button', {
            class: 'btn sm ghost', html: `${icon('refresh', { size: 14 })}<span>从服务端重新读取设置</span>`,
            onclick: async () => {
              try {
                const st = await api.get('/api/settings');
                if (st?.theme) { currentTheme = st.theme; ctx.setTheme(st.theme); themeCards.forEach((n, id) => n.classList.toggle('active', id === currentTheme)); }
                if (st?.language && st.language !== i18n.lang) i18n.setLang(st.language);
                ctx.toast('已从服务端读取设置');
              } catch (e) { ctx.toastError(e.message || String(e)); }
            },
          }),
          h('button', {
            class: 'btn sm ghost', html: `${icon('trash', { size: 14 })}<span>清除本地偏好</span>`,
            onclick: async () => {
              const ok = await confirmDialog({ title: '清除本地偏好', message: '会删除浏览器里保存的主题与语言偏好（下次打开跟随系统中/默认中文）。', confirmText: '清除' });
              if (!ok) return;
              ctx.store.remove('mk87.theme');
              ctx.store.remove('mk87.lang');
              ctx.toast('已清除本地偏好');
              ctx.reloadPage();
            },
          }),
        ),
      ),
    );

    const mockCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '演示模式（mock）'),
          h('div', { class: 'card-desc' }, '没有后端时自动启用，所有页面都能交互演示')),
        h('div', { class: 'spacer' }),
        badge(ctx.isMock ? '当前：演示数据' : '当前：真实设备', ctx.isMock ? 'violet' : 'ok'),
      ),
      h('div', { class: 'card-body' },
        h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
          h('p', {}, '演示模式会拦截 /api/* 请求并返回内置数据：状态、灯效、键位、宏、屏幕进度、音乐电平、无线通知等全部可交互；设备状态保存在浏览器 localStorage（mk87.mock.state）。'),
          h('p', {}, '进入方式：URL 加 ?mock=1，或后端 /api/status 不可用时自动启用。'),
        ),
        h('div', { class: 'row mt-12' },
          h('button', {
            class: 'btn sm', html: `${icon('plug', { size: 14 })}<span>模拟断开连接</span>`,
            disabled: !ctx.isMock, onclick: async () => { await ctx.simulateDisconnect(); ctx.toast('已模拟设备断连（观察顶部状态栏与全局提示）'); },
          }),
          h('button', {
            class: 'btn sm', html: `${icon('refresh', { size: 14 })}<span>模拟重新连接</span>`,
            disabled: !ctx.isMock, onclick: async () => { await ctx.simulateReconnect(); ctx.toast('已模拟重新连接'); },
          }),
          h('button', {
            class: 'btn sm', html: `${icon('wifi', { size: 14 })}<span>切换 USB / 2.4G</span>`,
            disabled: !ctx.isMock, onclick: async () => { await ctx.setTransport(ctx.status?.transport === '2.4g' ? 'usb' : '2.4g'); ctx.toast('已切换模拟连接方式，相关页面能力位同步变化'); },
          }),
          h('button', {
            class: 'btn sm', html: `${icon('trash', { size: 14 })}<span>重置演示数据</span>`,
            disabled: !ctx.isMock,
            onclick: async () => {
              const ok = await confirmDialog({ title: '重置演示数据', message: '会清空浏览器里保存的 mock 设备状态（灯效、键位、宏等）并刷新页面。', confirmText: '重置' });
              if (!ok) return;
              ctx.store.remove('mk87.mock.state');
              location.reload();
            },
          }),
        ),
        ctx.isMock ? h('div', { class: 'demo-box mt-16' },
          h('div', { class: 'demo-title', html: `${icon('info', { size: 15 })}<span>如何连接真实设备</span>` }),
          h('div', { class: 'tiny muted mt-8' }, '启动后端服务（python -m mk87 或 uvicorn）后访问它托管的页面地址，前端会自动检测 /api/status 并切换到真实设备模式。'),
        ) : null,
      ),
    );

    /* ---------------- 布局 ---------------- */
    root.append(prefCard);
    root.append(h('div', { class: 'grid grid-2 mt-16' }, autostartCard, mockCard));
    root.append(h('div', { class: 'mt-16' }, aboutCard));
    updateQuitVisibility();
    ctx.onStatus?.(() => updateQuitVisibility());
    loadAutostart();
  },
};
