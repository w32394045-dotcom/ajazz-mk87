# -*- coding: utf-8 -*-
"""Phase 5：音乐律动真机链路（WAV → 官方算法/渲染器 → 0x32 帧流 → 键盘）

用法:
  python phase5_music.py <frames.json> [--mode 128] [--loop 1] [--speed 1.0]

流程：
  1. LED 效果切到 mode=128（自定义族）——这是实测的「帧流可显示」激活条件
  2. 按 fps 节奏把 JSON 里的每帧 7 个包发给设备（逐包等 ACK，超时 40ms 不阻塞）
  3. 每 10 帧回读一次 GET_ALL_LIGHTS_RGB，验证设备缓冲确实跟着帧变
  4. 结束不恢复（固件 5 秒后自动回落到自定义表）；打印统计
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)


def read_all(kb):
    d = kb.read_all_lights_rgb()
    return [(d[i * 4], d[i * 4 + 1], d[i * 4 + 2], d[i * 4 + 3])
            for i in range(min(128, len(d) // 4))]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1]
    mode = 128
    loop = 1
    speed = 1.0
    for i, a in enumerate(sys.argv):
        if a == '--mode':
            mode = int(sys.argv[i + 1])
        elif a == '--loop':
            loop = int(sys.argv[i + 1])
        elif a == '--speed':
            speed = float(sys.argv[i + 1])
    data = json.load(open(path, encoding='utf-8'))
    frames = data['frames']
    fps = data.get('fps', 20)
    interval = 1.0 / fps

    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'file': os.path.basename(path),
           'mode': mode, 'fps': fps, 'n_frames': len(frames), 'loop': loop}
    try:
        orig = bytes(kb.get_led_effect()['raw'])
        # 激活：切到自定义族模式（20/21/128），亮度拉满
        p = bytearray(16)
        p[0] = mode
        p[1:4] = b'\xFF\xFF\xFF'
        p[4] = 0xFF
        p[8] = 1
        p[9] = 6
        p[10] = 3
        p[14] = 0xAA
        p[15] = 0x55
        kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)
        time.sleep(0.5)

        t_start = time.time()
        ack_ok = 0
        ack_total = 0
        checks = []
        for lp in range(loop):
            for fi, fr in enumerate(frames):
                for h in fr['packets']:
                    pkt = bytes.fromhex(h)
                    kb.proto.write_report(pkt)
                    ack_total += 1
                    t0 = time.time()
                    got = False
                    while time.time() - t0 < 0.04:
                        r = kb.proto.read_report(timeout=0.005)
                        if not r:
                            continue
                        if len(r) > 2 and r[1] == 0x55 and r[2] == 0x32:
                            got = True
                            break
                    if got:
                        ack_ok += 1
                if fi % 10 == 0:
                    allc = read_all(kb)
                    lit = [x for x in allc if max(x[1], x[2], x[3]) > 0]
                    exp = fr['packets']
                    checks.append({'frame': fi, 'amp': fr['amp'],
                                   'n_lit': len(lit),
                                   'first': lit[:2]})
                target = t_start + (lp * len(frames) + fi + 1) * interval
                dt = target - time.time()
                if dt > 0:
                    time.sleep(dt)
        total = time.time() - t_start
        res['stats'] = {'elapsed': round(total, 2),
                        'fps_actual': round(loop * len(frames) / total, 2),
                        'ack_ok': ack_ok, 'ack_total': ack_total,
                        'checks': checks}
        print('播放 %d 帧 ×%d: %.2fs = %.2f fps, ACK %d/%d'
              % (len(frames), loop, total, loop * len(frames) / total,
                 ack_ok, ack_total))
        for c in checks[:8]:
            print('  帧%3d amp=%4d 点亮 %2d 颗 前2=%s'
                  % (c['frame'], c['amp'], c['n_lit'], c['first']))
        amps = [f['amp'] for f in frames]
        print('振幅: max=%d 有声帧=%d/%d' % (max(amps), sum(1 for a in amps if a > 0),
                                          len(amps)))
        kb.request(CMD['SET_LED_EFFECT'], orig, content_size=16)
        res['restored'] = bytes(kb.get_led_effect()['raw']) == orig
        print('已恢复原灯效:', res['restored'])
    finally:
        kb.close()
        out = os.path.join(ROOT, 'docs', 'phase5_music.json')
        json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved', out)


if __name__ == '__main__':
    main()
