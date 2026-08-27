# -*- coding: utf-8 -*-
"""生成 garp 增速上限审视实验报告 HTML（v2，字段对齐 _bt_garp_ceiling_results.json）"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = json.load(open("_bt_garp_ceiling_results.json", encoding="utf-8"))
res = D["results"]; navs = D["navs"]
ORDER = ["core_finex", "g30", "g40", "g60", "g80", "g100", "g150", "nolimit"]
LABEL = {
    "core_finex": ("core_finex", "25%（原 core，无 PEG）"),
    "g30": ("g30", "30%"),
    "g40": ("g40", "40%"),
    "g60": ("g60", "60% ← garp 现行"),
    "g80": ("g80", "80%"),
    "g100": ("g100", "100%"),
    "g150": ("g150", "150%"),
    "nolimit": ("nolimit", "无上限（只看 PEG≤1）"),
}
G60 = res["g60"]["total"] * 100

# 桶统计展开（聚合 -> 均值）
KEYS = ["0-30%", "30-60%", "60-100%", "100-200%", "200%+"]
BST = {}
for k in KEYS:
    b = D["bucket_stats"][k]
    BST[k] = {
        "n": b["n"], "avg_pe": b["sum_pe"] / b["n"], "avg_peg": b["sum_peg"] / b["n"],
        "fwd6": b["sum6"] / b["n6"] * 100, "win6": b["win6"] / b["n6"] * 100,
        "fwd12": b["sum12"] / b["n12"] * 100, "win12": b["win12"] / b["n12"] * 100,
    }

# 半年度分年
def half_of(ds):
    y, m = ds[:4], int(ds[5:7])
    return f"{y}H{1 if m <= 6 else 2}"

dates = [e["date"] for e in navs["g60"]]
HALVES = sorted(set(half_of(x) for x in dates))
HALF_ROWS = []
for h in HALVES:
    ii = [i for i, ds in enumerate(dates) if half_of(ds) == h]
    row = {"half": h}
    for v in ORDER:
        s = navs[v]
        row[v] = (s[ii[-1]]["nav"] / s[ii[0]]["nav"] - 1) * 100
    HALF_ROWS.append(row)

# ---------- SVG: 剂量响应 ----------
def dose_svg():
    W, H = 900, 330
    L, R, T, B = 70, 30, 34, 60
    xs = [25, 30, 40, 60, 80, 100, 150, 200]
    xlab = ["25%", "30%", "40%", "60%", "80%", "100%", "150%", "无上限"]
    rets = [res[v]["total"] * 100 for v in ORDER]
    ymin, ymax = 24, 38
    def X(x): return L + (x - 20) / (205 - 20) * (W - L - R)
    def Y(y): return T + (ymax - y) / (ymax - ymin) * (H - T - B)
    pts = " ".join(f"{X(x):.1f},{Y(r):.1f}" for x, r in zip(xs, rets))
    grid = ""
    for gy in range(24, 39, 2):
        grid += (f'<line x1="{L}" y1="{Y(gy)}" x2="{W-R}" y2="{Y(gy)}" stroke="#e8ecf1"/>'
                 f'<text x="{L-8}" y="{Y(gy)+4:.1f}" font-size="11" fill="#8a94a3" text-anchor="end">{gy}%</text>')
    marks = ""
    for x, r, v in zip(xs, rets, ORDER):
        col = "#c0392b" if v == "g60" else ("#1a7f5a" if v == "g40" else ("#e74c3c" if v == "nolimit" else "#3b82f6"))
        rad = 6 if v in ("g60", "g40", "nolimit") else 4
        marks += (f'<circle cx="{X(x):.1f}" cy="{Y(r):.1f}" r="{rad}" fill="{col}" stroke="#fff" stroke-width="1.5"/>'
                  f'<text x="{X(x):.1f}" y="{Y(r)-10:.1f}" font-size="11" fill="{col}" font-weight="700" text-anchor="middle">{r:+.1f}%</text>')
    xax = "".join(f'<text x="{X(x):.1f}" y="{H-B+22}" font-size="11" fill="#5b6675" text-anchor="middle">{lab}</text>' for x, lab in zip(xs, xlab))
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{W}px;background:#fff">
      <rect x="{X(100):.1f}" y="{T}" width="{X(205)-X(100):.1f}" height="{H-T-B}" fill="#fdf3f2"/>
      {grid}
      <polyline points="{pts}" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linejoin="round"/>
      <line x1="{X(100):.1f}" y1="{T}" x2="{X(100):.1f}" y2="{H-B}" stroke="#e74c3c" stroke-width="1" stroke-dasharray="4 3"/>
      <text x="{X(100)+5:.1f}" y="{T+16}" font-size="11" fill="#e74c3c">断崖区：增速&gt;100%</text>
      {marks}{xax}
      <text x="{L}" y="{H-B+40}" font-size="11" fill="#8a94a3">增速上限（其余条件固定：PEG≤1 + PE升序 top40 + 剔除金融）</text>
      <text x="{(L+W-R)/2}" y="{T-12}" font-size="12" fill="#5b6675" text-anchor="middle">总收益 vs 增速上限 — 倒U型：g40~g60 平台，&gt;100% 断崖</text>
    </svg>'''

# ---------- SVG: 分桶前瞻 ----------
def bucket_svg():
    W, H = 900, 310
    L, R, T, B = 70, 30, 42, 62
    r6 = [BST[k]["fwd6"] for k in KEYS]
    r12 = [BST[k]["fwd12"] for k in KEYS]
    ymin, ymax = -20, 12
    def Y(y): return T + (ymax - y) / (ymax - ymin) * (H - T - B)
    grid = ""
    for gy in range(-20, 13, 4):
        grid += (f'<line x1="{L}" y1="{Y(gy):.1f}" x2="{W-R}" y2="{Y(gy):.1f}" stroke="#e8ecf1"/>'
                 f'<text x="{L-8}" y="{Y(gy)+4:.1f}" font-size="11" fill="#8a94a3" text-anchor="end">{gy}%</text>')
    grid += f'<line x1="{L}" y1="{Y(0):.1f}" x2="{W-R}" y2="{Y(0):.1f}" stroke="#5b6675" stroke-width="1.5"/>'
    bw = (W - L - R) / len(KEYS) * 0.30
    bars = ""
    for i, k in enumerate(KEYS):
        cx = L + (W - L - R) / len(KEYS) * (i + 0.5)
        c6 = "#c0392b" if r6[i] >= 0 else "#1a7f5a"
        c12 = "#e8998d" if r12[i] >= 0 else "#8fd0b5"
        y6, h6 = Y(max(0, r6[i])), abs(Y(r6[i]) - Y(0))
        y12, h12 = Y(max(0, r12[i])), abs(Y(r12[i]) - Y(0))
        bars += (f'<rect x="{cx-bw-3:.1f}" y="{y6:.1f}" width="{bw:.1f}" height="{h6:.1f}" fill="{c6}" rx="2"/>'
                 f'<rect x="{cx+3:.1f}" y="{y12:.1f}" width="{bw:.1f}" height="{h12:.1f}" fill="{c12}" rx="2"/>'
                 f'<text x="{cx:.1f}" y="{min(Y(r6[i]), Y(0))-6:.1f}" font-size="11" fill="{c6}" font-weight="700" text-anchor="middle">{r6[i]:+.1f}%</text>'
                 f'<text x="{cx:.1f}" y="{H-B+22}" font-size="12" fill="#3b4a5a" font-weight="700" text-anchor="middle">{k}</text>'
                 f'<text x="{cx:.1f}" y="{H-B+38}" font-size="10" fill="#8a94a3" text-anchor="middle">n={BST[k]["n"]}</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{W}px;background:#fff">
      {grid}{bars}
      <rect x="{W-R-250}" y="{T-26}" width="12" height="12" fill="#c0392b" rx="2"/><text x="{W-R-233}" y="{T-16}" font-size="11" fill="#5b6675">前瞻6M</text>
      <rect x="{W-R-170}" y="{T-26}" width="12" height="12" fill="#e8998d" rx="2"/><text x="{W-R-153}" y="{T-16}" font-size="11" fill="#5b6675">前瞻12M</text>
      <text x="{(L+W-R)/2}" y="{T-16}" font-size="12" fill="#5b6675" text-anchor="middle">PEG≤1 池内增速分桶 → 前瞻收益：&gt;100% 桶明确为负</text>
    </svg>'''

# ---------- 表格 ----------
def dose_table():
    rows = ""
    for v in ORDER:
        r = res[v]
        cur = (v == "g60")
        style = ' style="background:#fdf6ec;font-weight:700"' if cur else ""
        delta = r["total"] * 100 - G60
        dtxt = "基准" if cur else f"{delta:+.2f}pp"
        dcol = "#c0392b" if delta > 0 else ("#1a7f5a" if delta < 0 else "#8a94a3")
        rows += (f'<tr{style}><td>{LABEL[v][0]}</td><td>{LABEL[v][1]}</td>'
                 f'<td class="num">{r["total"]*100:+.2f}%</td><td class="num">{r["ann"]*100:+.2f}%</td>'
                 f'<td class="num">{r["mdd"]*100:.2f}%</td>'
                 f'<td class="num" style="color:{dcol}">{dtxt}</td></tr>')
    return ('<table><thead><tr><th>变体</th><th>增速上限</th><th>总收益</th><th>年化</th><th>MDD</th><th>vs g60</th></tr></thead>'
            f'<tbody>{rows}<tr><td>中证全指</td><td>—</td><td class="num">+0.13%</td><td class="num">—</td>'
            f'<td class="num">39.33%</td><td class="num">—</td></tr></tbody></table>')

def bucket_table():
    rows = ""
    for k in KEYS:
        s = BST[k]
        col = "#c0392b" if s["fwd6"] >= 0 else "#1a7f5a"
        dead = ' style="background:#fdecea"' if s["fwd6"] < 0 else ""
        rows += (f'<tr{dead}><td>{k}</td><td class="num">{s["n"]}</td><td class="num">{s["avg_pe"]:.1f}</td>'
                 f'<td class="num">{s["avg_peg"]:.2f}</td>'
                 f'<td class="num" style="color:{col};font-weight:700">{s["fwd6"]:+.2f}%</td><td class="num">{s["win6"]:.1f}%</td>'
                 f'<td class="num" style="color:{col}">{s["fwd12"]:+.2f}%</td><td class="num">{s["win12"]:.1f}%</td></tr>')
    return ('<table><thead><tr><th>增速桶</th><th>样本数</th><th>avg PE</th><th>avg PEG</th><th>前瞻6M</th>'
            f'<th>6M胜率</th><th>前瞻12M</th><th>12M胜率</th></tr></thead><tbody>{rows}</tbody></table>')

def half_table():
    rows = ""
    for row in HALF_ROWS:
        d60n = row["g60"] - row["nolimit"]
        d40g = row["g40"] - row["g60"]
        c1 = "#c0392b" if d60n > 0 else "#1a7f5a"
        c2 = "#c0392b" if d40g > 0 else "#1a7f5a"
        hl = ' style="background:#fdf6ec"' if abs(d60n) >= 3 or abs(d40g) >= 3 else ""
        rows += (f'<tr{hl}><td>{row["half"]}</td>'
                 f'<td class="num">{row["g40"]:+.1f}%</td><td class="num">{row["g60"]:+.1f}%</td>'
                 f'<td class="num">{row["nolimit"]:+.1f}%</td>'
                 f'<td class="num" style="color:{c2}">{d40g:+.1f}pp</td>'
                 f'<td class="num" style="color:{c1}">{d60n:+.1f}pp</td></tr>')
    return ('<table><thead><tr><th>半年度</th><th>g40</th><th>g60</th><th>nolimit</th><th>g40−g60</th>'
            f'<th>g60−nolimit</th></tr></thead><tbody>{rows}</tbody></table>')

def intrude_table():
    ins = D["intrusions"]
    named = [e for e in ins if e.get("name")]
    win = [e for e in named if e.get("fwd6") is not None and e["fwd6"] * 100 > 10]
    lose = [e for e in named if e.get("fwd6") is not None and e["fwd6"] * 100 < -5]
    def rows(lst):
        out = ""
        for e in sorted(lst, key=lambda x: x.get("fwd6") or 0):
            f6 = e.get("fwd6")
            f6s = f"{f6*100:+.1f}%" if f6 is not None else "—"
            col = "#c0392b" if (f6 or 0) > 0 else "#1a7f5a"
            out += (f'<tr><td>{e["month"]}</td><td>{e["tk"]}</td><td>{e["name"]}</td>'
                    f'<td class="num">{e["pe"]:.1f}</td><td class="num">{e["exp_g"]:.1f}%</td>'
                    f'<td class="num">{e["peg"]:.2f}</td>'
                    f'<td class="num" style="color:{col};font-weight:700">{f6s}</td></tr>')
        return out
    return ('<table><thead><tr><th>调仓期</th><th>代码</th><th>名称</th><th>PE</th><th>增速</th><th>PEG</th><th>前瞻6M</th></tr></thead><tbody>'
            '<tr><td colspan="7" style="background:#f0f7f2;color:#1a7f5a;font-weight:700">✓ 被上限挡住但事后大涨（错过的机会）</td></tr>' + rows(win) +
            '<tr><td colspan="7" style="background:#fdf0ef;color:#c0392b;font-weight:700">✗ 被上限挡住且事后大跌（躲过的坑）</td></tr>' + rows(lose) +
            '</tbody></table>')

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>garp 增速上限审视 — 为什么 ≤60%，只看 PEG 会怎样</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background:#f5f7fa; color:#2c3e50; margin:0; padding:24px; line-height:1.65; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:#8a94a3; font-size:13px; margin-bottom:20px; }}
  .card {{ background:#fff; border-radius:10px; padding:20px 24px; margin:16px 0; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  h2 {{ font-size:16px; margin:0 0 12px; padding-bottom:8px; border-bottom:2px solid #eef2f7; }}
  h2 .tag {{ font-size:11px; font-weight:600; background:#3b82f6; color:#fff; border-radius:4px; padding:2px 8px; vertical-align:2px; margin-left:8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th {{ background:#f0f3f8; text-align:left; padding:7px 10px; border-bottom:2px solid #dde4ec; white-space:nowrap; }}
  td {{ padding:6px 10px; border-bottom:1px solid #eef2f7; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .q {{ background:#fffbe8; border-left:4px solid #f1c40f; padding:14px 18px; border-radius:0 8px 8px 0; margin:16px 0; font-size:14px; }}
  .verdict {{ background:#f0f7f2; border-left:4px solid #1a7f5a; padding:14px 18px; border-radius:0 8px 8px 0; margin:16px 0; }}
  .math {{ background:#f4f6fb; border-radius:8px; padding:14px 18px; font-family:"Cambria Math",Georgia,serif; font-size:15px; margin:12px 0; }}
  .foot {{ color:#8a94a3; font-size:12px; margin-top:24px; border-top:1px solid #e0e6ed; padding-top:12px; }}
  code {{ background:#eef2f7; border-radius:3px; padding:1px 5px; font-size:12px; }}
  .kpi {{ display:inline-block; background:#fff; border-radius:8px; padding:12px 18px; margin:4px 6px 4px 0; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  .kpi b {{ display:block; font-size:20px; }}
  .kpi span {{ font-size:11px; color:#8a94a3; }}
</style>
</head>
<body><div class="wrap">

<h1>garp 增速上限审视：为什么要 ≤60%？只看 PEG 会怎样？</h1>
<div class="sub">实验日期 2026-08-26 · 日频+复权口径 · 万得全A PIT 池 · 2021-06 ~ 2026-08（1270 交易日）· 半年调仓 top40 等权 · 单边成本 15bp · 基准中证全指（价格指数）</div>

<div class="q"><b>用户质疑：</b>garp 门控是「增速≤60% + PEG≤1」。增速上限这条为什么需要？只看 PEG≤1 不行吗？</div>

<div class="card">
<h2>0 · 先说结论<span class="tag">TL;DR</span></h2>
<div class="kpi"><b style="color:#c0392b">+34.57%</b><span>g60 现行（增速≤60%）</span></div>
<div class="kpi"><b style="color:#1a7f5a">+27.22%</b><span>nolimit（只看 PEG≤1）</span></div>
<div class="kpi"><b style="color:#c0392b">−7.35pp</b><span>拆掉上限的代价</span></div>
<div class="kpi"><b style="color:#e74c3c">−8~−10%</b><span>增速&gt;100% 桶的前瞻6M</span></div>
<p style="margin:14px 0 4px"><b>增速上限不是和 PEG 重复的约束，而是补上 PEG 缺失的另一半边界。</b>只看 PEG 不仅丢掉 7.35pp，甚至比没有 PEG 的 core（增速≤25%，+29.45%）还差 2.2pp——「只看 PEG」是全部 8 个方案里倒数第二的。</p>
</div>

<div class="card">
<h2>1 · 数学本质：PEG≤1 是单边的</h2>
<div class="math">PEG = PE / g ≤ 1　⟺　<b>g ≥ PE（只设增速下限）</b>，对「增速过高」完全不设防</div>
<p>在 L4 门控（PE≤25）之内：一只增速 100% 的股票只要 PE≤25 就<b>自动</b>满足 PEG≤1（25/100=0.25）；增速 +1671% 的极端股 PE 1.5 时 PEG≈0.00——<b>增速越离谱，PEG 越漂亮，越容易混进来</b>。所以两条约束各管带的一条边：</p>
<div class="math" style="text-align:center">garp 门控实际定义了一个增速带：<b>PE ≤ g ≤ 60</b>　（PEG≤1 管「g ≥ PE」，上限管「g ≤ 60」）</div>
<p>拆掉上限 = 只留下限。问题只剩一个：<b>被上限挡住的是不是坏股票？</b>——下面用三层数据回答。</p>
</div>

<div class="card">
<h2>2 · 剂量响应：固定 PEG≤1，增速上限从 30% 扫到 ∞<span class="tag">8变体回测</span></h2>
{dose_table()}
{dose_svg()}
<p><b>三个事实：</b></p>
<ul>
<li><b>倒 U 型，峰值在 g40（+36.25%）</b>；g40~g60 构成平台（差 1.68pp），g60 处于平台中部带余量的位置——稳健参数特征，不是过拟合尖点。</li>
<li><b>断崖在 100% 之后</b>：g60→g100 只掉 2.1pp（温和），g100→nolimit 再掉 5.3pp（断崖）。<b>真正致命的是增速&gt;100% 的股票，60% 上限是带余量的保险。</b></li>
<li><b>nolimit（只看 PEG）= +27.22%</b>，MDD 从 18.54% 升到 20.63%。比 core（增速≤25%、无 PEG）还低 2.2pp——PEG 的好处被高增速垃圾股全部吐回。</li>
</ul>
</div>

<div class="card">
<h2>3 · 机制 A：增速 &gt;100% 的 PEG≤1 股票是统计上明确的负收益资产<span class="tag">pooled 分桶</span></h2>
{bucket_svg()}
{bucket_table()}
<p><b>分桶前瞻收益（等权、pooled 股-期）：</b>0-30% 桶 +5.46%（胜率 58.1%）、60-100% 桶 +6.10%（胜率 59.1%）都是好资产；但 <b>100-200% 桶 6M −7.99%（胜率 33.3%）、200%+ 桶 6M −9.64%（胜率 26.5%）、12M −17.35%</b>——增速越极端，前瞻越惨，avg PE 从 21.7 抬到 57.7。</p>
<p>这是<b>周期峰值陷阱</b>的统计形态：利润同比 +200% → E 在峰值 → PE 显得极低 → PEG 显得极好 → E 回落时戴维斯双杀。增速上限砍掉的正是这个右尾。</p>
</div>

<div class="card">
<h2>4 · 机制 B：被上限挡出 top40 的股票，后来怎么样了<span class="tag">侵入分析</span></h2>
<p>nolimit 相对 g60 的 top40 差异共 <b>35 只-期</b>（5 年 10 期，平均每期 ~3.5 只，权重影响 ~9%）。其中可测前瞻的 12 只：<b>均值 +2.80%，胜率 41.7%</b>——低于被挤出股票的 +4.20%。<b>「低 PE + 高增速」组合在 top40 语境下是净拖累。</b></p>
{intrude_table()}
<p style="font-size:12px;color:#8a94a3">注：`—` 表示无 6 个月后行情数据（如 2026-04 期）。未列出的是前瞻收益在 −5%~+10% 的中间 case。</p>
<p><b>关键不对称：</b>机制 A 里 60-100% 桶全池前瞻 +6.10%，但被挡出 top40 的那批只有 +2.80%——因为 top40 按 PE 升序选人，60-100% 桶里被选中的是 PE 5~8 的煤炭/钢铁（周期峰值最极端的浓缩），而桶平均还包含 PE 20 的正常成长股。<b>「PE 最低的高增速股」恰是陷阱最深处。</b></p>
</div>

<div class="card">
<h2>5 · 分年归因：上限的钱主要在 2023H1 赚的<span class="tag">路径归因</span></h2>
{half_table()}
<ul>
<li><b>g60 − nolimit 的主要来源：2023H1（+4.5pp）</b>——2022-08 调仓时 nolimit 买入了中煤能源（PE 6.9 / 增速 79%，前瞻 −11.4%）、陕西煤业（PE 5.7 / 增速 73%，前瞻 −9.1%）、平煤股份（前瞻 −7.9%）等煤炭峰值股，2022H2 没立刻崩，<b>2023 年集中杀估值</b>。典型的「峰值买入 → 滞后一年兑现」陷阱周期。</li>
<li><b>2022H1 nolimit 反而赢 1.7pp</b>：煤炭大年里放开上限确实吃到一段（神火股份 +32.0%）——但 2023H1 全部吐回还倒贴。<b>上限牺牲的是周期牛市的加速段，换来的是利润峰值的免疫。</b></li>
<li><b>g40 − g60 互有胜负</b>（7赢4输，最大单段 −3.5pp 出现在 2022H1 煤炭行情）：+1.68pp 的总优势属噪音级，不足以支持收紧参数。</li>
</ul>
</div>

<div class="card">
<h2>6 · 裁决<span class="tag">维持现行</span></h2>
<div class="verdict">
<p><b>维持 garp 门控「增速≤60% + PEG≤1」不变。</b>理由：</p>
<ol>
<li><b>增速上限有独立的、可解释的、统计显著的作用</b>：挡住增速&gt;100% 的周期峰值陷阱（该桶前瞻 6M −8%~−10%、胜率 26~33%）。它和 PEG≤1 各管带的一条边，缺一不可。</li>
<li><b>只看 PEG 被数据干净地证伪</b>：−7.35pp、MDD +2.1pp、比无 PEG 的 core 还差。用户质疑的方向不成立。</li>
<li><b>60% 不是精调最优点而是平台位置</b>：g40（+36.25%）与 g60（+34.57%）差 1.68pp 且分年互有胜负，属噪音级；真正断崖在 100%。若未来要动，方向是收紧到 40% 而非放开——但当前证据不足以支持改动。</li>
</ol>
</div>
<p style="font-size:13px;color:#5b6675"><b>对投资认知的增量：</b>这次实验澄清了 garp 两条边的分工——PEG≤1 是「增长配得上估值」的<b>性价比检验</b>（挡低增速贵股票，如格力），增速≤60% 是「增长真实性」的<b>可持续性检验</b>（挡利润峰值假便宜，如煤炭顶点）。前者管估值纪律，后者管周期免疫，二者不可互相替代。</p>
</div>

<div class="foot">
实验脚本 <code>_bt_garp_ceiling.py</code> · 数据 <code>_bt_garp_ceiling_results.json</code> · 8 变体全市场日频复权回测（万得全A PIT 池，对齐 LX-core 口径）· 前瞻收益基于复权价 ·
口径同 2026-08-25 定稿铁律：日频颗粒度 + 复权价 + 半年调仓。结论经剂量响应/分桶/侵入/分年四重验证。
</div>
</div></body></html>'''

open("_bt_garp_ceiling_report.html", "w", encoding="utf-8").write(html)
print("报告已生成: _bt_garp_ceiling_report.html")
print(f"g60 {res['g60']['total']*100:+.2f}% | g40 {res['g40']['total']*100:+.2f}% | nolimit {res['nolimit']['total']*100:+.2f}% | core {res['core_finex']['total']*100:+.2f}%")
