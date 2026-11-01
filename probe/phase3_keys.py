# -*- coding: utf-8 -*-
"""Phase 3：改键 / FN 层 / 宏 真机测试

用法:
  python phase3_keys.py apply    # 写入测试项（3 个键位 + FN 层 1 个 + phantom 槽），逐项回读校验
  python phase3_keys.py restore  # 用 device_dump_pre_test.json 整表回写恢复
  python phase3_keys.py show     # 打印指定槽位当前值

测试项（全部走「整表读-改-写」）：
  - 槽 103 Insert  -> 02 00 04 00 (KEYBOARD 'a')          人眼：记事本按 Insert 输入 a
  - 槽 105 PgUp    -> 0D 00 00 0D (FUNC 13 亮度+)          人眼：按 PgUp 背光变亮
  - FN 层槽 105    -> 0D 00 00 0E (FUNC 14 亮度-)          人眼：Fn+PgUp 背光变暗
  - 槽 120 (空槽)  -> 02 00 68 00 (KEYBOARD F13)           回读一致即可（无物理键）
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

CASES = {
    'key': {'103': bytes([0x02, 0x00, 0x04, 0x00]),
            '105': bytes([0x0D, 0x00, 0x00, 0x0D]),
            '120': bytes([0x02, 0x00, 0x68, 0x00])},
    'fn': {'105': bytes([0x0D, 0x00, 0x00, 0x0E])},
}


def hx4(b):
    return ' '.join(f'{x:02X}' for x in b)


def load_backup():
    d = json.load(open(DUMP, encoding='utf-8'))
    km = bytes.fromhex(d['key_matrix']['hex'])
    fn = bytes.fromhex(d['fn_key_matrix']['hex'])
    return km, fn


def write_matrix(kb, which, matrix, patch):
    m = bytearray(matrix)
    for slot, val in patch.items():
        m[int(slot) * 4:int(slot) * 4 + 4] = val
    if which == 'key':
        kb.request(CMD['SET_KEY'], bytes(m), content_size=512, timeout=0.8, retries=1)
        now = bytes(kb.read_key_matrix())
    else:
        kb.request(CMD['SET_FN_KEY'], bytes(m), content_size=512, timeout=0.8, retries=1)
        now = bytes(kb.read_fn_key_matrix())
    return bytes(m), now


def apply(kb):
    backup_key, backup_fn = load_backup()
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    cur_key = bytes(kb.read_key_matrix())
    cur_fn = bytes(kb.read_fn_key_matrix())
    print('当前 key == 备份:', cur_key == backup_key, '| fn == 备份:', cur_fn == backup_fn)
    if cur_key != backup_key:
        print('  注意：当前矩阵与备份不一致，以当前值做基线')
        backup_key = cur_key
    if cur_fn != backup_fn:
        backup_fn = cur_fn

    want_key, now_key = write_matrix(kb, 'key', backup_key, CASES['key'])
    ok_key = now_key == want_key
    diffs = [i for i in range(512) if now_key[i] != want_key[i]]
    print('[3.1/3.2/3.3] 普通层写入 3 槽:', 'PASS' if ok_key else 'FAIL',
          '差异字节', diffs[:8])
    for slot in CASES['key']:
        print('   槽 %3s -> %s | 回读 %s' % (
            slot, hx4(CASES['key'][slot]),
            hx4(now_key[int(slot) * 4:int(slot) * 4 + 4])))
    res['key_write'] = {'match': ok_key, 'diffs': diffs[:16],
                        'slots': {s: hx4(v) for s, v in CASES['key'].items()}}

    want_fn, now_fn = write_matrix(kb, 'fn', backup_fn, CASES['fn'])
    ok_fn = now_fn == want_fn
    print('[3.4] FN 层写入 1 槽:', 'PASS' if ok_fn else 'FAIL',
          '槽105 回读', hx4(now_fn[105 * 4:105 * 4 + 4]))
    res['fn_write'] = {'match': ok_fn}

    # 其它槽未被改动？
    untouched_key = all(now_key[i] == backup_key[i] for i in range(512)
                        if i // 4 not in [int(s) for s in CASES['key']])
    untouched_fn = all(now_fn[i] == backup_fn[i] for i in range(512)
                       if i // 4 not in [int(s) for s in CASES['fn']])
    print('   其它槽是否保持原值: key=%s fn=%s' % (untouched_key, untouched_fn))
    res['others_untouched'] = {'key': untouched_key, 'fn': untouched_fn}
    json.dump(res, open(os.path.join(ROOT, 'docs', 'phase3_keys.json'), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=2)
    print('\n>>> 测试已写入，请做人工验证 <<<')


def restore(kb):
    backup_key, backup_fn = load_backup()
    kb.request(CMD['SET_KEY'], backup_key, content_size=512, timeout=0.8, retries=1)
    kb.request(CMD['SET_FN_KEY'], backup_fn, content_size=512, timeout=0.8, retries=1)
    time.sleep(0.3)
    ok_key = bytes(kb.read_key_matrix()) == backup_key
    ok_fn = bytes(kb.read_fn_key_matrix()) == backup_fn
    print('恢复: key=%s fn=%s' % (ok_key, ok_fn))
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'restore': {
        'key': ok_key, 'fn': ok_fn}}
    json.dump(res, open(os.path.join(ROOT, 'docs', 'phase3_keys.json'), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=2)


def show(kb):
    slots = [int(x) for x in sys.argv[2:]] or [103, 105, 120]
    km = bytes(kb.read_key_matrix())
    fn = bytes(kb.read_fn_key_matrix())
    for s in slots:
        print('槽 %3d  key=%s  fn=%s' % (s, hx4(km[s * 4:s * 4 + 4]),
                                         hx4(fn[s * 4:s * 4 + 4])))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'show'
    kb = AjazzKeyboard()
    try:
        if action == 'apply':
            apply(kb)
        elif action == 'restore':
            restore(kb)
        else:
            show(kb)
    finally:
        kb.close()


if __name__ == '__main__':
    main()
