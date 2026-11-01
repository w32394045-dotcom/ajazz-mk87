# -*- coding: utf-8 -*-
"""Phase 3.6：宏写入 SET_MACRO 真机测试（官方 PZ/NZ 逐字节复刻）

宏表结构（来自 bundle PZ/NZ，静态推断 → 本轮真机验证）：
  SET_MACRO 第一次写：contentSize=400, addrStart=0, 全部包 last=0  → 100 个 u32 LE 绝对偏移
  SET_MACRO 第二次写：contentSize=动作数据总长, addrStart=400, 末包 last=1
  宏块 = [0..1]=动作数×2(u16 LE) [2..3]=0 之后每动作 4B：
         [0..1]=delay(ms,u16 LE) [2]=keyCode(HID usage) [3]=flags
         flags = ((actionType&7)<<4) | (isPress?0x80:0)   （键盘动作 actionType=3）

用法:
  python phase3_macro.py apply    # 写宏 "abc" + 绑定到 Insert(槽103) + 点亮 97红/98绿
  python phase3_macro.py verify   # 读回宏表并解码
  python phase3_macro.py restore  # 清空宏表 + 还原槽103 + 还原灯效
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ajazz import AjazzKeyboard, CMD  # noqa: E402

ROOT = os.path.dirname(HERE)
DUMP = os.path.join(ROOT, 'docs', 'device_dump_pre_test.json')


def hx(b):
    return ' '.join(f'{x:02X}' for x in b)


def encode_action(delay, keycode, action_type=3, is_press=True):
    flags = ((action_type & 7) << 4) | (0x80 if is_press else 0)
    return bytes([delay & 0xFF, (delay >> 8) & 0xFF, keycode & 0xFF, flags])


def build_macro_payloads(macros):
    """macros = [{id, actions:[bytes(4)]}] -> (table400, data)"""
    table = bytearray(400)
    data = bytearray()
    offset = 400
    for m in macros:
        acts = m['actions']
        n = len(acts)
        if n == 0:
            continue
        block = bytearray(4)
        block[0] = (n * 2) & 0xFF
        block[1] = ((n * 2) >> 8) & 0xFF
        for a in acts:
            block += a
        pos = m['id'] * 4
        table[pos:pos + 4] = offset.to_bytes(4, 'little')
        data += block
        offset += len(block)
    return bytes(table), bytes(data)


def send_macro_chunk(kb, payload, addr, last_flag, timeout=1.0):
    """按官方 NX 规则：std 8 字节头，chunk=body-8，逐包；last 标志可控"""
    iface = kb.proto
    body = iface.out_len - 1
    chunk = body - 8
    total = max(1, (len(payload) + chunk - 1) // chunk)
    acks = []
    for k in range(total):
        part = payload[k * chunk:(k + 1) * chunk]
        pkt = bytearray([0]) + bytearray(body)
        pkt[1] = 0xAA
        pkt[2] = CMD['SET_MACRO']
        pkt[3] = len(part) & 0xFF
        a = addr + k * chunk
        pkt[4] = a & 0xFF
        pkt[5] = (a >> 8) & 0xFF
        pkt[6] = 0
        pkt[7] = 1 if (k == total - 1 and last_flag) else 0
        pkt[9:9 + len(part)] = part
        iface.write_report(bytes(pkt))
        t0 = time.time()
        ok = False
        while time.time() - t0 < timeout:
            r = iface.read_report(timeout=0.02)
            if not r:
                continue
            p = r[1:]
            if len(p) >= 2 and p[0] == 0x55 and p[1] == CMD['SET_MACRO']:
                ok = True
                break
        acks.append(ok)
    return acks


def read_macro_table(kb, addr=0, size=400):
    return kb.request(CMD['GET_MACRO'], b'', addr_start=addr, content_size=size, timeout=1.0)


def decode_macros(table):
    out = []
    for i in range(100):
        off = int.from_bytes(table[i * 4:i * 4 + 4], 'little')
        if off == 0:
            continue
        out.append({'macroId': i, 'offset': off})
    return out


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'apply'
    kb = AjazzKeyboard()
    dump = json.load(open(DUMP, encoding='utf-8'))
    base_key = bytes.fromhex(dump['key_matrix']['hex'])
    orig_led = bytes.fromhex(dump['led_effect']['raw']['hex'])
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'action': action}
    try:
        if action == 'apply':
            # 1) 宏 "abc"：每个字符 press + release，delay 10ms
            acts = []
            for usage in (0x04, 0x05, 0x06):        # a, b, c
                acts.append(encode_action(10, usage, 3, True))
                acts.append(encode_action(10, usage, 3, False))
            table, data = build_macro_payloads([{'id': 0, 'actions': acts}])
            res['table_hex'] = hx(table[:16])
            res['data_hex'] = hx(data)
            print('宏表偏移[0..4]:', hx(table[:4]), '| 数据 %d 字节:' % len(data),
                  hx(data))
            a1 = send_macro_chunk(kb, table, 0, last_flag=False)
            print('写偏移表(400B): ACK', sum(a1), '/', len(a1))
            a2 = send_macro_chunk(kb, data, 400, last_flag=True)
            print('写动作数据(%dB): ACK' % len(data), sum(a2), '/', len(a2))
            # 2) 读回校验
            t = read_macro_table(kb)
            print('读回偏移表[0..4]:', hx(t[:4]))
            print('宏表非空项:', decode_macros(t))
            res['readback_table_head'] = hx(t[:4])
            res['readback_data'] = hx(kb.request(CMD['GET_MACRO'], b'', addr_start=400, content_size=len(data), timeout=1.0))
            print('读回数据:', res['readback_data'])

            # 3) 绑定 Insert(103) -> MACRO 0
            m = bytearray(bytes(kb.read_key_matrix()))
            m[103 * 4:103 * 4 + 4] = bytes([0x06, 0x00, 0x00, 0x00])
            kb.request(CMD['SET_KEY'], bytes(m), content_size=512, timeout=0.8, retries=1)
            now = bytes(kb.read_key_matrix())
            print('槽103 回读:', hx(now[103 * 4:103 * 4 + 4]),
                  '(期望 06 00 00 00)')

            # 4) 点亮槽 97 红 / 98 绿（供人眼定位）
            p = bytearray(16)
            p[0] = 128
            p[1:4] = b'\xFF\xFF\xFF'
            p[4] = 0xFF
            p[8] = 1
            p[9] = 6
            p[10] = 3
            p[14] = 0xAA
            p[15] = 0x55
            kb.request(CMD['SET_LED_EFFECT'], bytes(p), content_size=16)
            time.sleep(0.3)
            cust = bytearray(512)
            cust[97 * 4:97 * 4 + 4] = bytes([97, 255, 0, 0])    # 红
            cust[98 * 4:98 * 4 + 4] = bytes([98, 0, 255, 0])    # 绿
            kb.request(CMD['SET_CUSTOM_LED_DATA'], bytes(cust), content_size=512)
            time.sleep(0.5)
            print('\n>>> 已设置：槽97=红 槽98=绿 常亮（供定位）；Insert 键已绑定宏 abc <<<')

        elif action == 'verify':
            t = read_macro_table(kb)
            print('偏移表非空:', decode_macros(t))
            off = int.from_bytes(t[0:4], 'little')
            if off:
                head = kb.request(CMD['GET_MACRO'], b'', addr_start=off, content_size=4, timeout=1.0)
                n = int.from_bytes(head[:2], 'little') // 2
                print('宏0 块头:', hx(head), '动作数:', n)
                body = kb.request(CMD['GET_MACRO'], b'', addr_start=off + 4, content_size=n * 4, timeout=1.0)
                for e in range(n):
                    a = body[e * 4:e * 4 + 4]
                    print('  动作%d delay=%d key=%d flags=0x%02X (isPress=%s type=%d)'
                          % (e, a[0] | a[1] << 8, a[2], a[3], bool(a[3] & 0x80),
                             (a[3] >> 4) & 7))

        elif action == 'restore':
            # 清空宏表：写 400 字节 0（last=1 即可），不写数据区
            a = send_macro_chunk(kb, bytes(400), 0, last_flag=True)
            print('清空宏表 ACK', sum(a), '/', len(a))
            t = read_macro_table(kb)
            print('清空后非空:', decode_macros(t))
            # 还原键矩阵
            cur = bytearray(bytes(kb.read_key_matrix()))
            cur[103 * 4:103 * 4 + 4] = base_key[103 * 4:103 * 4 + 4]
            kb.request(CMD['SET_KEY'], bytes(cur), content_size=512, timeout=0.8, retries=1)
            print('槽103 还原:', hx(bytes(kb.read_key_matrix())[103 * 4:103 * 4 + 4]))
            # 还原灯效 + 自定义灯
            kb.request(CMD['SET_LED_EFFECT'], orig_led, content_size=16)
            cust0 = bytes.fromhex(dump['custom_led_data']['hex'])
            kb.request(CMD['SET_CUSTOM_LED_DATA'], cust0, content_size=512)
            time.sleep(0.3)
            res['restore'] = {
                'led_ok': bytes(kb.get_led_effect()['raw']) == orig_led,
                'custom_ok': bytes(kb.read_custom_led_data()) == cust0,
                'key_ok': bytes(kb.read_key_matrix()) == base_key,
            }
            print('恢复:', res['restore'])
    finally:
        kb.close()
        json.dump(res, open(os.path.join(ROOT, 'docs', 'phase3_macro.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        print('saved docs/phase3_macro.json')


if __name__ == '__main__':
    main()
