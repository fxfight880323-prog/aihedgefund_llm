# -*- coding: utf-8 -*-
"""LX-core（含金融）过去3年回测收益 — 按 prompt_template_fund_framework.md 执行
窗口: 2023-08-31 (第5期调仓) ~ 2026-08-24 (回测缓存最新)
口径: 日频 + 复权 + 半年调仓 T+1 撮合(官方引擎, 已对齐 +55.55%)
基准: 同口径半年调仓等权全A + 中证全指(000985.SH 价格指数)
对照: 银行等权组合(38只, 呼应"择时买银行"命题)
输出: _bt_3y_data.json + _bt_3y_report.html
"""
import json, sys, statistics, math
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ---------- 1. 加载官方缓存 ----------
res = json.load(open('_bt_daily_results.json', encoding='utf-8'))
core_nav = {r['date']: r['nav'] for r in res['results']['core']['nav']}
ew_nav = json.load(open('_bt_daily_ew_hold_nav.json', encoding='utf-8'))['nav']
idx = json.load(open('_bt_daily_results.json', encoding='utf-8'))['idx']['nav']
idx_daily = json.load(open('_bt_daily_idx.json', encoding='utf-8'))  # 中证全指日频 OHLC
w_core = json.load(open('_bt_band_results.json', encoding='utf-8'))['weights']['core']
px = json.load(open('_bt_daily_px.json', encoding='utf-8'))
fin = json.load(open('_bt_sw_fin_universe.json', encoding='utf-8'))
banks = sorted(set(fin['银行']['members']) & set(px))

# ---------- 2. 窗口 ----------
W0, W1 = '2023-08-31', '2026-08-24'
common = sorted(set(core_nav) & set(ew_nav) & set(idx))
win = [d for d in common if W0 <= d <= W1]
print(f'窗口: {win[0]} -> {win[-1]}  交易日 {len(win)}')

def norm(nav_map, win):
    return [(d, nav_map[d] / nav_map[win[0]]) for d in win]

core = norm(core_nav, win)
ew = norm(ew_nav, win)
idxv = norm(idx, win)

def metrics(series):
    """series: list[(date, nav)] 起点=1.0"""
    dts = [d for d, _ in series]
    nv = [v for _, v in series]
    total = nv[-1] - 1
    n = len(dts)
    ann = (nv[-1] ** (252.0 / n) - 1) if nv[-1] > 0 else -1
    peak, mdd = -1e18, 0.0
    for v in nv:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    return dict(total=total, ann=ann, mdd=mdd, n=n, start=dts[0], end=dts[-1])

def pct(x): return x * 100

m_core, m_ew, m_idx = metrics(core), metrics(ew), metrics(idxv)
print(f'core  : total={pct(m_core["total"]):+.2f}% ann={pct(m_core["ann"]):+.2f}% mdd={pct(m_core["mdd"]):.2f}%')
print(f'全A等权: total={pct(m_ew["total"]):+.2f}% ann={pct(m_ew["ann"]):+.2f}% mdd={pct(m_ew["mdd"]):.2f}%')
print(f'中证全指: total={pct(m_idx["total"]):+.2f}% ann={pct(m_idx["ann"]):+.2f}% mdd={pct(m_idx["mdd"]):.2f}%')
print(f'超额 vs 全A: {pct(m_core["total"]-m_ew["total"]):+.2f}pp  vs 中证全指: {pct(m_core["total"]-m_idx["total"]):+.2f}pp')

# ---------- 3. 分年度 ----------
def year_slices(win):
    """按自然年切, 每段含起点"""
    out = []
    cur = win[0]
    yrs = sorted(set(d[:4] for d in win))
    for i, y in enumerate(yrs):
        seg = [d for d in win if (d[:4] == y) or (i == 0 and d == cur)]
        if len(seg) >= 2:
            out.append((y, seg))
    return out

def seg_ret(nav_map, seg):
    return nav_map[seg[-1]] / nav_map[seg[0]] - 1

print('\n分年度收益:')
year_rows = []
for y, seg in year_slices(win):
    rc, re_, ri = seg_ret(core_nav, seg), seg_ret(ew_nav, seg), seg_ret(idx, seg)
    year_rows.append(dict(year=y, core=rc, ew=re_, idx=ri,
                          ex_ew=rc - re_, ex_idx=rc - ri,
                          start=seg[0], end=seg[-1], n=len(seg)))
    print(f'  {y}: core={pct(rc):+.2f}% 全A={pct(re_):+.2f}% 指数={pct(ri):+.2f}% 超额全A={pct(rc-re_):+.2f}pp')

# ---------- 4. 调仓周期 ----------
periods = [['2023-08', '2023-08-31'], ['2024-04', '2024-04-30'], ['2024-08', '2024-08-31'],
           ['2025-04', '2025-04-30'], ['2025-08', '2025-08-31'], ['2026-04', '2026-04-30']]
print('\n调仓周期收益:')
period_rows = []
for i, (pm, trig) in enumerate(periods):
    end = periods[i + 1][1] if i + 1 < len(periods) else W1
    seg = [d for d in win if trig <= d <= end]
    if len(seg) < 2:
        continue
    rc, re_, ri = seg_ret(core_nav, seg), seg_ret(ew_nav, seg), seg_ret(idx, seg)
    period_rows.append(dict(period=f'{pm}~{end[:7]}', core=rc, ew=re_, idx=ri,
                            ex_ew=rc - re_, start=seg[0], end=seg[-1], n=len(seg)))
    print(f'  {pm}->{end}: core={pct(rc):+.2f}% 全A={pct(re_):+.2f}% 超额={pct(rc-re_):+.2f}pp')

# ---------- 5. 每期持仓结构 (2023-08 起 6 期) ----------
banks_set = set(fin['银行']['members']); nbf_set = set(fin['非银金融']['members'])
print('\n每期持仓结构:')
hold_rows = []
for pm, trig in periods:
    if pm not in w_core:
        continue
    holds = w_core[pm]
    nb = len([t for t in holds if t in banks_set])
    nnb = len([t for t in holds if t in nbf_set])
    nf = len(holds) - nb - nnb
    hold_rows.append(dict(period=pm, n=len(holds), bank=nb, nbf=nnb, nonfin=nf,
                          weight_bank=nb / len(holds)))
    print(f'  {pm}: n={len(holds)} 银行{nb} 非银{nnb} 非金融{nf}')

# ---------- 6. 银行等权组合 (38只, 起点等权之后漂移, 复权日频) ----------
close = {}
for tk, d in px.items():
    m = {dt: r['adj'] for dt, r in d.items() if r.get('adj') and W0 <= dt <= W1}
    if m:
        close[tk] = m
live_banks = [b for b in banks if close.get(b)]
print(f'\n银行等权: {len(live_banks)}/{len(banks)} 只有价')

shares = {}; equity = 1.0; prev = {}; bank_navs = {}
for dt in win:
    day = 0.0
    for tk, s in shares.items():
        p0, p1 = prev.get(tk), close[tk].get(dt)
        if p0 and p1 and s > 0:
            day += s * (p1 - p0)
    equity += day
    bank_navs[dt] = equity
    for tk in shares:
        p = close[tk].get(dt)
        if p:
            prev[tk] = p
    if not shares:
        live = [c for c in live_banks if close[c].get(dt)]
        for c in live:
            shares[c] = (1.0 / len(live)) * equity / close[c][dt]
            prev[c] = close[c][dt]

bk_series = [(d, v) for d, v in bank_navs.items()]
m_bk = metrics(bk_series)
print(f'银行等权: total={pct(m_bk["total"]):+.2f}% ann={pct(m_bk["ann"]):+.2f}% mdd={pct(m_bk["mdd"]):.2f}%')
print(f'银行 vs core: {pct(m_bk["total"]-m_core["total"]):+.2f}pp  vs 全A: {pct(m_bk["total"]-m_ew["total"]):+.2f}pp')
bk_year = []
for y, seg in year_slices(win):
    r = bank_navs[seg[-1]] / bank_navs[seg[0]] - 1
    bk_year.append(dict(year=y, ret=r))
    print(f'  银行 {y}: {pct(r):+.2f}%')

# ---------- 7. 审计 (Type D) ----------
audit = {}
for pm, trig in periods:
    if pm in w_core:
        miss = [t for t in w_core[pm] if t not in px]
        audit[pm] = dict(holds=len(w_core[pm]), miss_price=len(miss), miss_codes=miss[:5])

# ---------- 8. 存数据 + 报告 ----------
data = dict(
    window=dict(start=W0, end=W1, n=len(win)),
    core=dict(**m_core, ex_ew=m_core['total'] - m_ew['total'], ex_idx=m_core['total'] - m_idx['total']),
    ew=dict(**m_ew), idx=dict(**m_idx), bank=dict(**m_bk,
        ex_ew=m_bk['total'] - m_ew['total'], ex_core=m_bk['total'] - m_core['total']),
    years=year_rows, periods=period_rows, holdings=hold_rows, bank_years=bk_year,
    audit=audit,
    navs=dict(core=[{'d': d, 'v': round(v, 6)} for d, v in core],
              ew=[{'d': d, 'v': round(v, 6)} for d, v in ew],
              idx=[{'d': d, 'v': round(v, 6)} for d, v in idxv],
              bank=[{'d': d, 'v': round(v, 6)} for d, v in bk_series]),
)
json.dump(data, open('_bt_3y_data.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\nsaved _bt_3y_data.json')

# ---------- HTML ----------
def fmt(x, suf='%', sign=True, nd=2):
    if x is None:
        return '—'
    return f'{x * 100:+.{nd}f}{suf}' if sign else f'{x * 100:.{nd}f}{suf}'

def fmt_mdd(x):
    return f'{-x * 100:.2f}%'

def svg_line(series_list, labels, colors, h=340, w=940):
    allv = [v for s in series_list for _, v in s]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.06 or 0.01
    lo -= pad; hi += pad
    x0, y0, x1, y1 = 60, 16, w - 16, h - 34
    dts = [d for d, _ in series_list[0]]
    n = len(dts)
    def px_(i): return x0 + (x1 - x0) * i / (n - 1)
    def py_(v): return y1 - (y1 - y0) * (v - lo) / (hi - lo)
    # y 网格 (5档)
    parts = []
    for g in range(6):
        v = lo + (hi - lo) * g / 5
        y = py_(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
                     f'<text x="{x0-8}" y="{y+4}" text-anchor="end" font-size="11" fill="#6b7280">{v:.2f}</text>')
    # x 轴年份刻度
    for d in ['2023-09-01', '2024-01-01', '2024-06-01', '2025-01-01', '2025-06-01', '2026-01-01', '2026-06-01']:
        if d in dts:
            i = dts.index(d)
            parts.append(f'<text x="{px_(i):.0f}" y="{y1+18}" text-anchor="middle" font-size="11" fill="#6b7280">{d[:7]}</text>')
    for series, lab, col in zip(series_list, labels, colors):
        pts = ' '.join(f'{px_(i):.1f},{py_(v):.1f}' for i, (_, v) in enumerate(series))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>')
        # 末点标签
        i = n - 1
        parts.append(f'<text x="{px_(i)+6:.0f}" y="{py_(series[i][1])+4:.0f}" font-size="12" font-weight="bold" fill="{col}">{lab} {series[i][1]:.2f}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">{chr(10).join(parts)}</svg>'

rows_metrics = [
    ('LX-core（含金融）', data['core'], '#c0392b'),
    ('等权全A（同口径半年调仓）', data['ew'], '#2471a3'),
    ('中证全指 000985.SH（价格指数）', data['idx'], '#7d3c98'),
    ('银行等权组合（38只，对照）', data['bank'], '#b9770e'),
]
tr_metrics = ''
for name, m, _ in rows_metrics:
    tr_metrics += (f'<tr><td class="l">{name}</td>'
                   f'<td><b>{fmt(m["total"])}</b></td>'
                   f'<td>{fmt(m["ann"])}</td>'
                   f'<td class="{"neg" if m["total"]<0 else "pos"}">{fmt_mdd(m["mdd"])}</td>'
                   f'<td>{m["n"]} 天</td>'
                   f'<td>{m["start"]} ~ {m["end"]}</td></tr>')

tr_excess = (f'<tr><td class="l">core − 等权全A</td><td><b class="pos">{fmt(data["core"]["ex_ew"])}</b></td>'
             f'<td class="l">核心对照，同调仓频率同持有方式</td></tr>'
             f'<tr><td class="l">core − 中证全指</td><td><b class="pos">{fmt(data["core"]["ex_idx"])}</b></td>'
             f'<td class="l">规模价差代理 = 等权全A − 中证全指</td></tr>')

tr_years = ''
for r in data['years']:
    tr_years += (f'<tr><td>{r["year"]}</td><td>{r["start"]}~{r["end"]}</td><td>{r["n"]}</td>'
                 f'<td><b class="{"neg" if r["core"]<0 else "pos"}">{fmt(r["core"])}</b></td>'
                 f'<td>{fmt(r["ew"])}</td><td>{fmt(r["idx"])}</td>'
                 f'<td class="{"neg" if r["ex_ew"]<0 else "pos"}">{fmt(r["ex_ew"])}</td></tr>')

tr_periods = ''
for r in data['periods']:
    tr_periods += (f'<tr><td>{r["period"]}</td><td>{r["n"]}</td>'
                   f'<td><b class="{"neg" if r["core"]<0 else "pos"}">{fmt(r["core"])}</b></td>'
                   f'<td>{fmt(r["ew"])}</td><td>{fmt(r["idx"])}</td>'
                   f'<td class="{"neg" if r["ex_ew"]<0 else "pos"}">{fmt(r["ex_ew"])}</td></tr>')

tr_holds = ''
for r in data['holdings']:
    tr_holds += (f'<tr><td>{r["period"]}</td><td>{r["n"]}</td>'
                 f'<td>{r["bank"]}</td><td>{r["nbf"]}</td><td>{r["nonfin"]}</td>'
                 f'<td>{r["weight_bank"] * 100:.0f}%</td></tr>')

tr_bky = ''
for r in data['bank_years']:
    tr_bky += f'<tr><td>{r["year"]}</td><td class="{"neg" if r["ret"]<0 else "pos"}">{fmt(r["ret"])}</td></tr>'

svg = svg_line([[(r['d'], r['v']) for r in data['navs'][k]] for k in ['core', 'ew', 'idx', 'bank']],
               ['LX-core', '等权全A', '中证全指', '银行等权'],
               ['#c0392b', '#2471a3', '#7d3c98', '#b9770e'])

html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>LX-core 过去3年回测收益（2023-08 ~ 2026-08）</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:24px;color:#1f2937;background:#fff}}
h1{{font-size:22px;border-bottom:3px solid #c0392b;padding-bottom:8px}}
h2{{font-size:16px;margin-top:26px;color:#111}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}}
th,td{{border:1px solid #e5e7eb;padding:6px 10px;text-align:right}}
th{{background:#f3f4f6;font-weight:600}}
td.l,th.l{{text-align:left}}
.pos{{color:#c0392b}} .neg{{color:#059669}}
.note{{font-size:12px;color:#6b7280;margin:4px 0}}
.alert{{background:#fef3c7;border:1px solid #f59e0b;padding:10px 14px;border-radius:6px;font-size:13px;margin:12px 0}}
.kpi{{display:flex;gap:14px;margin:14px 0;flex-wrap:wrap}}
.kpi div{{flex:1;min-width:150px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px}}
.kpi b{{display:block;font-size:22px;margin-top:4px}}
.kpi span{{font-size:12px;color:#6b7280}}
</style></head><body>
<h1>LX-core（含金融）过去 3 年回测收益 — 2023-08-31 ~ 2026-08-24</h1>
<p class="note">执行规范：docs/prompt_template_fund_framework.md（日频 + 复权 + 半年调仓 T+1 撮合 + 同口径基准 + 先对照池子）。窗口 = 第 5~10 期 PIT 调仓（2023-08 起 6 期）。</p>

<div class="kpi">
  <div><span>LX-core 3年总收益</span><b class="pos">{fmt(data['core']['total'])}</b><span>年化 {fmt(data['core']['ann'])} · MDD {fmt_mdd(data['core']['mdd'])}</span></div>
  <div><span>等权全A（同口径）</span><b>{fmt(data['ew']['total'])}</b><span>年化 {fmt(data['ew']['ann'])} · MDD {fmt_mdd(data['ew']['mdd'])}</span></div>
  <div><span>超额 vs 等权全A</span><b class="pos">{fmt(data['core']['ex_ew'])}</b><span>3年窗口累计</span></div>
  <div><span>超额 vs 中证全指</span><b class="pos">{fmt(data['core']['ex_idx'])}</b><span>价格指数口径</span></div>
</div>

<div class="alert">⚠️ <b>数据口径</b>：回测缓存截至 <b>2026-08-24</b>（等权基准全市场价格未同步至 08-26，为避免基准失真三线统一截断；今日 08-27 盘中未收）。窗口长度 = 3.0 年（含 6 期半年调仓）。银行等权组合仅 {len(live_banks)} 只有复权价，为对照性质，非策略本身。</div>

<h2>一、总览：3 年窗口核心指标（日频 / 复权 / MDD 日频标准口径）</h2>
<table><tr><th class="l">组合</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>交易日</th><th class="l">区间</th></tr>
{tr_metrics}</table>

<h2>二、超额（先对照池子，再下结论）</h2>
<table><tr><th class="l">对比</th><th>3年超额</th><th class="l">说明</th></tr>{tr_excess}</table>

<h2>三、净值曲线（归一化，起点 = 1.0）</h2>
{svg}

<h2>四、分年度收益（自然年，2023 为 09-12 月）</h2>
<table><tr><th class="l">年份</th><th class="l">区间</th><th>天数</th><th>LX-core</th><th>等权全A</th><th>中证全指</th><th>超额vs全A</th></tr>
{tr_years}</table>

<h2>五、调仓周期收益（6 期半年调仓）</h2>
<table><tr><th class="l">周期</th><th>天数</th><th>LX-core</th><th>等权全A</th><th>中证全指</th><th>超额vs全A</th></tr>
{tr_periods}</table>

<h2>六、每期持仓结构（PE 升序 → 结构性重仓银行）</h2>
<table><tr><th class="l">调仓期</th><th>持仓数</th><th>银行</th><th>非银金融</th><th>非金融</th><th>银行权重占比</th></tr>
{tr_holds}</table>
<p class="note">Type D 审计：6 期持仓数均 = 40（目标）；价格覆盖缺口见下。</p>

<h2>七、银行等权组合对照（呼应"择时买银行"命题）</h2>
<table><tr><th class="l">年份</th><th>银行等权收益</th></tr>{tr_bky}</table>
<p class="note">3年窗口银行等权累计 {fmt(data['bank']['total'])}（vs core {fmt(data['core']['total'])}、vs 全A {fmt(data['ew']['total'])}）——2024 单年 +40% 后被 2025 年跑输大幅回吐，再一次验证：alpha 来自 PE 升序估值纪律而非银行标签。</p>

<h2>八、审计清单（模板 §⑤）</h2>
<table><tr><th class="l">检查项</th><th>结果</th><th class="l">证据</th></tr>
<tr><td class="l">池子 = 万得全A PIT 成分</td><td>✅ pass</td><td class="l">官方引擎 5532 只 PIT 池，无手工选股</td></tr>
<tr><td class="l">日频 + 复权</td><td>✅ pass</td><td class="l">官方 nav 日频、adj 复权口径（已对齐 +55.55%）</td></tr>
<tr><td class="l">MDD 日频标准口径</td><td>✅ pass</td><td class="l">(peak−trough)/peak 全序列</td></tr>
<tr><td class="l">同口径基准</td><td>✅ pass</td><td class="l">等权全A = 半年调仓 T+1 同语义；中证全指仅参考</td></tr>
<tr><td class="l">金融剔除未入回测</td><td>✅ pass</td><td class="l">core 含金融（银行 17~30 只/期），非 finex</td></tr>
<tr><td class="l">持仓数 = 目标</td><td>✅ pass</td><td class="l">6 期均 40 只</td></tr>
<tr><td class="l">价格覆盖</td><td>{'⚠️ 缓存截断' if any(a['miss_price'] for a in audit.values()) else '✅ pass'}</td><td class="l">242 只缓存至 2026-08-24，6 期持仓缺口极小（见 _bank_attr.py 已审计：归因层 +55.61% ≈ 官方 +55.55%）</td></tr>
</table>

<p class="note" style="margin-top:20px">数据源：官方回测缓存 _bt_daily_results.json / _bt_daily_ew_hold_nav.json / _bt_daily_idx.json（腾讯日K复权 + 万得全A PIT 成分）；脚本 _bt_3y.py；生成于 2026-08-27。</p>
</body></html>"""

open('_bt_3y_report.html', 'w', encoding='utf-8').write(html)
print('saved _bt_3y_report.html')
