# -*- coding: utf-8 -*-
"""Phase 3.5：模拟官方 setKeyData 的写法（只填 keyList 的 87 槽，其余写 0），
验证「25 个配置外槽被清零」是否有可观察后果。

用法:
  python phase3_official.py apply    # 写入官方风格矩阵（清零 25 个配置外槽）
  python phase3_official.py restore  # 整表回写 device_dump_pre_test.json
  python phase3_official.py list     # 只打印 keyList 槽 / 配置外槽
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
LIGHT = os.path.join(ROOT, 'docs', 'lighting-modes.json')


def hx4(b):
    return ' '.join(f'{x:02X}' for x in b)


def keylist_slots():
    d = json.load(open(LIGHT, encoding='utf-8'))
    return sorted({x['ledId'] for x in d['ledKeyMap']['table']})


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'list'
    dump = json.load(open(DUMP, encoding='utf-8'))
    backup = bytes.fromhex(dump['key_matrix']['hex'])
    listed = keylist_slots()
    external = [s for s in range(128) if s not in listed]
    print('keyList 槽 %d 个；配置外槽 %d 个: %s' % (len(listed), len(external), external))

    if action == 'list':
        for s in external:
            v = backup[s * 4:s * 4 + 4]
            print('  槽 %3d: %s' % (s, hx4(v)))
        return

    kb = AjazzKeyboard()
    try:
        if action == 'apply':
            official = bytearray(512)
            for s in listed:
                official[s * 4:s * 4 + 4] = backup[s * 4:s * 4 + 4]
            kb.request(CMD['SET_KEY'], bytes(official), content_size=512,
                       timeout=0.8, retries=1)
            now = bytes(kb.read_key_matrix())
            ok = now == bytes(official)
            diffs = [i // 4 for i in range(512) if now[i] != official[i]]
            print('官方风格写入:', 'PASS' if ok else 'FAIL', '差异槽', sorted(set(diffs))[:12])
            res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'applied': ok, 'zeroed_slots': external,
                   'diff_slots': sorted(set(diffs))}
            json.dump(res, open(os.path.join(ROOT, 'docs', 'phase3_official.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=2)
            print('>>> 已清零 25 个配置外槽，请人工测试：正常打字 / Fn+旋钮锁定后转音量 <<<')
        elif action == 'restore':
            kb.request(CMD['SET_KEY'], backup, content_size=512, timeout=0.8, retries=1)
            time.sleep(0.3)
            ok = bytes(kb.read_key_matrix()) == backup
            print('恢复整表:', 'PASS' if ok else 'FAIL')
            res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'restored': ok}
            json.dump(res, open(os.path.join(ROOT, 'docs', 'phase3_official_restore.json'),
                                'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    finally:
        kb.close()


if __name__ == '__main__':
    main()
