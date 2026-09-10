# -*- coding: utf-8 -*-
"""路径A · N 敏感性截断 → 报告。"""
import json
import datetime

D = json.load(open("_bt_q20_nscan_results.json", encoding="utf-8"))
R = D["results"]   # str(n) -> dict
POOL = D["pool_sizes"]
ANCHOR = D["meta"].get("anchor_q20_cap8_total")

N_LIST = [int(k) for k in R.keys()]
N_LIST.sort()


def pct(x):
    return f"{x*100:+.1f}%"


def num(x, d=1):
    return f"{x:.{d}f}"


def html():
    rows = []
    for n in N_LIST:
        r = R[str(n)]
        ann = r["ann"]
        total = r["total"]
        mdd = r["mdd"]
        neff = r["neff"]
        avg = r["avg_holdings"]
        top3 = r["top3"]
        dep = r["dep"]
        rows.append((n, ann, total, mdd, avg, neff, top3, dep))

    # 找最优：年化最大
    best_ann = max(rows, key=lambda x: x[1])

    html_rows = ""
    for n, ann, total, mdd, avg, neff, top3, dep in rows:
        cls = "best" if (n, ann) == (best_ann[0], best_ann[1]) else ""
        html_rows += f"""
<tr class="{cls}">
  <td><b>top{n}</b></td>
  <td>{pct(ann)}</td>
  <td>{pct(total)}</td>
  <td>{pct(mdd)}</td>
  <td>{num(avg,1)}</td>
  <td>{num(neff,1)}</td>
  <td>{pct(top3)}</td>
  <td>{num(dep,2)}</td>
</tr>"""

    # 分年度矩阵
    years = ["2021", "2022", "2023", "2024", "2025", "2026"]
    yearly_rows = ""
    for n in N_LIST:
        yl = R[str(n)]["yearly"]
        cells = "".join(
            f'<td class="{"pos" if yl.get(y,0)>0 else "neg"}">{pct(yl.get(y,0))}</td>'
            for y in years)
        yearly_rows += f"<tr><td><b>top{n}</b></td>{cells}</tr>"

    # 早后期
    early_late_rows = ""
    for n in N_LIST:
        yl = R[str(n)]["yearly"]
        early = 1.0; late = 1.0
        for y, r in yl.items():
            if y <= "2023":
                early *= (1 + r)
            else:
                late *= (1 + r)
        early_late_rows += f"""
<tr>
  <td><b>top{n}</b></td>
  <td>{pct(early-1)}</td>
  <td>{pct(late-1)}</td>
  <td>{pct(R[str(n)]['dep'])}</td>
</tr>"""

    pool_avg = D["meta"]["pool_size_avg"]
    run_at = D["meta"]["run_at"]

    anchor_line = ""
    if ANCHOR is not None:
        cur = R["40"]["total"]
        anchor_line = f'<div class="kv"><span class="k">锚点对齐</span><span class="v">top40 本次 <b>{pct(cur)}</b> vs 历史 <b>{pct(ANCHOR)}</b> (差 {(cur-ANCHOR)*100:+.2f}pp)</span></div>'

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>路径A · N敏感性截断</title>
<style>
:root {{ --bg:#f5f6f8; --card:#fff; --ink:#1a1d24; --sub:#6b7280;
        --line:#e5e7eb; --red:#c0392b; --green:#1e8449; --blue:#1f5fa8; --amber:#d97706; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       background:var(--bg); color:var(--ink); padding:32px 20px; line-height:1.65; }}
.wrap {{ max-width:1080px; margin:0 auto; }}
h1 {{ font-size:26px; margin-bottom:6px; }}
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
.best {{ background:#fff7ed; }}
.concl {{ background:#eef4fb; border-left:4px solid var(--blue); padding:16px 18px;
         border-radius:8px; margin:14px 0; }}
.concl b {{ color:var(--blue); }}
.warn {{ background:#fdf2f2; border-left:4px solid var(--red); padding:14px 18px;
         border-radius:8px; margin:14px 0; }}
.warn b {{ color:var(--red); }}
.kv {{ display:flex; justify-content:space-between; padding:6px 0;
       border-bottom:1px dashed var(--line); font-size:14px; }}
.kv:last-child {{ border-bottom:none; }}
.kv .k {{ color:var(--sub); }}
.kv .v {{ font-weight:500; }}
.small {{ color:var(--sub); font-size:12.5px; }}
ul {{ margin:8px 0 8px 22px; }}
li {{ margin:5px 0; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
</style>
</head>
<body><div class="wrap">

<h1>路径A · q20_cap8 N 敏感性截断</h1>
<div class="sub">运行 {run_at} · 基座 full(含金融) · 日频+复权 · 5bp+10bp · L4+L5 · mv≥100亿</div>

<div class="card">
  <h3 style="margin-bottom:10px;">实验设定</h3>
  <div class="kv"><span class="k">基线锚点</span><span class="v">q20_cap8 = q20 排序 × cap8 加权 × top40 = +118.5% / MDD -15.6%</span></div>
  <div class="kv"><span class="k">变量</span><span class="v">持仓数 N ∈ {{8, 10, 12, 15, 20, 25, 30, 40}}</span></div>
  <div class="kv"><span class="k">不变项</span><span class="v">q20 排序（0.8×PE便宜度 + 0.2×质量分）、cap8 加权、半年调仓</span></div>
  <div class="kv"><span class="k">候选池</span><span class="v">每期 q20 通过：均值 {pool_avg:.0f} 只 / 最大 {max(POOL.values())} / 最小 {min(POOL.values())}</span></div>
  {anchor_line}
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">结论 · 持仓数 × 收益 × 风险 跷跷板</h3>
  <div class="concl">
    <ul>
      <li><b>N_eff 在 N≥12 后饱和</b>：top12 实际 N_eff=12.0，top15=14.0，top40=19.3 —— cap8 决定了有效持仓上限</li>
      <li><b>MDD 拐点 = N=12</b>：N≤10 时 MDD 暴增至 22-23%（太集中），N≥12 后稳定在 16-20%</li>
      <li><b>收益最优 = top30</b>：年化 17.2% / 总 +123.0% / MDD 16.1%（超越锚点 +4.5pp）</li>
      <li><b>top40 是次优</b>：年化 16.7% / 总 +118.5% / MDD 15.6%（更多票稍微拖累 alpha）</li>
      <li><b>早后期分布</b>：top12-15 已能填平 2021-2023 早期（+9~15%），不再完全靠 2024 单点</li>
    </ul>
  </div>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">汇总表（N → 收益/风险/集中度）</h3>
  <table>
    <tr>
      <th>变体</th><th>年化</th><th>总收益</th><th>MDD</th>
      <th>实际持仓</th><th>N_eff</th><th>top3 权重</th><th>依赖度</th>
    </tr>
    {html_rows}
  </table>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">分年度收益（%）</h3>
  <table>
    <tr>
      <th>N</th>{''.join(f'<th>{y}</th>' for y in years)}
    </tr>
    {yearly_rows}
  </table>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">早/后期分布 & 依赖度</h3>
  <table>
    <tr><th>N</th><th>2021-2023 早期</th><th>2024-2026 后期</th><th>单点依赖度</th></tr>
    {early_late_rows}
  </table>
  <div class="small" style="margin-top:8px;">"依赖度"=1 − (剔除最佳年后的累计 / 含最佳年的累计)。越小越不靠单点。</div>
</div>

<div class="card">
  <h3 style="margin-bottom:10px;">决策建议</h3>
  <ul>
    <li><b>进攻底仓</b>：<b>top30 (q20_cap8 池取前30)</b> —— +4.5pp 超额、MDD 与锚点持平、N_eff 17.9 已脱离"过度集中"区</li>
    <li><b>稳健底仓</b>：<b>top12-15</b> —— 持仓 ≤ 15 只、年化仍 12%+、MDD ≤ 20%、早后期更均衡</li>
    <li><b>不推荐</b>：top8/10 —— top3 权重 40-54%，单票波动直接击穿组合，违背"确定性"初衷</li>
  </ul>
  <div class="small" style="margin-top:10px;">
    下一步：路径B 在 pool 源头加硬门槛（候选池从 ~294 缩到 10-20 只），看 N 是否能进一步下降而不损收益。
  </div>
</div>

</div></body></html>"""
    open("_bt_q20_nscan_report.html", "w", encoding="utf-8").write(html_doc)
    print("→ _bt_q20_nscan_report.html")


if __name__ == "__main__":
    html()