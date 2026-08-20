# -*- coding: utf-8 -*-
"""Growth Loop v3 回测报告生成（分析师一致预期 + PEG + 增速二阶导）。

数据来自 _gl_v2_variant.py 的 v3a/v3b/v3rec + 已有 baseline/v2rec + 基准。
用法: python _gl_v3_report.py
"""
from __future__ import annotations

import base64
import io
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimSun", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ["baseline", "v2rec", "v3a", "v3b", "v3rec"]
CHART_MODES = ["baseline", "v2rec", "v3rec"]   # 净值/逐期图只画关键 3 条

MODE_LABEL = {
    "baseline": "baseline 原版",
    "v2rec": "v2rec 风格开关+估值卖出",
    "v3a": "v3a +分析师预期过滤",
    "v3b": "v3b +二阶导硬过滤",
    "v3rec": "v3rec 完整配置",
}
MODE_DESC = {
    "baseline": "HOOK 层原版，无任何改进",
    "v2rec": "v2 已验证有效组合：风格开关 + 估值卖出纪律",
    "v3a": "v3a = baseline + 分析师覆盖 / 预期增速>0 / rev4w>0 / PEG∈(0,2)",
    "v3b": "v3a + 实际营收增速二阶导>0 硬过滤（yoy 环比下滑即排除）",
    "v3rec": "v3a + 二阶导软加成(conv+0.1) + 风格开关 + 估值卖出纪律",
}
MODE_COLOR = {
    "baseline": "#888888",
    "v2rec": "#d62728",
    "v3a": "#ff7f0e",
    "v3b": "#9467bd",
    "v3rec": "#c00000",
}


def load_json(name: str):
    p = os.path.join(HERE, name)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def nav_series(mode: str) -> dict:
    return {r["month"]: r["nav"] for r in load_json(f"_bt_gl_v2_{mode}_nav.json")}


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def make_nav_chart(navs: dict, bench: dict) -> str:
    months = sorted(k for k in navs["v3rec"] if k in bench)
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for m in CHART_MODES:
        nv = navs[m]
        b0 = nv[months[0]]
        tot = nv[months[-1]] / b0 - 1
        ax.plot(months, [nv[x] / b0 for x in months],
                label=f"{MODE_LABEL[m]}（{tot:+.1%}）",
                color=MODE_COLOR[m], lw=2.2 if m == "v3rec" else 1.5)
    ax.plot(months, [bench[m] / bench[months[0]] for m in months],
            label=f"中证全指（{bench[months[-1]]/bench[months[0]]-1:+.1%}）",
            color="#1f77b4", lw=1.5, ls="--")
    for mk in ("2022-08", "2024-08", "2025-08"):
        ax.axvline(mk, color="#aaa", ls=":", lw=1)
    ax.set_title("growth_loop v3 净值对比（2021-08 ~ 2026-08，归一化）")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_ylabel("净值（起点=1）")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig_to_b64(fig)


def make_period_chart(diags: dict) -> str:
    periods = list(diags["baseline"]["per_period_ret"].keys())
    x = list(range(len(periods)))
    fig, ax = plt.subplots(figsize=(11, 4.8))
    w = 0.25
    for i, m in enumerate(CHART_MODES):
        vals = [diags[m]["per_period_ret"].get(p, 0.0) for p in periods]
        ax.bar([xi + (i - 1) * w for xi in x], vals, w,
               label=MODE_LABEL[m], color=MODE_COLOR[m], alpha=0.85)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=45, fontsize=8)
    ax.set_title("逐期收益对比（baseline vs v2rec vs v3rec）")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig_to_b64(fig)


def summary_table(diags: dict) -> str:
    rows = []
    for m in MODES:
        d = diags[m]
        rows.append(f"""
        <tr>
          <td><b>{MODE_LABEL[m]}</b><br><span class="sub">{MODE_DESC[m]}</span></td>
          <td class="{'pos' if d['total_return']>=0 else 'neg'}">{d['total_return']:+.1%}</td>
          <td class="{'pos' if d['annualized']>=0 else 'neg'}">{d['annualized']:+.1%}</td>
          <td class="neg">{d['mdd']:.1%}</td>
          <td class="{'pos' if d['excess']>=0 else 'neg'}">{d['excess']:+.1%}</td>
          <td>{d.get('n_sells', 0)}</td>
        </tr>""")
    return "".join(rows)


def period_table(diags: dict) -> str:
    periods = list(diags["baseline"]["per_period_ret"].keys())
    head = "".join(f"<th>{MODE_LABEL[m]}</th>" for m in MODES)
    rows = []
    for p in periods:
        tds = []
        for m in MODES:
            v = diags[m]["per_period_ret"].get(p)
            cls = "pos" if v and v >= 0 else "neg"
            tds.append(f"<td class='{cls}'>{v:+.1%}</td>" if v is not None
                       else "<td>–</td>")
        rows.append(f"<tr><td>{p}</td>{''.join(tds)}</tr>")
    return head, "".join(rows)


def attribution_table(diags: dict) -> str:
    d_b, d_v2, d_a, d_b2, d_r = (diags[m] for m in MODES)
    rows = [
        ("① 分析师一致预期买入过滤", "v3a vs baseline",
         f"{d_b['total_return']:+.1%} → {d_a['total_return']:+.1%}",
         f"正贡献（+{d_a['total_return']-d_b['total_return']:+.1f}pp）",
         "买入端叠加：必须有分析师覆盖 / 预期净利增速>0 / 近4周预期修正 rev4w>0（分析师在上调）/ PEG∈(0,2)。逐期滤掉 13-50% 候选（2023-04、2024-08、2025-04 约五成候选预期正在下调），留下的都是预期仍在改善的景气票。2025-04/2025-08 两期牛市 +35%/+44% vs baseline +20%/+35%；2024-08 期略逊（+44% vs +39%）但 2022-08 熊市 -18.0% vs -21.0% 更抗跌。"),
        ("② 实际增速二阶导硬过滤", "v3b vs v3a",
         f"{d_a['total_return']:+.1%} → {d_b2['total_return']:+.1%}",
         f"收益略降（{d_b2['total_return']-d_a['total_return']:+.1f}pp），MDD 大幅收窄（{-d_a['mdd']+d_b2['mdd']:+.1f}pp）",
         "实际营收 yoy 环比下滑即排除：2021-08 从 15→6 只、2022-08 从 27→14、2025-08 从 22→9。收益 -0.5pp 但最大回撤 -55.4% → -46.5%（+8.9pp）。代价是低仓期变多（2021-08 gross 48%、2024-08 48%），错过 2025-08 期部分弹性（+14.1% vs +44.4%）。适合风险偏好低的实盘；追求收益则用软加成版。"),
        ("③ 完整配置（+纪律层）", "v3rec vs v3a",
         f"{d_a['total_return']:+.1%} → {d_r['total_return']:+.1%}",
         f"强正贡献（+{d_r['total_return']-d_a['total_return']:+.1f}pp）",
         "v3rec = v3a 买入端 + 二阶导软加成(加速票 conviction+0.1) + 风格开关（2022-08/2024-08 熊市 gross 50%）+ 估值卖出纪律（16 笔，PS/PS_med≥2 清仓）。与共识过滤存在强交互：共识池里的票估值纪律更有辨识度（全是高 PEG 弹性票），2022-08 减仓把 -18.0% 收窄到 -13.8%，2026-04 期 -3.4% vs v3a -16.5%（估值卖出+减仓共同避雷）。"),
        ("④ 完整配置 vs 上一代", "v3rec vs v2rec",
         f"{d_v2['total_return']:+.1%} → {d_r['total_return']:+.1%}",
         f"+{d_r['total_return']-d_v2['total_return']:+.1f}pp",
         "v2rec 只在卖出端/仓位端做文章，买入端仍会买进'增速亮眼但分析师正在下调预期'的票（财报增速滞后于预期拐点）。v3rec 把买入端换成'预期仍在改善'的池子后，卖出纪律和风格开关的杀伤力大幅放大：总收益 +0.7% → +27.0%，超额 -3.8% → +22.5%。"),
    ]
    out = []
    for tag, cmp, result, verdict, note in rows:
        vcls = "bad" if verdict.startswith("负") or verdict.startswith("收益略降") else "good"
        out.append(f"""
        <tr>
          <td><b>{tag}</b></td>
          <td>{cmp}</td>
          <td>{result}</td>
          <td><span class="pill {vcls}">{verdict}</span></td>
          <td class="left">{note}</td>
        </tr>""")
    return "".join(out)


def consensus_coverage_table() -> str:
    """每期共识数据覆盖与 veto 统计（用 v3rec 的 diag）。"""
    diag = load_json("_bt_gl_v2_v3rec_diag.json")["diag"]
    rows = []
    for mk in diag:
        d = diag[mk]
        rows.append(f"""<tr>
          <td>{mk}</td>
          <td>{d['candidates']}</td>
          <td>{d['veto_cons_na']}</td>
          <td>{d['veto_cons_yoy_le0']}</td>
          <td>{d['veto_cons_down']}</td>
          <td>{d['veto_peg_bad']}</td>
          <td>{d['veto_yoy_decel']}</td>
          <td>{d['a_tier']+d['b_fill']}</td>
          <td>{d['holdings']}</td>
          <td>{d['gross']:.0%}</td>
          <td>{d['n_accel']}/{d['n_decel']}</td>
        </tr>""")
    return "".join(rows)


def sell_table(sells: list) -> str:
    rows = []
    for s in sells:
        k = "调仓 overlay" if s["kind"] == "rebalance_overlay" else "月度出场"
        w = f"{s['weight']:.1%}" if s.get("weight") is not None else "–"
        rows.append(f"""<tr>
          <td>{s['dt']}</td><td>{s['ticker']}</td><td>{k}</td>
          <td>{s['reason']}</td><td>{w}</td></tr>""")
    return "".join(rows)


def holdings_table(det: dict) -> str:
    sel_months = ["2021-08", "2022-08", "2024-08", "2025-08", "2026-04"]
    out = []
    for mk in sel_months:
        w = det["weights_by_dt"].get(mk, {})
        d = det["detail_by_dt"].get(mk, {})
        rows = []
        for tk, wt in sorted(w.items(), key=lambda x: -x[1])[:12]:
            dd = d.get(tk, {})
            hooks = "+".join(dd.get("hooks", [])) or "–"
            acc = ("↑" if dd.get("accel") else ("↓" if dd.get("accel") is False
                                                else "?"))
            rev = dd.get("con_rev4w")
            peg = dd.get("con_peg")
            rev_txt = f"{rev:+,.0f}" if rev is not None else "–"
            peg_txt = f"{peg:.2f}" if peg is not None else "–"
            rows.append(f"""<tr>
              <td>{dd.get('name','?')}</td><td>{dd.get('sw1','?')}</td>
              <td>{dd.get('yoy',0):+.0%}</td>
              <td>{hooks}</td><td>{acc}</td>
              <td>{rev_txt}</td><td>{peg_txt}</td>
              <td>{wt:.1%}</td></tr>""")
        out.append(f"""
        <h3>调仓 {mk} · 持仓 {len(w)} 只 · gross {sum(w.values()):.0%}
            <span class="sub">（acc=实际增速二阶导 ↑加速/↓减速 · rev4w=4周预期修正 · peg=一致预期PEG）</span></h3>
        <table class="tbl"><thead><tr><th>名称</th><th>行业</th>
        <th>营收YoY</th><th>HOOK</th><th>二阶导</th>
        <th>rev4w</th><th>PEG</th><th>权重</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>""")
    return "".join(out)


def main():
    diags = {m: load_json(f"_bt_gl_v2_{m}_diag.json") for m in MODES}
    bench = load_json("_bt_benchmark.json")
    navs = {m: nav_series(m) for m in MODES}
    det = load_json("_bt_gl_v2_v3rec_detail.json")

    nav_chart = make_nav_chart(navs, bench)
    period_chart = make_period_chart(diags)
    summary_rows = summary_table(diags)
    head, period_rows = period_table(diags)
    attr_rows = attribution_table(diags)
    cov_rows = consensus_coverage_table()
    sell_rows = sell_table(det["sell_log"])
    hold_html = holdings_table(det)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Growth Loop v3 一致预期回测报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f7f7f8; color: #222; }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  h2 {{ font-size: 20px; border-left: 4px solid #c00000; padding-left: 10px; margin-top: 40px; }}
  h3 {{ font-size: 15px; margin: 22px 0 8px; }}
  .sub {{ color: #666; font-size: 12px; }}
  .meta {{ color: #888; font-size: 12px; margin-bottom: 18px; }}
  .card {{ background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 16px 20px; margin: 14px 0; }}
  .kpis {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 160px; background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 12px 16px; }}
  .kpi .v {{ font-size: 25px; font-weight: 700; }}
  .kpi .l {{ color: #888; font-size: 12px; margin-top: 4px; }}
  .pos {{ color: #d62728; }} .neg {{ color: #2ca02c; }}
  .pill {{ padding: 2px 10px; border-radius: 10px; font-size: 12px; color: #fff; }}
  .pill.good {{ background: #d62728; }} .pill.bad {{ background: #2ca02c; }}
  table.tbl {{ border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }}
  .tbl th, .tbl td {{ border: 1px solid #e4e4e6; padding: 6px 8px; text-align: center; }}
  .tbl th {{ background: #f0f0f2; }}
  .tbl td.left {{ text-align: left; }}
  img.chart {{ width: 100%; border-radius: 8px; margin: 8px 0; }}
  .warn {{ background: #fff8e6; border: 1px solid #f0d68a; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .goodbox {{ background: #fdeeee; border: 1px solid #e8b4b4; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .note {{ color: #666; font-size: 12px; }}
</style></head><body><div class="wrap">

<h1>Growth Loop v3 · 分析师一致预期 + PEG + 增速二阶导</h1>
<div class="meta">vnpy 框架 · 2021-08 ~ 2026-08 五年 · point-in-time 数据 · 零未来数据 · 半年度调仓 · 成本 5bp+10bp · 2026-08-19</div>

<div class="card kpis">
  <div class="kpi"><div class="v neg">-14.0%</div><div class="l">baseline 总收益</div></div>
  <div class="kpi"><div class="v pos">+0.7%</div><div class="l">v2rec（风格开关+估值卖出）</div></div>
  <div class="kpi"><div class="v pos">+27.0%</div><div class="l">v3rec 完整配置（+26.3pp）</div></div>
  <div class="kpi"><div class="v pos">+22.5%</div><div class="l">v3rec 超额 vs 中证全指</div></div>
  <div class="kpi"><div class="v neg">-50.4%</div><div class="l">v3rec 最大回撤</div></div>
</div>

<div class="goodbox"><b>核心结论：</b>把买入端从「只看已披露财务增速」升级为「分析师一致预期仍在改善」（rev4w&gt;0 + 预期增速&gt;0 + PEG∈(0,2)），是这轮改进里<b>单点贡献最大</b>的一步：baseline -14.0% → v3a +5.6%（+19.6pp）。再叠加上一代已验证的风格开关 + 估值卖出纪律，得到 <b>v3rec +27.0%</b>，五年首次大幅跑赢中证全指（超额 +22.5pp）。实际增速二阶导做硬过滤略降收益但显著收窄回撤（-55.4% → -46.5%），适合作为风险开关而非收益来源。</div>

<div class="warn"><b>诚实声明：</b>LOOP 层 L1-L7（LLM 深研）无法诚实回测（模型训练数据含未来信息），本回测只用 HOOK 层确定性数值规则 + L8 信念代理。分析师一致预期数据为每个调仓月的 PIT 快照（juzi 一致预期表 as_of 口径），只用调仓日当日可得值，无前瞻偏差。universe = 每期全市场点时 top-100 增速候选，无行业偏好。</div>

<h2>一、5 个方案对比</h2>
<table class="tbl"><thead><tr>
  <th>方案</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额</th><th>估值卖出笔数</th>
</tr></thead><tbody>{summary_rows}</tbody></table>
<p class="note">v3b 低仓期多（2021-08 / 2024-08 gross 48%）且 2025-08 期只 +14.1%，是收益略低于 v3a 的原因；但其 -46.5% 回撤是全部方案最优。v3rec 用软加成保留了弹性。</p>

<h2>二、净值曲线与逐期对比</h2>
<img class="chart" src="data:image/png;base64,{nav_chart}" alt="净值对比">
<img class="chart" src="data:image/png;base64,{period_chart}" alt="逐期收益">

<h2>三、逐期收益明细</h2>
<table class="tbl"><thead><tr><th>期间</th>{head}</tr></thead>
<tbody>{period_rows}</tbody></table>

<h2>四、逐条归因（诚实评估）</h2>
<table class="tbl"><thead><tr>
  <th>改进</th><th>对比</th><th>效果</th><th>结论</th><th>归因分析</th>
</tr></thead><tbody>{attr_rows}</tbody></table>

<h2>五、共识数据覆盖与 veto 统计（v3rec 每期）</h2>
<table class="tbl"><thead><tr>
  <th>调仓月</th><th>候选</th><th>无覆盖</th><th>预期增速≤0</th><th>rev4w≤0(下调)</th>
  <th>PEG越界</th><th>二阶导滤(仅v3b)</th><th>通过池</th><th>最终持仓</th>
  <th>gross</th><th>加速/减速</th>
</tr></thead><tbody>{cov_rows}</tbody></table>
<p class="note">「rev4w≤0（分析师在下调）」是最大单一否决项：每期滤掉 6-15 只，证明候选池里近一半的「高增速」票其实分析师预期正在恶化——这正是纯财务策略买在高点的根源。</p>

<h2>六、v3rec 机制拆解</h2>
<div class="card">
<p><b>① 买入端（分析师预期）：</b>必须同时满足 有覆盖 / 预期净利增速&gt;0 / 近4周预期修正 rev4w&gt;0 / PEG∈(0,2)。淘汰「财务增速亮眼但预期恶化」的票。</p>
<p><b>② 增速二阶导（软加成）：</b>实际营收 yoy 环比仍在上行（二阶导&gt;0）的票 conviction +0.1，提高其权重排名；不硬排除，保留低仓期弹性。</p>
<p><b>③ 风格开关：</b>2022-08、2024-08 两个调仓月基准 12 月收益 &lt; -10% → gross 降至 50%。</p>
<p><b>④ 估值卖出纪律：</b>持仓中任意月份 PS/PS_med ≥ 2.0 → 卖出（次月撮合）。共 <b>{len(det['sell_log'])} 笔</b>。</p>
</div>
<table class="tbl"><thead><tr><th>触发月</th><th>代码</th><th>类型</th><th>触发原因</th><th>权重</th></tr></thead>
<tbody>{sell_rows}</tbody></table>

<h2>七、v3rec 代表性持仓（含共识字段）</h2>
{hold_html}

<h2>八、局限与下一步</h2>
<div class="card">
<ul class="note">
  <li><b>回撤 -50.4% 仍偏高</b>：虽然超额转正，但实盘 50% 回撤不可接受。下一步：PEG 上限网格（1.5/2.0/2.5）+ 分行业阈值；估值卖出可换用一致预期 PEG 触发（预期恶化即卖）而非只靠 PS 分位。</li>
  <li><b>rev4w 阈值敏感性</b>：目前 &gt;0 即放行。可测试 rev13w/rev26w 更长窗口做「预期持续改善」确认，减少单周噪音。</li>
  <li><b>二阶导硬/软之争</b>：v3b 回撤最优但收益略低。可做「熊市期启用硬过滤、牛市期软加成」的 state-dependent 组合。</li>
  <li><b>风格开关信号可升级</b>：12 月收益 &lt;-10% 是简单代理，可换 MA200/估值分位/分析师情绪宽度，减少 2024-08 的误判（当期少赚约 7pp）。</li>
  <li><b>预期数据时点</b>：当前用调仓月末快照。若月度调仓，可用每月最新预期值，卖出端响应更快（预期下调当日即可减仓）。</li>
</ul>
</div>

</div></body></html>"""

    out = os.path.join(HERE, "growth_loop_v3_consensus_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"→ {out} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
