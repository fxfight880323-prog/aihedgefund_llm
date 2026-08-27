# -*- coding: utf-8 -*-
"""AI产业链 + 半导体产业链 个股筛选（筹码合成因子，个股层用法）
- 池子: 东财概念板块成分（AI核心板块 + 半导体产业链板块）
- 因子: 申万筹码合成 @2026-07-31（负向: 值越低=筹码越集中=越好, 已验证仅个股层有效）
"""
import urllib.request, json, time, sys, csv
sys.stdout.reconfigure(encoding='utf-8')

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}

def em(fs, fields, pz=100, pn=1):
    url = (f'https://push2delay.eastmoney.com/api/qt/clist/get?pn={pn}&pz={pz}&po=1'
           f'&np=1&fltt=2&invt=2&fid=f20&fs={fs}&fields={fields}')
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def board_constituents(bk, retries=3):
    out, pn = [], 1
    while True:
        d = None
        for a in range(retries):
            try:
                d = em(f'b:{bk}', 'f12,f14', pn=pn)
                break
            except Exception as e:
                if a == retries - 1:
                    print(f'  {bk} page {pn} failed: {e}')
                    return out
                time.sleep(2)
        diff = d['data']['diff'] if d and d.get('data') else []
        if not diff:
            break
        out += [(it['f12'], it['f14']) for it in diff]
        if len(out) >= d['data']['total']:
            break
        pn += 1
        time.sleep(0.25)
    return out

AI_BOARDS = {
    'BK0800': '人工智能', 'BK1134': '算力概念', 'BK1138': '液冷服务器',
    'BK1128': 'CPO概念', 'BK1136': '光通信模块', 'BK1111': 'AIGC概念',
    'BK1127': 'AI芯片', 'BK1161': '英伟达概念', 'BK0809': 'AI智能体',
    'BK1153': '多模态AI', 'BK1172': 'AI语料', 'BK1629': 'AI应用',
}
SEMI_BOARDS = {
    'BK0917': '半导体概念', 'BK0891': '国产芯片', 'BK1137': '存储芯片',
    'BK0952': '第三代半导体', 'BK1101': '先进封装', 'BK0969': '汽车芯片',
    'BK1121': '第四代半导体',
}

# ---- 1. 拉成分股 ----
pool = {}  # code -> {name, tags:set}
for grp, boards in (('AI', AI_BOARDS), ('SEMI', SEMI_BOARDS)):
    for bk, bname in boards.items():
        lst = board_constituents(bk)
        print(f'{bk} {bname}: {len(lst)} 只')
        for code, name in lst:
            e = pool.setdefault(code, {'name': name, 'tags': set(), 'grp': set()})
            e['tags'].add(bname)
            e['grp'].add(grp)
        time.sleep(0.3)
print(f'池子合计: {len(pool)} 只')

# ---- 2. 拉行情快照(市值/PE/52周高点) ----
quotes = {}
pn = 1
FIELDS = 'f12,f13,f14,f2,f3,f9,f20,f21,f100,f115,f114'
while True:
    d = em('m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048', FIELDS, pn=pn)
    diff = d['data']['diff'] if d and d.get('data') else []
    if not diff:
        break
    for it in diff:
        quotes[it['f12']] = it
    if len(quotes) >= d['data']['total']:
        break
    pn += 1
    time.sleep(0.25)
print(f'行情快照: {len(quotes)} 只')

# ---- 3. 合并筹码因子 ----
chip = {r['ts_code']: r['chip'] for r in
        json.load(open('_chip_industry_data.json', encoding='utf-8'))['stocks']}

def num(x):
    if x in ('-', '', None):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

rows = []
for code, e in pool.items():
    q = quotes.get(code)
    if not q:
        continue
    ts = (f"{code}.SH" if str(q['f13']) == '1' else f"{code}.SZ")
    cv = chip.get(ts)
    px, hi52 = num(q.get('f2')), num(q.get('f115'))
    lo52 = num(q.get('f114'))
    dist52 = (px / hi52 - 1) if (px and hi52 and hi52 > 0) else None
    rows.append({
        'code': code, 'ts': ts, 'name': e['name'],
        'industry': q.get('f100', ''),
        'grp': '+'.join(sorted(e['grp'])),
        'tags': '|'.join(sorted(e['tags'])),
        'price': px, 'pct': num(q.get('f3')), 'pe': num(q.get('f9')),
        'mv': num(q.get('f20')),  # 总市值(亿, fltt=2)
        'hi52': hi52, 'lo52': lo52, 'dist52': dist52,
        'chip': cv,
    })
have_chip = [r for r in rows if r['chip'] is not None]
print(f'池内有行情: {len(rows)} 只, 有筹码因子: {len(have_chip)} 只')

json.dump({'meta': {'factor_date': '2026-07-31', 'generated': '2026-08-24',
                    'ai_boards': AI_BOARDS, 'semi_boards': SEMI_BOARDS},
           'rows': rows},
          open('_chain_screen_data.json', 'w', encoding='utf-8'),
          ensure_ascii=False, default=list)
print('saved -> _chain_screen_data.json')
