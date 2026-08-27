# -*- coding: utf-8 -*-
"""筹码合成 × 行业筛选 报告生成器 -> _chip_industry_report.html"""
import json
import os
import sqlite3
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
stats = json.load(open(os.path.join(HERE, "_chip_industry_stats.json"), encoding="utf-8"))
cur = json.load(open(os.path.join(HERE, "_chip_industry_data.json"), encoding="utf-8"))
ind_map = {r["ts_code"]: r["industry"] for r in cur["stocks"]}
chip2 = {r["ts_code"]: r["chip"] for r in cur["stocks"]}

# ---- 6 期验证（从缓存重算）----
hists = {}
for d in ["2025-10-31", "2025-12-31", "2026-02-28", "2026-04-30", "2026-06-30"]:
    fn = (f"_chip_hist_{d}.json" if d != "2026-06-30"
          else "_chip_industry_0630.json")
    hists[d] = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
hists["2026-07-31"] = chip2

con = sqlite3.connect(os.path.join(HERE, "data", "a_share_market.db"))
close = {}
for m in ("2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
          "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"):
    close[m] = dict(con.execute(
        "SELECT ticker, close FROM monthly_close WHERE month=?", (m,)))

periods = [("2025-10-31", "2025-10", "2025-11"), ("2025-12-31", "2025-12", "2026-01"),
           ("2026-02-28", "2026-02", "2026-03"), ("2026-04-30", "2026-04", "2026-05"),
           ("2026-06-30", "2026-06", "2026-07"), ("2026-07-31", "2026-07", "2026-08")]

val = []
for d, m0, m1 in periods:
    groups = {}
    for tc, v in hists[d].items():
        ind = ind_map.get(tc)
        if ind:
            groups.setdefault(ind, []).append((tc, v))
    rows = []
    for ind, lst in groups.items():
        if len(lst) < 15:
            continue
        rets = [close[m1][tc] / close[m0][tc] - 1 for tc, _ in lst
                if tc in close[m0] and tc in close[m1]]
        if len(rets) >= 9:
            rows.append((st.mean(v for _, v in lst), st.mean(rets)))
    rows.sort()
    q = len(rows) // 5
    lo = st.mean(r for _, r in rows[:q])
    hi = st.mean(r for _, r in rows[-q:])
    mid = st.mean(r for _, r in rows)
    xs = [r[0] for r in rows]; ys = [r[1] for r in rows]
    mx, my = st.mean(xs), st.mean(ys)
    corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / (st.pstdev(xs) * st.pstdev(ys))
    val.append({"date": d, "next": m1, "q1": lo, "mid": mid, "q5": hi,
                "spread": lo - hi, "corr": corr})

avg_spread = st.mean(v["spread"] for v in val)
avg_corr = st.mean(v["corr"] for v in val)
json.dump({"val": val, "avg_spread": avg_spread, "avg_corr": avg_corr},
          open(os.path.join(HERE, "_chip_industry_results.json"), "w",
               encoding="utf-8"), ensure_ascii=False, indent=1)

# ---- HTML ----
def tr_rank(s, i):
    reps = "、".join(f"{r['name']}({r['chip']:+.1f})" for r in s["reps"][:4])
    cls = "good" if i < 15 else "bad"
    return (f"<tr class='{cls}'><td>{i+1}</td><td>{s['industry']}</td><td>{s['n']}</td>"
            f"<td>{s['mean']:+.2f}</td><td>{s['median']:+.2f}</td>"
            f"<td>{s['low_share']*100:.0f}%</td><td class='reps'>{reps}</td></tr>")

rank_rows = "\n".join(tr_rank(s, i) for i, s in enumerate(stats["stats"][:20]))
avoid_rows = "\n".join(
    tr_rank(s, len(stats["stats"]) - 10 + i)
    for i, s in enumerate(stats["stats"][-10:]))

val_rows = "\n".join(
    f"<tr><td>{v['date']}</td><td>{v['next']}</td><td class='neg'>{v['q1']*100:+.2f}</td>"
    f"<td>{v['mid']*100:+.2f}</td><td class='pos'>{v['q5']*100:+.2f}</td>"
    f"<td class='neg'>{v['spread']*100:+.2f}</td><td>{v['corr']:+.2f}</td></tr>"
    for v in val)

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>筹码合成 × 行业筛选（2026-07-31）</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;max-width:1000px;margin:24px auto;
padding:0 16px;color:#1a1a1a;background:#fff;line-height:1.6}}
h1{{font-size:22px;border-bottom:3px solid #c0392b;padding-bottom:8px}}
h2{{font-size:17px;margin-top:32px;color:#c0392b}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}}
th,td{{border:1px solid #ddd;padding:6px 8px;text-align:center}}
th{{background:#f7f2f0}}
.reps{{text-align:left;font-size:12px;color:#555}}
tr.good td{{background:#fdf3f2}}
tr.bad td{{background:#f0f7f0}}
.pos{{color:#c0392b;font-weight:600}} .neg{{color:#1e7a34;font-weight:600}}
.note{{background:#fff8e6;border-left:4px solid #e6a700;padding:10px 14px;font-size:13px;margin:14px 0}}
.kpi{{display:flex;gap:16px;margin:16px 0}}
.kpi div{{flex:1;border:1px solid #ddd;border-radius:6px;padding:10px;text-align:center}}
.kpi b{{font-size:20px;display:block}}
footer{{font-size:11px;color:#999;margin-top:30px}}
</style></head><body>
<h1>筹码合成 × 行业筛选 —— 结论：行业层面无效（方向反了），因子价值在个股层</h1>

<h2>① 当前截面：筹码最集中的 20 个行业（因子值低 = 筹码集中，2026-07-31，n≥15）</h2>
<table><tr><th>#</th><th>行业（东财口径）</th><th>n</th><th>因子均值</th><th>中位数</th>
<th>低分占比</th><th>代表股（因子值）</th></tr>
{rank_rows}</table>

<h2>② 当前截面：筹码最分散的 10 个行业（个股层面应回避的区域）</h2>
<table><tr><th>#</th><th>行业</th><th>n</th><th>因子均值</th><th>中位数</th>
<th>低分占比</th><th>代表股（因子值）</th></tr>
{avoid_rows}</table>

<h2>③ 但是——行业层面领先性检验：因子方向不成立</h2>
<p>把 6 期因子截面按行业均值分成 5 组，检验下一月行业收益（行业收益 = 行业内等权）：</p>
<table><tr><th>因子期</th><th>下月</th><th>Q1 集中端 %</th><th>全体 %</th>
<th>Q5 分散端 %</th><th>Q1−Q5 (pp)</th><th>corr</th></tr>
{val_rows}</table>
<div class="kpi">
<div><b>{avg_spread*100:+.1f}pp</b>6 期 Q1−Q5 平均（集中端跑输）</div>
<div><b>{avg_corr:+.2f}</b>平均 corr（方向混乱）</div>
<div><b>4/6</b>集中端跑输分散端的期数</div>
</div>
<div class="note"><b>解读：</b>个股层面验证有效的方向（筹码集中→跑赢），聚合到行业层面后<b>消失甚至反转</b>。
最典型的例子：2026-06 截面上筹码最集中的行业（光学光电子 −0.51、金属新材料 −0.47、军工电子），
7 月平均跌 −12.0%（同期全体行业 −3.5%）——集中度在这里度量的是<b>行业拥挤度</b>，不是机构锁仓。
筹码集中的行业 = 交易过热的行业，随后均值回归。</div>

<h2>④ 怎么正确使用这个因子</h2>
<ul>
<li><b>不要</b>用它做行业配置 / 行业择时——本页检验已证伪（样本 6 期偏短，但方向一致偏负）</li>
<li><b>可以</b>在既定行业内做个股筛选：买行业内筹码集中的个股、避开筹码分散的个股——
这是 8 年 IC 全负、五分位严格单调所验证过的用法（T1 质量过滤器）</li>
<li>规避用法（负面清单）比优选用法更稳：Q5 分散端 8 年年化仅 +1.1%，避开它们本身就是 alpha</li>
<li>官方口径提示：机构主导池（中证500 内）信号衰减，散户参与度高的票最有效</li>
</ul>

<footer>数据：申万金工 MCP 筹码合成因子（z-score，2026-07-31，覆盖 5134 只）×
东方财富行业板块映射（现势口径，历史期存在映射前视，仅作快检）；
月度收益取自本地 a_share_market.db 月K。生成于 2026-08-24。仅供研究参考，不构成投资建议。</footer>
</body></html>"""

out = os.path.join(HERE, "_chip_industry_report.html")
open(out, "w", encoding="utf-8").write(html)
print("saved ->", out)
print(f"avg spread {avg_spread*100:+.2f}pp, avg corr {avg_corr:+.2f}")
