# -*- coding: utf-8 -*-
"""Phase 2：TFT 屏幕真机测试（会覆盖屏幕内容！）

用法:
  python phase2_tft.py red     # 用 SET_TFT_MATERIAL(0x4D) 推 1 帧纯红壁纸，逐包等 ACK
  python phase2_tft.py anim    # 用 SET_TFT_USER_ANIMATION(0x50) 推 3 帧红/绿/蓝动画，等 ACK 0x41
  python phase2_tft.py pattern # 推测试图（四象限+边框+文字，验证朝向/字节序/颜色）
  python phase2_tft.py time    # SET_TEMPORARY_COMMAND_DATA 同步屏幕时间
  python phase2_tft.py info    # 推 24B 系统信息（CPU/GPU/温度/天气码）
  python phase2_tft.py probe   # 只发 1 个 TFT 包，抓 TFT/主协议两个通道的所有回包

所有结果追加到 docs/phase2_tft.json；上传过程逐包打印 ACK。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)
W, H = 240, 135
CHUNK = 4096


def log(res, *keys):
    return res


def save(res):
    out = os.path.join(ROOT, 'docs', 'phase2_tft.json')
    old = []
    if os.path.exists(out):
        try:
            old = json.load(open(out, encoding='utf-8'))
            if isinstance(old, dict):
                old = old.get('runs', [])
        except Exception:  # noqa: BLE001
            old = []
    old.append(res)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'runs': old}, f, ensure_ascii=False, indent=2)
    print('saved', out)


def hx(b):
    return ' '.join(f'{x:02X}' for x in b) if b else ''


def rgb565_solid(r, g, b, w=W, h=H, byte_order=0):
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    lo, hi = v & 0xFF, (v >> 8) & 0xFF
    px = bytes([hi, lo]) if byte_order == 1 else bytes([lo, hi])
    return px * (w * h)


def pattern_image(byte_order=0):
    """生成测试图：四象限 (红/绿/蓝/白) + 边框 + 对角十字 + 文字"""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        print('PIL 不可用，退回纯色')
        return rgb565_solid(255, 0, 0)
    img = Image.new('RGB', (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W // 2 - 1, H // 2 - 1], fill=(255, 0, 0))       # 左上 红
    d.rectangle([W // 2, 0, W - 1, H // 2 - 1], fill=(0, 255, 0))      # 右上 绿
    d.rectangle([0, H // 2, W // 2 - 1, H - 1], fill=(0, 0, 255))      # 左下 蓝
    d.rectangle([W // 2, H // 2, W - 1, H - 1], fill=(255, 255, 255))  # 右下 白
    d.rectangle([0, 0, W - 1, H - 1], outline=(255, 255, 0), width=3)  # 黄边框
    d.line([0, 0, W - 1, H - 1], fill=(0, 0, 0), width=2)
    d.line([0, H - 1, W - 1, 0], fill=(0, 0, 0), width=2)
    try:
        d.text((8, 8), 'MK87 240x135', fill=(0, 0, 0))
        d.text((8, H - 14), 'TL-R TR-G', fill=(0, 0, 0))
    except Exception:  # noqa: BLE001
        pass
    buf = bytearray()
    for y in range(H):
        for x in range(W):
            r, g, b = img.getpixel((x, y))
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            lo, hi = v & 0xFF, (v >> 8) & 0xFF
            buf += bytes([hi, lo]) if byte_order == 1 else bytes([lo, hi])
    img.save(os.path.join(ROOT, 'docs', 'tft_pattern.png'))
    return bytes(buf)


def wait_ack(kb, ack_cmd, timeout=2.0):
    """同时在 TFT 通道和主协议通道上等 ACK（官方只在 TFT 通道等，实测确认）"""
    t0 = time.time()
    reports = []
    while time.time() - t0 < timeout:
        for label, iface in (('TFT', kb.tft), ('PROTO', kb.proto)):
            if iface is None:
                continue
            r = iface.read_report(timeout=0.03)
            if not r:
                continue
            p = r[1:]
            reports.append({'iface': label, 'hex': hx(p[:16])})
            if len(p) >= 8 and p[0] == 0x55 and p[1] == ack_cmd:
                return True, round((time.time() - t0) * 1000, 1), reports
    return False, round((time.time() - t0) * 1000, 1), reports


def upload(kb, data, kind, res):
    """kind='material' -> 0x4D/ACK 0x4D ; kind='anim' -> 0x50/ACK 0x41"""
    tft = kb.tft
    if tft is None:
        raise RuntimeError('没有 TFT 接口')
    cmd = CMD['SET_TFT_MATERIAL'] if kind == 'material' else CMD['SET_TFT_USER_ANIMATION']
    # 真机实测：0x4D(壁纸) 与 0x50(动画) 的逐包 ACK 命令字都是 0x41
    # （官方代码里壁纸路径按 0x4D 等 ACK —— 与 fw1.19 实际行为不符）
    ack = CMD['SET_LED_USER_ANIMATION']
    total = (len(data) + CHUNK - 1) // CHUNK
    rows = []
    print('上传 %s: %d 字节 -> %d 包 (每包 %d)' % (kind, len(data), total, CHUNK))
    for k in range(total):
        if kind == 'material':
            hdr = bytes([0xAA, cmd, k & 0xFF, (k >> 8) & 0xFF,
                         total & 0xFF, (total >> 8) & 0xFF, 0, 0])   # materialId=0
        else:
            hdr = bytes([0xAA, cmd, k & 0xFF, (k >> 8) & 0xFF,
                         total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
        part = data[k * CHUNK:(k + 1) * CHUNK]
        part = part + bytes(CHUNK - len(part))
        pkt = bytearray([0]) + bytearray(tft.out_len - 1)
        pkt[1:9] = hdr
        pkt[9:9 + CHUNK] = part
        t0 = time.time()
        tft.write_report(bytes(pkt))
        write_ms = round((time.time() - t0) * 1000, 1)
        ok, ms, reports = wait_ack(kb, ack, timeout=2.0 if k == 0 else 0.6)
        row = {'seq': k, 'write_ms': write_ms, 'ack': ok, 'ack_ms': ms,
               'reports': ['%s:%s' % (x['iface'], x['hex']) for x in reports[:3]]}
        rows.append(row)
        if k % 4 == 0 or not ok or k == total - 1:
            first = reports[0]['iface'] + ':' + reports[0]['hex'] if reports else ''
            print('  包 %3d/%d 写 %5.1fms ACK %s %s' % (
                k + 1, total, write_ms, 'OK' if ok else '超时', first))
    res['packets'] = rows
    res['ack_all'] = all(r['ack'] for r in rows)
    res['ack_avg_ms'] = round(sum(r['ack_ms'] for r in rows) / len(rows), 1)
    print('  ACK: %d/%d 通过, 平均 %.1f ms' % (
        sum(1 for r in rows if r['ack']), len(rows), res['ack_avg_ms']))
    return rows


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    kb = AjazzKeyboard()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'what': what}
    try:
        info = kb.get_device_info()
        res['device'] = {'tft': [i.mi + ' in=%d out=%d' % (i.in_len, i.out_len)
                                 for i in kb.ifaces if i.usage_page == 0xFF67],
                         'tftMaxFrames': info['tftMaxFrames'],
                         'tftDirection': info['tftDirection'],
                         'tftColorByteOrder': info['tftColorByteOrder']}
        print('TFT 接口:', res['device']['tft'], 'colorByteOrder=%d'
              % info['tftColorByteOrder'])
        bo = info['tftColorByteOrder']

        if what == 'red':
            res['data_len'] = W * H * 2
            upload(kb, rgb565_solid(255, 0, 0), 'material', res)
        elif what == 'pattern':
            upload(kb, pattern_image(bo), 'material', res)
        elif what == 'anim':
            delays = [50, 50, 50]          # 单位: 厘秒(cs)
            mv = bytearray(256)
            mv[0] = len(delays)
            for i in range(len(delays) - 1):
                mv[i + 1] = min(delays[i] * 5, 255)
            mv[len(delays)] = 0
            frames = (rgb565_solid(255, 0, 0) + rgb565_solid(0, 255, 0)
                      + rgb565_solid(0, 0, 255))
            res['frames'] = len(delays)
            res['data_len'] = len(mv) + len(frames)
            upload(kb, bytes(mv) + frames, 'anim', res)
        elif what == 'time':
            resp = kb.set_tft_datetime()
            res['resp'] = hx(resp)
            print('时间帧回显:', hx(resp))
        elif what == 'info':
            resp = kb.set_tft_screen_info(cpu_usage=45, cpu_temp=55, gpu_usage=30,
                                          gpu_temp=48, current_temp=22, max_temp=26,
                                          min_temp=18, weather=0, humidity=60)
            res['resp'] = hx(resp)
            print('系统信息帧回显:', hx(resp))
        elif what == 'probe':
            # 只发 1 个包，抓两个通道的所有回包，判断 ACK 走哪个接口
            data = rgb565_solid(255, 0, 0)
            pkt = bytearray([0]) + bytearray(kb.tft.out_len - 1)
            pkt[1:9] = bytes([0xAA, CMD['SET_TFT_MATERIAL'], 0, 0, 16, 0, 0, 0])
            pkt[9:9 + CHUNK] = data[:CHUNK]
            kb.tft.write_report(bytes(pkt))
            print('已发 1 包，抓 2 秒回包…')
            got = []
            t0 = time.time()
            while time.time() - t0 < 2.0:
                r = kb.tft.read_report(timeout=0.2)
                if r:
                    got.append({'iface': 'TFT', 'hex': hx(r[:20])})
            t1 = time.time()
            while time.time() - t1 < 0.5:
                r = kb.proto.read_report(timeout=0.1)
                if r:
                    got.append({'iface': 'PROTO', 'hex': hx(r[:20])})
            res['reports'] = got
            print('回包:', got)
    finally:
        kb.close()
        save(res)


if __name__ == '__main__':
    main()
