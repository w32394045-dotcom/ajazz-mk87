# -*- coding: utf-8 -*-
"""在官方 bundle 里按字面量搜索并打印上下文（分析用）。
用法: python bundle_grep.py "字面量" [前字符数] [后字符数] [最多几处]
"""
import os
import sys

BUNDLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'assets', 'layout-classic-CMxiG14P.js')


def main():
    pat = sys.argv[1]
    before = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    after = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    s = open(BUNDLE, encoding='utf-8', errors='replace').read()
    idx = []
    start = 0
    while True:
        i = s.find(pat, start)
        if i < 0:
            break
        idx.append(i)
        start = i + 1
    print('pattern %r occurrences: %d' % (pat, len(idx)))
    for n, i in enumerate(idx[:limit]):
        print('\n===== #%d @%d =====' % (n + 1, i))
        print(s[max(0, i - before):i + after].replace('\n', ' '))


if __name__ == '__main__':
    main()
