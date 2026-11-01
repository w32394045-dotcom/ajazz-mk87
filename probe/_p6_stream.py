# -*- coding: utf-8 -*-
"""2.4G 音乐帧：三种打包各连续推 5 秒（不同颜色），用于人眼判定哪条通道生效。

  B: cmd 0x35，4 字节头 AA 35 seq i，28 字节/包，RGB565 → 绿色
  C: cmd 0x3C，8 字节标准头，56 字节/包（走 0xFF59 64B 接口），RGB565 → 蓝色
  D: cmd 0x32，8 字节标准头，24 字节/包（0xFF60 32B 接口），4B/键 → 红色

用法: python _p6_stream.py [每段秒数=5]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import CMD  # noqa: E402
from phase4_frames import key_order  # noqa: E402
from _p6_variants import open_wireless, set_custom_mode, build_pkt  # noqa: E402

FPS = 20


def rgb565_stream(order, rgb):
    out = bytearray()
    r, g, b = rgb
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
    for _ in order:
        out += bytes([(v >> 8) & 0xFF, v & 0xFF])
    return bytes(out)


def payload4(order, rgb):
    r, g, b = rgb
    out = bytearray()
    for kv in order:
        out += bytes([kv, r, g, b])
    return bytes(out)


def pkts_for(iface, kind, data):
    rep = iface.out_len - 1
    if kind == 'B':
        n = rep - 4
        total = -(-len(data) // n)
        return [build_pkt(rep, bytes([0xAA, CMD['SET_MUSIC_DATA'], k & 0xFF, 0]),
                          data[k * n:(k + 1) * n]) for k in range(total)]
    if kind == 'C':
        n = rep - 8
        total = -(-len(data) // n)
        return [build_pkt(rep, bytes([0xAA, CMD['SET_MUSIC_DATA_24G_64_BYTE'],
                                      len(data[k * n:(k + 1) * n]) & 0xFF,
                                      (k * n) & 0xFF, (k * n) >> 8, 0,
                                      1 if k == total - 1 else 0]),
                          data[k * n:(k + 1) * n]) for k in range(total)]
    n = rep - 8
    total = -(-len(data) // n)
    return [build_pkt(rep, bytes([0xAA, CMD['GET_LED_DATA'],
                                  len(data[k * n:(k + 1) * n]) & 0xFF,
                                  (k * n) & 0xFF, (k * n) >> 8, 0,
                                  1 if k == total - 1 else 0]),
                      data[k * n:(k + 1) * n]) for k in range(total)]


def stream(iface, kind, data, seconds, label):
    pkts = pkts_for(iface, kind, data)
    print('  变体 %s: %d 包/帧 → %s 接口推 %.0f 秒' %
          (kind, len(pkts), '0xFF59' if iface.out_len == 65 else '0xFF60', seconds))
    t0 = time.time()
    n = 0
    frames = 0
    while time.time() - t0 < seconds:
        for p in pkts:
            iface.write_report(p)
            n += 1
        frames += 1
        target = t0 + frames / FPS
        dt = target - time.time()
        if dt > 0:
            time.sleep(dt)
    print('  共 %d 帧 %d 包, 实际 %.1f fps' %
          (frames, n, frames / (time.time() - t0)))


def main():
    sec = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    kb, proto64 = open_wireless()
    order = key_order()
    try:
        set_custom_mode(kb)
        time.sleep(0.4)
        print('[1/3] 绿色 = 0x35 通用分支')
        stream(kb.proto, 'B', rgb565_stream(order, (0, 255, 0)), sec, 'B')
        time.sleep(0.5)
        print('[2/3] 蓝色 = 0x3C 64 字节接口')
        if proto64:
            stream(proto64, 'C', rgb565_stream(order, (0, 0, 255)), sec, 'C')
        else:
            print('  没有 0xFF59 接口，跳过')
        time.sleep(0.5)
        print('[3/3] 红色 = 0x32 逐键帧')
        stream(kb.proto, 'D', payload4(order, (255, 0, 0)), sec, 'D')
        print('\n>>> 键盘刚才若出现过颜色，请对应：绿=0x35 / 蓝=0x3C / 红=0x32 <<<')
    finally:
        kb.close()


if __name__ == '__main__':
    main()
