# -*- coding: utf-8 -*-
"""恢复屏幕为官方默认动画（AK980_PRO defaultGif.json，135 帧 240×135）

数据来源：https://config.driveall.cn/gif/AK980_PRO/defaultGif.json
（官方 bundle 里 MK87 的 tftConfig.name = AK980_PRO，页面按 /gif/<name>/defaultGif.json 拉默认动画）

顺带验证：135 帧（< tftMaxFrames=140）完整动画上传 + 逐包 ACK，整条官方动画路径。
用法: python restore_tft_default.py [--limit N] [--dry]
输出 docs/restore_tft_default.json
"""
import base64
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard  # noqa: E402
from phase2_tft import upload, hx  # noqa: E402

ROOT = os.path.dirname(HERE)
GIF = os.path.join(ROOT, 'docs', '_default_gif.json')
W, H = 240, 135


def frame_bytes(data_url, byte_order=0, flip_dir=0):
    from PIL import Image
    b64 = data_url.split(',', 1)[1]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    if flip_dir in (1, 2, 3):
        img = img.rotate(90 * flip_dir if flip_dir != 2 else 180, expand=True)
        img = img.resize((W, H), Image.LANCZOS)
    buf = bytearray()
    px = img.load()
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            lo, hi = v & 0xFF, (v >> 8) & 0xFF
            if byte_order == 1:
                buf += bytes([hi, lo])
            else:
                buf += bytes([lo, hi])
    return bytes(buf)


def main():
    dry = '--dry' in sys.argv
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    d = json.load(open(GIF, encoding='utf-8'))
    fd = d['frameData']
    delays = [f.get('delay', 10) for f in fd]
    if limit:
        fd = fd[:limit]
        delays = delays[:limit]
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
           'source': 'defaultGif.json (AK980_PRO)', 'frames': len(fd),
           'delays_cs': delays[:10], 'dry': dry}
    print('默认动画: %d 帧 %dx%d, delay=%s …' % (len(fd), d['width'], d['height'],
                                              delays[:6]))
    kb = AjazzKeyboard()
    try:
        info = kb.get_device_info()
        bo = info.get('tftColorByteOrder', 0)
        print('tftMaxFrames=%d colorByteOrder=%d' % (info['tftMaxFrames'], bo))
        frames = []
        t0 = time.time()
        for i, f in enumerate(fd):
            frames.append(frame_bytes(f['dataUrl'], bo))
            if i % 30 == 0 or i == len(fd) - 1:
                print('  解码 %d/%d (%.1fs)' % (i + 1, len(fd), time.time() - t0),
                      flush=True)
        pixels = b''.join(frames)
        mv = bytearray(256)
        mv[0] = len(delays)
        for i in range(len(delays) - 1):
            mv[i + 1] = min(delays[i] * 5, 255)
        mv[len(delays)] = 0
        data = bytes(mv) + pixels
        res['data_len'] = len(data)
        res['packets'] = (len(data) + 4095) // 4096
        print('总数据 %d 字节 -> %d 包' % (len(data), res['packets']))
        if dry:
            print('--dry：不写入')
            return
        t1 = time.time()

        def prog(k, total):
            if k % 100 == 0 or k == total:
                print('  上传 %d/%d (%.0fs)' % (k, total, time.time() - t1), flush=True)

        rows = upload_with_progress(kb, data, res, prog)
        res['ack_all'] = all(r['ack'] for r in rows)
        res['ack_ok'] = sum(1 for r in rows if r['ack'])
        res['elapsed'] = round(time.time() - t1, 1)
        print('完成: ACK %d/%d, 用时 %.1fs' % (res['ack_ok'], len(rows), res['elapsed']))
    finally:
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', 'restore_tft_default.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved docs/restore_tft_default.json')


def upload_with_progress(kb, data, res, prog):
    """和 phase2_tft.upload 相同，但支持进度回调（逐包打印由 prog 控制）"""
    import time as _t
    from ajazz import CMD
    tft = kb.tft
    cmd = CMD['SET_TFT_USER_ANIMATION']
    ack = CMD['SET_LED_USER_ANIMATION']
    total = (len(data) + 4095) // 4096
    rows = []
    for k in range(total):
        hdr = bytes([0xAA, cmd, k & 0xFF, (k >> 8) & 0xFF,
                     total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
        part = data[k * 4096:(k + 1) * 4096]
        part = part + bytes(4096 - len(part))
        pkt = bytearray([0]) + bytearray(tft.out_len - 1)
        pkt[1:9] = hdr
        pkt[9:9 + 4096] = part
        tft.write_report(bytes(pkt))
        t0 = _t.time()
        ok = False
        while _t.time() - t0 < 0.35:
            r = tft.read_report(timeout=0.01)
            if r:
                p = r[1:]
                if len(p) >= 2 and p[0] == 0x55 and p[1] == ack:
                    ok = True
                    break
        rows.append({'seq': k, 'ack': ok, 'ms': round((_t.time() - t0) * 1000, 1)})
        if k % 50 == 0 or k == total - 1:
            prog(k + 1, total)
    return rows


if __name__ == '__main__':
    main()
