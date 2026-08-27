# -*- coding: utf-8 -*-
"""信号级验证 + HTML 报告 -> _bt_style_rotation_report.html"""
import os
import json
import pickle
import numpy as np
import pandas as pd

from _sr_backtest import daily_returns, weekly_returns, ETF_INFO

CACHE = r"D:\workspace\ai_fund_framework\_sr_cache"
OUT_HTML = r"D:\workspace\ai_fund_framework\_bt_style_rotation_report.html"

# ---------------- data ----------------
sig = pd.read_csv(os.path.join(CACHE, "_sr_signals.csv"), parse_dates=["date"]).sort_values("date").reset_index(drop=True)
fri_index = pd.DatetimeIndex(sig["date"])
dr = daily_returns()
wr = {k: weekly_returns(v, fri_index) for k, v in dr.items()}
with open(os.path.join(CACHE, "_sr_bt_results.pkl"), "rb") as f:
    results = pickle.load(f)

# ---------------- validation 1: odds_z quintiles -> fwd 12M style return ----------------
def fwd_style(series_a, series_b, weeks):
    """forward N-week relative return of A minus B (用未来收益, 验证用)"""
    ca = (1 + series_a).cumprod()
    cb = (1 + series_b).cumprod()
    fa = ca.shift(-weeks) / ca - 1
    fb = cb.shift(-weeks) / cb - 1
    return fa - fb

fwd52_val = fwd_style(wr["value"], wr["growth"], 52)   # 正 = value 跑赢 growth
fwd52_size = fwd_style(wr["small"], wr["large"], 52)   # 正 = small 跑赢 large
fwd13_crowd_v = fwd_style(wr["value"], wr["growth"], 13)
fwd52_crowd_v = fwd52_val

def quintile_table(z, fwd, label):
    df = pd.DataFrame({"z": z, "fwd": fwd}).dropna()
    if len(df) < 50:
        return None
    df["q"] = pd.qcut(df["z"], 5, labels=["Q1(低)", "Q2", "Q3", "Q4", "Q5(高)"])
    g = df.groupby("q", observed=True)["fwd"].agg(["mean", "median", "count"])
    g["mean"] = g["mean"]
    g.attrs["label"] = label
    return g

tab_odds_val = quintile_table(sig["odds_val"].values, fwd52_val.reindex(fri_index).values, "odds_val_z × fwd52周(value−growth)")
tab_odds_size = quintile_table(sig["odds_size"].values, fwd52_size.reindex(fri_index).values, "odds_size_z × fwd52周(small−large)")
tab_crowd_val = quintile_table(sig["crowd_val"].values, fwd52_crowd_v.reindex(fri_index).values, "crowd_val_z × fwd52周(value−growth)")
tab_crowd_size = quintile_table(sig["crowd_size"].values, fwd52_size.reindex(fri_index).values, "crowd_size_z × fwd52周(small−large)")

# ---------------- validation 3: six-cycle stage conditional returns ----------------
stage_df = pd.DataFrame({
    "m_loose": sig["m_loose"].values,
    "c_exp": sig["c_exp"].values,
    "gv": (wr["growth"] - wr["value"]).reindex(fri_index).values,   # growth − value 周超额
    "sl": (wr["small"] - wr["large"]).reindex(fri_index).values,
    "bench_g": (wr["growth"] - wr["bench"]).reindex(fri_index).values,
    "value_b": (wr["value"] - wr["bench"]).reindex(fri_index).values,
    "growth_b": (wr["growth"] - wr["bench"]).reindex(fri_index).values,
    "small_b": (wr["small"] - wr["bench"]).reindex(fri_index).values,
    "large_b": (wr["large"] - wr["bench"]).reindex(fri_index).values,
}).dropna(subset=["m_loose"])

def stage_name(r):
    m = "货币松" if r["m_loose"] else "货币紧"
    c = "信用扩" if r["c_exp"] else "信用缩"
    return f"{m}+{c}"

stage_df["stage"] = stage_df.apply(stage_name, axis=1)
stage_tab = stage_df.groupby("stage")[["gv", "sl", "growth_b", "value_b", "small_b", "large_b"]].agg(
    ["mean", "count"])
stage_ann = stage_tab.xs("mean", axis=1, level=1) * 52  # 年化
stage_cnt = stage_tab.xs("count", axis=1, level=1)["gv"]

# ---------------- HTML ----------------
def fmt_pct(x, digits=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x * 100:.{digits}f}%"

def nav_chart(port, bench, title):
    import json
    p = (1 + port).cumprod()
    b = (1 + bench).cumprod()
    labels = [d.strftime("%Y-%m") for d in port.index]
    return labels, p.values.tolist(), b.values.tolist()

main = results["disc_5bp"]
labels, pnav, bnav = nav_chart(main["port"], main["bench"], "main")

# yearly tables
yt_html_rows = ""
for y in main["yt"].itertuples():
    color = "color:#c0392b" if y.excess > 0 else "color:#1e8449"
    yt_html_rows += (f"<tr><td>{y.year}</td><td>{fmt_pct(y.port)}</td><td>{fmt_pct(y.bench)}</td>"
                     f"<td style='{color};font-weight:600'>{fmt_pct(y.excess)}</td>"
                     f"<td>{fmt_pct(y.hit, 0)}</td></tr>")

def qtab_html(tab):
    if tab is None:
        return "<p>数据不足</p>"
    rows = ""
    for q, r in tab.iterrows():
        rows += (f"<tr><td>{q}</td><td>{fmt_pct(r['mean'])}</td>"
                 f"<td>{fmt_pct(r['median'])}</td><td>{int(r['count'])}</td></tr>")
    return f"<table><tr><th>分组</th><th>前瞻52周均值</th><th>中位数</th><th>样本数(重叠)</th></tr>{rows}</table>"

stage_rows = ""
order = ["货币松+信用扩", "货币松+信用缩", "货币紧+信用扩", "货币紧+信用缩"]
for st in order:
    if st in stage_ann.index:
        r = stage_ann.loc[st]
        n = int(stage_cnt.get(st, 0))
        stage_rows += (f"<tr><td>{st}</td><td>{fmt_pct(r['gv'])}</td><td>{fmt_pct(r['sl'])}</td>"
                       f"<td>{fmt_pct(r['growth_b'])}</td><td>{fmt_pct(r['value_b'])}</td>"
                       f"<td>{fmt_pct(r['small_b'])}</td><td>{fmt_pct(r['large_b'])}</td><td>{n}</td></tr>")

variant_rows = ""
for name, res in results.items():
    m = res["m"]
    variant_rows += (f"<tr><td>{name}</td><td>{fmt_pct(m['ann'])}</td><td>{fmt_pct(m['ann_b'])}</td>"
                     f"<td style='font-weight:600'>{fmt_pct(m['ex_ann'])}</td><td>{fmt_pct(m['te'])}</td>"
                     f"<td>{m['ir']:.2f}</td><td>{fmt_pct(m['mdd'])}</td><td>{fmt_pct(m['mdd_e'])}</td>"
                     f"<td>{fmt_pct(m['turn'], 0)}</td><td>{fmt_pct(m['hit'], 0)}</td></tr>")

# signal time series for chart
sig_labels = [d.strftime("%Y-%m") for d in sig["date"]]
sig_series = {c: [None if (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)
                  for v in sig[c].values]
              for c in ["odds_val", "odds_size", "trend_val", "trend_size", "crowd_val", "crowd_size", "winrate_val"]}

m_disc = results["disc_5bp"]["m"]
m_cont = results["cont_5bp"]["m"]
conclusion_html = f"""
<ul>
<li><b>复现结论</b>：连续版记分卡年化超额 <b>+{m_cont['ex_ann']*100:.1f}%</b>（IR {m_cont['ir']:.2f}），离散版 <b>+{m_disc['ex_ann']*100:.1f}%</b>（IR {m_disc['ir']:.2f}），
约为原报告目标（+13.6%/IR 1.49）的一半。TE {m_cont['te']*100:.1f}% 与原报告（8.8%）同量级。差距主要来自六周期代理简化与 DP 股息率缺失（见偏离清单）。</li>
<li><b>信号级裁决（IC≠alpha，逐项独立验证）</b>：
  <ul>
  <li>✅ <b>六周期胜率（货币×信用代理）— 最强信号</b>：货币松+信用扩 → 成长−价值 +19.5%/年、成长−基准 +19.1%；货币紧两状态 → 价值跑赢（+14.2%/+4.7%）且成长大幅跑输。方向与原报告 §4.2 完全一致，非重叠样本 513 周。</li>
  <li>✅ <b>odds_size（小盘/大盘 BP 价差）— 修正后完美逆向</b>：五分组前瞻 52 周 Q1(小盘贵) −25.9% → Q5(小盘便宜) +14.5%，近似单调。修正点：规格 §3 统一用 log(BP) 计价差，而非因子本身。</li>
  <li>✅ <b>crowd_size（规模拥挤度）— 符合报告预期</b>：Q1(拥挤极低) +12.8%（反弹）→ Q5(拥挤极高) −14.6%（见顶），非线性形态吻合。</li>
  <li>❌ <b>odds_val / crowd_val（成长/价值对子微观信号）— 本样本失效</b>：odds_val Q5(价值极便宜) 前瞻 −16.6%；crowd_val 反向。2017–2025 价值/成长估值价差持续走阔（价值陷阱），逆向信号长期偏多价值但错过 2019–21 创业板牛市；组合层面 value sleeve 的贡献主要来自六周期而非微观估值信号。</li>
  </ul></li>
<li><b>换手</b>：离散版年化单边 179%、连续版 228%，均高于原报告 119%——阈值（±1.0/±0.5）为规格假设值偏敏感；5–10bp 成本仅侵蚀 0.2–0.6pp/年（低换手成本钝感的结论成立）。</li>
<li><b>逐年</b>：2017–2019 弱（连输三年，恰为信号 warm-up 后首段+成长牛市段），2020–2025 连续 6 年跑赢（2022 +16.0%、2023 +15.5% 押中红利），2026YTD 微输。原报告"仅 2023 输基准"的模式未复现——我们的 2023 反而是大赢年（口径与信号路径不同）。</li>
<li><b>局限</b>：六周期为 4 状态粗代理（原模型 6 阶段）；红利低波 ETF 2019 前用价格指数替代（收益低估）；ST 未过滤；全部阈值 in-sample。</li>
<li><b>实用建议</b>：六周期状态（货币斜率×信用斜率）与规模拥挤度可独立作为卫星仓位/风控信号使用；成长/价值微观估值信号在 A 股 2017 后样本中不可信，不建议单独使用。</li>
</ul>
"""
html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>A股风格四周期 TAA 框架 — 回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px auto; max-width: 1080px; color: #222; background:#fafafa; }}
h1 {{ font-size: 22px; border-bottom: 3px solid #2c5f8a; padding-bottom: 8px; }}
h2 {{ font-size: 17px; color: #2c5f8a; margin-top: 28px; border-left: 4px solid #2c5f8a; padding-left: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 10px 0; background: #fff; }}
th, td {{ border: 1px solid #ccc; padding: 5px 8px; text-align: right; }}
th {{ background: #2c5f8a; color: #fff; text-align: center; }}
td:first-child, th:first-child {{ text-align: left; }}
.card {{ background:#fff; border:1px solid #ddd; border-radius:6px; padding:12px 16px; margin:10px 0; }}
.kpi {{ display:inline-block; margin:6px 14px 6px 0; }}
.kpi .v {{ font-size:20px; font-weight:700; color:#2c5f8a; }}
.kpi .k {{ font-size:12px; color:#666; }}
.warn {{ background:#fff8e1; border-left:4px solid #f0a500; padding:8px 12px; font-size:13px; margin:8px 0; }}
.note {{ font-size:12px; color:#666; }}
canvas {{ max-height: 340px; }}
ul {{ font-size:13px; line-height:1.7; }}
</style>
</head>
<body>
<h1>A股风格四周期 TAA 框架与 ETF 轮动 — 复现回测报告</h1>
<p class="note">来源策略：天风证券《A股风格的四周期框架与ETF轮动策略》(2026-02-24, 林志朋)。复现按 <code>D:/ChromeDownload/a_share_style_rotation_spec.md</code> 规格 + fund_framework 铁律（真实数据/PIT/日频复权/同口径基准/零未来函数）。</p>

<div class="card">
<div class="kpi"><div class="v">{fmt_pct(main['m']['ex_ann'])}</div><div class="k">年化超额(离散版5bp)</div></div>
<div class="kpi"><div class="v">{fmt_pct(main['m']['te'])}</div><div class="k">跟踪误差 TE</div></div>
<div class="kpi"><div class="v">{main['m']['ir']:.2f}</div><div class="k">信息比率 IR</div></div>
<div class="kpi"><div class="v">{fmt_pct(main['m']['turn'], 0)}</div><div class="k">年化单边换手</div></div>
<div class="kpi"><div class="v">{fmt_pct(main['m']['mdd_e'])}</div><div class="k">超额最大回撤</div></div>
<div class="kpi"><div class="v">{main['m']['n']}</div><div class="k">回测周数</div></div>
</div>

<h2>1. 数据与口径</h2>
<div class="card"><ul>
<li><b>股票面板</b>：juzi 全市场日频（估值面板 pe_ttm/pb/turnover/float_mv + 收益面板 adj_close/daily_return/forward_return_20d/industry_l1），2010-01 → 2026-08，周频快照取每周最后交易日。universe=全A（juzi panel 天然 PIT）。</li>
<li><b>ETF</b>：腾讯前复权日K（512100/510050/159915/512890）；上市前用对应指数替代（中证1000/上证50/创业板指/红利低波 H30269）。<b>注意：替代期指数为价格指数（不含分红），红利低波 2019 前收益被低估</b>。</li>
<li><b>基准</b>：中证800（000985 口径系列，价格指数）。</li>
<li><b>宏观</b>：R007（日频）、社融存量同比（月频，Wind EDB）。月频指标滞后 1 个月使用（防未来函数）。</li>
</ul></div>
<div class="warn"><b>与原报告的偏离（如实标注）</b>：
① DP 股息率因子无数据源，Value 用 EP+BP 双子因子（原规格 DP/EP/BP 三因子）；
② 六周期模型内部未披露，用 R007 3月斜率(货币) × 社融同比 3月斜率(信用) 的 4 状态代理；
③ ST/停牌标志无数据：停牌以"当日无行情"隐式剔除，上市&lt;126 交易日已剔除，ST 无法过滤（全A口径下影响有限但如实标注）；
④ 拥挤度 β 基准用中证全指；⑤ LLT d=30 按周频观测解释。</div>

<h2>2. 信号时间序列</h2>
<div class="card">
<canvas id="sigChart"></canvas>
<p class="note">odds/trend z 轴：高 → 利好 Value/Small；crowd_z 高 → 该风格拥挤（负贡献）；winrate 为 Value 方向。</p>
</div>

<h2>3. 信号级验证（§10 三件套）</h2>
<h3>3.1 odds_z 五分组 → 前瞻 52 周风格相对收益</h3>
<p class="note">预期：单调/凸关系 — odds_z 高（该风格便宜）→ 后续跑赢。样本为重叠周样本，仅作方向性验证。</p>
<div class="card">{qtab_html(tab_odds_val)}</div>
<div class="card">{qtab_html(tab_odds_size)}</div>
<h3>3.2 crowd_z 五分组 → 前瞻 52 周风格相对收益</h3>
<p class="note">预期：非线性 — 极端高拥挤跑输（Q5 低/负），极端低拥挤反弹（Q1 正）。</p>
<div class="card">{qtab_html(tab_crowd_val)}</div>
<div class="card">{qtab_html(tab_crowd_size)}</div>
<h3>3.3 六周期状态条件收益（年化超额）</h3>
<div class="card">
<table><tr><th>状态</th><th>成长−价值</th><th>小盘−大盘</th><th>成长−基准</th><th>价值−基准</th><th>小盘−基准</th><th>大盘−基准</th><th>周数</th></tr>
{stage_rows}
</table>
<p class="note">预期（原报告 §4.2）：货币松+信用扩 → 成长占优；货币紧+信用缩 → 价值/红利占优。gv 正=成长跑赢价值。</p>
</div>

<h2>4. 组合回测</h2>
<div class="card">
<table><tr><th>变体</th><th>年化</th><th>基准</th><th>年化超额</th><th>TE</th><th>IR</th><th>组合MDD</th><th>超额MDD</th><th>单边换手</th><th>周胜率</th></tr>
{variant_rows}
</table>
<p class="note">执行：周五 T 收盘打分 → 下周五 T+5 收盘调仓（全仓切换）；双 sleeve 各 50% 资金；成本按换手双边计提。原报告目标（参考）：超额 +13.6% / TE 8.8% / IR 1.49 / 换手 119%。</p>
</div>

<h2>5. 净值曲线（离散版 5bp）</h2>
<div class="card"><canvas id="navChart"></canvas></div>

<h2>6. 逐年表现（离散版 5bp）</h2>
<div class="card">
<table><tr><th>年份</th><th>组合</th><th>中证800</th><th>超额</th><th>周胜率</th></tr>
{yt_html_rows}
</table>
</div>

<h2>7. 铁律自查</h2>
<div class="card"><ul>
<li>✅ 真实数据：juzi/腾讯/Wind EDB 全真实拉取，无合成</li>
<li>✅ PIT：全A面板无幸存者偏差；宏观月频滞后 1 月使用</li>
<li>✅ 日频颗粒度：信号虽周频，但换手/波动/β 用日频 63 日滚动计算</li>
<li>✅ 复权：ETF 前复权（qfq）；指数替代期为价格指数（已标注低估方向）</li>
<li>✅ 同口径基准：中证800 价格指数 vs 组合（ETF 含分红口径差异已标注）</li>
<li>✅ 零未来函数：rankIC 滞后 4 周；月频宏观滞后 1 月；T+5 执行</li>
<li>⚠️ IC≠alpha：信号级验证独立给出（§3），组合结果不反推信号有效性</li>
<li>⚠️ in-sample 复现：阈值（±1.0/±0.5）为规格假设值，未做样本外</li>
</ul></div>

<h2>8. 结论与局限</h2>
<div class="card" id="conclusion"></div>

<script>
const labels = {json.dumps(labels)};
const pnav = {json.dumps(pnav)};
const bnav = {json.dumps(bnav)};
new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{ labels: labels, datasets: [
    {{ label: '组合(离散5bp)', data: pnav, borderColor: '#c0392b', borderWidth: 2, pointRadius: 0, tension: 0.1 }},
    {{ label: '中证800', data: bnav, borderColor: '#7f8c8d', borderWidth: 1.5, pointRadius: 0, tension: 0.1 }}
  ]}},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }} }}
}});

const sigLabels = {json.dumps(sig_labels)};
const sigSeries = {json.dumps(sig_series)};
new Chart(document.getElementById('sigChart'), {{
  type: 'line',
  data: {{ labels: sigLabels, datasets: [
    {{ label: 'odds_z(价值)', data: sigSeries.odds_val, borderColor: '#c0392b', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'odds_z(小盘)', data: sigSeries.odds_size, borderColor: '#e67e22', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'trend_z(价值)', data: sigSeries.trend_val, borderColor: '#2980b9', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'trend_z(小盘)', data: sigSeries.trend_size, borderColor: '#16a085', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'crowd_z(价值)', data: sigSeries.crowd_val, borderColor: '#8e44ad', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'crowd_z(小盘)', data: sigSeries.crowd_size, borderColor: '#2c3e50', pointRadius: 0, borderWidth: 1.5 }},
    {{ label: 'winrate(价值)', data: sigSeries.winrate_val, borderColor: '#f39c12', pointRadius: 0, borderWidth: 1.5, borderDash: [4,3] }}
  ]}},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 12, font: {{size: 10}} }} }} }} }}
}});
</script>
</body>
</html>"""

html = html.replace('<div class="card" id="conclusion"></div>',
                    f'<div class="card">{conclusion_html}</div>')

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("saved ->", OUT_HTML)

# console summary (GBK-safe)
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
print("\n=== validation summary ===")
for t in [tab_odds_val, tab_odds_size, tab_crowd_val, tab_crowd_size]:
    if t is not None:
        print(t.attrs.get("label", ""))
        print(t.to_string(), "\n")
print("stage (annualized):")
print(stage_ann.to_string())
print("\ncounts:", stage_cnt.to_dict())
