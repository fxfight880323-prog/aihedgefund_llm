# -*- coding: utf-8 -*-
"""获取下一个待处理批次并输出其 ts_codes。用法: python _gbm_next.py [N]
N=批数(默认1)。输出: 每个待处理批次的 JSON 数组(逐行)。
"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
BATCH_DIR = os.path.join(BASE, '_gbm_batches')

with open(os.path.join(BATCH_DIR, 'manifest.json'), 'r', encoding='utf-8') as f:
    manifest = json.load(f)

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
done = []
pending = []
for month, info in manifest.items():
    for bname in info['batches']:
        if os.path.exists(os.path.join(BATCH_DIR, bname + '_res.json')):
            done.append(bname)
        else:
            pending.append(bname)

print(f'已完成: {len(done)}  待处理: {len(pending)}')
for bname in pending[:n]:
    with open(os.path.join(BATCH_DIR, bname + '.json'), 'r', encoding='utf-8') as f:
        d = json.load(f)
    print(f'### {bname} ### date={d["date"]}')
    print(json.dumps(d['ts_codes']))
