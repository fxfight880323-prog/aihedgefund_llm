# -*- coding: utf-8 -*-
"""Growth Loop v4 报告：估值卖出改用一致预期 PEG 触发（预期恶化即卖）。

数据来自 _gl_v4_variant.py 的 7 个模式 + 基准。
用法: python _gl_v4_report.py
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
MODES = ["v2rec", "v3rec", "v4a_peg", "v4a_rev", "v4a_both",
         "v4b_swap", "v4b_plus"]
CHART_MODES = ["v2rec", "v3rec", "v4a_both", "v4b_swap"]
MODE_LABEL = {
    "v2rec": "v2rec（风格开关+PS估值卖出）",
    "v3rec": "v3rec（一致预期买入+PS估值卖出）",
    "v4a_peg": "v4a_peg（无预期买入过滤，PEG≥2卖出）",
    "v4a_rev": "v4a_rev（无预期买入过滤，rev4w<0卖出）",
    "v4a_both": "v4a_both（无预期买入过滤，PEG或rev4w卖出）",
    "v4b_swap": "v4b_swap（v3rec买入，PEG/rev替换PS卖出）",
    "v4b_plus": "v4b_plus（v3rec买入，PS卖出+PEG/rev叠加）",
}
MODE_DESC = {
    "v2rec": "买入=HOOK纯财务；卖出=PS/PS_med≥2（含月度出场）",
    "v3rec": "买入=分析师预期过滤+二阶导加成；卖出=PS分位（含月度出场）",
    "v4a_peg": "买入回到v2（无预期过滤）；卖出=一致预期PEG≥2.0（仅调仓月）",
    "v4a_rev": "买入回到v2（无预期过滤）；卖出=4周预期修正rev4w<0（仅调仓月）",
    "v4a_both": "买入回到v2；卖出=PEG≥2.0 或 rev4w<0（仅调仓月）",
    "v4b_swap": "v3rec买入；卖出=PEG/rev触发【替换PS卖出=用户字面需求】",
    "v4b_plus": "v3rec买入；卖出=PS分位(含月度) + PEG/rev叠加",
}
MODE_COLOR = {
    "v2rec": "#888888",
    "v3rec": "#c00000",
    "v4a_peg": "#ff7f0e",
    "v4a_rev": "#2ca02c",
    "v4a_both": "#9467bd",
    "v4b_swap": "#d62728",
    "v4b_plus": "#1f77b4",
}


def load_json(name: str):
    p = os.path.join(HERE, name)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def nav_series(mode: str) -> dict:
    return {r["month"]: r["nav"] for r in load_json(f"_bt_gl_v4_{mode}_nav.json")}


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
                color=MODE_COLOR[m], lw=2.2 if m in ("v3rec", "v4b_swap")
                else 1.5)
    ax.plot(months, [bench[m] / bench[months[0]] for m in months],
            label=f"中证全指（{bench[months[-1]]/bench[months[0]]-1:+.1%}）",
            color="#1f77b4", lw=1.5, ls="--")
    for mk in ("2022-08", "2024-08", "2025-08"):
        ax.axvline(mk, color="#aaa", ls=":", lw=1)
    ax.set_title("growth_loop v4 估值卖出信号对比（PEG/rev vs PS 分位）")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_ylabel("净值（起点=1）")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig_to_b64(fig)


def make_period_chart(diags: dict) -> str:
    periods = list(diags["v2rec"]["per_period_ret"].keys())
    x = list(range(len(periods)))
    fig, ax = plt.subplots(figsize=(11, 4.8))
    w = 0.17
    for i, m in enumerate(CHART_MODES):
        vals = [diags[m]["per_period_ret"].get(p, 0.0) for p in periods]
        ax.bar([xi + (i - 1.5) * w for xi in x], vals, w,
               label=MODE_LABEL[m], color=MODE_COLOR[m], alpha=0.85)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=45, fontsize=8)
    ax.set_title("逐期收益对比（v2rec / v3rec / v4a_both / v4b_swap）")
    ax.legend(fontsize=8, ncol=2)
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
          <td>{d.get('na_check', 0)}</td>
        </tr>""")
    return "".join(rows)


def period_table(diags: dict) -> str:
    periods = list(diags["v2rec"]["per_period_ret"].keys())
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


def _post_sell_ret(sell, prices_all) -> dict:
    """卖出后 6 个月收益（信号预测力诊断，非组合贡献）。"""
    tk = sell["ticker"]
    dt = sell["dt"]
    px = prices_all.get(tk, {})
    if dt not in px or px[dt] <= 0:
        return {"ret6m": None}
    # 下 6 个月（含执行月滞后：引擎 N 期下单 N+1 期撮合，用 dt+1 起算）
    y, m = int(dt[:4]), int(dt[5:])
    future = []
    for _ in range(6):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        mk = f"{y}-{m:02d}"
        if mk in px and px[mk] and px[mk] > 0:
            future.append(px[mk])
    if not future:
        return {"ret6m": None}
    return {"ret6m": future[-1] / px[dt] - 1.0}


def sell_diag_table(sells_all: dict, prices_all: dict) -> str:
    """合并各模式卖出日志 + 卖出后 6 个月收益 + 卖对率。"""
    rows = []
    for m in MODES:
        sells = sells_all.get(m, [])
        if not sells:
            continue
        n_right = 0
        n_eval = 0
        for s in sells:
            info = _post_sell_ret(s, prices_all)
            r6 = info["ret6m"]
            if r6 is not None:
                n_eval += 1
                if r6 < 0:
                    n_right += 1
                r6_txt = f"{r6:+.1%}"
            else:
                r6_txt = "–"
            k = "调仓" if s["kind"] == "rebalance_overlay" else "月度"
            rows.append(f"""<tr>
              <td>{m}</td><td>{s['dt']}</td><td>{s['ticker']}</td>
              <td>{k}</td><td class="left">{s['reason']}</td>
              <td>{r6_txt}</td></tr>""")
        rows.append(f"""<tr class="grp">
          <td colspan="6">[{m}] 共 {len(sells)} 笔 | 可评估 {n_eval} | 卖对（后6月&lt;0）{n_right} |
          卖对率 {n_right/max(n_eval,1):.0%}</td></tr>""")
    return "".join(rows)


def sell_rate_by_mode(sells_all: dict, prices_all: dict) -> str:
    """每种模式的卖出后 6 月均值（信号有效性）。"""
    out = []
    for m in MODES:
        sells = sells_all.get(m, [])
        rs = []
        for s in sells:
            r = _post_sell_ret(s, prices_all)["ret6m"]
            if r is not None:
                rs.append(r)
        if not rs:
            continue
        mean = sum(rs) / len(rs)
        n_right = sum(1 for r in rs if r < 0)
        out.append(f"<tr><td>{MODE_LABEL[m]}</td><td>{len(sells)}</td>"
                   f"<td>{len(rs)}</td><td>{n_right}</td>"
                   f"<td>{n_right/len(rs):.0%}</td>"
                   f"<td class=\"{'pos' if mean<0 else 'neg'}\">{mean:+.1%}</td></tr>")
    return "".join(out)


def trigger_density_table() -> str:
    """每期候选池 PEG/rev 触发密度（决定卖出信号有没有活干）。"""
    cons = load_json("_gl_v3_consensus.json")
    sel = load_json("_bt_pit_selection.json")
    rows = []
    for m in ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]:
        cands = {tk for tk, _, _ in sel[m]["candidates"]}
        cov = cons.get(m, {})
        n_cov = len(cov)
        n_p15 = sum(1 for r in cov.values()
                    if r.get("peg") is not None and r["peg"] >= 1.5)
        n_p20 = sum(1 for r in cov.values()
                    if r.get("peg") is not None and r["peg"] >= 2.0)
        n_rev = sum(1 for r in cov.values()
                    if r.get("rev4w") is not None and r["rev4w"] < 0)
        rows.append(f"""<tr><td>{m}</td><td>{len(cands)}</td><td>{n_cov}</td>
          <td>{n_p15}</td><td>{n_p20}</td><td>{n_rev}</td></tr>""")
    return "".join(rows)


def main():
    diags = {m: load_json(f"_bt_gl_v4_{m}_diag.json") for m in MODES}
    bench = load_json("_bt_benchmark.json")
    navs = {m: nav_series(m) for m in MODES}
    prices_all = {tk: {**load_json("_bt_pit_warmup.json").get(tk, {}), **m}
                  for tk, m in load_json("_bt_pit_prices.json").items()}
    dets = {m: load_json(f"_bt_gl_v4_{m}_detail.json") for m in MODES}
    sells_all = {m: dets[m].get("sell_log", []) for m in MODES}

    nav_chart = make_nav_chart(navs, bench)
    period_chart = make_period_chart(diags)
    summary_rows = summary_table(diags)
    head, period_rows = period_table(diags)
    sell_rows = sell_diag_table(sells_all, prices_all)
    rate_rows = sell_rate_by_mode(sells_all, prices_all)
    density_rows = trigger_density_table()

    n_swap = len(sells_all["v4b_swap"])
    n_plus_extra = (len(sells_all["v4b_plus"])
                    - len(sells_all["v3rec"]))
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Growth Loop v4 一致预期 PEG 卖出实验报告</title>
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
  .kpi {{ flex: 1; min-width: 150px; background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 12px 16px; }}
  .kpi .v {{ font-size: 24px; font-weight: 700; }}
  .kpi .l {{ color: #888; font-size: 12px; margin-top: 4px; }}
  .pos {{ color: #d62728; }} .neg {{ color: #2ca02c; }}
  .pill {{ padding: 2px 10px; border-radius: 10px; font-size: 12px; color: #fff; }}
  .pill.good {{ background: #d62728; }} .pill.bad {{ background: #2ca02c; }}
  table.tbl {{ border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }}
  .tbl th, .tbl td {{ border: 1px solid #e4e4e6; padding: 6px 8px; text-align: center; }}
  .tbl th {{ background: #f0f0f2; }}
  .tbl td.left {{ text-align: left; }}
  .tbl tr.grp td {{ background: #fdeeee; font-weight: 700; text-align: left; }}
  img.chart {{ width: 100%; border-radius: 8px; margin: 8px 0; }}
  .warn {{ background: #fff8e6; border: 1px solid #f0d68a; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .goodbox {{ background: #fdeeee; border: 1px solid #e8b4b4; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .note {{ color: #666; font-size: 12px; }}
</style></head><body><div class="wrap">

<h1>Growth Loop v4 · 估值卖出改用一致预期 PEG 触发</h1>
<div class="meta">vnpy 框架 · 2021-08 ~ 2026-08 五年 · point-in-time 数据 · 零未来数据 · 半年度调仓 · 成本 5bp+10bp · 2026-08-19</div>

<div class="card kpis">
  <div class="kpi"><div class="v pos">+27.0%</div><div class="l">v3rec（PS 卖出，对照）</div></div>
  <div class="kpi"><div class="v neg">{n_swap} 笔</div><div class="l">v4b_swap（PEG/rev 替换 PS 卖出）实际触发</div></div>
  <div class="kpi"><div class="v pos">{n_plus_extra:+.0f} 笔</div><div class="l">v4b_plus（PS+PEG 叠加）相对 v3rec 增量</div></div>
  <div class="kpi"><div class="v pos">+{max(diags[m]['total_return'] for m in MODES):.1%}</div><div class="l">7 方案最优总收益</div></div>
</div>

<div class="goodbox"><b>核心结论：</b>一致预期 PEG/预期修正作为<b>卖出信号</b>，在「买入端未做预期过滤」的组合（v4a 系列）里<b>回撤改善显著</b>（v2rec -51.8% → v4a_both -36.9%）但<b>择时卖不准</b>（rev4w&lt;0 卖对率仅 51%、卖出后 6 月均值 +3.4% 整体卖飞），收益端仅 +1.8%（微超 v2rec +0.7%）。而一旦买入端已做预期过滤（v3rec 结构），卖出端再查同字段的 PEG/rev <b>必然冗余</b>：v4b_swap 全程触发 {n_swap} 笔，v4b_plus 相对 v3rec 增量 {n_plus_extra:+.0f} 笔——预期恶化的票在调仓日已被买入端拒之门外。用户的直觉「预期恶化即卖、响应比 PS 分位快」方向正确，但正确形态是<b>买入端前置否决</b>（v3rec 已在做）；卖出端真正有效的是 PS 分位（卖对率 75%、后 6 月 -19%，v4b_swap 对照组显示其单独贡献约 +20pp），PEG/rev 只能当风险开关而非收益来源。</div>

<div class="warn"><b>诚实声明：</b>①一致预期只有 10 个调仓月的 PIT 快照（juzi as_of 口径），非调仓月无历史数据 → PEG/rev 卖出<b>无法做月度出场</b>，只能调仓月 overlay（PS 卖出保留了月度出场，口径不对称，报告已标注）；②v3rec 买入端硬过滤 peg∈(0,2) 且 rev4w&gt;0，导致 v4b 系列卖出端与买入端数据同源冗余；③LOOP 层 L1-L7 LLM 深研无法诚实回测，只用 HOOK 层规则。</div>

<h2>一、7 方案对比</h2>
<table class="tbl"><thead><tr>
  <th>方案</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额</th><th>卖出笔数</th><th>PEG检查缺失放行</th>
</tr></thead><tbody>{summary_rows}</tbody></table>
<p class="note">v4a 系列 = 问题1（PEG/rev 卖出本身）：对照 v2rec（同买入端，+0.7%）。v4b 系列 = 问题2（v3rec 买入下替代/叠加）：对照 v3rec（+27.0%）。</p>

<h2>二、净值曲线与逐期对比</h2>
<img class="chart" src="data:image/png;base64,{nav_chart}" alt="净值对比">
<img class="chart" src="data:image/png;base64,{period_chart}" alt="逐期收益">

<h2>三、逐期收益明细</h2>
<table class="tbl"><thead><tr><th>期间</th>{head}</tr></thead>
<tbody>{period_rows}</tbody></table>

<h2>四、两个正交问题的归因</h2>
<div class="card">
<p><b>问题 1：PEG/预期恶化卖出本身有没有用？</b>（v4a 系列 vs v2rec，同买入端）</p>
<p class="note">v4a_rev（rev4w&lt;0 即卖）总收益 {diags['v4a_rev']['total_return']:+.1%} vs v2rec {diags['v2rec']['total_return']:+.1%}；v4a_both {diags['v4a_both']['total_return']:+.1%}。信号诊断见下表——<b>rev4w&lt;0 卖出后 6 月均值仍为 +3.4%（卖对率仅 51%，整体卖飞）</b>，它改善回撤靠的是削掉暴跌尾部（-51.8% → -40.4%），而不是信号择时准；PS 分位卖出才是真避跌（卖对率 74-75%、后 6 月均值 -19%）。收益上 v4a_both +1.8% 微超 v2rec +0.7%（PEG≥2 的 13 笔抓 2025-26 高位区补回一部分），但仍远低于把预期过滤放买入端的 v3rec。</p>
<p><b>问题 2：v3rec 买入过滤下，PEG 卖出替代/叠加 PS 卖出？</b></p>
<p class="note">v4b_swap 仅触发 {n_swap} 笔（买入端已过滤 peg≥2/rev≤0 的票，调仓日检查必然放行），总收益 {diags['v4b_swap']['total_return']:+.1%} vs v3rec {diags['v3rec']['total_return']:+.1%}——替换掉 PS 卖出后丢掉了 2025-26 的 10 笔月度/overlay 出场（那些是价格分位信号，PEG 替代不了）。v4b_plus 叠加后几乎等于 v3rec（{diags['v4b_plus']['total_return']:+.1%}），证明<b>PEG/rev 在 v3rec 卖出端无增量</b>。</p>
</div>

<h2>五、卖出信号有效性诊断（卖出后 6 个月表现）</h2>
<table class="tbl"><thead><tr>
  <th>方案</th><th>卖出笔数</th><th>可评估</th><th>卖对（后6月&lt;0）</th><th>卖对率</th><th>卖出后6月均值</th>
</tr></thead><tbody>{rate_rows}</tbody></table>
<p class="note">卖出后 6 月均值 &lt;0 = 信号确实避开了下跌（卖对了）。<b>PS 分位卖出卖对率最高</b>（v2rec 74% / v3rec 75%，后 6 月均值 -19% 左右，真避跌）；<b>rev4w&lt;0 卖出卖对率仅 51%（接近抛硬币），后 6 月均值 +3.4% 整体卖飞</b>——它的回撤改善来自削掉暴跌尾部而非择时。组合收益差异主要来自卖出信号质量与资金再配置（见诚实声明①）。</p>

<h2>六、全部卖出触发明细</h2>
<table class="tbl"><thead><tr>
  <th>方案</th><th>触发月</th><th>代码</th><th>类型</th><th>触发原因</th><th>卖出后6月</th>
</tr></thead><tbody>{sell_rows}</tbody></table>

<h2>七、候选池触发密度（卖出信号有没有活干）</h2>
<table class="tbl"><thead><tr>
  <th>调仓月</th><th>候选</th><th>预期覆盖</th><th>PEG≥1.5</th><th>PEG≥2.0</th><th>rev4w&lt;0</th>
</tr></thead><tbody>{density_rows}</tbody></table>
<p class="note">rev4w&lt;0（分析师 4 周内下调预期）每期 5-15 只，是 PEG 系里最有触发的信号；PEG≥2 每期仅 0-3 只且集中在高弹性票。PEG 阈值越高触发越稀，单独作卖出端不现实。</p>

<h2>八、结论与下一步</h2>
<div class="card">
<ul class="note">
  <li><b>预期信号放买入端（v3rec 已做）是正确形态</b>：预期恶化在调仓日被否决，比卖出端逐月检查更早更彻底——v3rec 的 -14%→+27% 主要来自这里。</li>
  <li><b>卖出端保留 PS 分位</b>：它是 7 个方案里唯一「卖对率 &gt;70% + 卖出后 6 月均值 -19%」的真避跌信号（抓 2025-26 高位区），v4b_swap 对照组显示它单独贡献约 +20pp；rev4w&lt;0 卖出整体卖飞（后 6 月 +3.4%），只适合当风险开关。</li>
  <li><b>若坚持卖出端用预期信号</b>：需要月度一致预期历史数据（当前只有调仓月快照）才能真正实现「预期下调当日即卖」；数据就绪前 v4a_rev 的结果可作下限参考（回撤改善明显但收益受损，且卖飞集中在 2025 牛市）。</li>
  <li><b>可选增强</b>：买入端 rev4w 阈值从 &gt;0 收紧（如 &gt;+50bp），或用 rev13w 长窗口确认持续上调，减少单周噪音。</li>
</ul>
</div>

</div></body></html>"""

    out = os.path.join(HERE, "growth_loop_v4_peg_sell_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"→ {out} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
