# -*- coding: utf-8 -*-
"""章宏帆框架 × 分析师一致预期 — 2×2 诚实回测报告 (HTML)。"""
from __future__ import annotations

import base64
import json

# ---------------- 数据 ----------------
w = json.loads(open("_bt_zhf_weights.json", encoding="utf-8").read())
diag_cons, diag_c = w["diag_cons"], w["diag_c"]

px = json.loads(open("_zhf_prices.json", encoding="utf-8").read())
from examples.alla_rotation import LEADER_SEEDS
leaders = {}
for link, seeds in LEADER_SEEDS.items():
    if link.startswith("_"):
        continue
    for name, tk in seeds.items():
        leaders.setdefault(tk, name)

cons = w["cons"]
ws25, ws26 = cons["2025-08"], cons["2026-04"]
dropped = [t for t in ws25 if t not in ws26]
drop_rows = []
for t in dropped:
    d = px.get(t, {})
    p0, p1 = d.get("2025-08"), d.get("2026-04")
    if p0 and p1:
        drop_rows.append((leaders.get(t, t), ws25[t], p1 / p0 - 1))
drop_rows.sort(key=lambda r: -r[2])

cost_rows = []
for t, nm in [("300308.SZ", "中际旭创"), ("300502.SZ", "新易盛"), ("300394.SZ", "天孚通信")]:
    d = px.get(t, {})
    w24 = cons["2024-08"].get(t, 0)
    w25 = cons["2025-08"].get(t, 0)
    p24, p25, p26 = d.get("2024-08"), d.get("2025-08"), d.get("2026-08")
    if p24 and p25 and p26:
        cost_rows.append((nm, w24, w25, p25 / p24 - 1, p26 / p25 - 1))

img_nav = base64.b64encode(open("_zhf_chart_nav.png", "rb").read()).decode()
img_rel = base64.b64encode(open("_zhf_chart_rel.png", "rb").read()).decode()


def cls_rows(diag: dict) -> str:
    out = []
    for m, d in diag.items():
        cls = d.get("cls", {})
        a = cls.get("A", 0); b = cls.get("B", 0); c = cls.get("C", 0); off = cls.get("OFF", 0)
        out.append(
            f"<tr><td>{m}</td><td>{d['cov']}/{d['pool']}</td>"
            f"<td>{d['abstain']}</td><td>{d['hold']}</td>"
            f"<td>{a}</td><td>{b}</td><td>{c}</td><td>{off}</td></tr>")
    return "\n".join(out)


def c_rows(diag: dict) -> str:
    out = []
    for m, d in diag.items():
        cd = d.get("c_dist", {})
        out.append(
            f"<tr><td>{m}</td><td>{d['cov']}</td>"
            f"<td>{cd.get('0',0)}</td><td>{cd.get('1',0)}</td><td>{cd.get('2',0)}</td>"
            f"<td>{cd.get('3',0)}</td><td>{cd.get('4',0)}</td><td>{d['hold']}</td></tr>")
    return "\n".join(out)


drop_tr = "\n".join(
    f"<tr><td class='left'>{n}</td><td>{wd:.0%}</td>"
    f"<td class='{'pos' if r>0 else 'neg'}'>{r:+.0%}</td></tr>"
    for n, wd, r in drop_rows)

cost_tr = "\n".join(
    f"<tr><td class='left'>{n}</td><td>{w24:.0%}</td><td>{w25:.0%}</td>"
    f"<td class='pos'>{r1:+.0%}</td><td class='pos'>{r2:+.0%}</td></tr>"
    for n, w24, w25, r1, r2 in cost_rows)

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>章宏帆框架 × 分析师一致预期 — 2×2 诚实回测报告</title>
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
  .kpi {{ flex: 1; min-width: 170px; background: #fff; border: 1px solid #e4e4e6; border-radius: 8px; padding: 12px 16px; }}
  .kpi .v {{ font-size: 24px; font-weight: 700; }}
  .kpi .l {{ color: #888; font-size: 12px; margin-top: 4px; }}
  .pos {{ color: #d62728; }} .neg {{ color: #2ca02c; }}
  .pill {{ padding: 2px 10px; border-radius: 10px; font-size: 12px; color: #fff; }}
  .pill.good {{ background: #d62728; }} .pill.bad {{ background: #2ca02c; }} .pill.gray {{ background: #888; }}
  table.tbl {{ border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }}
  .tbl th, .tbl td {{ border: 1px solid #e4e4e6; padding: 6px 8px; text-align: center; }}
  .tbl th {{ background: #f0f0f2; }}
  .tbl td.left {{ text-align: left; }}
  img.chart {{ width: 100%; border-radius: 8px; margin: 8px 0; border: 1px solid #e4e4e6; }}
  .warn {{ background: #fff8e6; border: 1px solid #f0d68a; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .goodbox {{ background: #fdeeee; border: 1px solid #e8b4b4; border-radius: 8px; padding: 12px 16px; font-size: 13px; }}
  .insight {{ background: #eef4fb; border: 1px solid #b8cfe8; border-radius: 8px; padding: 14px 18px; font-size: 13.5px; }}
  .note {{ color: #666; font-size: 12px; }}
</style></head><body><div class="wrap">

<h1>章宏帆框架 × 分析师一致预期 · 2×2 诚实回测</h1>
<div class="meta">vnpy 引擎 · 2021-08 ~ 2026-08 五年 · 同池（章宏帆龙头池 58 只）· 同价（腾讯 qfq 月K线）· 同成本（5bp+10bp）· 半年度调仓 10 期 · PIT 一致预期快照 · 2026-08-19</div>

<div class="card kpis">
  <div class="kpi"><div class="v">+455%</div><div class="l">龙头池等权（58只）总收益</div></div>
  <div class="kpi"><div class="v pos">+434%</div><div class="l">C-cons 纯一致预期（相对池子 −21pp）</div></div>
  <div class="kpi"><div class="v pos">+329%</div><div class="l">ZHF-cons 框架×预期（相对池子 −126pp）</div></div>
  <div class="kpi"><div class="v pos">+201%</div><div class="l">ZHF-act 框架×财报（相对池子 −255pp）</div></div>
  <div class="kpi"><div class="v">+5.9%</div><div class="l">沪深300 同期</div></div>
</div>

<div class="goodbox"><b>核心结论（必须先说清楚）：</b>这个实验的收益<b>绝大部分来自池子本身，不是策略</b>。58 只龙头（从 2026 年视角选出）等权持有 5 年 +455%，而沪深300 只有 +5.9% —— 幸存者偏差 + AI 硬件超级周期构成了巨量"池子 beta"。三个策略 <b>全部跑输等权池子</b>（−21 ~ −255pp）。在这个前提下，能分离出的真实信号是：<b>① 章宏帆框架的纪律把回撤压到池子的一半（−14.6% vs −33.9%）；② 一致预期数据让框架少误杀加速股，5 年多赚 128pp；③ 框架的估值纪律在泡沫主升浪（2025-08 调仓）成为收益杀手——被剔除的 8 只股票半年后平均再涨 53%。</b></div>

<div class="warn"><b>诚实声明：</b>① 龙头池 58 只由 2026 年的"环节龙头"名单构成，含幸存者偏差，池子等权 +455% 即其量级；② 环节稀缺度表（link_map）为 2026-05 快照，用今天的环节认知判断 2021 年属于前视；③ 一致预期数据 2021-2022 覆盖不全（39~47/58 只），2023 年起稳定 52/58；④ 价格为腾讯前复权月K线，含分红调整；⑤ 因此本报告<b>无法分离"环节稀缺度选股 alpha"</b>，只能分离"纪律价值"与"预期数据的响应价值"。</div>

<h2>一、实验设计：同池同价同成本，只换"数据源"</h2>
<div class="card">
<table class="tbl"><thead><tr><th>方案</th><th>选股逻辑</th><th>数据源</th></tr></thead><tbody>
  <tr><td><b>ZHF-act</b></td><td class="left">章宏帆决策树：L1 分类 → 类则估值 → 质量乘数 → blend 组合</td><td class="left">实际财报（PIT 披露截止日过滤）</td></tr>
  <tr><td><b>ZHF-cons</b></td><td class="left">同一决策树，字段映射：con_np_yoy→增速、con_roe→ROE、con_pe→估值、np_revision_4w→加速、环节稀缺度/类则/乘数保留</td><td class="left">分析师一致预期（朝阳永续 PIT 快照）</td></tr>
  <tr><td><b>C-cons</b></td><td class="left">纯 C-Score 四信号（con_roe&gt;12% / 预期增速&gt;0 / rev4w&gt;0 / rev13w&gt;0），无环节判断</td><td class="left">分析师一致预期</td></tr>
</tbody></table>
<div class="note">比较逻辑：ZHF-act vs ZHF-cons 回答"预期数据是否改变框架选股质量"；ZHF-cons vs C-cons 回答"框架的方向偏好是否在预期数据上产生增量"。</div>
</div>

<h2>二、结果总览（2021-08 → 2026-08）</h2>
<div class="card">
<table class="tbl"><thead><tr>
  <th>方案</th><th>总收益</th><th>最大回撤</th><th>相对池子</th><th>期末相对净值</th><th>回撤/收益比</th>
</tr></thead><tbody>
  <tr><td><b>龙头池等权</b><br><span class="sub">58只全持有，每月再平衡</span></td>
      <td class="pos">+455.2%</td><td class="neg">−33.9%</td><td>—</td><td>1.000</td><td>0.075</td></tr>
  <tr><td><b>C-cons 纯预期</b><br><span class="sub">C-Score≥2 即买，无框架</span></td>
      <td class="pos">+434.0%</td><td class="neg">−30.4%</td><td class="neg">−21.1pp</td><td>0.960</td><td>0.070</td></tr>
  <tr><td><b>ZHF-cons 框架×预期</b><br><span class="sub">章宏帆决策树 × 一致预期</span></td>
      <td class="pos">+329.1%</td><td class="neg">−27.0%</td><td class="neg">−126.1pp</td><td>0.771</td><td>0.082</td></tr>
  <tr><td><b>ZHF-act 框架×财报</b><br><span class="sub">章宏帆决策树 × 实际财报</span></td>
      <td class="pos">+200.6%</td><td class="neg">−14.6%</td><td class="neg">−254.6pp</td><td>0.540</td><td>0.073</td></tr>
  <tr><td><b>沪深300</b><br><span class="sub">大盘基准</span></td>
      <td class="pos">+5.9%</td><td class="neg">−40%+</td><td>—</td><td>—</td><td>—</td></tr>
</tbody></table>
<div class="note">三策略相对沪深300都是"巨幅跑赢"，但那是池子 beta 的功劳。相对池子才是策略的真实选股质量：全部为负。诚实解读：<b>在"后视镜龙头池"里，任何选股动作都不如等权傻持有</b>——选股越"聪明"（ZHF-act 的纪律最多），跑输越多。</div>
</div>

<h2>三、净值曲线</h2>
<div class="card">
<img class="chart" src="data:image/png;base64,{img_nav}" alt="净值对比">
<div class="note">对数轴。灰虚线=池子等权（+455%），绿=纯预期，红=框架×预期，橙=框架×财报，蓝=沪深300。三策略收益远高于大盘，但均低于池子。</div>
</div>

<div class="card">
<img class="chart" src="data:image/png;base64,{img_rel}" alt="相对池子超额">
<div class="note">相对池子净值（1.0=持平）。三个策略都经历"先跑赢（2022 熊市，框架/纪律抗跌）→ 后跑输（2023 起 AI 主升浪，纪律拖后腿）"。ZHF-act 在 2022-10 一度相对池子 +37%，到 2026-08 变成 −46%。</div>
</div>

<h2>四、预期数据如何改变框架：分类结构差异</h2>
<div class="card">
<table class="tbl"><thead><tr>
  <th>调仓期</th><th>预期覆盖</th><th>abstain</th><th>持仓数</th>
  <th colspan="4">ZHF-cons 资产分类</th>
</tr><tr><th></th><th></th><th></th><th></th>
  <th>A 景气</th><th>B 周期</th><th>C 新兴</th><th>OFF</th>
</tr></thead><tbody>
{cls_rows(diag_cons)}
</tbody></table>
<div class="note">ZHF-cons 的 <b>A 类（景气成长）每期 8~32 只</b>——一致预期的"高增速+分析师上调"组合能直接命中加速股。对比财报版 ZHF-act：A 类每期只有 2~6 只（2023-04 甚至 0 只）。财报滞后让框架在 2023 年只剩 8~9 个信号（B 类为主），而预期版同期有 15~26 个信号。<b>这是预期数据多赚 128pp 的直接机制：让框架从"财报验证景气"提前到"预期捕捉景气"。</b></div>
</div>

<h2>五、纯预期 C-cons 的画像：近似"满仓持有池子"</h2>
<div class="card">
<table class="tbl"><thead><tr>
  <th>调仓期</th><th>覆盖</th><th colspan="5">C-Score 分布（0/1/2/3/4）</th><th>持仓数</th>
</tr></thead><tbody>
{c_rows(diag_c)}
</tbody></table>
<div class="note">C-cons 每期持仓 23~46 只（占池子 40%~79%），C≥2 即买入。因为龙头池里大部分股票持续满足"预期增速>0 + 分析师上调"，纯预期信号几乎不淘汰任何股票 → 收益（+434%）贴近池子（+455%），只差 21pp（持仓分散 + 半年调仓的再平衡损耗）。<b>换句话说：C-Score 在"优质池"里的信息量约等于零——它擅长的是在全市场里筛选"谁有预期"，而不是在预期全好的池子里再排序。</b></div>
</div>

<h2>六、纪律的机会成本：2025-08 调仓的减仓代价</h2>
<div class="card">
<h3>6.1 被剔除的 8 只股票，之后半年表现</h3>
<table class="tbl"><thead><tr><th>股票</th><th>剔除前权重</th><th>2025-08 → 2026-04 涨跌</th></tr></thead><tbody>
{drop_tr}
</tbody></table>
<div class="note">8 只中 6 只继续大涨、平均再涨 53%（环旭电子 +100%、三环集团 +95%、伟测科技 +85%、华工科技 +75%、生益电子 +42%、鹏鼎控股 +21%）。剔除原因：估值超类则上限 / 分析师短期下调（rev4w≤0）——这两条纪律在熊市避雷有效，但在 2025-08 的 AI 主升浪里成了"把会飞的票全放掉"。</div>
</div>

<div class="card">
<h3>6.2 光模块三巨头：顶格 5% → 降权 3% 后继续翻倍</h3>
<table class="tbl"><thead><tr>
  <th>股票</th><th>2024-08 权重</th><th>2025-08 权重</th><th>24-08→25-08</th><th>25-08→26-08</th>
</tr></thead><tbody>
{cost_tr}
</tbody></table>
<div class="note">2024-08 框架顶格买入中际旭创/新易盛/天孚通信（各 5%），2025-08 因"涨太多、预期 PE 超环节上限"降权到 3%——随后一年三者再涨 +62%~+153%。<b>这是 ZHF-cons 相对池子 −126pp 的最大单一来源。</b></div>
</div>

<h2>七、投资经理个人 insight：这个实验诚实回答了什么</h2>
<div class="card">
<div class="insight">
<b>Q：章宏帆框架 × 分析师预期，会带来投资经理个人特别的 insight 吗？</b><br><br>
<b>① 环节稀缺度（框架最独特的部分）的 alpha，本实验无法证明，也无法证伪。</b>
环节稀缺度 S1-S5 打分是分析师数据里没有的"方向判断"。但在一个等权 +455% 的后视镜池子里，任何选股差异都被池子 beta 淹没——三策略全跑输池子说明：<b>框架的方向偏好在这 5 年没有比"全买"更好</b>。要诚实检验它，必须在"无幸存者偏差的全市场"里做，而不是这个池子。<br><br>
<b>② 框架真实的个人印记是"纪律"，不是"选股"。</b>
ZHF-act 回撤 −14.6% vs 池子 −33.9%——类则仓位上限（A 60% / B 35% / C 5%）、PE ceiling、质量乘数把回撤砍掉一半以上。2022 熊市里它相对池子一度 +37%。<b>这是"投资经理框架 vs 满仓指数"的真实差异：他少赚，但更稳。</b>代价是 2024-10 后 AI 主升浪中持续跑输——纪律和泡沫行情天然冲突，任何框架都要在"泡沫期少赚"和"熊市少亏"之间二选一，章宏帆选了后者。<br><br>
<b>③ 一致预期数据的价值 = 响应速度，这是财报永远给不了的。</b>
同一棵决策树，数据从财报换成预期，5 年多赚 128pp（+201% → +329%），机制清晰：预期版 A 类识别从 2~6 只提到 8~32 只。财报滞后 4-13 周，预期当场反应。<b>如果未来要把这个框架用于实盘，答案明确：用一致预期做信号、用框架做纪律。</b><br><br>
<b>④ 一个反直觉的结论：在这个池子里，"纯预期 C-Score" 比"框架×预期"赚得多（+434% vs +329%）。</b>
不是因为 C-Score 更好，而是因为它几乎没有动作（近似满仓池子）。框架的纪律让它少拿了 105pp，但把回撤从 −30.4% 压到 −27.0%。<b>投资经理的价值不在"多赚"而在"少亏"——这 5 年是 AI 单边牛市，纪律吃亏；换一个 2022 式的熊市年份，天平会完全反过来。</b>
</div>
</div>

<h2>八、局限与免责</h2>
<div class="warn">
① 幸存者偏差：龙头池为 2026 年视角名单，池子等权 +455% 是"事后最优池"的上限，实盘不可复制；② 环节表前视：2026-05 快照用于 2021 年调仓，高估了当时的环节判断能力；③ 一致预期 2021-2022 覆盖 39~47/58 只，早期结果受覆盖影响；④ 前复权价格含分红调整，但未计股息再投资细节；⑤ 半年度调仓、无停牌处理、无涨跌停约束，均为简化；⑥ 本报告为策略研究，不构成投资建议。
</div>

<div class="note" style="margin-top:20px">数据：腾讯行情（qfq 月K线）· 朝阳永续一致预期（juzi-mcp PIT 快照）· 东财财务（PIT 披露截止日）· vnpy 引擎（N 期下单 N+1 期撮合）· 基准沪深300</div>

</div></body></html>"""

open("zhf_cons_variant_report.html", "w", encoding="utf-8").write(html)
print("报告已生成: zhf_cons_variant_report.html")
