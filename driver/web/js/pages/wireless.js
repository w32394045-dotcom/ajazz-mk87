/* pages/wireless.js — 无线：2.4G 连接状态、身份、休眠时间、通知日志
   规格：spec-tft-wireless.md §4 / design.md §4.8
   GET /api/wireless → {transport, connected, sleepTime, identity:{manufacturer,product,workMode,productName,pid}, battery, notifications}
   PUT /api/wireless {sleepTime}（分钟；0=关，官方 UI 1/10/20/30） */
import { icon } from '../icons.js';
import { h, fmtDateTime, fmtClock, timeAgo, toMs } from '../util.js';
import { badge, kvList, sectionTitle } from '../components/widgets.js';

const SLEEP_OPTIONS = [
  { value: 0, label: '关闭', sub: '不自动休眠' },
  { value: 1, label: '1', sub: '分钟' },
  { value: 10, label: '10', sub: '分钟' },
  { value: 20, label: '20', sub: '分钟' },
  { value: 30, label: '30', sub: '分钟' },
];

const NOTIFY_META = {
  connect: { label: '已连接', icon: 'plug', cls: 'wake' },
  wake: { label: '设备唤醒', icon: 'zap', cls: 'wake' },
  sleep: { label: '设备休眠', icon: 'moon', cls: 'sleep' },
  disconnect: { label: '连接断开', icon: 'alert-triangle', cls: 'disconnect' },
  reset: { label: '设备复位', icon: 'refresh', cls: '' },
  config: { label: '设置已更新', icon: 'settings', cls: '' },
};

export default {
  id: 'wireless',
  async mount(root, ctx) {
    const { api } = ctx;

    let info = null;
    let loadError = null;
    try {
      info = await api.get('/api/wireless');
    } catch (e) {
      loadError = e;
    }

    const status = ctx.status;
    const is24g = status?.transport === '2.4g';
    const demoMode = !!info?.demo;
    let connected = info?.connected !== false && (is24g || demoMode);
    let sleepTime = Number(info?.sleepTime ?? 10);
    let sleepOptions = Array.isArray(info?.sleepOptions) && info.sleepOptions.length
      ? info.sleepOptions.map((v) => ({ value: Number(v), label: String(v), sub: Number(v) === 0 ? '不自动休眠' : '分钟' }))
      : SLEEP_OPTIONS.map((x) => ({ ...x }));
    if (!sleepOptions.some((o) => o.value === sleepTime)) {
      sleepOptions.push({ value: sleepTime, label: String(sleepTime), sub: '分钟（出厂默认）' });
      sleepOptions.sort((a, b) => a.value - b.value);
    }
    let notifications = [...(info?.notifications || status?.recentNotifications || [])].sort((a, b) => (b.ts || 0) - (a.ts || 0));
    let stateKind = demoMode && !is24g ? 'demo' : 'ok';
    const offs = [];

    /* ---------------- 组件 ---------------- */
    const connBadge = h('span', { class: 'badge' }, '—');
    const stateBox = h('div');

    const identityCard = h('div', { class: 'grid-stack' });
    function renderIdentity() {
      identityCard.innerHTML = '';
      const id = info?.identity || {};
      const five = `${id.vid ?? info?.vid ?? status?.device?.vid ?? 3141}:${id.pid ?? status?.device?.pid ?? 65278}:${id.productName || status?.device?.product || '2.4G Dongle'}:${id.manufacturer ?? 1}:${id.product ?? 18}`;
      identityCard.append(h('div', { class: 'stack' },
        kvList([
          ['传输方式', info?.transport === '2.4g' || demoMode ? '2.4G 无线（0xFF60）' : 'USB 有线'],
          ['连接状态', connected ? '已连接' : '未连接'],
          ['完整设备 ID', five],
          ['接收器', `${id.productName || status?.device?.product || '2.4G Dongle'}（VID ${(id.vid ?? info?.vid ?? 3141).toString(16).toUpperCase()} / PID ${(id.pid ?? status?.device?.pid ?? 65278).toString(16).toUpperCase()}）`],
          ['身份字段', `manufacturer=${id.manufacturer ?? '—'} · product=${id.product ?? '—'} · workMode=${id.workMode ?? '—'}`],
          ['电量', info?.battery ? `${info.battery.percent}%${info.battery.charging ? '（充电中）' : ''}` : (status?.battery ? `${status.battery.percent}%` : '—')],
        ]),

      ));
    }

    const sleepGrid = h('div', { class: 'sleep-options' });
    function renderSleep() {
      sleepGrid.innerHTML = '';
      for (const opt of sleepOptions) {
        const active = sleepTime === opt.value;
        sleepGrid.append(h('button', {
          type: 'button',
          class: `sleep-opt${active ? ' active' : ''}`,
          disabled: !connected,
          onclick: () => setSleep(opt.value),
        },
          h('span', { class: 'num' }, opt.label),
          h('span', {}, opt.sub),
        ));
      }
    }

    const timeline = h('div', { class: 'timeline' });
    function renderNotifications() {
      timeline.innerHTML = '';
      if (!notifications.length) {
        timeline.append(h('div', { class: 'empty notify-empty' },
          h('div', { html: icon('activity', { size: 24 }) }),
          h('div', {}, '还没有收到设备通知'),
          h('div', { class: 'tiny' }, '断连 / 休眠 / 唤醒事件会实时显示在这里'),
        ));
        return;
      }
      for (const n of notifications.slice(0, 30)) {
        const meta = NOTIFY_META[n.kind] || { label: n.kind || '通知', icon: 'activity', cls: '' };
        timeline.append(h('div', { class: `tl-item ${meta.cls}` },
          h('div', { class: 'tl-title', style: { display: 'flex', alignItems: 'center', gap: '6px' } },
            h('span', { html: icon(meta.icon, { size: 13 }), style: { color: 'var(--muted)' } }),
            h('span', {}, meta.label),
          ),
          h('div', { class: 'tl-meta' }, `${n.ts ? fmtDateTime(toMs(n.ts)) : '—'}${n.ts ? ` · ${timeAgo(toMs(n.ts))}` : ''}`),
        ));
      }
    }

    function renderState() {
      stateBox.innerHTML = '';
      connBadge.textContent = connected ? '已连接' : '未连接';
      connBadge.className = `badge ${connected ? 'ok' : 'danger'}`;
      if (!connected) {
        stateBox.append(h('div', { class: 'banner danger', style: { margin: '0 0 14px' } },
          h('div', { class: 'banner-icon', html: icon('alert-triangle', { size: 17 }) }),
          h('div', {}, h('strong', {}, '2.4G 连接已断开'),
            h('div', { class: 'tiny', style: { marginTop: '2px' } }, '接收器可能进入休眠或已拔出。按键盘任意键唤醒，或在设备信息页重新扫描。')),
        ));
      } else if (stateKind === 'sleep') {
        stateBox.append(h('div', { class: 'banner warn', style: { margin: '0 0 14px' } },
          h('div', { class: 'banner-icon', html: icon('moon', { size: 17 }) }),
          h('div', {}, h('strong', {}, '设备已进入休眠'),
            h('div', { class: 'tiny', style: { marginTop: '2px' } }, '按键盘任意按键唤醒设备（唤醒帧 A6 FF 01 走 0xFFFF / report ID=5）。')),
        ));
      } else if (!is24g && !demoMode) {
        stateBox.append(h('div', { class: 'banner', style: { margin: '0 0 14px' } },
          h('div', { class: 'banner-icon', html: icon('usb', { size: 17 }) }),
          h('div', {}, h('strong', {}, '当前通过 USB 有线连接'),
            h('div', { class: 'tiny', style: { marginTop: '2px' } }, '无线页在 USB 下只读；拔掉 USB 线、插上 2.4G 接收器后自动切换到 2.4G（配置存在键盘端，两条通道共享）。')),
        ));
      } else if (demoMode) {
        stateBox.append(h('div', { class: 'banner', style: { margin: '0 0 14px' } },
          h('div', { class: 'banner-icon', html: icon('info', { size: 17 }) }),
          h('div', {}, h('strong', {}, '演示模式：模拟 2.4G 接收器'),
            h('div', { class: 'tiny', style: { marginTop: '2px' } }, '真实后端连接 2.4G 后这里会显示接收器与键盘的实际状态；演示数据仅用于预览 UI。')),
        ));
      }
      renderIdentity();
      renderSleep();
    }

    async function setSleep(value) {
      const prev = sleepTime;
      sleepTime = value;
      renderSleep();
      try {
        await api.put('/api/wireless', { sleepTime: value });
        ctx.toastSuccess(value === 0 ? '已关闭自动休眠' : `空闲 ${value} 分钟后自动休眠（分钟字段已写入）`);
        await refresh();
      } catch (e) {
        sleepTime = prev;
        renderSleep();
        ctx.toastError(`写入失败：${e.message || e}`);
      }
    }

    async function refresh() {
      try {
        const next = await api.get('/api/wireless');
        if (next) {
          info = next;
          connected = next.connected !== false && (next.transport === '2.4g' || next.demo);
          if (typeof next.sleepTime === 'number') sleepTime = next.sleepTime;
          notifications = [...(next.notifications || [])].sort((a, b) => (b.ts || 0) - (a.ts || 0));
          if (Array.isArray(next.sleepOptions) && next.sleepOptions.length) {
            sleepOptions = next.sleepOptions.map((v) => ({ value: Number(v), label: String(v), sub: Number(v) === 0 ? '不自动休眠' : '分钟' }));
            if (!sleepOptions.some((o) => o.value === sleepTime)) { sleepOptions.push({ value: sleepTime, label: String(sleepTime), sub: '分钟（出厂默认）' }); sleepOptions.sort((a, b) => a.value - b.value); }
          }
          renderState();
          renderNotifications();
        }
      } catch (e) {
        console.warn('[wireless] 刷新失败', e);
      }
    }

    /* WS 通知 */
    offs.push(api.on('ws:notification', (n) => {
      if (!n) return;
      if (n.ts && n.ts < 1e12) n.ts = toMs(n.ts);
      notifications.unshift(n);
      if (notifications.length > 60) notifications.pop();
      if (n.kind === 'sleep') stateKind = 'sleep';
      else if (n.kind === 'wake' || n.kind === 'connect') stateKind = 'ok';
      else if (n.kind === 'disconnect') connected = false;
      renderState();
      renderNotifications();
      if (n.kind === 'wake') ctx.toast('设备已唤醒');
      if (n.kind === 'sleep') ctx.toast('设备进入休眠', { type: 'warn' });
    }));

    /* ---------------- 布局 ---------------- */
    const headerCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '2.4G 无线连接'),
          h('div', { class: 'card-desc' }, '接收器 0C45:FEFE（3141:65278）· 协议口 0xFF60')),
        h('div', { class: 'spacer' }),
        connBadge,
        h('button', {
          class: 'btn sm ghost', title: '刷新', html: icon('refresh', { size: 14 }),
          onclick: async () => { await refresh(); ctx.toast('无线状态已刷新'); },
        }),
      ),
      h('div', { class: 'card-body' }, stateBox),
    );

    const identityWrap = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '接收器与身份')),
        h('div', { class: 'spacer' }),
        badge('5 段设备 ID', 'violet'),
      ),
      h('div', { class: 'card-body' }, identityCard),
    );

    const sleepCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '自动休眠'),
          h('div', { class: 'card-desc' }, '空闲 N 分钟后进入休眠（写入 SET_GAME_MODE payload[3]）')),
        h('div', { class: 'spacer' }),
        badge('单位：分钟', ''),
      ),
      h('div', { class: 'card-body' },
        sleepGrid,
        h('div', { class: 'tiny muted mt-12' }, '出厂实测默认 5 分钟（不在官方下拉 1/10/20/30 内）；实测设 1 分钟后约 59.96s 收到断连通知。'),
      ),
    );

    const notifyCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, '通知日志'),
          h('div', { class: 'card-desc' }, '断连 55 FC 04 · 休眠 55 FC 06 · 唤醒 A6 FF 01')),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm ghost', title: '清空日志',
          onclick: () => { notifications = []; renderNotifications(); ctx.toast('已清空本地日志'); },
        }, '清空'),
      ),
      h('div', { class: 'card-body' }, timeline),
    );

    const capsCard = h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, '2.4G 能力边界')),
      h('div', { class: 'card-body' },
        h('div', { class: 'stack' },
          h('div', { class: 'row' }, badge('支持', 'ok'), h('span', { class: 'tiny muted' }, '灯效写入 / 改键 / FN 读取 / 宏 / 电量 / 通知（配置存键盘端，双通道共享）')),
          h('div', { class: 'row' }, badge('不支持', 'danger'), h('span', { class: 'tiny muted' }, '音乐律动（官方确认）、TFT 屏幕上传（无 0xFF67 接口）、GIF 灯效')),
          h('div', { class: 'divider-dashed' }),
          h('div', { class: 'tiny muted', style: { lineHeight: '1.8' } },
            h('p', {}, '· 2.4G 下 GET_FN_KEY 会返回主层数据（固件行为）→ 编辑 FN 请用 USB 连接，改键页会自动把 FN 层置为只读。'),
            h('p', {}, '· 2.4G 下 SET_LED_EFFECT 的颜色回读可能不等于写入（显示正确），不能拿回读当写成功判据。'),
            h('p', {}, '· USB 线 + 接收器同插可能触发 Windows 0xC000009A（资源不足），请只保留一种连接。'),
          ),
        ),
      ),
    );

    root.append(headerCard);
    root.append(h('div', { class: 'grid grid-main mt-16' },
      h('div', { class: 'grid-stack' }, identityWrap, sleepCard),
      h('div', { class: 'grid-stack' }, capsCard, notifyCard),
    ));

    renderState();
    renderNotifications();
    if (loadError) {
      ctx.toastWarn(`无线状态读取失败：${loadError.message || loadError}`, { timeout: 5000 });
    }

    return () => offs.forEach((off) => off?.());
  },
};
