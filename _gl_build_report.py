# -*- coding: utf-8 -*-
"""生成 growth_loop 持仓细节 + 个股贡献报告（HTML）。"""
from __future__ import annotations

import html
import json

A = json.loads(open("_gl_attribution.json", encoding="utf-8").read())
BENCH = json.loads(open("_bt_benchmark.json", encoding="utf-8").read())
NAV = json.loads(open("_bt_gl_nav.json", encoding="utf-8").read())
NAV = {r["month"]: r["nav"] for r in NAV}


def esc(x):
    return html.escape(str(x))


def pct(x, nd=1):
    return f"{x * 100:+.{nd}f}%" if x is not None else "—"


def fmt_money(x, nd=0):
    return f"{x:+,.{nd}f}" if x is not None else "—"


# 基准净值序列（月）用于区间对比
bench_series = BENCH
span_ret = {}
for p in A["periods"]:
    mk, nxt = p["dt"], None
    idx = [q["dt"] for q in A["periods"]].index(mk)
    nxt = A["periods"][idx + 1]["dt"] if idx + 1 < len(A["periods"]) else A["end"]
    r = NAV[nxt] / NAV[mk] - 1
    br = bench_series.get(nxt, 0) / bench_series.get(mk, 1) - 1 if bench_series.get(mk) else None
    p["_nxt"] = nxt
    p["_ret"] = r
    p["_bench"] = br

total_ret = A["total_return"]
total_pct = A["total_return_pct"]
bench_pct = A["bench_return"]

sp = A["stock_pnl"]
top = list(sp.items())[:20]
bot = list(sp.items())[-20:][::-1]

hook_groups = sorted(A["by_hook"].items(), key=lambda x: -x[1])
ind_groups = sorted(A["by_ind"].items(), key=lambda x: -x[1])

# 行业贡献条形最大绝对值（用于长度归一）
max_ind = max((abs(v) for _, v in ind_groups), default=1)


def bar_cell(v, maxv, neg_ok=True):
    w = max(2.0, abs(v) / maxv * 100)
    color = "#c0392b" if v >= 0 else "#1e8449"
    align = "left" if v >= 0 else "right"
    return (f'<div class="hbar"><div class="hbar-fill" style="width:{w:.1f}%;'
            f'background:{color};margin-left:{(0 if v >= 0 else 100 - w):.1f}%">'
            f'</div></div>')


def row_html(r, with_pnl=True):
    pnl = r.get("span_pnl", 0.0)
    cls = "pos" if pnl >= 0 else "neg"
    w = r["target_w"]
    mv = r["mkt_val"]
    return ("<tr>"
            f"<td>{esc(r['ticker'])}</td><td>{esc(r['name'])}</td>"
            f"<td>{esc(r['sw1'])}</td>"
            f"<td><span class='tag {('tag-a' if r['tier']=='A' else 'tag-b')}'>{r['tier']}</span></td>"
            f"<td>{esc(r['hooks'])}</td>"
            f"<td class='num'>{w * 100:.1f}%</td>"
            f"<td class='num'>{int(r['shares']):,}</td>"
            f"<td class='num'>{r['fill_price'] if r['fill_price'] else '—'}</td>"
            f"<td class='num'>{fmt_money(mv)}</td>"
            + (f"<td class='num {cls}'>{fmt_money(pnl)}</td>" if with_pnl else "")
            + "</tr>")


def period_panel(p):
    rows = "".join(row_html(r) for r in sorted(
        p["rows"], key=lambda x: -(x.get("span_pnl", 0))))
    top3 = sorted(p["rows"], key=lambda x: -x.get("span_pnl", 0))[:3]
    bot3 = sorted(p["rows"], key=lambda x: x.get("span_pnl", 0))[:3]
    t3 = " / ".join(f"{r['name']} {fmt_money(r.get('span_pnl',0))}" for r in top3)
    b3 = " / ".join(f"{r['name']} {fmt_money(r.get('span_pnl',0))}" for r in bot3)
    bench_s = pct(p["_bench"]) if p["_bench"] is not None else "—"
    ret_cls = "pos" if p["_ret"] >= 0 else "neg"
    return f"""
<details class="panel" {'open' if p['dt'] in ('2022-08', '2024-08') else ''}>
  <summary>
    <span class="pdt">{p['dt']}</span>
    <span class="pmeta">{p['n']} 只 · gross {p['gross'] * 100:.0f}%</span>
    <span class="pret {ret_cls}">{pct(p['_ret'])}</span>
    <span class="pbench">基准 {bench_s}</span>
  </summary>
  <div class="pbody">
    <div class="ptop3"><b>期间贡献 TOP3：</b>{esc(t3)}</div>
    <div class="ptop3"><b>期间拖累 BOTTOM3：</b>{esc(b3)}</div>
    <table class="tbl">
      <thead><tr><th>代码</th><th>名称</th><th>行业</th><th>层级</th><th>Hooks</th>
      <th class="num">目标权重</th><th class="num">股数</th><th class="num">参考价</th>
      <th class="num">期末市值</th><th class="num">期间贡献</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</details>"""


def stock_table(items, label):
    rows = []
    for sym, s in items:
        cls = "pos" if s["net_pnl"] >= 0 else "neg"
        pr = s["hold"].get("price_ret")
        pr_s = pct(pr) if pr is not None else "—"
        rows.append(
            "<tr>"
            f"<td>{esc(sym)}</td><td>{esc(s['name'])}</td>"
            f"<td>{esc(s['ind'])}</td>"
            f"<td><span class='tag {('tag-a' if s['tier']=='A' else 'tag-b')}'>{s['tier']}</span></td>"
            f"<td>{esc(s['hooks'])}</td>"
            f"<td class='num'>{s['first']} → {s['last']}</td>"
            f"<td class='num'>{pr_s}</td>"
            f"<td class='num {cls}'>{fmt_money(s['net_pnl'])}</td>"
            f"<td class='num'>{pct(s['pct_of_total'])}</td>"
            "</tr>")
    return f"""
<h3>{label}</h3>
<table class="tbl">
  <thead><tr><th>代码</th><th>名称</th><th>行业</th><th>层级</th><th>Hooks</th>
  <th class="num">持仓区间</th><th class="num">区间价格涨跌</th>
  <th class="num">贡献金额</th><th class="num">占总收益</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>"""


def hook_rows():
    rows = []
    for k, v in hook_groups:
        cls = "pos" if v >= 0 else "neg"
        rows.append(f"<tr><td>{esc(k)}</td><td class='num {cls}'>{fmt_money(v)}</td></tr>")
    return "".join(rows)


def ind_rows():
    rows = []
    for k, v in ind_groups[:12]:
        cls = "pos" if v >= 0 else "neg"
        rows.append(
            f"<tr><td>{esc(k)}</td><td class='num {cls}'>{fmt_money(v)}</td>"
            f"<td>{bar_cell(v, max_ind)}</td></tr>")
    return "".join(rows)


# 区间收益迷你条
max_abs = max(abs(p["_ret"]) for p in A["periods"])
spans = ""
for p in A["periods"]:
    v = p["_ret"]
    w = max(2.0, abs(v) / max_abs * 100)
    color = "#c0392b" if v >= 0 else "#1e8449"
    bench_s = pct(p["_bench"]) if p["_bench"] is not None else "—"
    spans += (f'<div class="spanbar"><span class="sdt">{p["dt"]}</span>'
              f'<div class="sbar"><div class="sbar-fill" style="width:{w:.1f}%;'
              f'background:{color};margin-left:{(0 if v >= 0 else 100 - w):.1f}%"></div></div>'
              f'<span class="sval" style="color:{color}">{pct(v)}</span>'
              f'<span class="sbench">基准 {bench_s}</span></div>')

tier_a_s = fmt_money(A["by_tier"].get("A", 0))
tier_b_s = fmt_money(A["by_tier"].get("B", 0))
kpis = f"""
<div class="kpis">
  <div class="kpi"><div class="k-label">5.2 年总收益</div>
    <div class="k-val neg">{pct(total_pct)}</div>
    <div class="k-sub">¥ {fmt_money(total_ret)}</div></div>
  <div class="kpi"><div class="k-label">中证全指同期</div>
    <div class="k-val">{pct(bench_pct) if bench_pct is not None else '—'}</div>
    <div class="k-sub">超额 {pct(total_pct - bench_pct) if bench_pct is not None else '—'}</div></div>
  <div class="kpi"><div class="k-label">正贡献合计</div>
    <div class="k-val pos">+{fmt_money(A['pos_contrib_sum'])}</div>
    <div class="k-sub">{sum(1 for s in sp.values() if s['net_pnl'] > 0)} 只贡献为正</div></div>
  <div class="kpi"><div class="k-label">负贡献合计</div>
    <div class="k-val neg">{fmt_money(A['neg_contrib_sum'])}</div>
    <div class="k-sub">{sum(1 for s in sp.values() if s['net_pnl'] < 0)} 只贡献为负</div></div>
  <div class="kpi"><div class="k-label">实际交易股票</div>
    <div class="k-val">{A['n_stocks']}</div>
    <div class="k-sub">A 层 {esc(tier_a_s)} · B 补位 {esc(tier_b_s)}</div></div>
</div>"""

doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>growth_loop 回测 · 持仓细节与个股贡献</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f7f8fa; color: #1f2329; }}
  .wrap {{ max-width: 1060px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: #646a73; font-size: 13px; margin-bottom: 18px; }}
  .banner {{ background: #fff8e6; border: 1px solid #f0d98c; border-radius: 8px;
             padding: 12px 16px; font-size: 13px; color: #7a5c00; margin-bottom: 20px;
             line-height: 1.7; }}
  .banner b {{ color: #5c4500; }}
  .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }}
  .kpi {{ background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .k-label {{ font-size: 12px; color: #646a73; }}
  .k-val {{ font-size: 20px; font-weight: 700; margin: 4px 0 2px; }}
  .k-sub {{ font-size: 12px; color: #646a73; }}
  .pos {{ color: #c0392b; }}
  .neg {{ color: #1e8449; }}
  h2 {{ font-size: 17px; margin: 28px 0 10px; padding-bottom: 6px;
        border-bottom: 2px solid #e5e6eb; }}
  .spanbar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 12px; }}
  .sdt {{ width: 64px; color: #646a73; }}
  .sbar {{ flex: 1; height: 14px; background: #f0f1f3; border-radius: 4px; position: relative; overflow: hidden; }}
  .sbar-fill {{ height: 100%; border-radius: 4px; }}
  .sval {{ width: 58px; font-weight: 600; }}
  .sbench {{ color: #9aa0a6; width: 130px; }}
  .panel {{ background: #fff; border: 1px solid #e5e6eb; border-radius: 10px;
            margin-bottom: 10px; overflow: hidden; }}
  .panel summary {{ display: flex; align-items: center; gap: 14px; padding: 12px 16px;
                    cursor: pointer; list-style: none; font-size: 13px; }}
  .panel summary::-webkit-details-marker {{ display: none; }}
  .pdt {{ font-weight: 700; font-size: 14px; width: 72px; }}
  .pmeta {{ color: #646a73; }}
  .pret {{ font-weight: 700; width: 70px; }}
  .pbench {{ color: #9aa0a6; }}
  .pbody {{ padding: 0 16px 14px; }}
  .ptop3 {{ font-size: 12px; color: #4e5969; margin: 8px 0; line-height: 1.8; }}
  .tbl {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  .tbl th {{ text-align: left; background: #f5f6f8; padding: 7px 8px;
             border-bottom: 1px solid #e5e6eb; font-weight: 600; white-space: nowrap; }}
  .tbl td {{ padding: 6px 8px; border-bottom: 1px solid #f0f1f3; white-space: nowrap; }}
  .tbl .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .tag {{ display: inline-block; padding: 0 7px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .tag-a {{ background: #fde8e8; color: #c0392b; }}
  .tag-b {{ background: #e8eefb; color: #2c5fb0; }}
  .hbar {{ width: 140px; height: 10px; background: #f0f1f3; border-radius: 4px; overflow: hidden; }}
  .hbar-fill {{ height: 100%; border-radius: 4px; }}
  .foot {{ color: #9aa0a6; font-size: 12px; margin-top: 30px; line-height: 1.8; }}
  @media (max-width: 800px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body><div class="wrap">

<h1>growth_loop 策略 · 5 年回测持仓细节与个股贡献</h1>
<div class="sub">回测区间 2021-06 → 2026-08（5.2 年）· 初始资金 ¥1,000,000 · 半年度调仓 · 单票上限 8% · 佣金 5bp + 滑点 10bp</div>

<div class="banner">
<b>诚实边界（先看这个）：</b>① 本回测只含 <b>HOOK 层确定性规则</b>（H1 营收加速 / H2 毛利率拐点 / H6 深回撤高增长）+ L8 信念的确定性代理（conviction 加权）。
LOOP 层 L1–L7 LLM 深研<b>未参与回测</b>——大模型训练数据含未来信息，无法诚实回测，诊断中记为"缺失层"。② universe 每期由全市场点时筛选
top-100 增速候选（无行业偏好），无幸存者偏差；财务字段按披露截止日过滤（点时语义）。③ 调仓信息在 N 期生成、N+1 期撮合成交，无前视。
④ 个股贡献口径 = 该股全部月份 <b>net_pnl</b>（持仓收益 + 交易收益 − 佣金）之和，各股合计精确等于组合总收益，可直接对账。
</div>

{kpis}

<h2>逐期持仓区间收益（策略 vs 中证全指）</h2>
{spans}

<h2>① 逐期持仓明细（10 个调仓期）</h2>
<div class="sub">每期 = 调仓月下单、次月撮合后的实际持仓。期间贡献 = 该股在该调仓区间内逐月 net_pnl 之和（含区间内部分月份的卖出落袋）。</div>
{"".join(period_panel(p) for p in A["periods"])}

<h2>② 个股贡献排行</h2>
<div class="sub">贡献金额 = 该股 5 年内全部 net_pnl（扣佣金）；占总收益 = 贡献 ÷ 组合总收益（总收益为负，正贡献显示为负占比，含义是"对冲了亏损"）。
区间价格涨跌 = 首次买入月 → 最后卖出月 / 期末的价格变动（近似口径，不含分红）。</div>
{stock_table(top, "贡献 TOP 20（组合赢家）")}
{stock_table(bot, "拖累 BOTTOM 20（组合失血点）")}

<h2>③ 聚合视图</h2>
<h3>按 Hook 触发组合的贡献合计</h3>
<table class="tbl" style="max-width:420px">
  <thead><tr><th>Hook 组合</th><th class="num">贡献合计</th></tr></thead>
  <tbody>{hook_rows()}</tbody>
</table>
<div class="sub" style="margin-top:6px">注意：这是"触发该 hook 组合的股票集合"的贡献，多因子相关，不能解读为 H 的边际因果。B 补位 = 无 hook 触发、低信念 0.30 补足 20 只下限的持仓。</div>

<h3>按行业贡献合计（TOP 12）</h3>
<table class="tbl" style="max-width:520px">
  <thead><tr><th>行业</th><th class="num">贡献合计</th><th></th></tr></thead>
  <tbody>{ind_rows()}</tbody>
</table>

<h2>④ 客观结论（不粉饰）</h2>
<ol style="font-size:13.5px; line-height:2; color:#2b3038;">
  <li><b>5 年总收益 −14.0%，跑输中证全指。</b>这不是一个赚钱的策略，是一个"选出过赢家但整体仍亏钱"的策略。</li>
  <li><b>选股能力并非为零：</b>正贡献合计 +¥707,896（68 只），但被负贡献 −¥847,717（106 只）淹没，净亏 ¥139,821。
      问题核心不在"选不出赢家"，而在<b>亏损票的持有与卖出纪律</b>。</li>
  <li><b>重灾区集中：</b>负贡献最大的 20 只几乎全是 2021–2024 持仓的锂电/半导体材料链（德方纳米 −3.8 万、明微电子 −3.4 万、晶丰明源 −2.9 万、
      钧达股份 −2.7 万、德福科技 +3.4 万却仍在前十拖累表之外……），单票 8% 上限下每只亏 1.7–3.8 万元即 −2%～−4% 的组合损失。</li>
  <li><b>时间结构：</b>2024-08 之前的 7 个区间仅 1 个微正（+2.1%），累计最深亏损出现在 2022-08 区间（−21.0%）；2024-08 之后三个区间
      +39.1% / +20.2% / +35.4%，说明策略在 2024 年中报后（AI/科技链行情）显著选对了方向，但为时已晚、回本不足。</li>
  <li><b>改进指向（数据支撑）：</b>① HOOK 触发 ≠ 长期持有依据——H2（毛利率拐点）触发组整体净负，需要更强的卖出/减仓信号（如 BSADF 泡沫相位
      或动量截断）替代"持有到下个调仓期"；② B 补位（无 hook 硬凑 20 只）合计 −¥17,078，比 A 层亏得少但也不该存在，剧本"空仓也是决策"
      应落到实处；③ 换仓集中在半年一次，2021–2024 的衰退链（锂电材料）被动扛跌，需要行业层面的止损。</li>
</ol>

<div class="foot">
数据文件：<code>_gl_attribution.json</code>（全量机器可读）· <code>_gl_stock_contribution.csv</code>（个股贡献）·
<code>_gl_holdings_detail.csv</code>（逐期持仓）。复现：<code>python _gl_attribution.py</code>。
<br>口径说明：net_pnl 由回测引擎逐月合约级 PnL（holding_pnl + trading_pnl − 佣金）累计；价格涨跌为近似口径（首买月末 → 末卖月末/期末收盘），未计分红与送转；
行业为申万一级（2026 当前口径，轻度前视，行业归类变化远小于个股幸存者偏差）。基准 = 中证全指。
</div>

</div></body></html>"""

open("growth_loop_holdings_report.html", "w", encoding="utf-8").write(doc)
print("report written:", len(doc), "bytes")
