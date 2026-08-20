# -*- coding: utf-8 -*-
"""行业聚合层实验 · 阶段5：三方案对比报告生成。

输入：
  _bt_gl_{baseline,plan2,plan1}_nav.json    逐期 NAV
  _bt_gl_{baseline,plan2,plan1}_detail.json 持仓明细（含光模块）
  _bt_gl_nav.json                           旧基线（数据漂移前）
  _bt_sel_{mode}.json                       候选
输出：industry_gate_experiment_report.html
"""
from __future__ import annotations

import json
import os

MODES = ["baseline", "plan2", "plan1"]
MODE_CN = {"baseline": "基线(新快照)", "plan2": "方案2 s1龙头分",
           "plan1": "方案1 top-100直通"}
BENCH = "中证全指"
CAPITAL = 1_000_000

OPTICS = {"300308.SZ": "中际旭创", "300502.SZ": "新易盛",
          "300394.SZ": "天孚通信", "688313.SH": "仕佳光子",
          "688668.SH": "鼎通科技", "603083.SH": "剑桥科技",
          "002281.SZ": "光迅科技", "300570.SZ": "太辰光"}

REB = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
       "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def fmt_money(x):
    return f"{x:+,.0f}"


def pct(x):
    return f"{x:+.1%}"


def load(mode):
    nav = json.loads(open(f"_bt_gl_{mode}_nav.json", encoding="utf-8").read())
    det = json.loads(open(f"_bt_gl_{mode}_detail.json",
                          encoding="utf-8").read())
    sel = json.loads(open(f"_bt_sel_{mode}.json", encoding="utf-8").read())
    return nav, det, sel


def main():
    bench = json.loads(open("_bt_benchmark.json", encoding="utf-8").read())
    data = {m: load(m) for m in MODES}
    old_nav = json.loads(open("_bt_gl_nav.json", encoding="utf-8").read())

    # ---- 总览 KPI ----
    rows_kpi = []
    for m in MODES:
        nav, det, sel = data[m]
        bal = {r["month"]: r["nav"] for r in nav}
        dts = sorted(bal.keys())
        r = bal[dts[-1]] / CAPITAL - 1
        br = bench[dts[-1]] / bench[dts[0]] - 1
        yrs = len(dts) / 12
        rows_kpi.append((MODE_CN[m], r, bal[dts[-1]], r - br,
                         ((1 + r) ** (1 / yrs) - 1),
                         ((1 + br) ** (1 / yrs) - 1)))
    # 旧基线参照
    old_bal = {r["month"]: r["nav"] for r in old_nav}
    old_dts = sorted(old_bal.keys())
    old_r = old_bal[old_dts[-1]] / CAPITAL - 1

    # ---- 逐期收益 ----
    rows_period = []
    for m in MODES:
        nav, det, sel = data[m]
        bal = {r["month"]: r["nav"] for r in nav}
        dts = sorted(bal.keys())
        hist = det["history"]
        hist_dts = [h["dt"] for h in hist]
        line = []
        for i, h in enumerate(hist):
            mk = h["dt"]
            nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
            end = nxt if nxt in bal else dts[-1]
            ret = bal[end] / bal[mk] - 1 if end in bal else 0.0
            m0, m1 = mk[:7], end[:7]
            brk = (bench[m1] / bench[m0] - 1
                   if bench.get(m0) and bench.get(m1) else None)
            opt_in = [OPTICS[t] for t in h["weights"] if t in OPTICS]
            line.append({"mk": mk, "ret": ret, "bench": brk,
                         "n": h["n"], "optics": opt_in,
                         "gross": sum(h["weights"].values())})
        rows_period.append(line)

    # ---- 光模块进池时间线 ----
    optics_tl = {}
    for m in MODES:
        nav, det, sel = data[m]
        tl = {}
        for month, v in sel.items():
            in_cand = [OPTICS[c[0]] for c in v["candidates"]
                       if c[0] in OPTICS]
            tl[month] = in_cand
        optics_tl[m] = tl

    # ---- HTML ----
    h = []
    h.append("""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>行业聚合层实验 · 三方案对比</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2329;--mut:#646a73;--line:#e5e6eb;
--pos:#d93026;--neg:#00a870;--ac:#2454ff;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--ink);padding:28px 20px;line-height:1.6}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:22px;margin-bottom:6px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:18px 20px;margin-bottom:16px}
h2{font-size:16px;margin-bottom:12px;border-left:3px solid var(--ac);
padding-left:8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--line);
white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:12px}
td:first-child,th:first-child{text-align:left}
.pos{color:var(--pos);font-weight:600}
.neg{color:var(--neg);font-weight:600}
.best{background:#fff7e6}
.kpi-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:4px}
.kpi{flex:1;min-width:170px;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:14px 16px}
.kpi .k{font-size:12px;color:var(--mut)}
.kpi .v{font-size:20px;font-weight:700;margin-top:2px}
.kpi .s{font-size:12px;color:var(--mut);margin-top:2px}
.note{font-size:12.5px;color:var(--mut);background:#f2f3f5;border-radius:8px;
padding:10px 14px;margin-top:10px}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:10px;
background:#eef1ff;color:var(--ac);margin:1px 2px}
.warn{background:#fff7e6;border:1px solid #ffd591}
</style></head><body><div class="wrap">
<h1>行业聚合层实验：删掉"行业 top-5"这一层会怎样</h1>
<div class="sub">growth_loop HOOK 层确定性回测 · 5 年（2021-08 → 2026-08）·
conviction_weighted + 单票 8% · 成本 5bp+10bp · 三方案共用同一份点时数据快照</div>
""")

    # ---- KPI ----
    kpi_html = '<div class="kpi-row">'
    for name, r, bal_e, ex, ar, ar_b in rows_kpi:
        cls = "pos" if r >= 0 else "neg"
        kpi_html += (f'<div class="kpi"><div class="k">{esc(name)}</div>'
                     f'<div class="v {cls}">{pct(r)}</div>'
                     f'<div class="s">期末 {bal_e:,.0f} 元 · 超额 {pct(ex)}'
                     f' · 年化 {pct(ar)}</div></div>')
    kpi_html += (f'<div class="kpi"><div class="k">旧基线参照（漂移前快照）</div>'
                 f'<div class="v neg">{pct(old_r)}</div>'
                 f'<div class="s">-139,821 元 · 数据源修订前的结果，仅供参照</div>'
                 f'</div></div>')
    h.append(kpi_html)

    # ---- 三方案对比表 ----
    h.append('<div class="card"><h2>三方案总览</h2><table>'
             '<tr><th>方案</th><th>总收益</th><th>期末市值</th>'
             '<th>超额(中证全指)</th><th>年化</th>'
             '<th>候选并集</th><th>期均持仓</th></tr>')
    for mi, (name, r, bal_e, ex, ar, ar_b) in enumerate(rows_kpi):
        union = set()
        n_h = []
        for v in data[MODES[mi]][2].values():
            union.update(c[0] for c in v["candidates"])
            n_h.append(len(v["candidates"]))
        cls = "pos" if r >= 0 else "neg"
        h.append(f'<tr><td>{esc(name)}</td>'
                 f'<td class="{cls}">{pct(r)}</td>'
                 f'<td>{bal_e:,.0f}</td>'
                 f'<td class="{cls}">{pct(ex)}</td>'
                 f'<td>{pct(ar)}</td>'
                 f'<td>{len(union)}</td>'
                 f'<td>{sum(n_h)/len(n_h):.0f}</td></tr>')
    h.append('</table>')

    # ---- 逐期对比 ----
    h.append('<h2>逐期收益对比（基准 = 中证全指同期）</h2><table>'
             '<tr><th>调仓期</th>')
    for m in MODES:
        h.append(f'<th>{esc(MODE_CN[m])}</th>')
    h.append('<th>基准</th></tr>')
    for i, mk in enumerate(REB):
        h.append(f'<tr><td>{mk}</td>')
        best = max((row[i]["ret"] for row in rows_period),
                   default=None)
        for row in rows_period:
            r = row[i]["ret"]
            cls = "pos" if r >= 0 else "neg"
            star = ' class="best"' if r == best else ""
            opt = ("<br><span style='font-size:11px;color:#2454ff'>"
                   + " ".join(f"<span class='tag'>{esc(o)}</span>"
                              for o in row[i]["optics"]) + "</span>"
                   if row[i]["optics"] else "")
            h.append(f'<td{star} class="{cls}">{pct(r)}{opt}</td>')
        b = rows_period[0][i]["bench"]
        h.append(f'<td>{pct(b) if b is not None else "—"}</td></tr>')
    h.append('</table>')
    h.append('<div class="note">蓝色标签 = 当期持仓中的光模块标的（中际旭创/'
             '新易盛/天孚通信/仕佳光子/鼎通科技/剑桥科技/光迅科技/太辰光）。'
             '收益为该调仓期到下个调仓期（或期末）的组合收益。</div>')

    # ---- 光模块进池时间线 ----
    h.append('<div class="card"><h2>光模块进候选池的时间线（三方案对比）</h2>'
             '<table><tr><th>调仓期</th>')
    for m in MODES:
        h.append(f'<th>{esc(MODE_CN[m])}</th>')
    h.append('</tr>')
    for mk in REB:
        h.append(f'<tr><td>{mk}</td>')
        for m in MODES:
            names = optics_tl[m].get(mk, [])
            h.append('<td>' + (" ".join(f"<span class='tag'>{esc(n)}</span>"
                                        for n in names) or "—") + '</td>')
        h.append('</tr>')
    h.append('</table>')
    h.append('<div class="note">2025-04 期是光模块主升浪窗口（新易盛 '
             '2025-04→08 +297%）。中际旭创 2025-04 期营收增速 38%，已跌出'
             '全市场增速 top-100（2024 年高基数），任何方案都抓不到它；'
             '新易盛增速 264% 在 top-100 内，plan2/plan1 均能在该期让其'
             '进候选。</div></div>')

    # ---- 新易盛反事实验证 ----
    h.append('<div class="card"><h2>反事实验证：新易盛 2025-04 期若进池</h2>'
             '<table><tr><th>标的</th><th>2025-04 营收YoY</th>'
             '<th>毛利率(最新4期)</th><th>HOOK 触发</th>'
             '<th>层级</th><th>2025-04→08 涨幅</th></tr>')
    h.append('<tr><td>新易盛</td><td>+264%</td>'
             '<td>48.7 / 44.7 / 42.3 / 43.0</td>'
             '<td><b>H1 + H2</b></td><td>A（高信念）</td>'
             '<td class="pos">+297%</td></tr>')
    h.append('<tr><td>仕佳光子</td><td>+121%</td>'
             '<td>39.1 / 26.3 / 25.8 / 23.8</td>'
             '<td><b>H1 + H2</b></td><td>A（高信念）</td>'
             '<td class="pos">+221%</td></tr>')
    h.append('<tr><td>中际旭创</td><td>+38%（top-100 外）</td>'
             '<td>36.7 / 33.8 / 33.3 / 33.1</td>'
             '<td>H2</td><td>—（不在候选池）</td>'
             '<td class="pos">+325%</td></tr>')
    h.append('</table>'
             '<div class="note warn">诚实边界：中际旭创 2025-04 期不在任何'
             '方案的候选池（增速 38% 跌出全市场 top-100），它是 2025 上半年'
             '涨幅最大的光模块（+325%），但当时的数值筛选体系无法预知——'
             '这属于“增速排名筛选”的固有盲区（高基数下增速回落但股价仍在'
             '主升浪），不是行业聚合层的问题。plan1/plan2 修复的是“新易盛”'
             '这类增速仍在顶部的光模块。</div></div>')

    # ---- 诚实标注 ----
    h.append('<div class="card"><h2>诚实边界与结论</h2><ul style='
             '"font-size:13px;padding-left:20px">'
             '<li><b>数据漂移</b>：本次三方案共用重新筛选的 top-100 快照'
             '（2026-08-19 查询历史报告期）。与 2026-08-17 旧快照相比，'
             '每期候选重叠率 80-95%，2024-08 期光模块三杰被修订进池——'
             '这是数据源修订导致的漂移，因此旧基线 -139,821 元仅作参照，'
             '以新快照 baseline 为对比基准。</li>'
             '<li><b>LOOP 层未回测</b>：仍只用 HOOK 层 + conviction 代理'
             '（L1-L7 LLM 深研无法诚实回测）。</li>'
             '<li><b>方案2 参数</b>：龙头质量分 = 池内存在 growth≥0.5 且 '
             'roe≥15 成员 +1，再存在 growth≥1.0 成员 +1（s1 上限 4）。'
             '这是“双钩龙头”在行业打分阶段（只有 growth/roe 两字段）的'
             '确定性近似。</li>'
             '<li><b>结论</b>：删掉行业聚合层（plan1）候选池扩大 2 倍以上，'
             'HOOK 层本身能识别光模块双钩；plan2 以极小候选变化在 2025-04 '
             '期抓到了新易盛/仕佳光子，是性价比最高的修复。</li>'
             '</ul></div>')

    h.append('</div></body></html>')
    html = "\n".join(h)
    open("industry_gate_experiment_report.html", "w",
         encoding="utf-8").write(html)
    print("报告已生成: industry_gate_experiment_report.html")


if __name__ == "__main__":
    main()
