#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tft_upload_gif2.py —— 按官方网驱抓包得到的「等 ACK」节奏推 GIF 到 MK87 的 TFT

官方抓包（capture/ajazz_tft_capture.jsonl）实测：
  - 4104B 报文, reportId=0, 头 AA 50 seq total 50 06, total=1155
  - 每包发完 ~140ms 后收到 64B ACK: 55 41 00 01 00...
  - 官方必须等 ACK 再发下一包，平均 146ms/包，1155 包共 168.5s
  - 首包 ACK 延迟 ~325ms（设备在擦写）

本脚本：每包等 ACK（默认超时 2s，最多重试 3 次），失败则报错退出（不再静默硬发）。

用法:
  python tft_upload_gif2.py "C:\\path\\anim.gif" [--max-frames N] [--ack-timeout 2.0] [--retries 3]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajazz  # noqa: E402
from tft_upload_gif import load_gif, build_delay_table, CMD_TFT_USER_ANIMATION  # noqa: E402

ACK_CMD = 0x41


def wait_ack(tft, timeout, t0, verbose=False):
    """等 cmd 0x41 的 ACK；返回 (ok, latency_ms, other_frames)"""
    deadline = time.time() + timeout
    others = 0
    while time.time() < deadline:
        r = tft.read_report(timeout=max(0.01, deadline - time.time()))
        if not r:
            return False, None, others
        payload = r[1:]
        if len(payload) >= 2 and payload[0] == 0x55 and payload[1] == ACK_CMD:
            return True, (time.time() - t0) * 1000, others
        others += 1
        if verbose and others <= 3:
            print(f"   [非 ACK 帧] {payload[:20].hex(' ')}")
    return False, None, others


def main():
    args = sys.argv[1:]
    if not args:
        print('用法: python tft_upload_gif2.py <gif> [--max-frames N] [--ack-timeout 2.0] [--retries 3]')
        return 1
    gif = args[0]
    max_frames, ack_timeout, retries = 140, 2.0, 3
    if '--max-frames' in args:
        max_frames = int(args[args.index('--max-frames') + 1])
    if '--ack-timeout' in args:
        ack_timeout = float(args[args.index('--ack-timeout') + 1])
    if '--retries' in args:
        retries = int(args[args.index('--retries') + 1])

    print(f'== GIF: {gif} ({os.path.getsize(gif)/1048576:.2f} MB)')
    kb = ajazz.AjazzKeyboard()
    try:
        info = kb.get_device_info()
        print(f'== 设备: fw={info["version"]} tftMaxFrames={info["tftMaxFrames"]} '
              f'tftColorByteOrder={info.get("tftColorByteOrder")}')
        tft = kb.tft
        if tft is None:
            print('!! 没找到 TFT 接口 (0xFF67)')
            return 2

        n_cap = min(max_frames, info['tftMaxFrames'] or max_frames)
        print(f'== 解码 GIF（≤{n_cap} 帧）...')
        t_dec = time.time()
        frames, delays, sizes, n_total = load_gif(gif, n_cap, info.get('tftColorByteOrder', 0))
        print(f'   {len(frames)}/{n_total} 帧, 解码 {time.time()-t_dec:.1f}s, 延时(厘秒)={delays[:6]}...')

        data = build_delay_table(delays) + b''.join(frames)
        body = tft.out_len - 1
        chunk = body - 8
        total = (len(data) + chunk - 1) // chunk
        print(f'== 载荷 {len(data)}B, 分包 {total} 包, 每包等 ACK（超时 {ack_timeout}s, 重试 {retries}）')

        ack_n = miss_n = retry_n = 0
        lat = []
        t_start = time.time()
        for seq in range(total):
            part = data[seq * chunk:(seq + 1) * chunk]
            pkt = bytearray([0]) + bytearray(body)
            pkt[1:9] = bytes([0xAA, CMD_TFT_USER_ANIMATION,
                              seq & 0xFF, (seq >> 8) & 0xFF,
                              total & 0xFF, (total >> 8) & 0xFF, 0x50, 0x06])
            pkt[9:9 + len(part)] = part

            ok = False
            for attempt in range(retries + 1):
                t0 = time.time()
                try:
                    tft.write_report(bytes(pkt))
                except Exception as e:
                    print(f'!! 包 {seq} 写入异常: {e}')
                    time.sleep(0.2)
                    continue
                ok, latency, others = wait_ack(tft, ack_timeout, t0, verbose=(seq == 0 and attempt == 0))
                if ok:
                    ack_n += 1
                    lat.append(latency)
                    break
                retry_n += 1
                if attempt < retries:
                    print(f'   [重试] 包 {seq} 第 {attempt+1} 次无 ACK，重发 ...')
                    time.sleep(0.2)
            if not ok:
                miss_n += 1
                print(f'!! 包 {seq} 重试 {retries} 次仍无 ACK，中止上传（已发 {seq+1}/{total}）')
                return 3

            if seq % 50 == 0 or seq == total - 1:
                elapsed = time.time() - t_start
                done = seq + 1
                avg = sum(lat) / len(lat) if lat else 0
                eta = (total - done) * avg / 1000 if lat else 0
                print(f'   包 {done}/{total} ({done*100//total}%) ack={ack_n} miss={miss_n} '
                      f'retry={retry_n} avg={avg:.0f}ms 用时 {elapsed:.1f}s ETA {eta:.0f}s')

        print(f'== 完成: {total} 包全部 ACK（{ack_n}）, 重试 {retry_n} 次, 总用时 {time.time()-t_start:.1f}s')
        if lat:
            print(f'   ACK 延迟 ms: min={min(lat):.0f} avg={sum(lat)/len(lat):.0f} max={max(lat):.0f}')
        print('\n== 现在看屏幕：应该开始播放这个 GIF。')
        return 0
    finally:
        kb.close()


if __name__ == '__main__':
    sys.exit(main())
