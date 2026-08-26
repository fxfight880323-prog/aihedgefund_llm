# -*- coding: utf-8 -*-
"""
_ai_fund_framework_summary.py — ai_fund_framework 全景总结报告 (2026-08-26)
==========================================================================
汇总: 三层Alpha结构 + garp门控采纳 + 回测证据矩阵 + 方法论铁律
      + 当前名单(2026-08-24 评分top40) + 数据基础设施 + 风险待办
"""
import json, os, html as H

BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

def load(name):
    try:
        return json.load(open(BASE + name, encoding="utf-8"))
    except Exception as e:
        return {"__err__": str(e)}

# ---------- 数据 ----------
final   = load("_lx_now_final.json")
garp    = load("_bt_garp_results.json")
qrelax  = load("_bt_qrelax_results.json")
daily   = load("_bt_daily_results.json")
res     = load("_lx_now_results.json")

as_of = final.get("as_of", "2026-08-24")

# 漏斗统计
stats = res.get("stats", {})
funnel = [
    ("万得全A PIT 成分 (881001.WI)", stats.get("univ", 0) + stats.get("fin_removed", 0), "基准池，消除幸存者偏差"),
    ("剔除金融 (银行/非银)", stats.get("univ", 0), "仅展示层铁律，不进回测管线"),
    ("市值 ≥ 100 亿", stats.get("core_pass", 0) + sum(stats.get(k, 0) for k in []), "质量保护下限"),
    ("PE > 0 且 L4 (PE≤25 或 股息率≥2%)", stats.get("core_pass", 0), "估值进入门槛"),
    ("L5-garp (增速≤60% 且 0<PEG≤1)", stats.get("core_pass", 0), "2026-08-26 采纳：增速可高但估值须匹配"),
    ("gm 质量层 (毛利率≥市场中位)", stats.get("gm_pass", 0), "回撤保护层"),
]

def esc(s):
    return H.escape(str(s)) if s is not None else "—"

# 名单表格行
def band_badge(flag):
    colors = {"安全边际": "#1e8449", "自身低位": "#2874a6", "中性": "#566573",
              "偏高": "#b9770e", "规避": "#c0392b"}
    c = colors.get(flag, "#566573")
    if flag == "偏高":
        return f'<span style="background:{c};color:#fff;padding:2px 7px;border-radius:10px;font-size:11px">{esc(flag)}</span>'
    return f'<span style="background:{c};color:#fff;padding:2px 7px;border-radius:10px;font-size:11px">{esc(flag)}</span>'

def num(v, nd=1):
    try:
        f = float(v)
        return f"{f:.{nd}f}" if f == f else "—"
    except:
        return "—"

rows_html = ""
for r in sorted(final.get("final", []), key=lambda x: (x.get("score_rank") is None, x.get("score_rank") or 99)):
    hl = ' style="background:#fef9e7"' if r.get("band_flag") in ("安全边际", "自身低位") else ""
    rows_html += f"""<tr{hl}>
    <td>{esc(r.get('score_rank'))}</td><td class="l"><b>{esc(r.get('name'))}</b></td>
    <td class="mono">{esc(r.get('code'))}</td>
    <td class="pe">{num(r.get('pe'))}</td><td>{num(r.get('peg'), 2)}</td>
    <td>{num(r.get('exp_g'))}%</td><td>{num(r.get('con_roe'))}%</td>
    <td>{num(r.get('gpm'))}%</td><td>{num(r.get('dy'))}%</td>
    <td>{num(r.get('pb_pct'))}%</td><td>{band_badge(r.get('band_flag'))}</td>
    <td>{esc(r.get('score_total'))}</td></tr>"""

# 回测证据矩阵（有效）
valid_rows = [
    ("LX-core 真实口径", "日频+复权 2021-08~2026-08", "+55.55% / 年化 +9.16% / MDD -19.13% / 超额等权全A +14.4pp", "L2 最强基准，排序信念=PE升序"),
    ("garp 门控 (增速≤60%+PEG≤1)", "日频+复权", "+34.57% / +5.12pp / MDD 18.54% (-3.6pp)", "L2 已采纳：收益+风险双赢，2022熊市少亏6.2pp"),
    ("PB band 规避层 (PB 5y分位>90%剔除)", "日频+复权", "+34.48% (+5.03pp)", "L3 可选保护层，不替代排序"),
    ("q20 混合排序 (80%PE+20%质量)", "日频+复权", "+32.85% (+3.40pp)", "L2 边缘微调：每期换1-6只，可作参考不主排序"),
    ("C-Score 一致预期", "月频", "+30.7% / 超额 +26.2pp", "L1 数据层核心资产"),
    ("F-Score 预期差", "月频", "+12.6%", "L1 财报基线"),
    ("dist52 52周高点近距", "全A裸测", "+12.3pp (8期)", "L3 辅助/规避层：近高点防御、深跌不抄底"),
]

invalid_rows = [
    ("two_bucket (30便宜+10质量)", "-13.16pp", "质量优先排序退化版"),
    ("qadj_pe (PE×质量折扣)", "-4.33pp", "乘法过度放利质量因子"),
    ("garp_q50 (garp池+50%质量排序)", "+2.69pp→变负", "garp池内混合排序稀释收益"),
    ("PEG 升序排序", "-22.55pp", "排序信念=PE升序不可动摇"),
    ("完全放开增速门控", "-3.35pp", "增速≤99% 引入高预期陷阱"),
    ("金融剔除进 LX-core 管线", "-26.1pp", "框架收益~85%来自金融组；剔除只用于展示层"),
    ("GBM 量价 (全A PIT)", "-40.6pp (mv≥100亿)", "IC≠alpha，90%+是小市值暴露"),
    ("Growth Loop 纯增速", "-14.0% / MDD -56.6%", "追高接盘循环"),
    ("质量优先排序 (ROE/毛利降序)", "-12.2% vs 便宜优先", "价值完胜质量"),
    ("IRR 门控 / BSADF 叠加", "无效", "门控类改造无增量"),
    ("yoy_drop 下修清仓", "MDD -66.3%", "清仓接刀循环"),
    ("深跌抄底 (距52周高点远)", "-36.9pp", "接飞刀，两个极端价格行为都不能反向交易"),
    ("12月动量/反转排序", "-18.8pp / -20.8pp", "纯价格外推无alpha"),
    ("筹码合成行业层配置", "行业层Q1-Q5 -3.97pp/月", "个股层集中=锁仓(好)，行业层=拥挤(坏)"),
]

# garp 8 变体表
g_variants = [
    ("core_finex 基线 (增速≤25%+PEG≤2)", "29.45", "5.26", "22.12", "—", "旧L5"),
    ("g40 (增速≤40%+PEG≤2)", "34.43", "6.05", "22.04", "+4.98pp", "备选"),
    ("g60 (增速≤60%+PEG≤2)", "28.33", "5.07", "22.49", "-1.12pp", "PEG≤2时放松增速有害"),
    ("g99 (≈不限增速)", "26.10", "4.71", "23.23", "-3.35pp", "完全放开=高预期陷阱"),
    ("garp (增速≤60%+PEG≤1)", "34.57", "6.07", "18.54", "+5.12pp", "✅ 采纳：双赢"),
    ("peg_sort (PEG升序)", "6.90", "1.33", "14.89", "-22.55pp", "排序信念不可动摇"),
    ("garp_q20 (garp池+80%PE20%质量)", "32.14", "5.69", "18.01", "+2.69pp", "池内混合排序稀释收益"),
    ("garp_q50 (garp池+50%质量)", "23.84", "4.33", "14.74", "-5.61pp", "质量权重过高"),
]

# qrelax 6 变体表
q_variants = [
    ("纯PE升序 (基线)", "29.45", "22.12", "—", "当前方案"),
    ("q20 (80%PE+20%质量)", "32.85", "22.03", "+3.40pp", "✅ 最优增量"),
    ("q40 (60%PE+40%质量)", "30.30", "20.42", "+0.84pp", "⚠️ 收益微增"),
    ("q50 (50%PE+50%质量)", "30.53", "19.05", "+1.08pp", "⚠️ 最佳风险控制"),
    ("two_bucket (30便宜+10质量)", "16.29", "23.42", "-13.16pp", "❌ 灾难"),
    ("qadj_pe (PE×质量折扣)", "25.13", "21.64", "-4.33pp", "❌ 负贡献"),
]

# 分年度稳健性
yearly = [
    ("2021", "+3.7%", "+3.3%", "-0.4pp", "煤炭大牛年：garp 不押风格"),
    ("2022", "-6.3%", "-0.1%", "+6.2pp", "熊市少亏 6.2pp = 主要超额来源"),
    ("2023", "-4.2%", "-2.4%", "+1.8pp", "震荡市仍占优"),
    ("2024", "+18.8%", "+13.9%", "-4.9pp", "牛市略输：高增长股回撤后反弹"),
    ("2025", "+17.7%", "+17.9%", "+0.2pp", "持平"),
    ("2026至今", "-2.1%", "-1.7%", "+0.4pp", "持平"),
]

# 漏斗图数字
n_pit = stats.get("univ", 0) + stats.get("fin_removed", 0)
n_fin = stats.get("fin_removed", 0)
n_core = stats.get("core_pass", 0)
n_gm = stats.get("gm_pass", 0)

funnel_svg = f"""<svg viewBox="0 0 680 320" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;font-family:'Segoe UI',Microsoft YaHei,sans-serif">
  <defs>
    <linearGradient id="fun1" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#1f6feb"/><stop offset="1" stop-color="#388bfd"/>
    </linearGradient>
    <linearGradient id="fun2" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2da44e"/><stop offset="1" stop-color="#4ac26b"/>
    </linearGradient>
    <linearGradient id="fun3" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#d29922"/><stop offset="1" stop-color="#e3b341"/>
    </linearGradient>
  </defs>
  <!-- 漏斗梯形 每级 -70 宽度 -->
  <polygon points="40,10 640,10 590,64 90,64" fill="url(#fun1)" opacity="0.9"/>
  <text x="340" y="30" text-anchor="middle" fill="#fff" font-size="15" font-weight="700">万得全A PIT 成分 {n_pit:,} 只</text>
  <text x="340" y="50" text-anchor="middle" fill="#e6edf7" font-size="11">基准池 · PIT 无幸存者偏差 · 消除 ~53pp 虚高</text>

  <polygon points="90,64 590,64 548,118 132,118" fill="url(#fun2)" opacity="0.85"/>
  <text x="340" y="84" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">剔除金融 (银行/非银) -{n_fin:,} 只</text>
  <text x="340" y="102" text-anchor="middle" fill="#e9f6ec" font-size="11">仅展示层铁律 · 不进回测管线（回测证明金融剔除为负贡献）</text>

  <polygon points="132,118 548,118 500,172 180,172" fill="url(#fun3)" opacity="0.9"/>
  <text x="340" y="137" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">市值≥100亿 + PE&gt;0 + L4 + L5-garp</text>
  <text x="340" y="155" text-anchor="middle" fill="#fdf3dc" font-size="11">PE≤25或股息率≥2% · 增速≤60%且0&lt;PEG≤1 → core 通过 {n_core:,} 只</text>

  <polygon points="180,172 500,172 440,224 240,224" fill="#8250df" opacity="0.92"/>
  <text x="340" y="190" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">gm 质量层 {n_gm} 只（毛利率≥市场中位 {stats.get("gpm_median",0):.1f}%）</text>
  <text x="340" y="208" text-anchor="middle" fill="#f0e9fb" font-size="11">质量标记层 · 回测中收益持平、MDD 砍半</text>

  <polygon points="240,224 440,224 400,278 280,278" fill="#bf3989" opacity="0.92"/>
  <text x="340" y="243" text-anchor="middle" fill="#fff" font-size="13" font-weight="700">评分 Top40 + Band 规避层</text>
  <text x="340" y="261" text-anchor="middle" fill="#fbeef5" font-size="10">评分(价值50%+质量25%+安全25%) · PB 5y分位&gt;90% 剔除 · 等权</text>
  <text x="340" y="300" text-anchor="middle" fill="#566573" font-size="11">排序信念 = PE 升序（回测验证 alpha 来源）| 展示口径 = 评分 top40</text>
</svg>"""

# 时间线
timeline = [
    ("08-21", "三层 Alpha 框架定稿；万得全A PIT 池落地；dist52 行为因子验证"),
    ("08-22", "GBM 量价全A回测证伪：IC≠alpha，90%+ 是小市值暴露"),
    ("08-24", "申万金工因子扫描；筹码合成行业层证伪（个股=锁仓/行业=拥挤）"),
    ("08-25", "回测口径铁律定稿：日频+复权；金融剔除证伪；PB band 规避层验证 +5.03pp"),
    ("08-26", "高质量×低估值买入框架；福耀案例→q20/q50 混合排序实验；紫金案例→garp 门控实验并采纳"),
]

# 风险清单
risks = [
    ("紫金矿业增速预期仍在 58.1% 且 4w 修正 +81% 上调中", "若一致预期增速突破 60%，将滑出 garp 池——高增长+高预期的固有风险"),
    ("garp 门控副作用：格力/海尔/TCL智家等 PEG∈(1,2] 白马被踢", "名单从纯低估值白马转向低估值+成长匹配；白名单层可主观保留但回测为拖累项"),
    ("HF 因子数据污染边界 (2026-08-20 起 juzi 落库异常)", "刷新前必须探测健康日，08-19 为当前已知健康日"),
    ("名单有效期 = 数据快照 2026-08-24", "下次刷新需重跑 fetch→screen→score→band→apply 全管线"),
    ("评分口径 (展示) vs PE升序 (回测信念) 双轨", "回测验证的是 PE 升序；当前名单按评分展示，二者须区分，不可混用结论"),
]

# HTML 组装
html_doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ai_fund_framework 全景总结 · 2026-08-26</title>
<style>
:root {{ --red:#c62828; --green:#1e8449; --blue:#1f6feb; --gray:#566573; --bg:#fafbfc; }}
* {{ box-sizing:border-box; }}
body {{ font-family:'Segoe UI','Microsoft YaHei',sans-serif; margin:0; background:var(--bg); color:#222; line-height:1.6; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:28px 20px 60px; }}
.hero {{ background:linear-gradient(135deg,#0d1b2a 0%,#1b3a5c 60%,#1f6feb 100%); color:#fff; border-radius:16px; padding:32px 36px; margin-bottom:24px; }}
.hero h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:.5px; }}
.hero .sub {{ opacity:.85; font-size:14px; }}
.hero .tag {{ display:inline-block; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.28); padding:3px 12px; border-radius:14px; font-size:12px; margin:10px 6px 0 0; }}
.eq {{ margin:18px 0 6px; background:rgba(255,255,255,.1); border-radius:10px; padding:12px 16px; font-family:Consolas,monospace; font-size:15px; text-align:center; letter-spacing:1px; }}
h2 {{ font-size:19px; margin:34px 0 12px; padding-left:12px; border-left:4px solid var(--blue); }}
h3 {{ font-size:15px; color:#333; margin:18px 0 8px; }}
.card-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:14px 0; }}
.card {{ background:#fff; border:1px solid #e3e8ee; border-radius:12px; padding:14px 16px; }}
.card .k {{ font-size:12px; color:#667; }}
.card .v {{ font-size:22px; font-weight:700; margin-top:2px; }}
.card .d {{ font-size:11px; color:#889; margin-top:4px; }}
.good {{ color:var(--green); }} .bad {{ color:var(--red); }} .warn {{ color:#b9770e; }}
table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:13px; background:#fff; }}
th,td {{ border:1px solid #e3e8ee; padding:7px 9px; text-align:center; }}
th {{ background:#f0f4f8; font-weight:600; color:#334; }}
td.l {{ text-align:left; }} td.mono {{ font-family:Consolas,monospace; font-size:12px; }}
tr:nth-child(even) td {{ background:#fafcfe; }}
td.pe {{ font-weight:700; color:var(--red); }}
.verdict {{ background:#eafaf1; border:1px solid #c8e6d0; border-radius:10px; padding:12px 16px; margin:10px 0; }}
.verdict.reject {{ background:#fdecea; border-color:#f5c6c0; }}
.note {{ background:#f8f9fa; border-left:4px solid #999; padding:10px 14px; font-size:12px; color:#555; margin:12px 0; }}
.two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:800px) {{ .two-col {{ grid-template-columns:1fr; }} }}
.legend {{ font-size:12px; color:#667; margin-top:6px; }}
.tl {{ position:relative; margin:16px 0 8px 8px; padding-left:24px; }}
.tl::before {{ content:''; position:absolute; left:6px; top:4px; bottom:4px; width:2px; background:#d0d7de; }}
.tl .it {{ position:relative; padding:8px 0 8px 8px; border-bottom:1px dashed #e6eaef; }}
.tl .it::before {{ content:''; position:absolute; left:-24px; top:13px; width:10px; height:10px; border-radius:50%; background:var(--blue); }}
.tl .it .d {{ font-family:Consolas,monospace; font-size:12px; color:var(--blue); font-weight:700; }}
.footer {{ margin-top:36px; color:#889; font-size:12px; text-align:center; border-top:1px solid #e3e8ee; padding-top:14px; }}
.chip {{ display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:600; }}
.chip.ok {{ background:#eafaf1; color:#1e8449; }} .chip.no {{ background:#fdecea; color:#c62828; }}
.chip.warn {{ background:#fef9e7; color:#b9770e; }}
</style></head><body><div class="wrap">

<!-- HERO -->
<div class="hero">
  <h1>ai_fund_framework · 全景总结</h1>
  <div class="sub">A股量化投研框架 — 数据基础设施 × 诚实回测方法论 × 已验证策略资产 &nbsp;|&nbsp; 版本 2026-08-26（garp 门控已采纳）</div>
  <span class="tag">三层 Alpha 记账</span><span class="tag">万得全A PIT 基准池</span><span class="tag">日频+复权口径</span><span class="tag">garp 门控 L5</span><span class="tag">PB band 规避层</span>
  <div class="eq">A股投资收益 = 基准(池子) + 数据端(因子) + 方法论 + 卖出时点</div>
</div>

<!-- 1. 核心资产卡 -->
<h2>① 框架核心资产（一句话版）</h2>
<div class="card-grid">
  <div class="card"><div class="k">最强方法论基准</div><div class="v good">LX-core</div><div class="d">+55.55% / 超额+14.4pp / MDD -19.13%（日频+复权真实口径）</div></div>
  <div class="card"><div class="k">已采纳门控升级</div><div class="v" style="color:#8250df">garp L5</div><div class="d">增速≤60% + 0&lt;PEG≤1 → +5.12pp / MDD -3.6pp 双赢</div></div>
  <div class="card"><div class="k">排序信念</div><div class="v" style="color:var(--red)">PE 升序</div><div class="d">便宜优先完胜质量优先（72pp 差距）；所有替换排序均跑输</div></div>
  <div class="card"><div class="k">保护层</div><div class="v" style="color:#2da44e">PB band</div><div class="d">PB 5y分位&gt;90% 剔除 +5.03pp；毛利率≥市场中位 = 回撤保护</div></div>
  <div class="card"><div class="k">数据层核心</div><div class="v" style="color:#1f6feb">C-Score</div><div class="d">一致预期 PIT +30.7% / 超额 +26.2pp；否决&gt;打分</div></div>
  <div class="card"><div class="k">诚实回测</div><div class="v">铁律 ×5</div><div class="d">PIT池 / 日频+复权 / 半年调仓等权基准 / IC≠alpha / 先对比再下结论</div></div>
</div>

<!-- 2. 三层结构 -->
<h2>② 三层 Alpha 目标结构</h2>
<table>
<tr><th style="width:15%">层</th><th style="width:25%">来源</th><th>当前有效资产（已验证）</th><th style="width:22%">Benchmark / 协议</th></tr>
<tr><td><b style="color:#1f6feb">L1 数据层</b></td><td>接入什么数据，决定 alpha 天花板</td><td>万得全A PIT 池（消除 ~53pp 幸存者偏差）· 一致预期 PIT（+26.2pp）· 腾讯行情基础设施</td><td>同方法论下基线数据源 vs 新数据源</td></tr>
<tr><td><b style="color:#8250df">L2 方法论层</b></td><td>怎么决策，决定 alpha 能否稳定提取</td><td>刘旭式框架（+14.4pp）· <b>garp 门控（+5.12pp，2026-08-26 采纳）</b> · q20 混合排序（+3.40pp，参考）· F-Score 基线（+12.6%）</td><td>F-Score 基线 / EW-全A / LX-core</td></tr>
<tr><td><b style="color:#bf3989">L3 数量信号层</b></td><td>什么时候买卖，决定 alpha 兑现率</td><td>估值卖出（+11pp）· PB band 规避（+5.03pp）· dist52 近高点（+12.3pp，规避向）· ZHF 否决制（纪律价值）</td><td>无信号基线 vs 加信号组合</td></tr>
</table>
<div class="note">铁律：每笔 alpha 只能记一层；无效实验同样记账（防踩坑）；卖出>买入（A股）。</div>

<!-- 3. 漏斗 -->
<h2>③ 选股漏斗最终形态（garp 版 · 2026-08-24 快照）</h2>
{funnel_svg}
<div class="legend">当前快照：PIT {n_pit:,} → 剔金融 → 市值/L4/L5-garp 硬门槛 → core {n_core:,} 只 → gm 质量层 {n_gm} 只 → 评分 top40 + band 规避 → 最终名单。garp 门控使池子从旧 L5 的 226 只收窄到 182 只（PEG≤1 严于 PEG≤2，踢掉 PEG∈(1,2] 的低增速股）。</div>

<!-- 4. 证据矩阵 -->
<h2>④ 回测证据矩阵（2026-08 系列，日频+复权口径）</h2>
<div class="two-col">
<div>
<h3>✅ 已验证有效</h3>
<table>
<tr><th>资产/信号</th><th>结果</th><th>归因/备注</th></tr>
{"".join(f'<tr><td class="l"><b>{a}</b></td><td><b class="good">{b}</b></td><td class="l">{c}</td></tr>' for a,b,c,d in valid_rows)}
</table>
</div>
<div>
<h3>❌ 已验证无效（无效清单）</h3>
<table>
<tr><th>尝试</th><th>结果</th><th>教训</th></tr>
{"".join(f'<tr><td class="l"><b>{a}</b></td><td><b class="bad">{b}</b></td><td class="l">{c}</td></tr>' for a,b,c in invalid_rows)}
</table>
</div>
</div>

<!-- 5. garp 实验细节 -->
<h2>⑤ garp 门控采纳证据（今日核心裁决）</h2>
<div class="verdict"><b>裁决：L5 从「增速≤25% + PEG≤2」升级为「增速≤60% + 0&lt;PEG≤1」。</b>机制 = 增速可以高，但估值必须匹配（PEG≤1 严格补偿）。已落地到 <span class="mono">_lx_now_screen.py</span>，全管线重跑生效。</div>
<h3>8 变体回测（2021-08 ~ 2026-08，日频+复权）</h3>
<table>
<tr><th>变体</th><th>总收益</th><th>年化</th><th>MDD</th><th>vs 基线</th><th>判定</th></tr>
{"".join(f'<tr>{"<td class=\"l\"><b>" + a + "</b></td>" if "garp (" in a else "<td class=\"l\">" + a + "</td>"}<td class="pe">{b}%</td><td>{c}%</td><td>{d}%</td><td><b class="{'good' if '+' in e else 'bad'}">{e}</b></td><td class="l">{f}</td></tr>' for a,b,c,d,e,f in g_variants)}
</table>
<h3>分年度稳健性：超额来自风控而非风格押注</h3>
<table>
<tr><th>年度</th><th>基线 core_finex</th><th>garp</th><th>差值</th><th>解读</th></tr>
{"".join(f'<tr><td>{a}</td><td>{b}</td><td>{c}</td><td><b class="{"good" if d.startswith("+") else "bad"}">{d}</b></td><td class="l">{e}</td></tr>' for a,b,c,d,e in yearly)}
</table>

<!-- 6. 案例裁决 -->
<h2>⑥ 今日两大案例裁决（驱动实验的缘起）</h2>
<div class="two-col">
<div class="verdict reject">
<b>福耀玻璃（600660.SH）→ 不救。</b><br>
PE 17.4 排 132/226，中PE中质量（gpm 38% 在池内不算拔尖，吉比特 94%/周大生 82% 都在前面），质量分 65。q20 下 blend 46.7 排 128/226，q50 下 53.8 排 100/226——<b>两种混合都救不回</b>；garp 采纳后 PEG 1.3 &gt; 1 被直接踢出池。<br><span class="chip no">判定</span> 排序问题是框架诚实暴露，不为单票开后门。
</div>
<div class="verdict">
<b>紫金矿业（601899.SH）→ 门控误杀，garp 拯救类别。</b><br>
PE 13.6 / ROE 32.9% 顶级 / gpm 31.1% 全过，唯独一致预期增速 58% 撞旧 L5 上限被剔除。<b>它不贵，是门控冤枉了它</b>。garp 采纳后进池（rank 47/182），评分口径下入选最终名单。<br><span class="chip ok">判定</span> 修正的是「增速门控误杀」整个类别（煤炭/航运/有色高增长龙头回池），不是为单票开白名单。
</div>
</div>
<div class="note">⚠️ 副作用：格力/海尔/TCL智家等 PEG∈(1,2] 的低增速白马被 garp 踢出池（格力 PEG 1.64、海尔 1.69）——名单从「纯低估值白马」转向「低估值+成长匹配」。若对这些白马有执念只能走白名单主观层，回测说它们在框架内是拖累项。</div>

<!-- 7. 当前名单 -->
<h2>⑦ 当前推荐名单（{as_of} · 评分 top40 + band 规避 · 等权）</h2>
<table>
<tr><th>评分排名</th><th>名称</th><th>代码</th><th>PE</th><th>PEG</th><th>增速%</th><th>ROE%</th><th>毛利率%</th><th>股息率%</th><th>PB分位%</th><th>Band</th><th>总分</th></tr>
{rows_html}
</table>
<div class="legend">绿色底 = 安全边际/自身低位标记；PB分位 &gt; 90% 会被 band 规避层剔除；本批 40 只无命中规避层。紫金矿业（评分口径入选）、宇通客车（PB 87% 偏高警示）等均在列。</div>

<!-- 8. 方法论铁律 -->
<h2>⑧ 诚实回测方法论铁律</h2>
<table>
<tr><th style="width:6%">#</th><th style="width:30%">铁律</th><th>原因 / 反例</th></tr>
<tr><td>1</td><td class="l"><b>池子一律用万得全A (881001.WI) PIT 成分</b></td><td class="l">禁止手工精选股票池；幸存者偏差 ~53pp（龙头池 +455% vs 全A等权 +52.9% 是已知赢家 artifact）</td></tr>
<tr><td>2</td><td class="l"><b>收益统计一律日频颗粒度 + 复权价</b></td><td class="l">月频 T+1 月末撮合多持旧仓 1 个月 → 虚高；未复权 close 缺分红 → 高分红金融股被低估 +30~38pp。旧月频/未复权数字一律视为旧口径</td></tr>
<tr><td>3</td><td class="l"><b>策略半年调仓 → 基准用半年调仓等权全A</b></td><td class="l">每日再平衡基准含 +93.5% 再平衡收益会严重高估基准；市值加权基准用中证全指 000985.SH 替代</td></tr>
<tr><td>4</td><td class="l"><b>IC ≠ alpha</b></td><td class="l">GBM IC 0.114 全库第一但超额 -40.6pp（小市值暴露）；筹码成本 IC 0.038 被极端值污染，多空实际 -1.6%</td></tr>
<tr><td>5</td><td class="l"><b>先与等权池子对比再下结论</b></td><td class="l">高收益可能是池子 beta / 幸存者偏差 / 风格周期；任何改进必须对照 EW-全A 与自身 v0</td></tr>
</table>

<!-- 9. 数据基础设施 -->
<h2>⑨ 数据基础设施</h2>
<div class="card-grid">
  <div class="card"><div class="k">全市场宽表</div><div class="v" style="font-size:16px">data/a_share_market.db</div><div class="d">SQLite 56MB · PIT成分/月K/估值/因子/一致预期 · 回测一律从库读</div></div>
  <div class="card"><div class="k">juzi-mcp</div><div class="v" style="font-size:16px;color:#1f6feb">179 工具</div><div class="d">万得全A PIT 成分 · 一致预期 · 日频估值面板 · HF因子（注意健康日探测）</div></div>
  <div class="card"><div class="k">申万金工 MCP</div><div class="v" style="font-size:16px;color:#1f6feb">因子扫描</div><div class="d">月频 Spearman IC / 分位收益 · 成长/筹码/行业轮动三类因子</div></div>
  <div class="card"><div class="k">腾讯行情</div><div class="v" style="font-size:16px;color:#2da44e">日K/月K/名称</div><div class="d">qt.gtimg.cn 线程池 5500+ 只 5-8 分钟 · 复权折算 OHLC</div></div>
</div>

<!-- 10. 风险与待办 -->
<h2>⑩ 风险与待办</h2>
<table>
<tr><th style="width:34%">风险/待办</th><th>说明</th></tr>
{"".join(f'<tr><td class="l"><b>{a}</b></td><td class="l">{b}</td></tr>' for a,b in risks)}
</table>

<!-- 11. 时间线 -->
<h2>⑪ 框架演进时间线（2026-08）</h2>
<div class="tl">
{"".join(f'<div class="it"><span class="d">{a}</span> &nbsp;{b}</div>' for a,b in timeline)}
</div>

<div class="footer">ai_fund_framework · 全景总结 v2026-08-26 · 数据截至 {as_of} · 回测口径 = 日频 + 复权 + 万得全A PIT 等权基准</div>
</div></body></html>"""

out = BASE + "_ai_fund_framework_summary.html"
open(out, "w", encoding="utf-8").write(html_doc)
print(f"OK -> {out}  ({len(html_doc)//1024} KB)")
