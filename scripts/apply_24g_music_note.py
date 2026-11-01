# -*- coding: utf-8 -*-
"""把「官方确认 2.4G 不支持音乐律动」写回文档（2026-11-01）"""
import os

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')


def read(f):
    return open(os.path.join(DOCS, f), encoding='utf-8').read()


def write(f, s):
    open(os.path.join(DOCS, f), 'w', encoding='utf-8').write(s)


def replace_once(f, old, new):
    s = read(f)
    if old in s:
        write(f, s.replace(old, new, 1))
        print('[OK]', f, '|', old[:40])
    else:
        print('[MISS]', f, '|', old[:40])


def append(f, text, marker):
    s = read(f)
    if marker in s:
        print('[SKIP]', f)
        return
    write(f, s.rstrip('\n') + text)
    print('[APPEND]', f)


# 1) TEST-REPORT：§8.3 结论改为「官方确认不支持」
replace_once('TEST-REPORT.md',
             '- 结论：**2.4G 逐键帧流的正确格式未还原**（⬜ 待解，需要 Music.exe 协议或 2.4G 抓包）；\n'
             '  影响面：仅「2.4G 下自研音乐律动」，USB 下已完整可用',
             '- **结论（2026-11-01 更新）：官方明确表示 2.4G 模式不支持音乐律动** —— 与真机现象一致：\n'
             '  帧数据虽被通道接收，但固件没有合法的 2.4G 帧映射（表现为短暂白脉冲/随机色/竖条纹）。\n'
             '  ⇒ 该项由「⬜ 待解」改为 **⛔ 设备不支持**；自研音乐律动工具**仅走 USB 模式**（USB 下已完整验证）。')

# 2) TEST-REPORT：§13 第 2 条改为已关闭
replace_once('TEST-REPORT.md',
             '| 2 | 2.4G 逐键帧流格式 | 三种官方分支都出现「乱色/竖条纹」，说明数据格式不对 | 抓 Music.exe 的 2.4G HID 流量，或试更多头格式 |',
             '| 2 | ~~2.4G 逐键帧流格式~~ | **已关闭：官方确认 2.4G 不支持音乐律动**（真机异常显示与此一致） | 不做；音乐律动工具强制 USB |')

# 3) TEST-REPORT：一句话结论表同步
replace_once('TEST-REPORT.md',
             '| Phase 6 | 2.4G 无线（身份/通道/灯效/帧流/矩阵） | ✅ 身份与常规命令全通；帧流格式仍有异常（见 §9） |',
             '| Phase 6 | 2.4G 无线（身份/通道/灯效/帧流/矩阵） | ✅ 身份与常规命令全通；⛔ 音乐律动官方确认 2.4G 不支持 |')

# 4) FEATURES：第 23 行
replace_once('FEATURES.md',
             '| 23 | 2.4G 专用命令（0x37/0x3B/0x3C/0xFC） | — | ✅ | 🧪 0xFF60 通道常规命令全通；**逐键帧流格式仍异常**（见报告 §8.3） | [wireless-constants.json](wireless-constants.json) |',
             '| 23 | 2.4G 专用命令（0x37/0x3B/0x3C/0xFC） | — | ✅ | 🧪 0xFF60 通道常规命令全通；**音乐律动：官方确认 2.4G 不支持**（⛔，帧流仅 USB 可用） | [wireless-constants.json](wireless-constants.json) |')

# 5) FEATURES：能力边界 + 修正记录 + 下一步
replace_once('FEATURES.md',
             '2.4G 无线（0xFF60 通道，配置与 USB 共享，矩阵逐字节一致）。',
             '2.4G 无线（0xFF60 通道，配置与 USB 共享，矩阵逐字节一致；**音乐律动仅 USB，官方确认 2.4G 不支持**）。')
replace_once('FEATURES.md',
             '18. **2.4G dongle 与键盘 USB 同插会触发 Windows 0xC000009A（资源不足）**，拔掉其一即恢复；不是固件问题。',
             '18. **2.4G dongle 与键盘 USB 同插会触发 Windows 0xC000009A（资源不足）**，拔掉其一即恢复；不是固件问题。\n'
             '19. **官方确认 2.4G 模式不支持音乐律动**（用户转述官方说明）：真机三种帧格式均只产生「短暂白脉冲/随机色/竖条纹」，\n'
             '    与「通道收到数据但固件无 2.4G 帧映射」一致 → 该项从「待还原」改为 **⛔ 设备不支持**，自研音乐律动只做 USB。')
replace_once('FEATURES.md',
             '剩余项见 [TEST-REPORT.md](TEST-REPORT.md) §13：\n宏写入编码、2.4G 帧流格式（需 Music.exe 协议/抓包）、2.4G 休眠通知、12/24h 重启验证、97/98 LED 物理定位。',
             '剩余项见 [TEST-REPORT.md](TEST-REPORT.md) §13：\n宏写入编码、2.4G 休眠通知、12/24h 重启验证、97/98 LED 物理定位（2.4G 音乐律动已确认不支持，关闭）。')

# 6) 无线文档
append('wireless-profiles-led-animation.md', '''

### 2026-11-01 补充：官方确认 2.4G 不支持音乐律动

用户转述官方说明：**2.4G 模式下不支持音乐律动**。与真机现象一致（三种帧格式都只出现
「短暂白脉冲 / 随机色 / 竖条纹」，属于通道收了数据但固件没有合法 2.4G 帧映射）。
⇒ 自研音乐律动工具**只做 USB 模式**；2.4G 仅支持常规灯效/自定义灯/改键/设置。
''', '官方确认 2.4G 不支持音乐律动')

# 7) 音乐文档
append('music-rhythm.md', '''

### ⛔ 2.4G 分支（2026-11-01 更新）

**官方确认 2.4G 模式不支持音乐律动**。真机在 MK87 dongle（0xFF60，32B 报文）上试了三种官方打包
（cmd 0x32 4B/键、cmd 0x35 RGB565 28B/包、cmd 0x3C RGB565 走 0xFF59 64B 接口），
都只出现「短暂白脉冲 / 随机色 / 竖条纹」，没有任何一种能正确显示。
⇒ 自研音乐律动**只走 USB**（USB 下 cmd 0x32 + mode 20/21/128 已完整验证，见 §9）。
''', '2.4G 模式不支持音乐律动')

print('done')
