# -*- coding: utf-8 -*-
"""LX-core vs LX-gm 质量过滤版 — 过去3年窗口完整对比
口径: garp 门控(增速≤60% + 0<PEG≤1) 全池含金融, 日频复权, 5bp费+10bp滑点
窗口: 2023-08-31(第5期调仓) ~ 2026-08-24(缓存截断, 三线统一)
锚点: core 5年 +67.01% 已对齐 garp 审计
"""
import json

D = json.load(open("_bt_gm_daily_data.json", encoding="utf-8"))
W0, W1 = "2023-08-31", "2026-08-24"

def metrics(nav):
    m = {r["date"]: r["nav"] for r in nav}
    ks = [d for d in sorted(m) if W0 <= d <= W1]
    tot = m[ks[-1]] / m[ks[0]] - 1
    yrs = len(ks) / 252
    ann = (1 + tot) ** (1 / yrs) - 1 if tot > -1 else -1
    peak = m[ks[0]]; mdd = 0.0
    for d in ks:
        peak = max(peak, m[d]); mdd = max(mdd, 1 - m[d] / peak)
    return tot, ann, mdd, m, ks

def yearly(m, ks):
    seg = {}
    for d in ks:
        seg.setdefault(d[:4], []).append(d)
    return {y: m[ds[-1]] / m[ds[0]] - 1 for y, ds in seg.items()}

R = {}
for k, label in [("core", "LX-core"), ("gm", "LX-gm"), ("ew", "等权全A"), ("idx", "中证全指")]:
    tot, ann, mdd, m, ks = metrics(D[k])
    R[k] = dict(label=label, tot=tot, ann=ann, mdd=mdd, m=m, ks=ks, yr=yearly(m, ks))
    print(f"{label:>8}: total {tot:+8.2%}  ann {ann:+8.2%}  mdd {mdd:7.2%}  days {len(ks)}")

print(f"\ncore 超EW: {R['core']['tot']-R['ew']['tot']:+.2%} | gm 超EW: {R['gm']['tot']-R['ew']['tot']:+.2%} | core-gm: {R['core']['tot']-R['gm']['tot']:+.2%}")
print("分年度:")
for y in ["2023", "2024", "2025", "2026"]:
    c, g, e, i = (R[k]["yr"].get(y, 0.0) for k in ("core", "gm", "ew", "idx"))
    print(f"  {y}: core {c:+.2%}  gm {g:+.2%}  EW {e:+.2%}  idx {i:+.2%}  | 超额core {c-e:+.2%}  超额gm {g-e:+.2%}")

# 银行占比（3年窗口 = 2023-08 起 6 期）
fin = set(D["fin"])
wc, wg = D["weights"]["core"], D["weights"]["gm"]
periods = sorted(p for p in wc if p >= "2023-08")
print("期银行占比:")
for p in periods:
    cb = sum(1 for t in wc[p] if t in fin); gb = sum(1 for t in wg[p] if t in fin)
    ov = len(set(wc[p]) & set(wg[p]))
    print(f"  {p}: core银行{cb:>2}  gm银行{gb:>2}  重叠{ov}/40")

# ---------- 生成 HTML ----------
def nav_pct(nav):
    m = {r["date"]: r["nav"] for r in nav}
    ks = [d for d in sorted(m) if W0 <= d <= W1]
    base = m[ks[0]]
    return ks, [m[d] / base - 1 for d in ks]

def svg_lines(series, colors, labels):
    W, H, pad_l, pad_b, pad_t, pad_r = 900, 300, 60, 34, 16, 16
    allv = [v for _, vs in series for v in vs]
    vmin, vmax = min(allv), max(allv)
    xs = [i / (len(series[0][1]) - 1) for i in range(len(series[0][1]))]
    def X(i): return pad_l + xs[i] * (W - pad_l - pad_r)
    def Y(v): return pad_t + (vmax - v) / (vmax - vmin) * (H - pad_t - pad_b)
    g = [f'<text x="{W-pad_r}" y="{pad_t+8}" text-anchor="end" font-size="11" fill="#666">净值（2023-08-31=0）</text>']
    for (ks, vs), c in zip(series, colors):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vs))
        g.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.8"/>')
    # 网格 + 0 线
    for v in [vmin, (vmin+vmax)/2, 0, vmax]:
        if vmin <= v <= vmax:
            g.append(f'<line x1="{pad_l}" y1="{Y(v):.1f}" x2="{W-pad_r}" y2="{Y(v):.1f}" stroke="#ddd" stroke-width="0.6"/>')
            g.append(f'<text x="{pad_l-6}" y="{Y(v)+4:.1f}" text-anchor="end" font-size="10" fill="#888">{v*100:+.0f}%</text>')
    # 图例
    lx, ly = pad_l + 8, pad_t + 6
    for (_, vs), c, lab in zip(series, colors, labels):
        g.append(f'<rect x="{lx}" y="{ly-9}" width="14" height="3" fill="{c}"/>')
        g.append(f'<text x="{lx+18}" y="{ly-4}" font-size="11" fill="#333">{lab}</text>')
        lx += 24 + len(lab) * 12
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;background:#fff">' + "".join(g) + "</svg>"

names = ["LX-core（含金融）", "LX-gm 质量过滤版", "等权全A（同口径）", "中证全指 000985.SH"]
colors = ["#c0392b", "#2471a3", "#7d3c98", "#b9770e"]
series = [(nav_pct(D[k])) for k in ("core", "gm", "ew", "idx")]
svg = svg_lines(series, colors, names)

def row(k, bold=False):
    r = R[k]
    s = "font-weight:700;background:#fdf2f2" if bold else ""
    return (f'<tr style="{s}"><td>{r["label"]}</td><td>{r["tot"]:+.2%}</td>'
            f'<td>{r["ann"]:+.2%}</td><td>{r["mdd"]:.2%}</td>'
            f'<td>{r["tot"]-R["ew"]["tot"]:+.2%}</td></tr>')

yr_rows = ""
for y in ["2023", "2024", "2025", "2026"]:
    c, g, e, i = (R[k]["yr"].get(y, 0.0) for k in ("core", "gm", "ew", "idx"))
    yr_rows += (f'<tr><td>{y}{"（09-12月）" if y=="2023" else "（至08-24）" if y=="2026" else ""}</td>'
                f'<td style="color:{("#c0392b" if c>=0 else "#27ae60")}">{c:+.2%}</td>'
                f'<td style="color:{("#c0392b" if g>=0 else "#27ae60")}">{g:+.2%}</td>'
                f'<td>{e:+.2%}</td><td>{i:+.2%}</td>'
                f'<td style="color:{("#c0392b" if c-e>=0 else "#27ae60")}">{c-e:+.2%}</td>'
                f'<td style="color:{("#c0392b" if g-e>=0 else "#27ae60")}">{g-e:+.2%}</td></tr>')

bk_rows = ""
for p in periods:
    cb = sum(1 for t in wc[p] if t in fin); gb = sum(1 for t in wg[p] if t in fin)
    ov = len(set(wc[p]) & set(wg[p]))
    bk_rows += f"<tr><td>{p}</td><td>{cb}/40</td><td>{gb}/40</td><td>{ov}/40</td></tr>"

html_doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>LX-core vs LX-gm 过去3年对比</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:24px auto;max-width:960px;color:#222;background:#fff}}
h1{{font-size:20px}} h2{{font-size:15px;margin-top:28px;border-left:4px solid #c0392b;padding-left:8px}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}}
th,td{{border:1px solid #ddd;padding:6px 10px;text-align:right}}
th{{background:#f5f5f5}} td.l{{text-align:left}}
.note{{font-size:12px;color:#666;line-height:1.7;background:#fafafa;padding:10px 14px;border-radius:4px;margin-top:8px}}
.tag{{display:inline-block;background:#fdecea;color:#c0392b;border-radius:3px;padding:1px 7px;font-size:12px;font-weight:600}}
</style></head><body>
<h1>LX-core vs 质量过滤版（LX-gm）— 过去3年收益对比</h1>
<p style="font-size:13px;color:#555">口径：garp 门控（增速≤60% + 0&lt;PEG≤1）+ 含金融全池 + 日频复权 + 5bp费/10bp滑点 · 窗口 2023-08-31 ~ 2026-08-24（第5~10期调仓）</p>

<h2>核心指标（3年）</h2>
<table>
<tr><th>组合</th><th>总收益</th><th>年化</th><th>MDD</th><th>3年超额（vs 等权全A）</th></tr>
{row('core', True)}{row('gm')}{row('ew')}{row('idx')}
</table>
<p class="tag">结论</p>
<p style="font-size:13px">3 年窗口下质量过滤版依然负贡献：<b>core +49.14% vs gm +35.41%（−13.73pp）</b>，gm 甚至跑输等权全A −3.5pp、跑赢中证全指 +10.9pp。超额差距较 5 年窗口（−21.9pp）收窄，但方向一致——质量硬过滤仍不值得。</p>

<h2>分年度（超额分布）</h2>
<table>
<tr><th>年份</th><th>LX-core</th><th>LX-gm</th><th>等权全A</th><th>中证全指</th><th>core超额</th><th>gm超额</th></tr>
{yr_rows}
</table>

<h2>净值曲线（2023-08-31 = 0）</h2>
{svg}

<h2>持仓结构（银行数 / 40）</h2>
<table>
<tr><th>调仓期</th><th>LX-core 银行</th><th>LX-gm 银行</th><th>两版重叠</th></tr>
{bk_rows}
</table>
<p class="note">质量过滤（毛利率≥全市场中位数）每期把银行从 core 的 18~26 只压到 0~5 只，两版重叠仅 2~9/40——本质是"结构性剔银行 + 换入高毛利成长"。2024 低估值修复大年是 core 全部超额来源（+35.1pp），gm 在该年踏空 −22.4pp（5年口径），3 年口径下仍 −13.7pp。</p>

<h2>结论</h2>
<ul style="font-size:13px;line-height:1.9">
<li><b>质量硬过滤（gm）在两个窗口都是负贡献</b>：5年 −21.94pp、3年 −13.73pp，且 3 年窗口下跑输同口径等权全A −3.5pp。</li>
<li><b>负贡献来源一致</b>：2024 修复年踏空（低估值银行/周期被滤掉），2025 小盘大年也未补齐（+5.9pp 不够填坑）。</li>
<li><b>质量层的正确用法是软排序 q20（0.8×PE+0.2×质量，+3.40pp）</b>，不是设门槛。gm 式硬过滤＝亲手扔掉框架 alpha 主要来源。</li>
</ul>
</body></html>"""

open("_bt_gm_3y_report.html", "w", encoding="utf-8").write(html_doc)
data = {k: dict(tot=R[k]["tot"], ann=R[k]["ann"], mdd=R[k]["mdd"],
                yr=R[k]["yr"], label=R[k]["label"]) for k in R}
json.dump(data, open("_bt_gm_3y_data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nreport: _bt_gm_3y_report.html")
