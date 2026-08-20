# -*- coding: utf-8 -*-
"""Growth Loop v2 改进回测报告生成（HTML + 图表）。

数据来自 _gl_v2_variant.py 的 6 个模式产物 + 基准。
用法: python _gl_v2_report.py
"""
from __future__ import annotations

import base64
import io
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimSun", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ["baseline", "v2a", "v2b", "v2c", "v2all", "v2rec"]

MODE_LABEL = {
    "baseline": "原版 baseline",
    "v2a": "v2a +过滤暴增",
    "v2b": "v2b +估值买入护栏",
    "v2c": "v2c +风格开关",
    "v2all": "v2all 4条全上",
    "v2rec": "v2rec 风格开关+估值卖出",
}
MODE_DESC = {
    "baseline": "HOOK 层原版：无任何改进",
    "v2a": "YoY>300% 周期暴增过滤",
    "v2b": "v2a + PS/PS_med≥2 买入端估值护栏",
    "v2c": "v2b + 熊市降仓 50%（风格开关）",
    "v2all": "v2c + 增速见顶降权50%再配置",
    "v2rec": "风格开关 + 估值卖出纪律（持仓中 PS/PS_med≥2 清仓）",
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


def make_nav_chart() -> str:
    bench = load_json("_bt_benchmark.json")
    nav_b = nav_series("baseline")
    nav_r = nav_series("v2rec")
    months = sorted(k for k in nav_b if k in bench)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    # 归一化到 1.0
    b0 = nav_b[months[0]]
    ax.plot(months, [nav_b[m] / b0 for m in months],
            label="baseline（-14.0%）", color="#888", lw=1.6)
    ax.plot(months, [nav_r[m] / nav_b[months[0]] for m in months],
            label="v2rec（+0.7%）", color="#d62728", lw=2.2)
    ax.plot(months, [bench[m] / bench[months[0]] for m in months],
            label="中证全指（+4.5%）", color="#1f77b4", lw=1.6, ls="--")
    for mk in ("2022-08", "2024-08"):
        ax.axvline(mk, color="#aaa", ls=":", lw=1)
    ax.set_title("growth_loop v2 净值对比（2021-08 ~ 2026-08，归一化）")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylabel("净值（起点=1）")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig_to_b64(fig)


def make_period_chart(diags: dict) -> str:
    periods = list(diags["baseline"]["per_period_ret"].keys())
    x = list(range(len(periods)))
    fig, ax = plt.subplots(figsize=(10, 4.6))
    w = 0.28
    for i, m in enumerate(["baseline", "v2rec"]):
        vals = [diags[m]["per_period_ret"].get(p, 0.0) for p in periods]
        color = "#d62728" if m == "v2rec" else "#888"
        ax.bar([xi + (i - 0.5) * w for xi in x], vals, w,
               label=MODE_LABEL[m], color=color, alpha=0.85)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=45, fontsize=8)
    ax.set_title("逐期收益对比（baseline vs v2rec）")
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


def attribution_table() -> str:
    rows = [
        ("A · 排除周期暴增", "v2a vs baseline", "-14.0% → -18.6%",
         "负贡献（-4.6pp）",
         "候选池已是全市场 top-100 增速，300% 一刀切误杀真成长：2025-08 牛市被滤掉的海力风电(yoy=461%)、中航成飞(yoy=2430%)正是当期涨幅主力；2024-08 牛市 +36.6% vs +39.1%。建议放弃或改为行业上下文判断（周期行业 300% 才滤）。"),
        ("B · 估值护栏（买入端）", "v2b vs v2a", "-18.6% → -16.9%",
         "微弱正贡献（+1.7pp）",
         "买入端过滤仅在候选池拦截少数票（每期 0-6 只），远不及之前 valsell 卖出实验的 -14% → -2.6%。真正有效的机制是<b>卖出端</b>：持仓中估值涨到 PS/PS_med≥2 就卖（见 v2rec）。"),
        ("C · 风格开关", "v2c vs v2b", "-16.9% → -13.8%",
         "正贡献（+3.1pp，MDD 收窄 3.5pp）",
         "2022-08、2024-08 两个熊市期降仓 50%：2022-08 期 -20.5% → -16.0%；2024-04 至 2024-08 期间基准 12 月收益仍负 → 2024-08 降仓（少赚 7pp 但换来后续确定性）。牛市期（2025-04 起）未被误判，完整吃到 +42%。"),
        ("D · 增速见顶降权再配置", "v2all vs v2c", "-13.8% → -19.7%",
         "负贡献（-5.9pp）",
         "2021-08 期 14/29 候选触发 decel → 降权后仅 6 只持仓 gross 48%，把组合砍半；2022-04 反弹期 -1.6% vs +2.0% 证明降权资金再配置给了低增长票，错失反弹。减速信号更适合做<b>不追加</b>而非降权现有仓位。"),
    ]
    out = []
    for tag, cmp, result, verdict, note in rows:
        vcls = "bad" if verdict.startswith("负") else "good"
        out.append(f"""
        <tr>
          <td><b>{tag}</b></td>
          <td>{cmp}</td>
          <td>{result}</td>
          <td><span class="pill {vcls}">{verdict}</span></td>
          <td class="left">{note}</td>
        </tr>""")
    return "".join(out)


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
        for tk, wt in sorted(w.items(), key=lambda x: -x[1])[:10]:
            dd = d.get(tk, {})
            vr = dd.get("val_ratio")
            vr_txt = f"{vr:.2f}" if vr is not None else "–"
            rows.append(f"""<tr>
              <td>{dd.get('name','?')}</td><td>{dd.get('sw1','?')}</td>
              <td>{dd.get('yoy',0):+.0%}</td>
              <td>{vr_txt}</td><td>{wt:.1%}</td></tr>""")
        out.append(f"""
        <h3>调仓 {mk} · 持仓 {len(w)} 只 · gross {sum(w.values()):.0%}</h3>
        <table class="tbl"><thead><tr><th>名称</th><th>行业</th>
        <th>营收YoY</th><th>PS/PS_med</th><th>权重</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>""")
    return "".join(out)


def main():
    diags = {m: load_json(f"_bt_gl_v2_{m}_diag.json") for m in MODES}
    det = load_json("_bt_gl_v2_v2rec_detail.json")
    nav_chart = make_nav_chart()
    period_chart = make_period_chart(diags)
    summary_rows = summary_table(diags)
    head, period_rows = period_table(diags)
    attr_rows = attribution_table()
    sell_rows = sell_table(det["sell_log"])
    hold_html = holdings_table(det)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Growth Loop v2 改进回测报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f7f7f8; color: #222; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  h2 {{ font-size: 20px; border-left: 4px solid #d62728; padding-left: 10px; margin-top: 40px; }}
  h3 {{ font-size: 15px; margin: 22px 0 8px; }}
  .sub {{ color: #666; font-size: 13px; }}
  .meta {{ color: #888; font-size: 12px; margin-bottom: 18px; }}
  .card {{ background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 16px 20px; margin: 14px 0; }}
  .kpis {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 150px; background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 12px 16px; }}
  .kpi .v {{ font-size: 26px; font-weight: 700; }}
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
  .note {{ color: #666; font-size: 12px; }}
</style></head><body><div class="wrap">

<h1>Growth Loop v2 · 4 条改进落地回测</h1>
<div class="meta">vnpy 框架 · 2021-08 ~ 2026-08 五年 · 点时(point-in-time)数据 · 零未来数据 · 半年度调仓 · 成本 5bp+10bp · 2026-08-19</div>

<div class="card kpis">
  <div class="kpi"><div class="v neg">-14.0%</div><div class="l">baseline 总收益</div></div>
  <div class="kpi"><div class="v pos">+0.7%</div><div class="l">v2rec 总收益（+14.7pp）</div></div>
  <div class="kpi"><div class="v neg">-51.8%</div><div class="l">v2rec 最大回撤（-56.6% →）</div></div>
  <div class="kpi"><div class="v neg">-3.8%</div><div class="l">v2rec 超额 vs 中证全指（-18.5% →）</div></div>
</div>

<div class="warn"><b>诚实声明：</b>LOOP 层 L1-L7（LLM 深研）无法诚实回测（模型训练数据含未来信息），本回测只用 HOOK 层确定性数值规则 + L8 信念代理。universe = 每期全市场点时 top-100 增速候选，无行业偏好。所有改进均只用调仓日已披露数据，无前瞻偏差。</div>

<h2>一、核心结果：6 个方案对比</h2>
<table class="tbl"><thead><tr>
  <th>方案</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额</th><th>估值卖出笔数</th>
</tr></thead><tbody>{summary_rows}</tbody></table>
<p class="note">v2all = 4 条改进全上（-19.7%）；v2rec = 证据支持的组合：风格开关 + 估值<b>卖出</b>纪律（+0.7%）。买入端估值护栏效果微弱，卖出端才是估值因子的正确用法。</p>

<h2>二、净值曲线与逐期对比</h2>
<img class="chart" src="data:image/png;base64,{nav_chart}" alt="净值对比">
<img class="chart" src="data:image/png;base64,{period_chart}" alt="逐期收益">

<h2>三、逐期收益明细</h2>
<table class="tbl"><thead><tr><th>期间</th>{head}</tr></thead>
<tbody>{period_rows}</tbody></table>

<h2>四、4 条改进逐条归因（诚实评估）</h2>
<table class="tbl"><thead><tr>
  <th>改进</th><th>对比</th><th>效果</th><th>结论</th><th>归因分析</th>
</tr></thead><tbody>{attr_rows}</tbody></table>

<h2>五、v2rec 机制拆解</h2>
<div class="card">
<p><b>① 风格开关：</b>2022-08、2024-08 两个调仓月基准 12 月收益 &lt; -10% → gross 降至 50%。2022-08 期回撤从 -21.0% 收窄到 -15.6%；2024-04 至 2024-08 少赚约 7pp，但换来了 2025-04 之后牛市完整参与（+21.6% / +33.9%）。</p>
<p><b>② 估值卖出纪律：</b>持仓中任意月份 PS/PS_med ≥ 2.0 → 卖出（次月撮合）。共 <b>19 笔</b>（调仓 overlay 12 / 月度出场 7），其中 <b>2026 年 10 笔</b>集中在 2026 上半年回调——2026-04 期收益 -1.1% vs baseline -12.5%（+11.4pp），是 v2rec 转正的最大单一来源。</p>
</div>
<table class="tbl"><thead><tr><th>触发月</th><th>代码</th><th>类型</th><th>触发原因</th><th>权重</th></tr></thead>
<tbody>{sell_rows}</tbody></table>

<h2>六、v2rec 代表性持仓</h2>
{hold_html}

<h2>七、局限与下一步</h2>
<div class="card">
<ul class="note">
  <li><b>超额仍为负（-3.8%）</b>：五年里策略仅 +0.7% vs 基准 +4.5%。候选池是 top-100 增速，本身是高风险高波动域，回撤 -51.8% 对实盘不可接受。</li>
  <li><b>降权再配置方向是对的但执行错了</b>：D 证明"减速=降权"会错过反弹；建议改为"减速=不追加买入"，让仓位自然衰减，而不是主动砍仓再配置。</li>
  <li><b>YoY>300% 过滤需要行业上下文</b>：一刀切会杀掉新能源/军工的真爆发；可改为"行业 PE 分位 &gt; 90% 且 YoY&gt;300% 才滤"。</li>
  <li><b>估值卖出阈值可再网格</b>：val15（1.5x）已验证更激进，可做 val15/val20/val25 三档敏感性 + 分行业差异化。</li>
  <li><b>风格开关信号可升级</b>：12 月收益 &lt;-10% 是简单代理，可换 MA200/估值分位/宽度指标，减少 2024-08 的误判。</li>
</ul>
</div>

</div></body></html>"""

    out = os.path.join(HERE, "growth_loop_v2_improvements_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"→ {out} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
