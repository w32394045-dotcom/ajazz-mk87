#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tft_upload_gif.py —— 把 GIF 推到 MK87 的 240×135 TFT 屏（走官方同款「用户动画」通道）
协议来源：docs/tft-page.md / docs/tft-constants.json（官方 setTftUserAnimation = cmd 0x50）

流程：
  GIF → 拆帧(≤140) → 240×135 cover 缩放 → RGB565(按 tftColorByteOrder)
      → 256B 延时表(单位 2ms, 厘秒×5) + 帧数据拼接
      → MI_03 TFT 通道（usagePage 0xFF67），4104B 报文 = 8B 自定义头 + 4096B 数据
      → 每包等 ACK cmd=0x41（自适应：前 10 包都没 ACK 就改为不等，避免卡死）

用法：
  python tft_upload_gif.py "C:\\path\\to\\anim.gif"
  python tft_upload_gif.py "anim.gif" --max-frames 60
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz  # noqa: E402

from PIL import Image, ImageSequence  # noqa: E402

W, H = 240, 135
MAX_FRAMES_DEFAULT = 140
CMD_TFT_USER_ANIMATION = 0x50
ACK_CMD = 0x41  # 官方 responseCmd = SET_LED_USER_ANIMATION


def load_gif(path, max_frames=MAX_FRAMES_DEFAULT, byte_order=0):
    im = Image.open(path)
    frames, delays, src_sizes = [], [], set()
    for frame in ImageSequence.Iterator(im):
        if len(frames) >= max_frames:
            break
        src_sizes.add(frame.size)
        f = frame.convert('RGB')
        sw, sh = f.size
        scale = max(W / sw, H / sh)
        nw = max(1, int(round(sw * scale)))
        nh = max(1, int(round(sh * scale)))
        f = f.resize((nw, nh), Image.LANCZOS)
        left = (nw - W) // 2
        top = (nh - H) // 2
        f = f.crop((left, top, left + W, top + H))
        px = f.tobytes()
        buf = bytearray(W * H * 2)
        for i in range(W * H):
            r, g, b = px[3 * i], px[3 * i + 1], px[3 * i + 2]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
            hi, lo = (v >> 8) & 0xFF, v & 0xFF
            if byte_order == 1:
                buf[2 * i], buf[2 * i + 1] = hi, lo
            else:
                buf[2 * i], buf[2 * i + 1] = lo, hi
        frames.append(bytes(buf))
        d = frame.info.get('duration') or 50
        delays.append(max(1, int(round(d / 10.0))))  # 毫秒 → 厘秒(10ms)
    return frames, delays, src_sizes, getattr(im, 'n_frames', len(frames))


def build_delay_table(delays):
    """官方 MV(): [0]=帧数, [1..n-1]=min(delay_cs*5,255), [n]=0, 其余 255"""
    n = len(delays)
    mv = bytearray([255] * 256)
    mv[0] = n & 0xFF
    for i in range(n - 1):
        mv[i + 1] = min(delays[i] * 5, 255)
    mv[n] = 0
    return bytes(mv)


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print('用法: python tft_upload_gif.py <gif> [--max-frames N]')
        return 1
    gif = args[0]
    max_frames = MAX_FRAMES_DEFAULT
    if '--max-frames' in args:
        max_frames = int(args[args.index('--max-frames') + 1])

    print(f'== GIF: {gif}')
    print(f'   文件大小: {os.path.getsize(gif) / 1024 / 1024:.2f} MB')

    kb = ajazz.AjazzKeyboard()
    try:
        info = kb.get_device_info()
        byte_order = info.get('tftColorByteOrder', 0)
        print(f'== 设备: fw={info["version"]} tftMaxFrames={info["tftMaxFrames"]} '
              f'tftDirection={info["tftDirection"]} tftColorByteOrder={byte_order}')
        tft = kb.tft
        if tft is None:
            print('!! 没找到 TFT 接口 (usagePage 0xFF67)，检查键盘是否连 USB')
            return 2
        print(f'== TFT 接口: {tft.mi} usagePage=0x{tft.usage_page:04X} '
              f'in={tft.in_len} out={tft.out_len}')

        n_cap = min(max_frames, info['tftMaxFrames'] or max_frames)
        print(f'== 解码 GIF（最多 {n_cap} 帧, RGB565 byteOrder={byte_order}) ...')
        t0 = time.time()
        frames, delays, sizes, n_total = load_gif(gif, n_cap, byte_order)
        print(f'   源尺寸: {sizes}  源帧数: {n_total}  实际取: {len(frames)} 帧 '
              f'({time.time() - t0:.1f}s)')
        print(f'   延时(厘秒): {delays[:12]}{" ..." if len(delays) > 12 else ""}')
        if len(frames) == 0:
            print('!! 没有可用帧')
            return 2

        mv = build_delay_table(delays)
        data = bytes(mv) + b''.join(frames)
        print(f'== 载荷: 延时表 256B + 像素 {len(data) - 256}B = {len(data)}B')

        body = tft.out_len - 1          # 4104
        chunk = body - 8                # 4096
        total = (len(data) + chunk - 1) // chunk
        print(f'== 分包: {total} 包（每包 4096B 数据, 4104B 报文）')

        acks = 0
        misses = 0
        others = 0
        latencies = []
        wait_ack = True
        t_start = time.time()

        for seq in range(total):
            part = data[seq * chunk:(seq + 1) * chunk]
            hdr = bytes([0xAA, CMD_TFT_USER_ANIMATION,
                         seq & 0xFF, (seq >> 8) & 0xFF,
                         total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
            pkt = bytearray([0]) + bytearray(body)   # report ID 0 + 4104 字节
            pkt[1:9] = hdr
            pkt[9:9 + len(part)] = part

            t0 = time.time()
            tft.write_report(bytes(pkt))

            if wait_ack:
                matched = False
                deadline = t0 + 0.5
                while time.time() < deadline:
                    r = tft.read_report(timeout=max(0.01, deadline - time.time()))
                    if not r:
                        break
                    payload = r[1:]
                    if len(payload) >= 2 and payload[0] == 0x55 and payload[1] == ACK_CMD:
                        matched = True
                        acks += 1
                        latencies.append((time.time() - t0) * 1000)
                        break
                    others += 1
                    if others <= 5:
                        print(f'   [非 ACK 帧] {payload[:20].hex(" ")}')
                if not matched:
                    misses += 1
                    if acks == 0 and misses >= 10:
                        wait_ack = False
                        print('   [警告] 前 10 包都没有 ACK，切换为「不等 ACK」模式继续发送')

            if seq % 100 == 0 or seq == total - 1:
                pct = (seq + 1) * 100 // total
                print(f'   包 {seq + 1}/{total} ({pct}%)  ack={acks} miss={misses} '
                      f'用时 {time.time() - t_start:.1f}s')

        print(f'== 发送完成: {total} 包, ACK {acks}, 无 ACK {misses}, 其它帧 {others}, '
              f'总用时 {time.time() - t_start:.1f}s')
        if latencies:
            print(f'   ACK 延迟 ms: min={min(latencies):.1f} avg={sum(latencies) / len(latencies):.1f} '
                  f'max={max(latencies):.1f}')

        print('== 收尾：再监听 2 秒 TFT 通道主动帧 ...')
        end = time.time() + 2
        got = 0
        while time.time() < end:
            r = tft.read_report(timeout=0.3)
            if not r:
                continue
            got += 1
            payload = r[1:]
            print(f'   [TFT] {payload[:24].hex(" ")}')
        print(f'   收尾主动帧数: {got}')
        print('\n== 完成。如果屏幕没变化，试试按设备端功能键切到「GIF/用户动画」页（如 Fn+Home）。')
        return 0
    finally:
        kb.close()


if __name__ == '__main__':
    sys.exit(main())
