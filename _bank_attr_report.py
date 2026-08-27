# -*- coding: utf-8 -*-
"""银行/金融贡献归因报告 HTML 生成。数据源 _bank_attr_data.json + 补充检验结果。"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

d = json.load(open("_bank_attr_data.json", encoding="utf-8"))

# 任意起点检验（2026-08-27 计算，日频复权，起点每月抽样）
holding = [
    ("1年", 49, "+8.6%", "+7.2%", "47%"),
    ("2年", 37, "+34.3%", "+9.5%", "68%"),
    ("3年", 25, "+49.9%", "+37.3%", "88%"),
]

gc = d["grp_contrib"]
bank_share = gc["银行"] / sum(gc.values())
yl = d["yearly"]

rows_year = ""
for y, v in yl.items():
    excess = v["bank_idx_ret"] - v["ew_allA_ret"]
    color = "#c0392b" if excess > 0 else "#1e8449"
    rows_year += f"""<tr>
      <td><b>{y}</b></td>
      <td>{v['bank_contrib']:+.2%}</td>
      <td>{v['nonbk_contrib']:+.2%}</td>
      <td>{v['other_contrib']:+.2%}</td>
      <td>{v['bank_idx_ret']:+.2%}</td>
      <td>{v['ew_allA_ret']:+.2%}</td>
      <td style="color:{color};font-weight:600">{excess:+.2%}</td></tr>"""

rows_hold = "".join(
    f"<tr><td><b>{h}</b></td><td>{n}</td><td>{b}</td><td>{a}</td><td>{w}</td></tr>"
    for h, n, b, a, w in holding)

rows_holdings = "".join(
    f"<tr><td>{m}</td><td>{n}</td><td>{b}</td><td>{nb}</td><td>{p}</td></tr>"
    for m, n, b, nb, p in d["holdings"])

top_bank = "".join(
    f"<tr><td>{tk}</td><td>{v:+.2%}</td></tr>" for tk, v in d["top_bank_contrib"][:8])
top_other = "".join(
    f"<tr><td>{tk}</td><td>{v:+.2%}</td></tr>" for tk, v in d["top_other_contrib"][:8])

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>LX-core 银行/金融贡献归因 —— "择时买银行"命题检验</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background:#f7f8fa; color:#2c3e50; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }}
  h1 {{ font-size: 22px; border-left: 5px solid #c0392b; padding-left: 12px; }}
  h2 {{ font-size: 17px; margin-top: 34px; border-left: 4px solid #34495e; padding-left: 10px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  th, td {{ border: 1px solid #e3e6ea; padding: 7px 10px; text-align: right; }}
  th {{ background: #34495e; color: #fff; text-align: center; font-weight: 500; }}
  td:first-child, th:first-child {{ text-align: left; }}
  tr:nth-child(even) td {{ background: #fbfcfd; }}
  .card {{ background:#fff; border-radius:10px; padding:16px 20px; margin:14px 0; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .verdict {{ background:#fff8e1; border-left:5px solid #f39c12; padding:14px 18px; margin:16px 0; line-height:1.8; }}
  .no {{ background:#fdecea; border-left:5px solid #c0392b; padding:14px 18px; margin:16px 0; line-height:1.8; }}
  .yes {{ background:#eafaf1; border-left:5px solid #1e8449; padding:14px 18px; margin:16px 0; line-height:1.8; }}
  .num {{ font-size:26px; font-weight:700; color:#c0392b; }}
  .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:14px 0; }}
  .kpi {{ background:#fff; border-radius:10px; padding:14px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .kpi .lab {{ font-size:12px; color:#7f8c8d; }}
  .kpi .val {{ font-size:20px; font-weight:700; margin-top:4px; }}
  .up {{ color:#c0392b; }} .down {{ color:#1e8449; }}
  .note {{ font-size:12px; color:#7f8c8d; line-height:1.7; }}
</style>
</head>
<body><div class="wrap">
<h1>LX-core 银行/金融贡献归因 —— 兼论"择时买银行"命题</h1>
<div class="note">区间 {d['period']} ｜ 日频复权价 ｜ 调仓语义对齐官方引擎（触发日收盘挂单→次日开盘成交，费率近似15bp/换手）
｜ 银行/非银分类：juzi 中信一级 PIT ∩ 万得全A PIT（银行42只、非银81只）｜ 生成 2026-08-27</div>

<h2>0. 一句话结论</h2>
<div class="verdict">
<b>前半句对：是的，LX-core 的收益大头来自银行。</b>归因分解：银行贡献
<span class="num">+{gc['银行']:.1f}pp</span>，占全部盈亏来源的 <b>{bank_share:.0%}</b>；
组合层对照（含金融 +55.55% vs 剔金融 +29.45%）金融板块带来 <b>+26.1pp</b>。<br>
<b>后半句错：但推不出"择时买银行是对的"。</b>银行的超额几乎全部集中在 2024 一个年份（等权银行 +40.5% vs 等权全A +0.4%）；
2021/2023/2025 三年银行均大幅跑输全A（-11pp / -8pp / -27pp）。任意起点持有 1 年，银行跑赢全A 的概率只有
<b>47%</b>——和抛硬币无异。"买银行赚钱"是本回测样本期（起点恰在银行估值历史大底、终点在 2024 行情后）的产物，
而 LX-core 的可持续 alpha 来自 <b>PE 升序的估值纪律</b>，银行只是这套规则在 2021-2026 的市场表达载体，不是规则本身。
</div>

<h2>1. LX-core 收益逐股分解（归因层，与官方引擎对齐 +55.61% ≈ +55.55%）</h2>
<div class="grid">
  <div class="kpi"><div class="lab">core 总收益（含费，官方）</div><div class="val up">+55.55%</div></div>
  <div class="kpi"><div class="lab">银行贡献</div><div class="val up">+{gc['银行']:.2f}pp</div></div>
  <div class="kpi"><div class="lab">其他（非金融）贡献</div><div class="val up">+{gc['其他']:.2f}pp</div></div>
  <div class="kpi"><div class="lab">非银金融贡献</div><div class="val up">+{gc['非银金融']:.2f}pp</div></div>
</div>
<table>
<tr><th>分组</th><th>贡献（占初始资金）</th><th>占比</th><th>说明</th></tr>
<tr><td>银行（42只池）</td><td class="up">{gc['银行']:+.2%}</td><td class="up">{bank_share:.0%}</td>
    <td style="text-align:left">历次调仓持仓 18~30 / 40 只，平均约 57% 权重</td></tr>
<tr><td>其他（非金融）</td><td class="up">{gc['其他']:+.2%}</td><td>{gc['其他']/sum(gc.values()):.0%}</td>
    <td style="text-align:left">地产/建筑/交运等低 PE 股，正贡献但波动大</td></tr>
<tr><td>非银金融（81只池）</td><td class="up">{gc['非银金融']:+.2%}</td><td>{gc['非银金融']/sum(gc.values()):.0%}</td>
    <td style="text-align:left">2025-2026 才少量入选（0→5只），贡献很小</td></tr>
<tr><td><b>合计</b></td><td><b>{sum(gc.values()):+.2%}</b></td><td>100%</td>
    <td style="text-align:left">归因层无费 +55.61%，与官方含费 +55.55% 对齐 ✓</td></tr>
</table>
<div class="note">组合层交叉验证：core（含金融）+55.55% vs core_finex（剔金融，重新排序取top40）+29.45%，
金融板块组合层贡献 +26.10pp —— 与逐股归因（银行+42pp，含金融剔除后排序/持仓结构变化的间接效应）方向一致、量级吻合。</div>

<h2>2. 银行是 core 的重仓 —— 这是 PE 升序规则的必然结果</h2>
<table>
<tr><th>调仓期</th><th>持仓数</th><th>其中银行</th><th>其中非银</th><th>银行权重占比</th></tr>
{rows_holdings}
</table>
<div class="note">银行 A 股常年占据全市场 PE 最低的席位，PE 升序取 top40 必然大量吸入银行。
这不是行业判断，是估值纪律的结构性暴露。</div>

<h2>3. 银行股独立检验：等权买银行 vs 基准（同区间、同口径）</h2>
<table>
<tr><th>组合</th><th>总收益</th><th>年化</th><th>MDD(日频)</th><th>超额(等权全A)</th></tr>
<tr><td>等权银行（{d['bank_n']}只，半年再平衡）</td><td class="up">{d['bank_ew']['total']:+.2%}</td>
    <td class="up">{d['bank_ew']['ann']:+.2%}</td><td>{d['bank_ew']['mdd']:.2%}</td>
    <td class="up">{d['bank_ew']['total']-d['ew_allA']['total']:+.2%}</td></tr>
<tr><td>等权全A（万得全A PIT，半年调仓）</td><td class="up">{d['ew_allA']['total']:+.2%}</td><td>—</td>
    <td>{d['ew_allA']['mdd']:.2%}</td><td>—</td></tr>
<tr><td>中证全指（市值加权价格指数）</td><td class="{ 'up' if d['idx']['total']>0 else 'down'}">{d['idx']['total']:+.2%}</td>
    <td>—</td><td>{d['idx']['mdd']:.2%}</td><td class="down">{d['idx']['total']-d['ew_allA']['total']:+.2%}</td></tr>
<tr><td>LX-core（对照）</td><td class="up">+55.55%</td><td>+9.16%</td><td>19.13%</td>
    <td class="up">+14.42pp</td></tr>
</table>
<div class="verdict">表面看，"无脑等权买银行"（+53.4%，MDD 17.4%）几乎追平 LX-core（+55.6%，MDD 19.1%）。
这是最有迷惑性的数字 —— 但它高度依赖样本期，见下一节。</div>

<h2>4. 银行超额的时间分布：2024 一年定胜负</h2>
<table>
<tr><th>年份</th><th>银行贡献(core内)</th><th>非银贡献</th><th>其他贡献</th><th>等权银行指数</th><th>等权全A</th><th>银行超额</th></tr>
{rows_year}
</table>
<div class="no">
<b>关键事实：</b><br>
① 等权银行 5 年 +53.4% 里，<b>2024 一年贡献 +40.5%</b>；2021-2023 三年银行累计约 <b>-6.5%</b>（同期全A约 +2%）。<br>
② 2024 银行超额 +40.1pp 的驱动是汇金增持 + 险资高股息配置 + 长端利率下行 —— 一次性 regime，事前没有可操作信号。<br>
③ 2025 年银行 <b>跑输全A 26.6pp</b>（+14.2% vs +40.8%）—— regime 已经切换走，"买银行"在最近一年半是拖累（相对等权口径）。<br>
④ "择时买银行"要求你在 2023 年底（银行连输三年、全市场共识"银行=价值陷阱"时）重仓切入，并在 2025 年初切走。
两个时点都和当时的市场共识相反，且本回测没有验证任何能提前识别它们的信号。
</div>

<h2>5. 任意起点检验：换一个入场月份，银行还赚钱吗？</h2>
<table>
<tr><th>持有期</th><th>起点数（每月抽样）</th><th>银行中位收益</th><th>等权全A中位</th><th>银行跑赢概率</th></tr>
{rows_hold}
</table>
<div class="note">持有 1 年：银行跑赢概率 47%（≈抛硬币）；持有 3 年：88% —— 但 3 年窗口高度重叠且几乎都被 2024 覆盖，
本质仍是"这一个行情"而非稳定规律。数据起点限制（2021-06），无法检验 2018-2020 等更早入场点（那几年银行长期跑输成长）。</div>

<h2>6. 结论：命题辨析</h2>
<div class="yes"><b>可以说的：</b><br>
① "在 2021-2026 样本期内，A股赚钱的一条路径是低估值纪律，银行是该纪律的最大收益载体" —— 成立，银行贡献 core 约 76% 的盈亏。<br>
② "含金融的全市场 PE 升序组合优于剔金融组合" —— 成立（+26.1pp），金融剔除是负贡献。<br>
③ "银行在本区间兼具收益与低回撤（MDD 17.4% vs 全A 31.9%）" —— 成立，防御属性真实（2022、2026 两个下跌年均跑赢）。</div>
<div class="no"><b>不能说的：</b><br>
① "择时买银行是对的" —— 不成立。银行 1 年持有期跑赢概率仅 47%；超额集中在单一 2024 regime；
样本期起点恰在银行 PB 历史大底（~0.6x），起点偏置严重。若 2017 或 2021 年前入场，结论可能完全反转。<br>
② "LX-core 的 alpha 来自银行" —— 不准确。剔金融后 finex +29.45% 仍碾压中证全指 +0.13%、跑赢等权全A池子。
alpha 的来源是<b>规则</b>（PE 升序 + 半年再平衡纪律），银行只是规则当前选中的表达。若未来银行估值修复到不再便宜，规则会自动离开银行 —— 这正是规则优于行业判断的地方。<br>
③ 把"银行=低PE=安全"外推为永恒 —— 银行低 PE 长期存在有其资产负债表原因（杠杆生意、隐含不良、增长天花板），
"便宜"不自动等于"会涨"。本框架已有结论：低估≠催化剂（药明 760 天陷阱）。</div>
<div class="verdict"><b>正确的表述：</b>不是"择时买银行"，而是"用可事前定义的估值纪律持有全市场最便宜的一篮子股票，
并接受它的行业暴露随市场状态漂移"。2021-2026 这篮子恰好装的主要是银行；下一个五年可能不是。
押行业标签 = 押单一 regime；押规则 = 押估值回归的长期统计规律。后者才是可外推的。</div>

<h2>附：Top 贡献个股</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
<div><table><tr><th colspan="2">Top 银行贡献（占初始资金）</th></tr>{top_bank}</table></div>
<div><table><tr><th colspan="2">Top 非银行贡献（占初始资金）</th></tr>{top_other}</table></div>
</div>
<div class="note">数据：_bt_daily_px.json（复权日频）/_bt_band_results.json（core 权重）/_bt_sw_fin_universe.json（金融分类）/
_bt_daily_ew_hold_nav.json（等权全A基准）。脚本：_bank_attr.py。缺口：等权银行组合缺 4 只无日频价的小银行；
归因层费用为换手额 15bp 近似。</div>
</div></body></html>"""

open("_bank_attr_report.html", "w", encoding="utf-8").write(html)
print("→ _bank_attr_report.html")
