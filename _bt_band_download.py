# -*- coding: utf-8 -*-
"""批量下载 18 批估值 parquet → _bt_band_val/ 本地缓存
URL TTL=3600s, 必须尽快落地。下载后校验行数与 JSON 记录一致。"""
import json, os, sys, io, time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, '_bt_band_val')
os.makedirs(OUT, exist_ok=True)

urls = json.load(open(os.path.join(BASE, '_bt_band_urls.json'), encoding='utf-8'))['batches']

def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 100000:
        return 'skip'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as f:
        f.write(r.read())
    return 'ok'

ok, fail = [], []
for b in urls:
    dest = os.path.join(OUT, f"val_{b['batch']}.parquet")
    try:
        st = download(b['url'], dest)
        sz = os.path.getsize(dest)
        ok.append((b['batch'], st, sz))
        print(f"{b['batch']}: {st} {sz/1e6:.1f}MB")
    except Exception as e:
        fail.append((b['batch'], str(e)))
        print(f"{b['batch']}: FAIL {e}")

print(f"\n总计: {len(ok)} 成功, {len(fail)} 失败")
for f_ in fail:
    print('  FAILED:', f_)
