# -*- coding: utf-8 -*-
"""Phase 4：逐键实时帧流（cmd 0x32 GET_LED_DATA，官方 setMusicData USB 分支）

用法:
  python phase4_frames.py allred     # 87 键全红 1 帧
  python phase4_frames.py esc        # 只把 Esc(第0个可见键) 点白，其余黑
  python phase4_frames.py rainbow    # 按行渐变一帧
  python phase4_frames.py stream     # 20fps 连续 10 秒渐变（测帧率/稳定性）
  python phase4_frames.py probe      # 只发 1 包，测 ACK 命令字与延迟

每包：report[0]=0, [1]=0xAA,[2]=0x32,[3]=len,[4..5]=addr(LE),[6]=i(0),[7]=last,[8]=0，数据从 [9] 开始
载荷：87 键 × 4 字节 [keyValue, r, g, b]，顺序 = 官方 keyList 行优先（见 docs/music-rhythm.md §5.4）
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard  # noqa: E402

ROOT = os.path.dirname(HERE)
LIGHT = os.path.join(ROOT, 'docs', 'lighting-modes.json')


def key_order():
    """官方 keyList 行优先展平 -> 87 个 keyValue（= 矩阵槽 = ledId）"""
    d = json.load(open(LIGHT, encoding='utf-8'))
    rows = d['ledKeyMap']['rowsInPreview']
    order = []
    for r in rows:
        for k in r['keys']:
            order.append(k['ledId'])
    return order


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


def pack_frame(payload, report_payload=64, i=0):
    chunk = report_payload - 8
    total = (len(payload) + chunk - 1) // chunk or 1
    pkts = []
    for k in range(total):
        addr = k * chunk
        part = payload[addr:addr + chunk]
        pkt = bytearray(report_payload + 1)
        pkt[0] = 0
        pkt[1] = 0xAA
        pkt[2] = 0x32
        pkt[3] = len(part) & 0xFF
        pkt[4] = addr & 0xFF
        pkt[5] = (addr >> 8) & 0xFF
        pkt[6] = i & 0xFF
        pkt[7] = 1 if k == total - 1 else 0
        pkt[8] = 0
        pkt[9:9 + len(part)] = part
        pkts.append(bytes(pkt))
    return pkts


def wait_ack(kb, cmd=0x32, timeout=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = kb.proto.read_report(timeout=0.01)
        if not r:
            continue
        p = r[1:]
        if len(p) >= 2 and p[0] == 0x55:
            return True, round((time.time() - t0) * 1000, 2), bytes(p[:12])
    return False, round((time.time() - t0) * 1000, 2), None


def send_frame(kb, payload, wait=True, timeout=0.2):
    pkts = pack_frame(payload)
    rows = []
    t0 = time.time()
    for k, pkt in enumerate(pkts):
        kb.proto.write_report(pkt)
        if wait:
            ok, ms, resp = wait_ack(kb, timeout=timeout)
            rows.append({'seq': k, 'ack': ok, 'ms': ms, 'resp': hx(resp) if resp else None})
    return rows, round((time.time() - t0) * 1000, 2), len(pkts)


def payload_from_colors(order, fn):
    buf = bytearray()
    for idx, kv in enumerate(order):
        r, g, b = fn(idx, kv)
        buf += bytes([kv & 0xFF, r & 0xFF, g & 0xFF, b & 0xFF])
    return bytes(buf)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    order = key_order()
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'action': action,
           'n_keys': len(order), 'order': order}
    try:
        if action == 'probe':
            payload = payload_from_colors(order, lambda i, k: (255, 255, 255))
            pkts = pack_frame(payload)
            kb.proto.write_report(pkts[0])
            ok, ms, resp = wait_ack(kb, timeout=1.5)
            res['probe'] = {'ack': ok, 'ms': ms, 'resp': hx(resp) if resp else None,
                            'pkt0': hx(pkts[0][:24])}
            print('probe: ack=%s %.2fms resp=%s' % (ok, ms, hx(resp) if resp else None))
            print('  pkt0:', hx(pkts[0][:24]))
        elif action == 'allred':
            payload = payload_from_colors(order, lambda i, k: (255, 0, 0))
            rows, ms, n = send_frame(kb, payload)
            res['frame'] = {'packets': rows, 'total_ms': ms, 'n': n}
            print('allred: %d 包, 总 %s ms, ACK %d/%d'
                  % (n, ms, sum(1 for r in rows if r['ack']), n))
            print('  各包 ACK:', [(r['seq'], r['ack'], r['ms']) for r in rows])
        elif action == 'esc':
            payload = payload_from_colors(
                order, lambda i, k: (255, 255, 255) if i == 0 else (0, 0, 0))
            rows, ms, n = send_frame(kb, payload)
            res['frame'] = {'packets': rows, 'total_ms': ms, 'n': n}
            print('esc: %d 包 %s ms ACK %d/%d' % (n, ms,
                                                sum(1 for r in rows if r['ack']), n))
        elif action == 'rainbow':
            payload = payload_from_colors(order, lambda i, k: (
                (i * 37) & 0xFF, (i * 91) & 0xFF, (i * 53) & 0xFF))
            rows, ms, n = send_frame(kb, payload)
            res['frame'] = {'packets': rows, 'total_ms': ms, 'n': n}
            print('rainbow: %d 包 %s ms ACK %d/%d' % (n, ms,
                                                     sum(1 for r in rows if r['ack']), n))
        elif action == 'stream':
            frames = int(sys.argv[2]) if len(sys.argv) > 2 else 200
            fps = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
            lat = []
            ack_ok = 0
            t0 = time.time()
            for f in range(frames):
                phase = f / 20.0
                payload = payload_from_colors(order, lambda i, k, p=phase: (
                    int(127 + 127 * __import__('math').sin(p + i * 0.2)),
                    int(127 + 127 * __import__('math').sin(p * 1.3 + i * 0.3)),
                    int(127 + 127 * __import__('math').sin(p * 0.7 + i * 0.1))))
                rows, ms, n = send_frame(kb, payload, wait=True, timeout=0.12)
                ack_ok += sum(1 for r in rows if r['ack'])
                lat.append(ms)
                target = t0 + (f + 1) / fps
                if time.time() < target:
                    time.sleep(target - time.time())
            total = time.time() - t0
            res['stream'] = {'frames': frames, 'fps_target': fps,
                             'elapsed': round(total, 2),
                             'avg_frame_ms': round(sum(lat) / len(lat), 1),
                             'max_frame_ms': max(lat), 'ack_ok': ack_ok,
                             'ack_total': frames * 7}
            print('stream: %d 帧 / %.2fs = %.1f fps; 平均帧 %sms 最大 %sms; ACK %d/%d'
                  % (frames, total, frames / total, res['stream']['avg_frame_ms'],
                     max(lat), ack_ok, frames * 7))
    finally:
        kb.close()
        out = os.path.join(ROOT, 'docs', 'phase4_frames.json')
        old = {'runs': []}
        if os.path.exists(out):
            try:
                old = json.load(open(out, encoding='utf-8'))
            except Exception:  # noqa: BLE001
                pass
        runs = old.get('runs', []) if isinstance(old, dict) else old
        runs.append(res)
        json.dump({'runs': runs}, open(out, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        print('saved', out)


if __name__ == '__main__':
    main()
