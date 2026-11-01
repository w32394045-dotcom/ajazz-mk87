/*!
 * hook.js —— AJAZZ 网页驱动 WebHID 抓包钩子
 * ---------------------------------------------------------------------------
 * 用途：
 *   本文件由 run.js 通过 CDP 的 Page.addScriptToEvaluateOnNewDocument 注入，
 *   在页面脚本**之前**执行，做三件事：
 *
 *   (a) 设备名适配：把 productName 以 "KEYBOARD " 开头的设备名剥掉前缀
 *       （Linux 上 Chrome 读到的 hidraw 产品串常带 "KEYBOARD " 前缀，会让网页
 *        驱动按 "VID:PID:产品名" 匹配配置表时失败；Windows 上无此前缀，行为不变）。
 *
 *   (b) 全通道拦截：HIDDevice 的 open / close / forget / sendReport /
 *       sendFeatureReport / receiveFeatureReport，以及 open 之后的 inputreport
 *       事件流。每条记录都带 ts / dir / method / reportId / data(数组+hex) /
 *       device / collections / caller / error。
 *
 *   (c) 控制面记录：navigator.hid.getDevices / requestDevice 的调用与返回、
 *       connect / disconnect 事件。
 *
 *   所有记录通过 window.__ajazzFlush(JSON.stringify(entry)) 实时推送 ——
 *   这个函数由 CDP 的 Runtime.addBinding('__ajazzFlush') 注入，它会把字符串
 *   异步送回浏览器进程，run.js 收到 Runtime.bindingCalled 后逐行写 JSONL。
 *   推送失败（binding 还没就绪 / 已被移除）时先塞进 window.__ajazzLog 数组并
 *   排队重试，保证不丢记录、也绝不影响页面本身。
 *
 * 设计红线：
 *   - 包装必须保持原方法语义：返回值、抛出的异常、this 绑定都不变。
 *     - 同步抛错：原样再抛（throw err）。
 *     - 返回 Promise：**返回原 Promise 对象本身**（不返回派生 Promise，
 *       避免页面比较 Promise 身份或做 thenable 判断时出现差异）；
 *       记录用副作用 handler 完成。
 *     - 唯一的可观测差异：因为我们挂了 rejection handler，浏览器原本可能打印的
 *       "Unhandled promise rejection" 警告可能不再出现。页面自己的 try/catch
 *       不受影响。
 *   - 任何钩子内部异常都必须被吞掉，绝不冒泡到页面（全部 try/catch）。
 *   - 幂等：同一文档重复注入只生效一次（window.__ajazzHookInstalled）。
 *
 * 字段约定（每行 JSON 一个对象）：
 *   ts         performance.now()，毫秒，3 位小数
 *   epoch      Date.now()，墙上时间，方便和抓图/抓包对齐
 *   seq        本页内的自增序号
 *   dir        out | out-feature | in-feature | in | open | close | forget |
 *              hid | event | meta        （含义见 README）
 *   phase      call | ok | error       （调用时刻 / 成功返回 / 失败）
 *   method     被拦截的方法名或事件名
 *   reportId   number | null
 *   data       { length, array[], hex, ascii } | null   —— 报文原始字节
 *   device     { vendorId, productId, productName, opened } | null
 *   collections [{ usagePage, usage, type, children[] }] | null
 *   caller     new Error().stack 前 6 行（去掉首行 "Error"），用于定位 UI 触发点
 *   error      string | null
 *   durationMs number | null
 * ---------------------------------------------------------------------------
 */
(function () {
  'use strict';

  /* =======================================================================
   * 0. 幂等保护 & 原生函数备份
   * ===================================================================== */
  if (window.__ajazzHookInstalled) return;
  window.__ajazzHookInstalled = true;

  var nativeDefineProperty = Object.defineProperty;      // 备份：后面会包装它
  var nativeGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
  var nativeDefineProperties = Object.defineProperties;
  var nativeReflectDefineProperty = Reflect.defineProperty;

  var HOOK_VERSION = '1.0.0';
  var PREFIX_RE = /^KEYBOARD\s+/i;                        // "KEYBOARD " 前缀
  var STACK_LINES = 6;                                    // caller 保留的行数

  var H = {
    version: HOOK_VERSION,
    startedAt: Date.now(),
    seq: 0,
    log: [],            // 同时暴露成 window.__ajazzLog
    pending: [],        // binding 还没就绪时的待发送队列
    maxLog: 5000,       // 本地留档上限，防止长时间采集吃内存
    errors: [],         // 钩子自身遇到的问题
    hidWrapped: false,
    devicesPatched: 0,
    flushTimer: null,
  };

  /* =======================================================================
   * 1. 基础工具
   * ===================================================================== */
  function nowMs() {
    try {
      return (typeof performance !== 'undefined' && performance.now)
        ? performance.now()
        : Date.now() - H.startedAt;
    } catch (e) { return Date.now(); }
  }

  function round3(n) {
    return (typeof n === 'number' && isFinite(n)) ? Math.round(n * 1000) / 1000 : null;
  }

  /** 把任意「类字节」输入统一复制成新的 Uint8Array（必须复制：inputreport 的
   *  DataView 在事件派发结束后会被浏览器复用/失效）。 */
  function copyBytes(v) {
    if (v == null) return null;
    try {
      // 同 realm 的快速路径
      if (v instanceof Uint8Array) {
        return new Uint8Array(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength));
      }
      if (ArrayBuffer.isView(v)) {
        return new Uint8Array(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength));
      }
      if (v instanceof ArrayBuffer) return new Uint8Array(v.slice(0));
      if (typeof v === 'object' && v.buffer && typeof v.byteLength === 'number') {
        // 跨 realm 的 TypedArray / DataView（iframe）
        return new Uint8Array(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength));
      }
      if (Array.isArray(v)) {
        var out = new Uint8Array(v.length);
        for (var i = 0; i < v.length; i++) out[i] = v[i] & 0xff;
        return out;
      }
    } catch (e) { /* 退化为 null，不让钩子抛错 */ }
    return null;
  }

  function toHex(bytes) {
    var parts = [];
    for (var i = 0; i < bytes.length; i++) {
      parts.push((bytes[i] < 16 ? '0' : '') + bytes[i].toString(16));
    }
    return parts.join(' ');
  }

  function toAscii(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) {
      var b = bytes[i];
      s += (b >= 0x20 && b <= 0x7e) ? String.fromCharCode(b) : '.';
    }
    return s;
  }

  /** 报文 -> { length, array, hex, ascii } */
  function bytesInfo(bytes) {
    if (!bytes) return null;
    var arr = [];
    for (var i = 0; i < bytes.length; i++) arr.push(bytes[i]);
    return { length: arr.length, array: arr, hex: toHex(bytes), ascii: toAscii(bytes) };
  }

  function errText(err) {
    try {
      if (err == null) return 'null';
      if (typeof err === 'string') return err;
      var name = err.name ? String(err.name) : '';
      var msg = err.message ? String(err.message) : String(err);
      return name ? (name + ': ' + msg) : msg;
    } catch (e) { return 'unknown error'; }
  }

  /** 调用栈前 6 行（去掉首行 "Error"），用来定位是哪个 UI 操作触发的 */
  function callerStack() {
    try {
      var s = new Error().stack;
      if (!s) return null;
      var lines = String(s).split('\n');
      // 首行通常只是 "Error"，去掉它，再取 6 行
      if (lines.length && /^\s*Error\b/.test(lines[0])) lines = lines.slice(1);
      var out = [];
      for (var i = 0; i < lines.length && out.length < STACK_LINES; i++) {
        var t = lines[i].trim();
        if (t) out.push(t);
      }
      return out.join('\n');
    } catch (e) { return null; }
  }

  function stripKeyboardPrefix(name) {
    try {
      if (typeof name !== 'string') return name;
      if (!PREFIX_RE.test(name)) return name;
      var stripped = name.replace(PREFIX_RE, '').trim();
      return stripped ? stripped : name;   // 只有前缀的怪名字保持原样
    } catch (e) { return name; }
  }

  /* =======================================================================
   * 2. 记录推送（window.__ajazzFlush + window.__ajazzLog）
   * ===================================================================== */
  H.log = [];
  window.__ajazzLog = H.log;

  function flushPending() {
    H.flushTimer = null;
    if (!H.pending.length) return;
    var fn = window.__ajazzFlush;
    if (typeof fn !== 'function') return;      // binding 还没注入，等下一轮
    var rest = [];
    for (var i = 0; i < H.pending.length; i++) {
      try { fn(H.pending[i]); }
      catch (e) { rest.push(H.pending[i]); }
    }
    H.pending = rest;
    if (H.pending.length) scheduleFlush();
  }

  function scheduleFlush() {
    if (H.flushTimer != null) return;
    try { H.flushTimer = setTimeout(flushPending, 200); } catch (e) { H.flushTimer = null; }
  }

  function emit(entry) {
    var rec;
    try {
      rec = {
        ts: round3(nowMs()),
        epoch: Date.now(),
        seq: ++H.seq,
        dir: entry.dir,
        phase: entry.phase || 'call',
        method: entry.method || null,
        reportId: (typeof entry.reportId === 'number') ? entry.reportId : null,
        data: entry.data || null,
        device: entry.device || null,
        collections: entry.collections || null,
        caller: entry.caller || null,
        error: (entry.error == null) ? null : String(entry.error),
        durationMs: (typeof entry.durationMs === 'number') ? entry.durationMs : null,
      };
      // 允许附加自定义字段（filters / devices / note 等）
      if (entry.filters !== undefined) rec.filters = entry.filters;
      if (entry.devices !== undefined) rec.devices = entry.devices;
      if (entry.note !== undefined) rec.note = entry.note;
      if (entry.extra !== undefined) rec.extra = entry.extra;
    } catch (e) {
      rec = { ts: round3(nowMs()), epoch: Date.now(), seq: ++H.seq, dir: 'meta', phase: 'error', method: 'emit', error: errText(e) };
    }

    // ① 本地留档
    try {
      H.log.push(rec);
      if (H.log.length > H.maxLog) H.log.splice(0, H.log.length - H.maxLog);
    } catch (e) { /* 忽略 */ }

    // ② 实时推送（序列化失败也要兜底，绝不抛出）
    var line;
    try {
      line = JSON.stringify(rec);
    } catch (e) {
      try {
        line = JSON.stringify({
          ts: rec.ts, epoch: rec.epoch, seq: rec.seq, dir: 'meta', phase: 'error',
          method: 'serialize', error: errText(e),
        });
      } catch (e2) { return; }
    }

    var fn = window.__ajazzFlush;
    if (typeof fn === 'function') {
      try { fn(line); return; } catch (e) { H.errors.push('flush: ' + errText(e)); }
    }
    H.pending.push(line);
    if (H.pending.length > 2000) H.pending.splice(0, H.pending.length - 2000); // 兜底
    scheduleFlush();
  }

  /* =======================================================================
   * 3. 设备/集合描述
   * ===================================================================== */
  function describeDevice(d) {
    if (!d) return null;
    var out = {};
    try { out.vendorId = d.vendorId; } catch (e) { out.vendorId = null; }
    try { out.productId = d.productId; } catch (e) { out.productId = null; }
    try { out.productName = d.productName; } catch (e) { out.productName = null; }
    try { out.opened = d.opened; } catch (e) { out.opened = null; }
    return out;
  }

  function describeCollections(d) {
    try {
      var list = d && d.collections;
      if (!list) return null;
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var c = list[i] || {};
        var item = { usagePage: c.usagePage, usage: c.usage, type: c.type };
        if (c.children) {
          item.children = [];
          for (var j = 0; j < c.children.length; j++) {
            var k = c.children[j] || {};
            item.children.push({ usagePage: k.usagePage, usage: k.usage, type: k.type });
          }
        } else {
          item.children = [];
        }
        out.push(item);
      }
      return out;
    } catch (e) { return null; }
  }

  function summarizeDevices(list) {
    try {
      if (!list) return null;
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var d = list[i];
        var s = describeDevice(d) || {};
        var cols = describeCollections(d);
        s.usagePage = (cols && cols.length) ? cols[0].usagePage : null;
        s.usage = (cols && cols.length) ? cols[0].usage : null;
        s.collections = cols;
        out.push(s);
      }
      return out;
    } catch (e) { return null; }
  }

  function safeJson(v) {
    try {
      if (v === undefined) return null;
      return JSON.parse(JSON.stringify(v));
    } catch (e) { return null; }
  }

  /* =======================================================================
   * 4. 设备名适配：剥掉 "KEYBOARD " 前缀
   * ===================================================================== */
  var WRAPPED = Symbol.for('ajazz.wrapped');            // 标记「已被我们包装」
  var PN_PATCHED = Symbol.for('ajazz.productNamePatched');
  var DEV_PATCHED = Symbol.for('ajazz.devicePatched');
  var INPUT_ATTACHED = Symbol.for('ajazz.inputAttached');
  var HID_WRAPPED = Symbol.for('ajazz.hidWrapped');

  function markWrapped(fn) {
    try { nativeDefineProperty(fn, WRAPPED, { value: true }); } catch (e) { /* 忽略 */ }
    return fn;
  }

  function isWrapped(fn) {
    try { return typeof fn === 'function' && fn[WRAPPED] === true; } catch (e) { return false; }
  }

  /**
   * 包装 productName：沿原型链找到 productName 描述符
   *   - 访问器（真 Chrome 的 HIDDevice.prototype getter）：在拥有它的对象上重定义，
   *     所有实例共享，返回值剥离前缀。
   *   - 数据属性（页面伪造设备常见）：在实例上定义剥离后的同名属性。
   */
  function patchProductName(device) {
    try {
      if (device[PN_PATCHED]) return;
      var owner = device, desc = null, depth = 0;
      while (owner && depth < 8) {
        desc = nativeGetOwnPropertyDescriptor(owner, 'productName');
        if (desc) break;
        owner = Object.getPrototypeOf(owner);
        depth++;
      }
      if (!desc) return;

      if (typeof desc.get === 'function') {
        if (isWrapped(desc.get)) {
          try { nativeDefineProperty(device, PN_PATCHED, { value: true, configurable: true }); } catch (e) {}
          return;
        }
        var origGet = desc.get;
        var patchedGet = markWrapped(function () {
          return stripKeyboardPrefix(origGet.call(this));
        });
        nativeDefineProperty(owner, 'productName', {
          get: patchedGet,
          set: desc.set,
          configurable: true,
          enumerable: desc.enumerable,
        });
      } else if ('value' in desc) {
        var stripped = stripKeyboardPrefix(desc.value);
        if (stripped !== desc.value) {
          nativeDefineProperty(device, 'productName', {
            value: stripped,
            writable: !!desc.writable,
            configurable: true,
            enumerable: desc.enumerable,
          });
        }
      }
      // 设备可能允许 expando；失败也无所谓
      try { nativeDefineProperty(device, PN_PATCHED, { value: true, configurable: true }); } catch (e) {}
    } catch (e) {
      H.errors.push('patchProductName: ' + errText(e));
    }
  }

  /* =======================================================================
   * 5. inputreport 监听
   * ===================================================================== */
  function onInputReport(ev) {
    try {
      // 必须同步取走并复制字节：事件返回后底层 buffer 可能被复用
      var bytes = copyBytes(ev && ev.data);
      var reportId = (ev && typeof ev.reportId === 'number') ? ev.reportId : null;
      emit({
        dir: 'in',
        phase: 'call',
        method: 'inputreport',
        reportId: reportId,
        data: bytesInfo(bytes),
        device: describeDevice(this),
        collections: describeCollections(this),
        caller: callerStack(),
      });
    } catch (e) {
      H.errors.push('onInputReport: ' + errText(e));
    }
  }

  function attachInputReport(device) {
    try {
      if (!device || device[INPUT_ATTACHED]) return;
      if (typeof device.addEventListener !== 'function') return;
      nativeDefineProperty(device, INPUT_ATTACHED, { value: true, configurable: true });
      device.addEventListener('inputreport', onInputReport);
    } catch (e) {
      H.errors.push('attachInputReport: ' + errText(e));
    }
  }

  /* =======================================================================
   * 6. HIDDevice 方法包装
   * ===================================================================== */
  /** 生成一个保持语义的包装函数 */
  function makeWrapper(name, dir, orig) {
    var wrapper = function () {
      /*__ajazz_hook__*/   // 标记：页面/测试脚本可用它判断「已被包装」
      var self = this;
      var args = arguments;
      var t0 = nowMs();
      var caller = callerStack();

      // ---- 参数解析（按 dir 区分）----
      var reportId = null;
      var bytes = null;
      if (dir === 'out' || dir === 'out-feature' || dir === 'in-feature') {
        var rawId = args[0];
        if (typeof rawId === 'number') reportId = rawId;
        else if (rawId != null && !isNaN(Number(rawId))) reportId = Number(rawId);
        if (dir !== 'in-feature') bytes = copyBytes(args[1]);
      }

      var base = {
        dir: dir,
        method: name,
        reportId: reportId,
        data: (dir === 'in-feature') ? null : bytesInfo(bytes),
        device: describeDevice(self),
        collections: describeCollections(self),
        caller: caller,
      };

      // ---- open 前先挂 inputreport 监听，避免 open 解析期间漏事件 ----
      if (dir === 'open') attachInputReport(self);

      // ---- 先记录「调用时刻」，保证即使原方法抛错也有据可查 ----
      emit({ dir: base.dir, phase: 'call', method: name, reportId: reportId, data: base.data,
             device: base.device, collections: base.collections, caller: caller });

      // ---- 调用原方法（保留 this 与全部实参）----
      var ret;
      try {
        ret = Reflect.apply(orig, self, args);
      } catch (err) {
        emit({ dir: base.dir, phase: 'error', method: name, reportId: reportId, data: null,
               device: base.device, collections: base.collections, caller: caller,
               error: errText(err), durationMs: round3(nowMs() - t0) });
        throw err;    // 保持原异常语义
      }

      // ---- 异步返回：只记录，不改变返回的 Promise 身份 ----
      if (ret && typeof ret.then === 'function') {
        try {
          var onOk = function (val) {
            var done = round3(nowMs() - t0);
            if (dir === 'in-feature') {
              // receiveFeatureReport 的返回值才是真正的「读到的数据」
              emit({ dir: dir, phase: 'ok', method: name, reportId: reportId,
                     data: bytesInfo(copyBytes(val)), device: base.device,
                     collections: base.collections, caller: caller, durationMs: done });
              return;
            }
            if (dir === 'out' || dir === 'out-feature') return;   // 报文已在 call 时落盘，避免重复
            emit({ dir: dir, phase: 'ok', method: name, reportId: reportId, data: null,
                   device: base.device, collections: base.collections, caller: caller,
                   durationMs: done });
          };
          var onErr = function (err) {
            emit({ dir: dir, phase: 'error', method: name, reportId: reportId, data: null,
                   device: base.device, collections: base.collections, caller: caller,
                   error: errText(err), durationMs: round3(nowMs() - t0) });
          };
          ret.then(onOk, onErr);
        } catch (e) { H.errors.push('wrapThen: ' + errText(e)); }
        return ret;   // ★ 返回原 Promise，语义完全不变
      }

      // ---- 同步返回的伪造实现（测试页可能有）----
      var done2 = round3(nowMs() - t0);
      if (dir === 'in-feature') {
        emit({ dir: dir, phase: 'ok', method: name, reportId: reportId,
               data: bytesInfo(copyBytes(ret)), device: base.device,
               collections: base.collections, caller: caller, durationMs: done2 });
      } else if (dir === 'open' || dir === 'close' || dir === 'forget') {
        emit({ dir: dir, phase: 'ok', method: name, reportId: null, data: null,
               device: base.device, collections: base.collections, caller: caller,
               durationMs: done2 });
      }
      return ret;
    };

    try {
      // 尽量让包装后的函数看起来像原函数（不改变 length/name 会让调试更自然）
      nativeDefineProperty(wrapper, 'name', { value: orig.name || name, configurable: true });
      nativeDefineProperty(wrapper, 'length', { value: orig.length, configurable: true });
    } catch (e) { /* 忽略 */ }
    return markWrapped(wrapper);
  }

  var METHOD_SPECS = [
    ['sendReport', 'out'],
    ['sendFeatureReport', 'out-feature'],
    ['receiveFeatureReport', 'in-feature'],
    ['open', 'open'],
    ['close', 'close'],
    ['forget', 'forget'],
  ];

  /** 在「实例」上定义包装方法（用于页面自定义的 HIDDevice 类 / 原型不可改的场景） */
  function wrapDeviceMethod(device, name, dir) {
    try {
      var orig = device[name];
      if (typeof orig !== 'function') return;
      if (isWrapped(orig)) return;                 // 原型级已包装，跳过避免双重记录
      var wrapper = makeWrapper(name, dir, orig);
      nativeDefineProperty(device, name, {
        value: wrapper,
        writable: true,
        configurable: true,
        enumerable: false,
      });
    } catch (e) {
      H.errors.push('wrapDeviceMethod(' + name + '): ' + errText(e));
    }
  }

  function patchDevice(device) {
    try {
      if (!device || (typeof device !== 'object' && typeof device !== 'function')) return device;
      if (device[DEV_PATCHED]) return device;
      try { nativeDefineProperty(device, DEV_PATCHED, { value: true, configurable: true }); } catch (e) {}
      H.devicesPatched++;
      patchProductName(device);
      for (var i = 0; i < METHOD_SPECS.length; i++) {
        wrapDeviceMethod(device, METHOD_SPECS[i][0], METHOD_SPECS[i][1]);
      }
      attachInputReport(device);
    } catch (e) {
      H.errors.push('patchDevice: ' + errText(e));
    }
    return device;
  }

  function patchDeviceList(list) {
    try {
      if (!list) return list;
      for (var i = 0; i < list.length; i++) patchDevice(list[i]);
    } catch (e) { H.errors.push('patchDeviceList: ' + errText(e)); }
    return list;
  }

  /** 真实 Chrome 里 HIDDevice 是全局构造器：直接补原型最省事 */
  function patchHidDevicePrototype() {
    try {
      var Ctor = window.HIDDevice;
      if (typeof Ctor !== 'function' || !Ctor.prototype) return;
      var proto = Ctor.prototype;
      for (var i = 0; i < METHOD_SPECS.length; i++) {
        var name = METHOD_SPECS[i][0], dir = METHOD_SPECS[i][1];
        var d = nativeGetOwnPropertyDescriptor(proto, name);
        if (!d || typeof d.value !== 'function' || isWrapped(d.value)) continue;
        nativeDefineProperty(proto, name, {
          value: makeWrapper(name, dir, d.value),
          writable: d.writable,
          configurable: true,
          enumerable: d.enumerable,
        });
      }
    } catch (e) {
      H.errors.push('patchHidDevicePrototype: ' + errText(e));
    }
  }

  /* =======================================================================
   * 7. navigator.hid 包装（getDevices / requestDevice / 事件）
   * ===================================================================== */
  function installHidEvents(hid) {
    try {
      if (typeof hid.addEventListener !== 'function') return;
      // WebHID 规范的事件名是 connect / disconnect（HIDConnectionEvent）
      var pairs = [['connect', 'connect'], ['disconnect', 'disconnect'],
                   // 兼容性兜底：某些环境/文档写作 deviceconnect / devicedisconnect
                   ['deviceconnect', 'deviceconnect'], ['devicedisconnect', 'devicedisconnect']];
      for (var i = 0; i < pairs.length; i++) {
        (function (type) {
          hid.addEventListener(type, function (ev) {
            try {
              var dev = ev && ev.device;
              patchDevice(dev);
              emit({
                dir: 'event',
                phase: 'call',
                method: type,
                data: null,
                device: describeDevice(dev),
                collections: describeCollections(dev),
                caller: callerStack(),
              });
            } catch (e) { H.errors.push('hidEvent(' + type + '): ' + errText(e)); }
          });
        })(pairs[i][0]);
      }
    } catch (e) {
      H.errors.push('installHidEvents: ' + errText(e));
    }
  }

  function wrapHidMethod(hid, name) {
    try {
      var orig = hid[name];
      if (typeof orig !== 'function' || isWrapped(orig)) return;

      var wrapper = function () {
        /*__ajazz_hook__*/   // 标记：页面/测试脚本可用它判断「已被包装」
        var self = this;
        var args = arguments;
        var options = args[0];
        var t0 = nowMs();
        var caller = callerStack();
        var filters = null;
        if (name === 'requestDevice' && options && typeof options === 'object') {
          filters = safeJson({ filters: options.filters, exclusionFilters: options.exclusionFilters });
        }

        emit({ dir: 'hid', phase: 'call', method: name, reportId: null, data: null,
               device: null, collections: null, caller: caller, filters: filters });

        var ret;
        try {
          ret = Reflect.apply(orig, self, args);
        } catch (err) {
          emit({ dir: 'hid', phase: 'error', method: name, data: null, caller: caller,
                 filters: filters, error: errText(err), durationMs: round3(nowMs() - t0) });
          throw err;
        }

        // 结果里的设备立刻打补丁（我们的 then 先注册，先于页面 await 的续体执行）
        var applyAndLog = function (devices) {
          patchDeviceList(devices);
          emit({ dir: 'hid', phase: 'ok', method: name, data: null, caller: caller,
                 filters: filters, devices: summarizeDevices(devices),
                 durationMs: round3(nowMs() - t0) });
          return devices;
        };
        var logErr = function (err) {
          emit({ dir: 'hid', phase: 'error', method: name, data: null, caller: caller,
                 filters: filters, error: errText(err), durationMs: round3(nowMs() - t0) });
          throw err;
        };

        if (ret && typeof ret.then === 'function') {
          try { ret.then(applyAndLog, logErr); } catch (e) { /* 忽略 */ }
          return ret;
        }
        return applyAndLog(ret);
      };

      try {
        nativeDefineProperty(wrapper, 'name', { value: name, configurable: true });
        nativeDefineProperty(wrapper, 'length', { value: orig.length, configurable: true });
      } catch (e) { /* 忽略 */ }

      nativeDefineProperty(hid, name, {
        value: markWrapped(wrapper),
        writable: true,
        configurable: true,
        enumerable: false,
      });
    } catch (e) {
      H.errors.push('wrapHidMethod(' + name + '): ' + errText(e));
    }
  }

  function wrapHid(hid) {
    try {
      if (!hid || (typeof hid !== 'object' && typeof hid !== 'function')) return hid;
      if (hid[HID_WRAPPED]) return hid;
      nativeDefineProperty(hid, HID_WRAPPED, { value: true, configurable: true });
      H.hidWrapped = true;
      patchHidDevicePrototype();
      wrapHidMethod(hid, 'getDevices');
      wrapHidMethod(hid, 'requestDevice');
      installHidEvents(hid);
      return hid;
    } catch (e) {
      H.errors.push('wrapHid: ' + errText(e));
      return hid;
    }
  }

  /* =======================================================================
   * 8. 让「页面后定义的 navigator.hid」也能被接管
   *    - 真 Chrome：navigator.hid 是 Navigator.prototype 上的 getter，直接包装即可；
   *    - 伪造页（测试页）：页面会用 Object.defineProperty 覆盖 navigator.hid，
   *      这里包装 Object.defineProperty / defineProperties / Reflect.defineProperty
   *      在定义发生的那一刻就把值包好，保证页面脚本第一眼看到的就是包装后的对象。
   * ===================================================================== */
  function isNavigatorTarget(t) {
    try {
      if (t === navigator) return true;
      if (typeof Navigator !== 'undefined' && t === Navigator.prototype) return true;
      return false;
    } catch (e) { return false; }
  }

  function cloneDescriptor(desc) {
    var out = {};
    var keys = ['value', 'writable', 'get', 'set', 'enumerable', 'configurable'];
    for (var i = 0; i < keys.length; i++) {
      try { if (desc[keys[i]] !== undefined) out[keys[i]] = desc[keys[i]]; } catch (e) {}
    }
    return out;
  }

  /** 把描述符里的 hid 值 / hid getter 包装后再交给原生 defineProperty */
  function prepareHidDescriptor(desc) {
    try {
      if (!desc || typeof desc !== 'object') return desc;
      var d = cloneDescriptor(desc);
      if ('value' in d) {
        if (d.value) d.value = wrapHid(d.value);
      } else if (typeof d.get === 'function' && !isWrapped(d.get)) {
        var origGet = d.get;
        d.get = markWrapped(function () { return wrapHid(origGet.call(this)); });
      }
      return d;
    } catch (e) {
      H.errors.push('prepareHidDescriptor: ' + errText(e));
      return desc;
    }
  }

  function installDefinePropertyTrap() {
    try {
      var patchedDefineProperty = function defineProperty(target, prop, desc) {
        try {
          if (prop === 'hid' && isNavigatorTarget(target)) desc = prepareHidDescriptor(desc);
        } catch (e) { /* 忽略 */ }
        return nativeDefineProperty(target, prop, desc);
      };
      markWrapped(patchedDefineProperty);
      Object.defineProperty = patchedDefineProperty;

      var patchedDefineProperties = function defineProperties(target, props) {
        try {
          if (props && typeof props === 'object' && isNavigatorTarget(target) && 'hid' in props) {
            var copy = {};
            for (var k in props) {
              if (!Object.prototype.hasOwnProperty.call(props, k)) continue;
              copy[k] = (k === 'hid') ? prepareHidDescriptor(props[k]) : props[k];
            }
            return nativeDefineProperties(target, copy);
          }
        } catch (e) { /* 忽略 */ }
        return nativeDefineProperties(target, props);
      };
      markWrapped(patchedDefineProperties);
      Object.defineProperties = patchedDefineProperties;

      if (typeof nativeReflectDefineProperty === 'function') {
        var patchedReflect = function defineProperty(target, prop, desc) {
          try {
            if (prop === 'hid' && isNavigatorTarget(target)) desc = prepareHidDescriptor(desc);
          } catch (e) { /* 忽略 */ }
          return nativeReflectDefineProperty(target, prop, desc);
        };
        markWrapped(patchedReflect);
        Reflect.defineProperty = patchedReflect;
      }
    } catch (e) {
      H.errors.push('installDefinePropertyTrap: ' + errText(e));
    }
  }

  /** 给 navigator 装一个 hid 槽位：既接管赋值，也保留原生值 */
  function installHidSlot() {
    var nativeHid = null;
    try { nativeHid = navigator.hid; } catch (e) { nativeHid = null; }
    if (nativeHid) { wrapHid(nativeHid); return; }

    // 原生没有（例如 file:// 下被关闭）——装可写槽位，等页面赋值/defineProperty
    var slot;
    try {
      nativeDefineProperty(navigator, 'hid', {
        configurable: true,
        enumerable: true,
        get: function () { return slot; },
        set: function (v) { slot = wrapHid(v); },
      });
    } catch (e) {
      H.errors.push('installHidSlot: ' + errText(e));
    }
  }

  /* =======================================================================
   * 9. 安装 & 自检
   * ===================================================================== */
  function install() {
    installDefinePropertyTrap();
    installHidSlot();

    // 页面可能在稍后才创建/替换 navigator.hid，做个短周期看门狗兜底
    var ticks = 0;
    var timer = null;
    try {
      timer = setInterval(function () {
        ticks++;
        try {
          var hid = navigator.hid;
          if (hid && !hid[HID_WRAPPED]) wrapHid(hid);
          patchHidDevicePrototype();
        } catch (e) { /* 忽略 */ }
        if (ticks >= 120) { clearInterval(timer); }   // 1 分钟
      }, 500);
    } catch (e) { /* 忽略 */ }

    try {
      document.addEventListener('DOMContentLoaded', function () {
        try {
          var hid = navigator.hid;
          if (hid) wrapHid(hid);
          patchHidDevicePrototype();
        } catch (e) {}
      }, true);
    } catch (e) {}

    // 安装自检记录：JSONL 里出现这条说明注入成功
    emit({
      dir: 'meta', phase: 'ok', method: 'hook-installed', data: null,
      device: null, collections: null, caller: null,
      extra: {
        hookVersion: HOOK_VERSION,
        href: (function () { try { return location.href; } catch (e) { return null; } })(),
        webhid: !!navigator.hid,
        secure: (function () { try { return isSecureContext; } catch (e) { return null; } })(),
        userAgent: (function () { try { return navigator.userAgent; } catch (e) { return null; } })(),
        hidCtor: typeof window.HIDDevice,
      },
    });
  }

  /* 调试/取证用的便利函数（页面和 --eval 里都能用） */
  window.__ajazzSnapshot = function () { return H.log.slice(); };
  window.__ajazzDump = function () { return JSON.stringify(H.log); };
  window.__ajazzState = function () {
    return {
      version: H.version,
      seq: H.seq,
      hidWrapped: H.hidWrapped,
      devicesPatched: H.devicesPatched,
      pending: H.pending.length,
      errors: H.errors.slice(),
    };
  };

  try {
    install();
  } catch (e) {
    try {
      emit({ dir: 'meta', phase: 'error', method: 'hook-install', error: errText(e) });
    } catch (e2) { /* 页面级异常一律吞掉 */ }
  }
})();
