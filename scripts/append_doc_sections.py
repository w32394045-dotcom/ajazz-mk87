# -*- coding: utf-8 -*-
"""向 protocol.md / wireless-profiles-led-animation.md 追加真机实测补充章节。"""
import os

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')

PROTO = '''

---

## 10. 真机实测补充（2026-11-01，详见 [TEST-REPORT.md](TEST-REPORT.md)）

- **写命令 ACK = 原样回显所发 payload**（含 TFT 上传的 4096 字节数据包）；
  `SET_TFT_MATERIAL(0x4D)` 与 `SET_TFT_USER_ANIMATION(0x50)` 的逐包 ACK 都是 **0x41**。
- `GET_LED_DATA(0x32)` 写入的是**逐键 LED 缓冲**：发帧后 `GET_ALL_LIGHTS_RGB(0x33)` 可读回帧颜色；
  0x32 的响应数据是「回显请求数据」，不是设备状态。
- 帧流展示前必须 `SET_LED_EFFECT` 切到 **mode 20/21/128**；停帧约 5s 回落。
- 常规写包耗时：主协议 64B 包约 1–2 ms；TFT 4105B 包约 65 ms（USB FS 64B/ms 上限，实测吞吐约 63 KB/s）。
- 2.4G：协议口为 usagePage **0xFF60**（33B 报文）；0xFF59（65B）无响应且不在官方过滤器表。
'''

WIRELESS = '''

---

## 真机实测结果（2026-11-01）

- 接收器 = `VID 0C45 / PID FEFE`，product string "2.4G Dongle"；
  `GET_DEVICE_INFO` 回 `manufacturer=1, product=18, workMode=2, fw=1.19, battery 73%, charge=1`
  → 与静态还原的 `3141-65278-2.4G Dongle-1-18` 完全命中。
- 可用协议接口 = **MI_03 / usagePage 0xFF60 / 33B 报文**（官方过滤器表包含 0xFF60）；
  MI_04 / 0xFF59 / 65B 对 GET 命令**无响应**、且**不在**官方过滤器表
  `[65384, 65408, 65376, 65280, 65281, 65307]`。
- 2.4G 下 `GET_KEY`/`GET_FN_KEY` 与 USB 时代 dump **逐字节一致**（配置存在键盘端，双通道共享）。
- 2.4G 写灯效生效；但 `SET_LED_EFFECT` 的**颜色 / colorMode 回读可能不等于写入**（显示正确）
  → 回读不能作为 2.4G 写成功判据。
- 逐键帧流：三种官方打包分支（0x32 / 0x35 / 0x3C）在 MK87 2.4G 下都出现
  「短暂白脉冲 + 随机色 + 竖条纹」→ 通道收到了帧数据但**格式/映射不对**，未还原
  （官方逻辑本身要求 `reportCount=64 && lightingVersion=1`，MK87 两者都不满足）。
- **Windows 兼容**：dongle 与键盘 USB 同插会报 Code 10 / **0xC000009A
  (STATUS_INSUFFICIENT_RESOURCES)**，拔掉其一即恢复；不是固件问题，
  建议两设备插不同 USB 控制器。

详见 [TEST-REPORT.md](TEST-REPORT.md) §8。
'''


def main():
    for fname, add, marker in (
        ('protocol.md', PROTO, '真机实测补充'),
        ('wireless-profiles-led-animation.md', WIRELESS, '真机实测结果'),
    ):
        path = os.path.join(DOCS, fname)
        s = open(path, encoding='utf-8').read()
        if marker in s:
            print('[SKIP]', fname)
            continue
        open(path, 'w', encoding='utf-8').write(s.rstrip('\n') + add)
        print('[OK] appended ->', fname)


if __name__ == '__main__':
    main()
