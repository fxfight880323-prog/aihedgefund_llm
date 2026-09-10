# -*- coding: utf-8 -*-
"""三路径综合汇总报告 —— 路径A 缩持仓 + 路径B 硬门槛 + 路径D 双信号 gate。

把三路径结论整合到一页，回答用户原问题：
"持仓更少 = 更确定？怎么做？什么条件？"
"""
import json
import datetime

A = json.load(open("_bt_q20_nscan_results.json", encoding="utf-8"))
B = json.load(open("_bt_q20_hardfilter_results.json", encoding="utf-8"))
D = json.load(open("_bt_q20_momgate_results.json", encoding="utf-8"))

A_R = A["results"]
B_R = B["results"]
D_R = D["results"]

run_at = max(A["meta"]["run_at"], B["meta"]["run_at"], D["meta"]["run_at"])

# 锚点对齐
a_anchor = A["meta"].get("anchor_q20_cap8_total")
b_anchor = B["meta"]["anchor_q20_top20"]


def pct(x): return f"{x*100:+.1f}%"


def html():
    # === 路径A 汇总 ===
    A_rows = ""
    A_NLIST = sorted([int(k) for k in A_R.keys()])
    for n in A_NLIST:
        r = A_R[str(n)]
        A_rows += f"""
<tr>
  <td><b>top{n}</b></td>
  <td>{pct(r['ann'])}</td>
  <td>{pct(r['total'])}</td>
  <td>{pct(r['mdd'])}</td>
  <td>{r['avg_holdings']:.0f}</td>
  <td>{r['neff']:.1f}</td>
  <td>{pct(r['top3'])}</td>
  <td>{r['dep']:.2f}</td>
</tr>"""

    # === 路径B 汇总 ===
    B_rows = ""
    B_VARS = ["q20_top20", "roe12", "peg5", "roe12_peg5", "roe12_peg5_pb80", "roe15_peg5"]
    B_LB = {"q20_top20": "锚点（L4+L5）", "roe12": "+ ROE≥12%",
            "peg5": "+ PEG≤0.5", "roe12_peg5": "+ ROE≥12% AND PEG≤0.5",
            "roe12_peg5_pb80": "+ ROE≥12% + PEG≤0.5 + PB分位≤80%",
            "roe15_peg5": "+ ROE≥15% AND PEG≤0.5"}
    for name in B_VARS:
        r = B_R[name]
        delta = (r["total"] - b_anchor) * 100
        B_rows += f"""
<tr>
  <td><b>{B_LB[name]}</b></td>
  <td>{r['pool_avg']:.1f}</td>
  <td>{pct(r['ann'])}</td>
  <td>{pct(r['total'])} <span class="small">(Δ {delta:+.1f}pp)</span></td>
  <td>{pct(r['mdd'])}</td>
  <td>{r['avg_holdings']:.1f}</td>
  <td>{r['neff']:.1f}</td>
</tr>"""

    # === 路径D 汇总 ===
    D_rows = ""
    D_VARS = ["q20_mom60", "q20_mom120", "q20_mom60_top50", "q20_breakout250", "q20_breakout120"]
    D_LB = {"q20_mom60": "mom60>0", "q20_mom120": "mom120>0",
            "q20_mom60_top50": "mom60 截面前50%", "q20_breakout250": "现价/250日高≥80%",
            "q20_breakout120": "现价/120日高≥90%"}
    for name in D_VARS:
        r = D_R[name]
        delta = (r["total"] - b_anchor) * 100
        D_rows += f"""
<tr>
  <td><b>{D_LB[name]}</b></td>
  <td>{r['gate_pass_avg']:.1f}</td>
  <td>{pct(r['ann'])}</td>
  <td>{pct(r['total'])} <span class="small">(Δ {delta:+.1f}pp)</span></td>
  <td>{pct(r['mdd'])}</td>
  <td>{r['avg_holdings']:.1f}</td>
  <td>{r['neff']:.1f}</td>
</tr>"""

    # === 综合决策矩阵 ===
    decision_rows = f"""
<tr><td colspan="7" style="background:#fafbfc;font-weight:600;color:var(--blue);">A · N 截断（基础）</td></tr>
<tr>
  <td>A</td><td><b>top8</b></td>
  <td>+65.4%</td><td>-22.9%</td><td>8</td><td>6.7</td>
  <td>❌ MDD 暴增（top3=54%）</td>
</tr>
<tr>
  <td>A</td><td><b>top12</b></td>
  <td>+79.7%</td><td>-19.4%</td><td>12</td><td>12.0</td>
  <td>⚠️ MDD 与收益同时改善的<b>拐点</b></td>
</tr>
<tr>
  <td>A</td><td><b>top30</b></td>
  <td><b>+123.0%</b></td><td>-16.1%</td><td>30</td><td>17.9</td>
  <td>✅ <b>进攻首选</b>（年化 17.2%）</td>
</tr>
<tr>
  <td>A</td><td><b>top40 (锚点)</b></td>
  <td>+118.5%</td><td>-15.6%</td><td>40</td><td>19.3</td>
  <td>原 q20_cap8 锚点</td>
</tr>
<tr><td colspan="7" style="background:#fafbfc;font-weight:600;color:var(--blue);">B · 硬门槛（不推荐方向）</td></tr>
<tr>
  <td>B</td><td>+ ROE≥12%</td>
  <td>+97.0%</td><td>-18.4%</td><td>20</td><td>15.7</td>
  <td>❌ 与锚点完全相同（ROE 全员 ≥12%）</td>
</tr>
<tr>
  <td>B</td><td>+ PEG≤0.5</td>
  <td>+73.7%</td><td>-20.6%</td><td>20</td><td>16.2</td>
  <td>❌ 缩池过猛 -23pp</td>
</tr>
<tr>
  <td>B</td><td>+ ROE+PEG+PB分位≤80%</td>
  <td>+55.1%</td><td>-20.6%</td><td>20</td><td>16.1</td>
  <td>❌ 最严组合 -42pp</td>
</tr>
<tr><td colspan="7" style="background:#fafbfc;font-weight:600;color:var(--blue);">D · 双信号 gate（升级方向）</td></tr>
<tr>
  <td>D</td><td>+ mom60 截面前 50%</td>
  <td><b>+99.1%</b></td><td>-21.6%</td><td>16</td><td>19.4</td>
  <td>✅ <b>收益升级首选</b>（Δ +2.1pp）</td>
</tr>
<tr>
  <td>D</td><td>+ breakout250 (现价/250日高≥80%)</td>
  <td>+91.7%</td><td><b>-13.8%</b></td><td>16</td><td>19.4</td>
  <td>✅ <b>风控升级首选</b>（MDD 全实验最优）</td>
</tr>
<tr>
  <td>D</td><td>+ mom60>0</td>
  <td>+71.4%</td><td>-18.7%</td><td>16</td><td>19.1</td>
  <td>❌ 绝对动量门过严</td>
</tr>
<tr>
  <td>D</td><td>+ breakout120</td>
  <td>+74.0%</td><td>-15.8%</td><td>16</td><td>19.1</td>
  <td>⚠️ 120 日窗偏短</td>
</tr>
"""

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>三路径综合汇总 · 持仓更少 = 更确定？</title>
<style>
:root {{ --bg:#f5f6f8; --card:#fff; --ink:#1a1d24; --sub:#6b7280;
        --line:#e5e7eb; --red:#c0392b; --green:#1e8449; --blue:#1f5fa8; --amber:#d97706; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       background:var(--bg); color:var(--ink); padding:32px 20px; line-height:1.65; }}
.wrap {{ max-width:1180px; margin:0 auto; }}
h1 {{ font-size:28px; margin-bottom:6px; }}
.sub {{ color:var(--sub); font-size:14px; margin-bottom:28px; }}
h2 {{ font-size:20px; margin:34px 0 14px; padding-left:10px; border-left:4px solid var(--blue); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:20px 22px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px; margin:10px 0; }}
th, td {{ padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); }}
th {{ background:#fafbfc; font-weight:600; color:var(--sub); white-space:nowrap; }}
td:first-child, th:first-child {{ text-align:left; }}
.pos {{ color:var(--red); font-weight:600; }}
.neg {{ color:var(--green); font-weight:600; }}
.best {{ background:#fff7ed; font-weight:600; }}
.concl {{ background:#eef4fb; border-left:4px solid var(--blue); padding:16px 18px;
         border-radius:8px; margin:14px 0; }}
.concl b {{ color:var(--blue); }}
.warn {{ background:#fdf2f2; border-left:4px solid var(--red); padding:14px 18px;
         border-radius:8px; margin:14px 0; }}
.warn b {{ color:var(--red); }}
.good {{ background:#eefaf1; border-left:4px solid var(--green); padding:14px 18px;
         border-radius:8px; margin:14px 0; }}
.good b {{ color:var(--green); }}
.kv {{ display:flex; justify-content:space-between; padding:6px 0;
       border-bottom:1px dashed var(--line); font-size:14px; }}
.kv:last-child {{ border-bottom:none; }}
.kv .k {{ color:var(--sub); }}
.kv .v {{ font-weight:500; }}
.small {{ color:var(--sub); font-size:12.5px; }}
ul {{ margin:8px 0 8px 22px; }}
li {{ margin:5px 0; }}
</style>
</head>
<body><div class="wrap">

<h1>三路径综合汇总 · "持仓更少 = 更确定？"</h1>
<div class="sub">运行 {run_at} · 基座 full(含金融) · 日频+复权 · 5bp+10bp · q20 排序</div>

<div class="card">
  <h3 style="margin-bottom:10px;">核心结论</h3>
  <div class="concl">
    <ul>
      <li><b>路径A 验证"持仓数敏感性"</b>：N=12 是 MDD/收益同时改善的<b>拐点</b>；N≥20 后 N_eff 饱和在 15-19</li>
      <li><b>路径B 否证"硬门槛缩池"</b>：ROE/PEG/PB 分位叠加全是冗余或负贡献（最多 -42pp）</li>
      <li><b>路径D 验证"正交第二信号"</b>：mom60 截面分位前 50% 是唯一<b>正向</b>的升级（+99.1% / Δ +2.1pp）</li>
    </ul>
  </div>
  <div class="good">
    <b>📌 最终推荐三档实盘组合</b>
    <ul style="margin-top:8px;">
      <li><b>进攻位</b>：路径A <b>top30</b> —— +123.0% / MDD -16.1% / 持仓 30（年化 17.2%，超额最大）</li>
      <li><b>均衡位</b>：路径D <b>q20_mom60_top50</b> —— +99.1% / MDD -21.6% / 持仓 16（信号最稳）</li>
      <li><b>风控位</b>：路径D <b>q20_breakout250</b> —— +91.7% / <b>MDD -13.8%</b> / 持仓 16（MDD 全实验最优）</li>
    </ul>
  </div>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">决策矩阵 · 11 个变体横向对比</h3>
  <table>
    <tr>
      <th>路径</th><th>变体</th><th>总收益</th><th>MDD</th>
      <th>持仓</th><th>N_eff</th><th>评估</th>
    </tr>
    {decision_rows}
  </table>
  <div class="small" style="margin-top:8px;">锚点：路径B q20_top20 = {pct(b_anchor)} / MDD -18.4%（与路径A top20 = {pct(A_R['20']['total'])} 一致）</div>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">路径A · N 敏感性（持仓数 = 唯一变量）</h3>
  <table>
    <tr>
      <th>N</th><th>年化</th><th>总收益</th><th>MDD</th>
      <th>实际持仓</th><th>N_eff</th><th>top3</th><th>依赖度</th>
    </tr>
    {A_rows}
  </table>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">路径B · 硬门槛缩池（全部负贡献或冗余）</h3>
  <table>
    <tr>
      <th>变体</th><th>池均</th><th>年化</th><th>总收益</th><th>MDD</th>
      <th>持仓</th><th>N_eff</th>
    </tr>
    {B_rows}
  </table>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">路径D · 双信号 gate（升级方向）</h3>
  <table>
    <tr>
      <th>变体</th><th>gate通过</th><th>年化</th><th>总收益</th><th>MDD</th>
      <th>持仓</th><th>N_eff</th>
    </tr>
    {D_rows}
  </table>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">回答用户的原始问题</h3>
  <div class="warn">
    <b>"如果持仓需要更大确定性（减少持仓股票数量），能够怎么做，需要什么条件？"</b>
    <ol style="margin-top:10px;">
      <li><b>路径A（截断）：</b>最稳。条件是 N ≥ 12 —— N_eff 自动 ≤ 12。MDD 在 N=12 改善到 -19.4%；再小（≤10）则 top3 集中度暴增（40-54%），MDD 反向恶化</li>
      <li><b>路径B（硬门槛）：</b>❌ 不推荐。L4+L5 之后的池子本身已优质，再叠 ROE/PEG/PB 分位是"在优中砍优"，最多 -42pp</li>
      <li><b>路径D（正交第二信号）：</b>✅ 升级方向。条件是 gate 信号必须 (i) as_of 当日可见 (ii) 与 q20 正交。<b>最佳 gate</b>：mom60 截面分位前 50%（收益优先）或 breakout250（风控优先）</li>
    </ol>
  </div>
  <div class="kv" style="margin-top:14px;">
    <span class="k">关键铁律</span>
    <span class="v">要"持仓更少"必须从<b>信号源头</b>改，而不是<b>在已有候选池做减法</b></span>
  </div>
</div>

</div></body></html>"""
    open("_bt_q20_deterministic_summary.html", "w", encoding="utf-8").write(html_doc)
    print("→ _bt_q20_deterministic_summary.html")


if __name__ == "__main__":
    html()