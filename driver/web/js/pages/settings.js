/* pages/settings.js — 设置：主题（浅色/深色/跟随系统）、语言、关于、演示模式控制 */
import { icon, brandLogo } from '../icons.js';
import { h, copyText } from '../util.js';
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

    /* ---------------- 系统托盘（v0.1.8.6：GNOME 扩展一键安装 + 置顶醒目提示） ---------------- */
    const TXT = {
      title: ['系统托盘', 'System tray'],
      desc: ['托盘图标、右键菜单与 GNOME AppIndicator 扩展（Linux）。一键安装只需要一次管理员密码',
        'Tray icon, right-click menu and the GNOME AppIndicator extension (Linux). The one-click install asks for an admin password once'],
      backend: ['托盘后端', 'Tray backend'],
      host: ['托盘宿主', 'Tray host'],
      desktop: ['桌面环境', 'Desktop'],
      extension: ['GNOME 扩展', 'GNOME extension'],
      system: ['系统', 'System'],
      distroFamily: ['发行版', 'Distro'],
      elevation: ['提权方式', 'Privilege'],
      ok: ['正常', 'OK'],
      needsWork: ['需要处理', 'Needs attention'],
      browserMode: ['浏览器模式', 'Browser mode'],
      reading: ['读取中…', 'Reading…'],
      readFailed: ['读取失败', 'Read failed'],
      unknownHost: ['检测中 / 未知', 'Detecting / unknown'],
      available: ['可用', 'Available'],
      unavailable: ['不可用', 'Unavailable'],
      backendQt: ['Qt QSystemTrayIcon（右键菜单可用）', 'Qt QSystemTrayIcon (right-click menu works)'],
      backendPystray: ['pystray（Linux 下无右键菜单）', 'pystray (no right-click menu on Linux)'],
      extNoNeedWindows: ['不需要（Windows 通知区域）', 'Not needed (Windows notification area)'],
      extNotApplicable: ['不适用（当前桌面不是 GNOME）', 'Not applicable (desktop is not GNOME)'],
      extInstalledEnabled: ['已安装并启用', 'Installed and enabled'],
      extInstalledDisabled: ['已安装，未启用', 'Installed, not enabled'],
      extMissing: ['未安装', 'Not installed'],
      install: ['一键安装 AppIndicator 扩展（一次管理员密码）', 'Install AppIndicator extension (one admin password)'],
      enable: ['启用扩展（无需管理员密码）', 'Enable extension (no admin password)'],
      copyCommands: ['复制安装命令', 'Copy install commands'],
      showCommands: ['查看/复制安装命令', 'Show / copy install commands'],
      refresh: ['重新检测', 'Re-check'],
      retry: ['重试', 'Retry'],
      installTitle: ['安装 GNOME 托盘扩展', 'Install the GNOME tray extension'],
      installMessage: [
        '将通过系统包管理器安装 gnome-shell-extension-appindicator，需要一次管理员密码（pkexec 图形密码框）。'
        + '安装完成后需要注销重新登录（Wayland）或按 Alt+F2 → r（X11）才能显示托盘图标。',
        'The system package manager will install gnome-shell-extension-appindicator; this asks for an admin '
        + 'password once (pkexec prompt). After installing, log out and back in (Wayland) or press Alt+F2 → r (X11) '
        + 'for the tray icon to appear.',
      ],
      installConfirm: ['开始安装', 'Install'],
      installing: ['正在安装…如弹出管理员密码窗口，请输入当前登录用户的密码',
        'Installing… if a password prompt appears, enter the password of your logged-in user'],
      installingProgress: ['正在等待管理员密码并安装扩展，可能需要几分钟，请不要关闭窗口…',
        'Waiting for the admin password and installing the extension; this can take a few minutes, please keep this window open…'],
      enabling: ['正在启用扩展…', 'Enabling the extension…'],
      enablingProgress: ['写入 GNOME 扩展启用列表，几秒钟就好。',
        'Adding the extension to the GNOME enabled list; this only takes a moment.'],
      installFailed: ['安装失败：', 'Install failed: '],
      enableFailed: ['启用失败：', 'Enable failed: '],
      copied: ['安装命令已复制到剪贴板', 'Install commands copied to clipboard'],
      copyFailed: ['复制失败，请手动选择命令文本', 'Copy failed; please select the command text manually'],
      badResult: ['操作未成功', 'Operation failed'],
      attentionMissingTitle: ['GNOME 默认不显示托盘图标，还差一个扩展',
        'GNOME does not show tray icons yet — one extension is missing'],
      attentionDisabledTitle: ['托盘扩展已安装，但还没有启用',
        'The tray extension is installed but not enabled'],
      attentionReloginTitle: ['扩展已就绪，注销重新登录后托盘才会出现',
        'Extension ready — log out and back in to show the tray icon'],
      attentionMissingBody: [
        '点下面的按钮即可自动安装（用发行版的包管理器），全程只需要输入一次管理员密码，装完自动启用。',
        'Click the button below to install it automatically with your distro package manager. It needs one admin password and enables the extension afterwards.',
      ],
      attentionDisabledBody: [
        '不需要重新安装，点「启用扩展」即可（不需要管理员密码），之后注销重新登录。',
        'No reinstall needed: click "Enable extension" (no admin password), then log out and back in.',
      ],
      attentionReloginBody: [
        'Wayland 下请注销并重新登录；X11 下按 Alt+F2 → 输入 r → 回车重启 GNOME Shell。',
        'On Wayland, log out and back in; on X11 press Alt+F2, type r and press Enter to restart GNOME Shell.',
      ],
      attentionPasswordHint: ['点击安装后系统会弹出密码框：输入当前登录用户的密码（只需要一次）',
        'After clicking install, a password prompt appears: enter the password of your logged-in user (only once)'],
      attentionEnableHint: ['启用扩展不需要管理员密码；启用后注销重新登录（Wayland）或按 Alt+F2 → r（X11）即可。',
        'Enabling the extension needs no admin password; afterwards log out and back in (Wayland) or press Alt+F2 → r (X11).'],
      attentionManualHint: ['这个系统里没有可用的图形提权方式（pkexec），无法弹出密码框。请把下面的命令复制到终端执行，或用发行版「软件」应用安装 gnome-shell-extension-appindicator。',
        'No graphical elevation method (pkexec) is available, so no password prompt can be shown. Copy the commands below into a terminal, or install gnome-shell-extension-appindicator from your distro software center.'],
      attentionBrowserHint: [
        '当前是浏览器调试模式，无法弹出提权窗口。请用桌面版（.deb / .rpm）打开设置页一键安装，或复制命令到终端执行。',
        'This is browser debug mode, so no admin prompt can be shown. Open Settings in the desktop app (.deb / .rpm) for one-click install, or copy the commands into a terminal.',
      ],
      nextTitle: ['下一步', 'Next step'],
      installSuccess: ['AppIndicator 扩展已安装', 'AppIndicator extension installed'],
      enableSuccess: ['AppIndicator 扩展已启用', 'AppIndicator extension enabled'],
      alreadyInstalled: ['AppIndicator 扩展已安装并启用，无需重复安装',
        'The AppIndicator extension is already installed and enabled'],
      reloginWayland: ['请注销并重新登录（或重启系统）后，托盘图标就会出现。',
        'Log out and back in (or reboot) and the tray icon will appear.'],
      reloginX11: ['按 Alt+F2 → 输入 r → 回车，重启 GNOME Shell 后托盘图标就会出现。',
        'Press Alt+F2, type r and press Enter to restart GNOME Shell; the tray icon will then appear.'],
      reloginReboot: ['请重启系统后扩展才会生效。', 'Please reboot the system for the extension to take effect.'],
      failureTitle: ['没有安装成功', 'Install did not complete'],
      failureHint: ['可以点「重试」；如果仍然失败，把下面的命令复制到终端执行，就能看到完整报错。',
        'You can retry; if it still fails, copy the commands below into a terminal to see the full error.'],
      showOutput: ['查看详细输出', 'Show details'],
      hideOutput: ['收起详细输出', 'Hide details'],
      elevationPkexec: ['pkexec（图形密码框）', 'pkexec (graphical prompt)'],
      elevationSudo: ['sudo（终端密码）', 'sudo (terminal password)'],
      elevationManual: ['需要在终端里手动执行', 'Run the commands in a terminal'],
      elevationNotNeeded: ['不需要（已安装或无需安装）', 'Not needed'],
      commandsTitle: ['可复制的手动命令', 'Manual commands (copyable)'],
    };
    const tx = (pair) => (i18n.lang === 'en' ? pair[1] : pair[0]);

    const trayBadge = badge(tx(TXT.reading), '');
    const trayAlert = h('div', { class: 'hidden' });
    const trayProgress = h('div', { class: 'hidden' });
    const trayFeedback = h('div', { class: 'hidden' });
    const trayDetail = h('div', { class: 'mt-12' });
    const trayAdvice = h('div', { class: 'tiny muted mt-12', style: { lineHeight: '1.8' } });
    const trayActions = h('div', { class: 'row mt-12', style: { gap: '8px', flexWrap: 'wrap' } });
    const trayCommands = h('pre', {
      class: 'code-block tiny mono',
      style: {
        display: 'none', marginTop: '10px', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        maxHeight: '220px', overflow: 'auto', lineHeight: '1.7',
      },
    });
    const trayState = {
      loading: true, data: null, busy: false, busyKind: '',
      lastResult: null, lastAction: '', lastError: '', showOutput: false,
    };
    const TRAY_ATTENTION_CODES = ['gnome-missing-extension', 'gnome-extension-disabled', 'gnome-needs-relogin'];

    function trayAdviceCode(data) { return data?.advice?.code || ''; }
    function trayNeedsAttention(data) {
      if (!data || data.platform !== 'linux') return false;
      return TRAY_ATTENTION_CODES.includes(trayAdviceCode(data));
    }
    function trayAction(data) { return data?.install?.action || 'none'; }
    function trayBrowserMode(data) { return data?.shellMode === false; }
    function trayLocalized(obj) {
      if (!obj) return '';
      return i18n.lang === 'en' ? (obj.en || obj.zh || '') : (obj.zh || obj.en || '');
    }
    function trayCommandText(data) {
      const parts = [];
      const command = data?.install?.commandText;
      if (command) parts.push(`$ ${command}`);
      const cmds = data?.install?.manualCommands || [];
      if (cmds.length) parts.push(cmds.join('\n'));
      return parts.join('\n\n');
    }
    function trayHasCommands(data) { return !!trayCommandText(data); }
    function trayBadgeState(data) {
      if (!data) return [tx(TXT.readFailed), 'warn'];
      const code = data?.advice?.code;
      if (code === 'ok' || code === 'windows-ok') return [tx(TXT.ok), 'ok'];
      if (code === 'browser') return [tx(TXT.browserMode), 'violet'];
      return [tx(TXT.needsWork), 'danger'];
    }
    function trayBackendLabel(data) {
      const backend = data?.tray?.backend;
      if (!backend) return '—';
      if (backend === 'qt') return tx(TXT.backendQt);
      if (backend === 'pystray') return tx(TXT.backendPystray);
      return String(backend);
    }
    function trayHostLabel(data) {
      const v = data?.tray?.available;
      return v === true ? tx(TXT.available) : v === false ? tx(TXT.unavailable) : tx(TXT.unknownHost);
    }
    function trayExtLabel(data) {
      if (data?.platform === 'windows') return tx(TXT.extNoNeedWindows);
      if (!data?.gnome?.detected) return tx(TXT.extNotApplicable);
      const ext = data?.extension || {};
      if (ext.installed && ext.enabled) return tx(TXT.extInstalledEnabled);
      if (ext.installed) return tx(TXT.extInstalledDisabled);
      return tx(TXT.extMissing);
    }
    function trayElevationLabel(data) {
      const install = data?.install || {};
      const tool = install.elevation?.tool;
      if (tool === 'pkexec') return tx(TXT.elevationPkexec);
      if (tool === 'sudo') return tx(TXT.elevationSudo);
      const reason = install.reason;
      if (reason === 'already-enabled' || reason === 'not-gnome' || reason === 'unsupported-platform') {
        return tx(TXT.elevationNotNeeded);
      }
      return tx(TXT.elevationManual);
    }
    function trayAdviceText(data) {
      const advice = data?.advice;
      if (!advice) return '';
      return i18n.lang === 'en' ? (advice.en || advice.zh || '') : (advice.zh || advice.en || '');
    }
    function trayReloadText(res) {
      if (!res) return '';
      if (res.reloadHint) return trayLocalized(res.reloadHint);
      if (res.rebootRequired) return tx(TXT.reloginReboot);
      const sessionType = String(res.sessionType || trayState.data?.desktop?.sessionType || '').toLowerCase();
      return sessionType === 'wayland' ? tx(TXT.reloginWayland) : tx(TXT.reloginX11);
    }

    async function copyTrayCommands() {
      const ok = await copyText(trayCommandText(trayState.data) || '');
      if (ok) ctx.toast(tx(TXT.copied), { timeout: 2200 });
      else ctx.toastWarn(tx(TXT.copyFailed));
    }

    function applyTrayAttention(on) {
      trayCard.style.borderColor = on
        ? 'color-mix(in srgb, var(--warn) 55%, var(--border))' : '';
      trayCard.style.boxShadow = on
        ? '0 0 0 1px color-mix(in srgb, var(--warn) 22%, transparent), 0 18px 44px -26px color-mix(in srgb, var(--warn) 70%, transparent)'
        : '';
    }

    function renderTrayAlert(data) {
      trayAlert.innerHTML = '';
      if (trayState.loading || !trayNeedsAttention(data)) {
        trayAlert.classList.add('hidden');
        return;
      }
      const code = trayAdviceCode(data);
      const browser = trayBrowserMode(data);
      const canAutoInstall = !!data?.install?.canAutoInstall;
      const canEnable = !!data?.install?.canEnable;
      let title = tx(TXT.attentionMissingTitle);
      let body = tx(TXT.attentionMissingBody);
      let hint = tx(TXT.attentionPasswordHint);
      if (code === 'gnome-extension-disabled') {
        title = tx(TXT.attentionDisabledTitle);
        body = tx(TXT.attentionDisabledBody);
        hint = tx(TXT.attentionEnableHint);
      } else if (code === 'gnome-needs-relogin') {
        title = tx(TXT.attentionReloginTitle);
        body = tx(TXT.attentionReloginBody);
        hint = '';
      }
      if (code !== 'gnome-needs-relogin') {
        if (browser) hint = tx(TXT.attentionBrowserHint);
        else if (!canAutoInstall && !canEnable) hint = tx(TXT.attentionManualHint);
      }

      const buttons = [];
      if (!browser && data?.install?.canAutoInstall) {
        buttons.push(h('button', {
          class: 'btn primary', disabled: trayState.busy,
          html: `${icon('download', { size: 16 })}<span>${tx(TXT.install)}</span>`,
          onclick: installTrayExtension,
        }));
      } else if (!browser && data?.install?.canEnable) {
        buttons.push(h('button', {
          class: 'btn primary', disabled: trayState.busy,
          html: `${icon('power', { size: 16 })}<span>${tx(TXT.enable)}</span>`,
          onclick: enableTrayExtension,
        }));
      }
      if (code === 'gnome-needs-relogin') {
        buttons.push(h('button', {
          class: 'btn sm', disabled: trayState.busy,
          html: `${icon('refresh', { size: 14 })}<span>${tx(TXT.refresh)}</span>`,
          onclick: () => loadTray(true),
        }));
      }
      if (trayHasCommands(data)) {
        buttons.push(h('button', {
          class: 'btn sm ghost',
          html: `${icon('copy', { size: 14 })}<span>${tx(TXT.copyCommands)}</span>`,
          onclick: copyTrayCommands,
        }));
      }

      trayAlert.append(h('div', {
        style: {
          display: 'flex', alignItems: 'flex-start', gap: '12px',
          padding: '14px 16px', borderRadius: '12px',
          border: '1px solid color-mix(in srgb, var(--warn) 50%, var(--border))',
          background: 'color-mix(in srgb, var(--warn) 10%, var(--surface))',
        },
      },
        h('span', {
          style: { color: 'var(--warn)', flex: 'none', display: 'grid', marginTop: '1px' },
          html: icon('alert-triangle', { size: 22 }),
        }),
        h('div', { style: { minWidth: 0, flex: '1' } },
          h('div', { style: { fontWeight: '700', fontSize: '14px', lineHeight: '1.45' } }, title),
          body ? h('div', {
            class: 'tiny muted', style: { marginTop: '5px', lineHeight: '1.75' },
          }, body) : null,
          hint ? h('div', {
            class: 'tiny', style: { marginTop: '6px', lineHeight: '1.7', color: 'var(--text-2)' },
          }, hint) : null,
          buttons.length ? h('div', {
            class: 'row', style: { marginTop: '10px', gap: '8px', flexWrap: 'wrap' },
          }, ...buttons) : null,
        ),
      ));
      trayAlert.classList.remove('hidden');
    }

    function renderTrayProgress() {
      trayProgress.innerHTML = '';
      if (!trayState.busy) {
        trayProgress.classList.add('hidden');
        return;
      }
      const isEnable = trayState.busyKind === 'enable';
      trayProgress.append(h('div', {
        class: 'row',
        style: {
          gap: '10px', alignItems: 'center', marginTop: '10px', padding: '11px 14px',
          borderRadius: '10px', flexWrap: 'nowrap',
          border: '1px solid color-mix(in srgb, var(--accent) 40%, var(--border))',
          background: 'color-mix(in srgb, var(--accent) 8%, var(--surface))',
        },
      },
        h('span', { style: { display: 'grid', color: 'var(--accent)', flex: 'none' }, html: icon('spinner', { size: 18 }) }),
        h('div', { class: 'tiny', style: { lineHeight: '1.65', minWidth: 0 } },
          h('div', { style: { fontWeight: '600' } }, isEnable ? tx(TXT.enabling) : tx(TXT.installing)),
          h('div', { class: 'muted', style: { marginTop: '2px' } },
            isEnable ? tx(TXT.enablingProgress) : tx(TXT.installingProgress)),
        ),
      ));
      trayProgress.classList.remove('hidden');
    }

    function renderTrayFeedback() {
      trayFeedback.innerHTML = '';
      const res = trayState.lastResult;
      const hasStandaloneError = !res && !!trayState.lastError;
      if (!res && !hasStandaloneError) {
        trayFeedback.classList.add('hidden');
        return;
      }
      const ok = !!res?.ok;
      const accent = ok ? 'var(--ok)' : 'var(--danger)';
      let title;
      if (ok) {
        if (res.alreadyInstalled) title = tx(TXT.alreadyInstalled);
        else title = trayState.lastAction === 'enable' ? tx(TXT.enableSuccess) : tx(TXT.installSuccess);
      } else {
        title = tx(TXT.failureTitle);
      }
      const rows = [
        h('div', { class: 'row', style: { gap: '8px', alignItems: 'center' } },
          h('span', { style: { color: accent, display: 'grid', flex: 'none' }, html: icon(ok ? 'check-circle' : 'alert-circle', { size: 18 }) }),
          h('div', { style: { fontWeight: '700', lineHeight: '1.4' } }, title),
        ),
      ];
      const nextText = ok ? trayReloadText(res) : tx(TXT.failureHint);
      if (nextText) {
        rows.push(h('div', { class: 'tiny', style: { marginTop: '5px', lineHeight: '1.75' } }, nextText));
      }
      if (ok && (res.warnings || []).length) {
        rows.push(h('div', {
          class: 'tiny', style: { marginTop: '5px', lineHeight: '1.7', color: 'var(--warn)' },
        }, trayLocalized(res.warnings[0])));
      }
      if (!ok) {
        const failureText = res?.failure ? trayLocalized(res.failure) : (trayState.lastError || '');
        if (failureText) {
          rows.push(h('div', {
            class: 'tiny', style: { marginTop: '5px', lineHeight: '1.75', color: 'var(--text-2)' },
          }, failureText));
        }
      }
      const buttons = [];
      if (ok || hasStandaloneError) {
        buttons.push(h('button', {
          class: 'btn sm', disabled: trayState.busy,
          html: `${icon('refresh', { size: 14 })}<span>${tx(TXT.refresh)}</span>`,
          onclick: () => loadTray(true),
        }));
      } else {
        buttons.push(h('button', {
          class: 'btn sm', disabled: trayState.busy,
          html: `${icon('refresh', { size: 14 })}<span>${tx(TXT.retry)}</span>`,
          onclick: () => (trayState.lastAction === 'enable' ? enableTrayExtension() : installTrayExtension()),
        }));
        if (trayHasCommands(trayState.data)) {
          buttons.push(h('button', {
            class: 'btn sm ghost',
            html: `${icon('copy', { size: 14 })}<span>${tx(TXT.copyCommands)}</span>`,
            onclick: copyTrayCommands,
          }));
        }
        if (res?.output || res?.commandText) {
          buttons.push(h('button', {
            class: 'btn sm ghost',
            html: `${icon('file', { size: 14 })}<span>${trayState.showOutput ? tx(TXT.hideOutput) : tx(TXT.showOutput)}</span>`,
            onclick: () => { trayState.showOutput = !trayState.showOutput; renderTrayFeedback(); },
          }));
        }
      }
      rows.push(h('div', { class: 'row', style: { marginTop: '9px', gap: '8px', flexWrap: 'wrap' } }, ...buttons));
      trayFeedback.append(h('div', {
        style: {
          marginTop: '10px', padding: '12px 14px', borderRadius: '10px',
          border: `1px solid color-mix(in srgb, ${accent} 45%, var(--border))`,
          background: `color-mix(in srgb, ${accent} 7%, var(--surface))`,
        },
      }, ...rows));
      if (trayState.showOutput) {
        const out = [
          res?.message || '',
          res?.commandText ? `$ ${res.commandText}` : '',
          res?.failure ? trayLocalized(res.failure) : '',
          res?.output || '',
        ].filter(Boolean).join('\n\n');
        if (out) {
          trayFeedback.append(h('pre', {
            class: 'code-block tiny mono',
            style: {
              marginTop: '8px', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              maxHeight: '220px', overflow: 'auto', lineHeight: '1.7',
            },
          }, out));
        }
      }
      trayFeedback.classList.remove('hidden');
    }

    function renderTray() {
      const data = trayState.data;
      trayTitleEl.textContent = tx(TXT.title);
      trayDescEl.textContent = tx(TXT.desc);
      const [label, kind] = trayState.loading ? [tx(TXT.reading), ''] : trayBadgeState(data);
      trayBadge.className = 'badge';
      if (kind) trayBadge.classList.add(kind);
      trayBadge.textContent = label;

      const attention = !trayState.loading && trayNeedsAttention(data);
      applyTrayAttention(attention);
      if (attention && root.firstChild !== trayCardWrap) root.prepend(trayCardWrap);

      trayDetail.innerHTML = '';
      if (data && !trayState.loading) {
        const rows = [
          [tx(TXT.backend), trayBackendLabel(data)],
          [tx(TXT.host), trayHostLabel(data)],
          [tx(TXT.desktop), `${data.desktop?.currentDesktop || '—'}${data.desktop?.sessionType ? ' · ' + String(data.desktop.sessionType).toUpperCase() : ''}`],
          [tx(TXT.extension), trayExtLabel(data)],
        ];
        if (data.platform === 'linux') rows.push([tx(TXT.elevation), trayElevationLabel(data)]);
        if (String(data.platform || '').toLowerCase() === 'windows') {
          // v0.1.8.6：Windows 显示实测图标状态（visible / 溢出区 / 恢复中 / 不可用）
          const iconState = String(data.diagnostics?.iconState || data.diagnostics?.icon?.state || '');
          const mapZh = {
            visible: '正常显示', hidden: '在「显示隐藏的图标」溢出区',
            rebuilding: '正在自动恢复', missing: '暂时不可用', unconfirmed: '未确认',
          };
          const mapEn = {
            visible: 'Visible', hidden: 'In “Show hidden icons” overflow',
            rebuilding: 'Recovering', missing: 'Unavailable', unconfirmed: 'Unconfirmed',
          };
          const stateText = (i18n.lang === 'en' ? mapEn[iconState] : mapZh[iconState]) || iconState || '—';
          rows.push([i18n.lang === 'en' ? 'Tray icon' : '托盘图标', stateText]);
        }
        if (data.gnome?.shellVersion) rows.push(['GNOME Shell', String(data.gnome.shellVersion)]);
        if (data.os?.name) rows.push([tx(TXT.system), `${data.os.name}${data.os.version ? ' ' + data.os.version : ''}`]);
        if (data.os?.family && data.os.family !== 'unknown' && data.os.family !== data.platform) {
          rows.push([tx(TXT.distroFamily), String(data.os.family)]);
        }
        trayDetail.append(kvList(rows));
      }

      trayAdvice.textContent = trayState.loading ? '' : trayAdviceText(data);

      renderTrayAlert(data);
      renderTrayProgress();

      trayActions.innerHTML = '';
      if (!trayState.loading && data) {
        const browser = trayBrowserMode(data);
        if (!attention && data.install?.supported && !browser) {
          trayActions.append(h('button', {
            class: 'btn primary sm', disabled: trayState.busy,
            html: `${icon('download', { size: 14 })}<span>${tx(TXT.install)}</span>`,
            onclick: installTrayExtension,
          }));
        } else if (!attention && data.install?.needsEnable && !browser) {
          trayActions.append(h('button', {
            class: 'btn primary sm', disabled: trayState.busy,
            html: `${icon('power', { size: 14 })}<span>${tx(TXT.enable)}</span>`,
            onclick: enableTrayExtension,
          }));
        }
        if (!attention && trayHasCommands(data)) {
          trayActions.append(h('button', {
            class: 'btn sm ghost',
            html: `${icon('copy', { size: 14 })}<span>${tx(TXT.copyCommands)}</span>`,
            onclick: copyTrayCommands,
          }));
          trayActions.append(h('button', {
            class: 'btn sm ghost',
            html: `${icon('list', { size: 14 })}<span>${tx(TXT.showCommands)}</span>`,
            onclick: () => {
              trayCommands.textContent = trayCommandText(trayState.data) || '';
              trayCommands.style.display = trayCommands.style.display === 'none' ? '' : 'none';
            },
          }));
        }
        trayActions.append(h('button', {
          class: 'btn sm ghost', disabled: trayState.busy,
          html: `${icon('refresh', { size: 14 })}<span>${tx(TXT.refresh)}</span>`,
          onclick: () => loadTray(true),
        }));
      } else if (!trayState.loading && !data) {
        trayActions.append(h('button', {
          class: 'btn sm', disabled: trayState.busy,
          html: `${icon('refresh', { size: 14 })}<span>${tx(TXT.retry)}</span>`,
          onclick: () => loadTray(true),
        }));
      }
      renderTrayFeedback();
    }

    async function installTrayExtension() {
      if (trayState.busy) return;
      const data = trayState.data;
      if (trayBrowserMode(data)) {
        ctx.toastWarn(tx(TXT.attentionBrowserHint));
        await copyTrayCommands();
        return;
      }
      const ok = await confirmDialog({
        title: tx(TXT.installTitle),
        message: tx(TXT.installMessage),
        confirmText: tx(TXT.installConfirm),
      });
      if (!ok) return;
      trayState.busy = true;
      trayState.busyKind = 'install';
      trayState.lastAction = 'install';
      trayState.lastResult = null;
      trayState.lastError = '';
      trayState.showOutput = false;
      renderTray();
      ctx.toastInfo(tx(TXT.installing), { timeout: 8000 });
      try {
        const res = await api.post('/api/tray/install-extension', { confirm: true });
        trayState.lastResult = res || null;
        if (res?.ok) {
          ctx.toastSuccess(res.message || tx(TXT.ok));
          const nextText = trayReloadText(res);
          if (nextText) ctx.toastInfo(nextText, { timeout: 12000 });
        } else {
          ctx.toastWarn(res?.message || tx(TXT.badResult));
        }
      } catch (err) {
        trayState.lastResult = null;
        trayState.lastError = String(err?.message || err);
        ctx.toastError(tx(TXT.installFailed) + (err.message || err));
      } finally {
        trayState.busy = false;
        trayState.busyKind = '';
        await loadTray(true);
      }
    }

    async function enableTrayExtension() {
      if (trayState.busy) return;
      if (trayBrowserMode(trayState.data)) {
        ctx.toastWarn(tx(TXT.attentionBrowserHint));
        await copyTrayCommands();
        return;
      }
      trayState.busy = true;
      trayState.busyKind = 'enable';
      trayState.lastAction = 'enable';
      trayState.lastResult = null;
      trayState.lastError = '';
      trayState.showOutput = false;
      renderTray();
      try {
        const res = await api.post('/api/tray/enable-extension');
        trayState.lastResult = res || null;
        if (res?.ok) {
          ctx.toastSuccess(res.message || tx(TXT.ok));
          const nextText = trayReloadText(res);
          if (nextText) ctx.toastInfo(nextText, { timeout: 12000 });
        } else {
          ctx.toastWarn(res?.message || tx(TXT.badResult));
        }
      } catch (err) {
        trayState.lastResult = null;
        trayState.lastError = String(err?.message || err);
        ctx.toastError(tx(TXT.enableFailed) + (err.message || err));
      } finally {
        trayState.busy = false;
        trayState.busyKind = '';
        await loadTray(true);
      }
    }

    async function loadTray(refresh = false) {
      trayState.loading = true;
      renderTray();
      try {
        const data = await api.get(`/api/tray/status${refresh ? '?refresh=true' : ''}`);
        trayState.data = data || null;
      } catch (err) {
        trayState.data = null;
        console.warn('[settings] 读取托盘状态失败', err);
      } finally {
        trayState.loading = false;
        renderTray();
      }
    }

    const trayTitleEl = h('div', { class: 'card-title' }, tx(TXT.title));
    const trayDescEl = h('div', { class: 'card-desc' }, tx(TXT.desc));
    const trayCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, trayTitleEl, trayDescEl),
        h('div', { class: 'spacer' }),
        trayBadge,
      ),
      h('div', { class: 'card-body' },
        trayAlert,
        trayProgress,
        trayDetail,
        trayAdvice,
        trayFeedback,
        trayActions,
        trayCommands,
      ),
    );
    // 需要醒目提示时把整个包裹节点（含 mt-16）置顶，避免留下空 wrapper
    const trayCardWrap = h('div', { class: 'mt-16' }, trayCard);

    /* ---------------- 日志与诊断 ---------------- */
    const logBadge = badge('读取中…', '');
    const logDirEl = h('div', { class: 'tiny muted mono', style: { wordBreak: 'break-all' } }, '—');
    const logSessionEl = h('div', { class: 'tiny muted mono', style: { wordBreak: 'break-all' } }, '—');
    const logFilesEl = h('div', { class: 'stack', style: { gap: '2px', marginTop: '8px' } });
    const logExportsEl = h('div', { class: 'stack', style: { gap: '2px', marginTop: '8px' } });
    const exportLogBtn = h('button', {
      class: 'btn primary sm', html: `${icon('download', { size: 14 })}<span>导出日志</span>`,
    });
    const openLogBtn = h('button', {
      class: 'btn sm', html: `${icon('archive', { size: 14 })}<span>打开日志目录</span>`,
    });
    const refreshLogBtn = h('button', {
      class: 'btn sm ghost', html: `${icon('refresh', { size: 14 })}<span>刷新</span>`,
    });
    function fmtKB(n) { return `${(Number(n || 0) / 1024).toFixed(1)} KB`; }
    function fmtTime(s) { return String(s || '').replace('T', ' '); }

    async function loadLogs() {
      try {
        const st = await api.get('/api/logs');
        logBadge.className = 'badge ok';
        logBadge.textContent = st.installed ? '记录中' : '未初始化';
        logDirEl.textContent = st.dir || '—';
        const cur = (st.files || []).find((f) => f.current);
        logSessionEl.textContent = cur ? `${cur.name} · ${fmtKB(cur.size)}` : '—';
        logFilesEl.innerHTML = '';
        const files = (st.files || []).slice(-6).reverse();
        if (!files.length) logFilesEl.append(h('div', { class: 'tiny muted' }, '暂无日志文件'));
        for (const f of files) {
          logFilesEl.append(h('div', { class: 'row between tiny' },
            h('span', { class: 'mono', style: { wordBreak: 'break-all' } }, f.name),
            h('span', { class: 'muted mono' }, `${fmtKB(f.size)} · ${fmtTime(f.modified)}`),
          ));
        }
        logExportsEl.innerHTML = '';
        const exps = (st.exports || []).slice(-4).reverse();
        if (!exps.length) {
          logExportsEl.append(h('div', { class: 'tiny muted' }, '还没有导出过诊断包'));
        } else {
          for (const e of exps) {
            logExportsEl.append(h('div', { class: 'row between tiny' },
              h('a', { class: 'mono', href: `/api/logs/download?name=${encodeURIComponent(e.name)}`, style: { wordBreak: 'break-all' } }, e.name),
              h('span', { class: 'muted mono' }, fmtKB(e.size)),
            ));
          }
        }
      } catch (err) {
        logBadge.className = 'badge danger';
        logBadge.textContent = '不可用';
        logDirEl.textContent = String(err.message || err);
      }
    }
    exportLogBtn.addEventListener('click', async () => {
      exportLogBtn.disabled = true;
      try {
        const res = await api.post('/api/logs/export', {
          context: '设置页手动导出',
        });
        if (!res || !res.ok) throw new Error(res?.message || '导出失败');
        ctx.toastSuccess(`日志已导出：${res.name}（${fmtKB(res.size)}）`);
        window.open(res.downloadUrl || `/api/logs/download?name=${encodeURIComponent(res.name)}`, '_blank');
        await loadLogs();
      } catch (err) {
        ctx.toastError(`导出失败：${err.message || err}`);
      } finally {
        exportLogBtn.disabled = false;
      }
    });
    openLogBtn.addEventListener('click', async () => {
      try {
        const res = await api.post('/api/logs/open', {});
        if (!res?.ok) ctx.toastWarn('当前环境无法自动打开文件管理器，可复制上方日志目录路径');
      } catch (err) {
        ctx.toastError(err.message || String(err));
      }
    });
    refreshLogBtn.addEventListener('click', () => loadLogs());

    const logsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '日志与诊断'),
          h('div', { class: 'card-desc' }, '完整记录运行/设备/API/TFT 通信；出问题一键导出诊断包发给开发者')),
        h('div', { class: 'spacer' }),
        logBadge,
      ),
      h('div', { class: 'card-body' },
        kvList([
          ['日志目录', logDirEl],
          ['当前会话', logSessionEl],
        ]),
        h('div', { class: 'tiny muted', style: { marginTop: '10px', lineHeight: '1.8' } },
          h('p', {}, '日志级别 DEBUG：mk87.log（滚动总日志）· session-*.log（本次运行完整日志）· errors.log（仅错误）。导出包含系统信息与设备状态快照，不含键盘输入内容。'),
        ),
        h('div', { class: 'row mt-12', style: { gap: '8px', flexWrap: 'wrap' } },
          exportLogBtn, openLogBtn, refreshLogBtn),
        h('div', { class: 'section-title', style: { marginTop: '16px' } }, h('h2', {}, '日志文件')),
        logFilesEl,
        h('div', { class: 'section-title', style: { marginTop: '14px' } }, h('h2', {}, '最近导出')),
        logExportsEl,
      ),
    );

    /* ---------------- 布局 ---------------- */
    root.append(prefCard);
    // 托盘卡片默认放在设置页靠前的位置；GNOME 缺扩展时 renderTray 会把它整套置顶
    root.append(trayCardWrap);
    root.append(h('div', { class: 'grid grid-2 mt-16' }, autostartCard, mockCard));
    root.append(h('div', { class: 'mt-16' }, logsCard));
    root.append(h('div', { class: 'mt-16' }, aboutCard));
    updateQuitVisibility();
    ctx.onStatus?.(() => updateQuitVisibility());
    loadAutostart();
    loadLogs();
    loadTray();
    // 语言切换时重渲染托盘卡片（后端建议文案有中英两份）
    const offLang = i18n.onChange(() => renderTray());
    return () => offLang();
  },
};
