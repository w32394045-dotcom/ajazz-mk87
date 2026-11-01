# -*- coding: utf-8 -*-
"""把真机测试的修正写回静态文档（一次性脚本，2026-11-01）"""
import os

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')


def patch(fname, pairs):
    path = os.path.join(DOCS, fname)
    s = open(path, encoding='utf-8').read()
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new, 1)
            print('[OK] %s: %s' % (fname, old[:38]))
        else:
            print('[MISS] %s: %s' % (fname, old[:38]))
    open(path, 'w', encoding='utf-8').write(s)


def main():
    # 1) tft-page.md：0x4D 的 ACK 也是 0x41
    patch('tft-page.md', [(
        '壁纸等 `cmd=0x4D`，动画等 `cmd=0x41`（不是 0x50！）',
        '壁纸等 `cmd=0x4D`，动画等 `cmd=0x41`（不是 0x50！）'
        '【**真机修正 2026-11-01**：`0x4D` 的逐包 ACK 实测也是 **0x41**，'
        'fw1.19 对 0x4D/0x50 都回 0x41；且 MK87 无壁纸页，0x4D 写入不可见】',
    ), (
        '## 2. 屏幕显示模式 / 内置页（问题 1）',
        '> 【**真机补充 2026-11-01**】屏幕是**设备端菜单**（旋钮操作）：主页=时钟/电量/状态图标；'
        '设置=灯光效果/灯光颜色/灯光亮度/灯光速率/语言选择；另有自定义动画页。\n'
        '> **没有系统信息页、没有壁纸页**。`SET_TFT_BUILT_IN_INDEX(0x51)` 发 0..5 设备回 ACK 但屏幕不切页。\n'
        '> `tftDisplayTime`（12/24h）写入回读一致，但屏幕时钟格式**无可见变化**（fw1.19）。'
        '详见 [TEST-REPORT.md](TEST-REPORT.md)。\n\n## 2. 屏幕显示模式 / 内置页（问题 1）',
    )])

    # 2) keymap.md：写 0 的真实语义
    patch('keymap.md', [(
        '**一次"应用"就会把这 25 个槽清空**（小键盘整套 + 音量± + 旋钮相关）。',
        '**【真机修正 2026-11-01】写 0 并不会清空这 25 个槽**：fw1.19 会拒绝置零、保持原值'
        '（写非零则生效）；而 keyList 内的槽写 0 = **恢复出厂默认**（例：Insert 写 0 → `02 00 49 00`）。'
        '静态阶段的「会丢小键盘/音量」推断实测不成立，保留原文作对比。',
    )])

    # 3) music-rhythm.md：激活假设已被真机落定（若 §9 还是旧表格则替换）
    path = os.path.join(DOCS, 'music-rhythm.md')
    s = open(path, encoding='utf-8').read()
    if 'H2（主假设' in s or 'H1（主假设）' in s:
        start = s.find('## 9. ')
        end = s.find('## 10. ')
        if start >= 0 and end > start:
            new = ('## 9. 激活 / 退出行为（✅ 真机已测，2026-11-01）\n\n'
                   '真机结论（详见 [TEST-REPORT.md](TEST-REPORT.md) §6）：\n\n'
                   '- **H1 不成立**：灯效 mode=1 时发 0x32 帧无任何显示变化\n'
                   '- **H2 成立**：先 `SET_LED_EFFECT(mode ∈ {20,21,128})`（自定义族），再发帧立即显示\n'
                   '- **H3 成立**：停止发帧约 **5 秒**后自动回落到该模式的自定义表\n'
                   '- 单包 ACK 0.5–3ms；全帧 7 包 + 逐包 ACK = **15.5ms** → **20fps 稳定**（实测 150 帧/7.5s，'
                   '1050/1050 ACK），理论上限约 60fps\n'
                   '- 帧数据写入同一块逐键 LED 缓冲：`GET_ALL_LIGHTS_RGB` 可实时读回（可自动化验证）\n'
                   '- 自研链路已跑通：WAV → 官方 K7/Nse 振幅 → 官方渲染器（13/14/17）→ 0x32 帧流 → 键盘\n\n')
            s = s[:start] + new + s[end:]
            open(path, 'w', encoding='utf-8').write(s)
            print('[OK] music-rhythm.md §9 已替换为真机结论')
    else:
        print('[SKIP] music-rhythm.md §9 已是新版本')

    # 4) lighting.md：亮度/物理槽/自定义族
    patch('lighting.md', [(
        '# MK87 灯效系统逆向（纯静态：bundle + 官方站点 chunk）',
        '# MK87 灯效系统逆向（纯静态：bundle + 官方站点 chunk）\n\n'
        '> 【**真机补充 2026-11-01**】①亮度字段 1..6 为 identity，**brightness=1 = 全灭**'
        '（PWM 0/49/97/143/191/253），越界值未定义（0→255、7→11…），工具应钳 2..6；'
        '②`mode=0` 关灯后 **Fn 键仍亮红灯 = 充电指示灯**（无法用 LED 数据覆盖）；'
        '③**20/21/128 三个自定义族模式共用同一张 SET_CUSTOM_LED_DATA 表**（真机验证）；'
        '④**物理 LED 只有 86 个**：官方 keyList 标有键的 99/100/102 实际无灯（该处是小屏幕），'
        '标无键的 97/98 实际有灯（logo 灯区域）。详见 [TEST-REPORT.md](TEST-REPORT.md)。',
    ), (
        '## 15. ', '## 15. ',
    )])

    # 5) protocol.md：TFT ACK / 0x32 语义
    patch('protocol.md', [(
        '- `SET_TFT_MATERIAL`', '- `SET_TFT_MATERIAL`',
    )])

    # 6) key-events.md：RawInput 结论
    path = os.path.join(DOCS, 'key-events.md')
    s = open(path, encoding='utf-8').read()
    lines = s.split('\n')
    banner = ('> 【**真机补充 2026-11-01**】直接读键盘 HID `\\kbd` 集合（MI_00 / MI_01 COL03）'
              '**CreateFile 失败 err=5 ACCESS_DENIED**（Windows 键盘类保护）；'
              '**Windows RawInput 方案可用**：`RegisterRawInputDevices`(1/6 + 0x0C/1) + 隐藏窗口 WM_INPUT，'
              '实测拿到 `vkey/make/flags/msg`，且 `GetRawInputDeviceInfo` 能取到 '
              '`VID_0C45&PID_8047&MI_00` 设备路径（可过滤本键盘）。RawInput 只给 VKey+MakeCode，'
              '不给 HID usage；要 usage 级映射需自维护 VKey→usage 表（见 §4.3）。')
    if '真机补充' not in s:
        lines.insert(1, '\n' + banner + '\n')
        open(path, 'w', encoding='utf-8').write('\n'.join(lines))
        print('[OK] key-events.md 已补 RawInput 真机结论')


if __name__ == '__main__':
    main()
