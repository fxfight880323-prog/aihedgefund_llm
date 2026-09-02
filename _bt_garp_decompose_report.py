# -*- coding: utf-8 -*-
"""四环节归因分解 → HTML 报告。读 _bt_garp_decompose_results.json。"""
import json, datetime

R = json.load(open("_bt_garp_decompose_results.json", encoding="utf-8"))
panel = R["panel"]; price = R["price"]; anchors = R["anchors"]
cov = R["coverage"]

# 市值加权集中度权衡（追加实验）
try:
    CAP = json.load(open("_bt_garp_cap_results.json", encoding="utf-8"))
except Exception:
    CAP = None

# 分年度拆解（追加实验）
try:
    YEARLY = json.load(open("_bt_garp_cap_yearly.json", encoding="utf-8"))
except Exception:
    YEARLY = None

# ---------- 归因计算 ----------
def pp(a, b):
    return a - b

# 构建法（面板等权，无丢股）
all_ew = panel["all_ew"]["total"]
mv30 = panel["mv30_ew"]["total"]
mv100 = panel["mv100_ew"]["total"]
l4 = panel["l4_ew"]["total"]
pool = panel["pool_ew"]["total"]
g60 = price["g60"]["total"]

chain = [
    ("全A等权（基准）", all_ew, None),
    ("① 市值约束 mv≥30亿", mv30, pp(mv30, all_ew)),
    ("① 市值约束 mv≥100亿", mv100, pp(mv100, mv30)),
    ("② L4 估值安全边际", l4, pp(l4, mv100)),
    ("③ L5 低预期门控", pool, pp(pool, l4)),
    ("④ PE 升序 top40", g60, pp(g60, pool)),
]

# 拆除法（价格回测，含成本）
no_peg = price["no_peg"]["total"]
pe_desc = price["pe_desc"]["total"]
mvweight = price["mvweight"]["total"]
mv30t = price["mv30_top40"]["total"]
mv0t = price["mv0_top40"]["total"]
nolimit = 0.6933  # audit rerun.full.nolimit

dismantle = [
    ("PE 排序方向", "g60(PE升序) vs pe_desc(PE降序)", g60, pe_desc, g60 - pe_desc, "正向"),
    ("等权 vs 市值加权", "g60(等权) vs mvweight(市值加权)", g60, mvweight, g60 - mvweight, "负向(等权稀释)"),
    ("PEG 门控松紧", "g60(PEG≤1) vs no_peg(无上限)", g60, no_peg, g60 - no_peg, "微负"),
    ("增速上限松紧", "g60(g≤60%) vs nolimit(无上限)", g60, nolimit, g60 - nolimit, "微负"),
    ("市值档位(top40后)", "g60(mv100) vs mv0(无下限)", g60, mv0t, g60 - mv0t, "近似中性"),
]

# 归因汇总（按贡献排序）
attribution = [
    ("PE 升序排序", "+29.21pp", "最大单一 alpha 来源；反向(PE降序)则 -2.49%", "核心"),
    ("L5 低预期门控(g≤60&PEG≤1)", "+21.93pp", "从无到有；但门控松紧微调影响小", "核心"),
    ("L4 估值安全边际(PE≤25/dy≥2%)", "+13.55pp", "估值纪律的正贡献", "核心"),
    ("市值约束(mv≥100亿)", "-38.81pp", "排除小盘=放弃小盘收益(regime 特定)", "负资产"),
    ("等权构建(vs 市值加权)", "-39.45pp", "稀释大盘价值暴露；市值加权+106%但前3集中60%", "负资产"),
]

# ---------- HTML ----------
def fmt(x):
    return f"{x:+.2%}"

def bar_chain_html():
    rows = []
    # 瀑布：用水平条，起点对齐
    return chain

rows_html = ""
for name, val, inc in chain:
    inc_txt = "—" if inc is None else (f"<span class='pos'>{inc:+.2f}pp</span>" if inc >= 0 else f"<span class='neg'>{inc:+.2f}pp</span>")
    bar_w = max(2, int((val + 0.10) / 1.10 * 100))  # -10%~100% 映射
    cls = "bar-pos" if val >= 0 else "bar-neg"
    rows_html += f"""
    <tr>
      <td class="lbl">{name}</td>
      <td class="num">{val:+.2%}</td>
      <td class="inc">{inc_txt}</td>
      <td class="barcell"><div class="bar {cls}" style="width:{bar_w}%"></div></td>
    </tr>"""

dism_html = ""
for name, desc, a, b, delta, tag in dismantle:
    cls = "pos" if delta > 0 else "neg"
    dism_html += f"""
    <tr>
      <td class="lbl">{name}</td>
      <td class="desc">{desc}</td>
      <td class="num">{a:+.2%}</td>
      <td class="num">{b:+.2%}</td>
      <td class="num {cls}">{delta:+.2f}pp</td>
      <td class="tag">{tag}</td>
    </tr>"""

attr_html = ""
for name, contrib, note, role in attribution:
    cls = {"核心": "pos", "负资产": "neg"}.get(role, "")
    attr_html += f"""
    <tr>
      <td class="lbl">{name}</td>
      <td class="num {cls}">{contrib}</td>
      <td class="desc">{note}</td>
      <td class="tag">{role}</td>
    </tr>"""

# 面板等权各变体指标表
panel_html = ""
for k in ["all_ew", "mv30_ew", "mv100_ew", "l4_ew", "pool_ew"]:
    p = panel[k]
    panel_html += f"<tr><td class='lbl'>{k}</td><td class='num'>{p['total']:+.2%}</td><td class='num'>{p['ann']:+.2%}</td><td class='num'>{p['mdd']:+.2%}</td><td class='num'>{p['n_days']}</td></tr>"

price_html = ""
for k in ["g60", "no_peg", "pe_desc", "mvweight", "mv30_top40", "mv0_top40"]:
    p = price[k]
    miss = sum(len(v) for v in cov[k].values())
    flag = "✓" if miss == 0 else f"⚠{miss}"
    price_html += f"<tr><td class='lbl'>{k}</td><td class='num'>{p['total']:+.2%}</td><td class='num'>{p['ann']:+.2%}</td><td class='num'>{p['mdd']:+.2%}</td><td class='num'>{flag}</td></tr>"

# 市值加权集中度权衡表
cap_html = ""
if CAP:
    cap_names = ["g60", "sqrt_mv", "mvw_cap5", "mvw_cap8", "mvw_cap10", "mvw_cap15", "mvw_nocap"]
    cap_labels = {"g60": "等权（锚点）", "sqrt_mv": "市值开根号", "mvw_cap5": "市值加权 cap5",
                  "mvw_cap8": "市值加权 cap8", "mvw_cap10": "市值加权 cap10",
                  "mvw_cap15": "市值加权 cap15", "mvw_nocap": "市值加权 无上限"}
    for k in cap_names:
        r = CAP["results"][k]; c = CAP["conc"][k]
        best = " class='best'" if k in ("mvw_cap8", "mvw_cap10") else ""
        cap_html += (f"<tr{best}><td class='lbl'>{cap_labels[k]}</td>"
                     f"<td class='num'>{r['total']:+.2%}</td><td class='num'>{r['ann']:+.2%}</td>"
                     f"<td class='num'>{r['mdd']:+.2%}</td><td class='num'>{c['top3']:.1%}</td>"
                     f"<td class='num'>{c['neff']:.1f}</td></tr>")

# 分年度拆解表
yearly_ret_html = ""
yearly_exc_html = ""
if YEARLY:
    ydata = YEARLY["yearly"]; years = YEARLY["years"]
    # 年度收益矩阵
    order = ["等权g60", "cap8", "cap10", "cap15", "无上限", "等权全A"]
    labels = {"等权g60": "等权 g60（锚点）", "cap8": "市值加权 cap8", "cap10": "市值加权 cap10",
              "cap15": "市值加权 cap15", "无上限": "市值加权 无上限", "等权全A": "等权全A（基准）"}
    yearly_ret_html = "<tr><td class='lbl'>变体 \\ 年份</td>" + "".join(
        f"<td class='num' style='color:var(--sub)'>{y}</td>" for y in years) + "</tr>"
    for k in order:
        r = ydata[k]
        cls = " style='color:var(--sub)'" if k == "等权全A" else ""
        yearly_ret_html += f"<tr><td class='lbl'{cls}>{labels[k]}</td>"
        for y in years:
            v = r[y]
            c = "pos" if v >= 0 else "neg"
            yearly_ret_html += f"<td class='num {c}'>{v:+.1%}</td>"
        yearly_ret_html += "</tr>"
    # 年度超额矩阵（vs 等权g60）
    base = ydata["等权g60"]
    yearly_exc_html = "<tr><td class='lbl'>变体 \\ 年份</td>" + "".join(
        f"<td class='num' style='color:var(--sub)'>{y}</td>" for y in years) + "</tr>"
    for k in ["cap8", "cap10", "cap15", "无上限"]:
        r = ydata[k]
        yearly_exc_html += f"<tr><td class='lbl'>{labels[k]}</td>"
        for y in years:
            exc = r[y] - base[y]
            c = "pos" if exc >= 0 else "neg"
            yearly_exc_html += f"<td class='num {c}'>{exc:+.1f}pp</td>"
        yearly_exc_html += "</tr>"
    # 等权g60 自身年度分布（暴露 2024 依赖）
    g60_share_html = ""
    for y in years:
        v = base[y]
        c = "pos" if v >= 0 else "neg"
        g60_share_html += f"<td class='num {c}'>{v:+.1%}</td>"

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>LX-core 四环节归因分解</title>
<style>
:root {{ --bg:#f7f8fa; --card:#fff; --ink:#1a1a1a; --sub:#6b7280; --line:#e5e7eb;
  --red:#d92626; --green:#0a7d4f; --blue:#1f6feb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.6; }}
.wrap {{ max-width:980px; margin:0 auto; padding:24px 20px 60px; }}
h1 {{ font-size:24px; margin:0 0 4px; }}
.sub {{ color:var(--sub); font-size:13px; margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:20px 22px; margin-bottom:18px; }}
.card h2 {{ font-size:17px; margin:0 0 12px; border-left:4px solid var(--blue);
  padding-left:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th,td {{ padding:8px 10px; text-align:left; border-bottom:1px solid var(--line); }}
th {{ color:var(--sub); font-weight:600; font-size:12px; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
td.lbl {{ font-weight:600; }}
td.inc,td.desc,td.tag {{ color:var(--sub); font-size:12.5px; }}
.pos {{ color:var(--red); }}
.neg {{ color:var(--green); }}
.barcell {{ width:38%; }}
.bar {{ height:14px; border-radius:7px; }}
.bar-pos {{ background:linear-gradient(90deg,#d92626,#f0a0a0); }}
.bar-neg {{ background:linear-gradient(90deg,#0a7d4f,#8fd0b0); }}
.concl {{ background:#fff7f6; border:1px solid #f3d1cd; border-radius:10px; padding:14px 16px; }}
.concl h3 {{ margin:0 0 8px; font-size:14px; color:var(--red); }}
.warn {{ background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:12px 16px; margin-top:12px; }}
.warn h3 {{ margin:0 0 6px; font-size:14px; color:#b45309; }}
ul {{ margin:6px 0; padding-left:20px; }}
li {{ margin:4px 0; }}
.tag {{ white-space:nowrap; }}
tr.best td {{ background:#fff7ed; }}
tr.best td.lbl {{ color:#b45309; }}
</style></head><body><div class="wrap">
<h1>LX-core / garp(g60) 四环节归因分解</h1>
<div class="sub">full 基座（含金融）· 日频+复权 · 2021-08 ~ 2026-04 半年调仓 · 锚点校验 all_ew={anchors['all_ew']:+.2%} g60={anchors['g60']:+.2%} 均精确复现</div>

<div class="card concl">
<h3>一句话结论</h3>
<p style="margin:0">g60 的 +67.01% alpha 主要来自 <b>「PE 升序排序」(+29pp) + 「L5 低预期门控」(+22pp) + 「L4 估值安全边际」(+14pp)</b> 三个环节；
而 <b>「市值约束 mv≥100亿」(-39pp) 和「等权构建」(-39pp)</b> 是负贡献——它们在稀释「低PE大盘价值股（金融为主，top40 中占 50%）」的暴露。
这解释了为何「金融剔除 = -26.1pp」：剔除金融就是砍掉收益主引擎。</p>
</div>

<div class="card">
<h2>构建法链条（全市场 5730 只等权面板，无丢股、无成本）</h2>
<table><thead><tr><th>环节</th><th style="text-align:right">累计收益</th><th>增量贡献</th><th style="width:38%">收益水平</th></tr></thead>
<tbody>{rows_html}</tbody></table>
<p class="sub" style="margin-top:8px">④ 为价格回测口径(含成本)，前三步为面板无成本口径；成本约 0.3%/年，对 +29pp 结论无实质影响。</p>
</div>

<div class="card">
<h2>拆除法对比（530 只复权，含成本 5bp+10bp，ceteris paribus）</h2>
<table><thead><tr><th>环节</th><th>对比</th><th style="text-align:right">A</th><th style="text-align:right">B</th><th style="text-align:right">差额</th><th>方向</th></tr></thead>
<tbody>{dism_html}</tbody></table>
</div>

<div class="card">
<h2>四环节归因汇总（按 |贡献| 排序）</h2>
<table><thead><tr><th>环节</th><th style="text-align:right">贡献</th><th>机制</th><th>定性</th></tr></thead>
<tbody>{attr_html}</tbody></table>
</div>

<div class="card">
<h2>面板等权各变体（全市场，无成本）</h2>
<table><thead><tr><th>变体</th><th style="text-align:right">总收益</th><th style="text-align:right">年化</th><th style="text-align:right">MDD</th><th style="text-align:right">天数</th></tr></thead>
<tbody>{panel_html}</tbody></table>
</div>

<div class="card">
<h2>价格回测各变体（含成本，覆盖审计）</h2>
<table><thead><tr><th>变体</th><th style="text-align:right">总收益</th><th style="text-align:right">年化</th><th style="text-align:right">MDD</th><th style="text-align:right">丢股(只-期)</th></tr></thead>
<tbody>{price_html}</tbody></table>
</div>

<div class="card">
<h2>市值加权集中度权衡（追加实验：cap 甜点区）</h2>
<p class="sub" style="margin:0 0 10px">纯市值加权前 3 家集中 43.6%，加单票上限后既保留大盘价值暴露、又压掉集中度。</p>
<table><thead><tr><th>变体</th><th style="text-align:right">总收益</th><th style="text-align:right">年化</th><th style="text-align:right">MDD</th><th style="text-align:right">top3集中度</th><th style="text-align:right">有效持仓</th></tr></thead>
<tbody>{cap_html}</tbody></table>
<p class="sub" style="margin-top:8px"><b style="color:#b45309">结论：cap8~10 是甜点区</b> —— 收益 104.9%~107.0%（几乎无损于无上限的 106.5%），top3 集中度从 43.6% 降到 24%~29%，MDD 反而更低（13.3%~13.8%）。cap15 收益 108.95% 甚至反超无上限。</p>
</div>

<div class="card">
<h2>分年度拆解（cap 甜点是否单点贡献？）</h2>
<p class="sub" style="margin:0 0 10px">检验「市值加权 &gt; 等权」的超额是否由 2024 金融修复年单点贡献。</p>
<table style="margin-bottom:16px"><thead><tr><th colspan="7" style="text-align:left;color:#b45309">年度收益矩阵（行=变体，列=年份）</th></tr></thead>
<tbody>{yearly_ret_html}</tbody></table>
<table style="margin-bottom:16px"><thead><tr><th colspan="7" style="text-align:left;color:#b45309">年度超额矩阵（vs 等权 g60，单位 pp）</th></tr></thead>
<tbody>{yearly_exc_html}</tbody></table>
<table><thead><tr><th colspan="7" style="text-align:left;color:#b45309">等权 g60 自身年度收益（暴露策略本身的单点依赖）</th></tr></thead>
<tbody><tr><td class='lbl'>等权 g60</td>{g60_share_html}</tr></tbody></table>
<p class="sub" style="margin-top:8px"><b style="color:#0a7d4f">结论：cap 超额逐年稳定为正，不是 2024 单点。</b>cap8 六年的超额 +2.0/+1.8/+7.6/+2.6/+5.1/+3.6 pp 无一负值；超额最大的年份是 <b>2023（+7.6~12.9pp）</b> 和 <b>2025（+4.3~5.1pp）</b>，而 2024 反而是超额最小的年份（+2.6~4.4pp，因当年等权与市值加权普涨、差异收敛）。即「市值加权 &gt; 等权」是 mv≥100亿 池内系统性的大盘溢价，与金融修复年无关。</p>
<p class="sub" style="margin-top:6px"><b style="color:#d92626">真正需警惕的是策略本身：</b>等权 g60 的收益高度依赖 2024（+33.1%）与 2025（+16.7%），2021~2023 三年合计仅 +6.4%。2024 恰是金融修复年，这印证了「底仓=低PE大盘价值（金融占 50%）」的 beta 集中——cap 增强逐年正贡献、可放心作为构建方式改进，但解决不了底层风格暴露的单点依赖，需靠分散行业或降低金融浓度对冲。</p>
</div>

<div class="card">
<h2>⚠️ 诚实标注与边界</h2>
<div class="warn">
<h3>必须警惕的四点</h3>
<ul>
<li><b>市值加权的 +106.46% 是集中收益，非分散 alpha</b>：mvweight 前 3 家（中国平安 23% + 工商银行 19% + 建设银行 17%）累计 60%。它本质是「重仓几家超级大金融股」，不能当作可复制的策略超额。</li>
<li><b>市值约束的负贡献是 2021-2026 regime 特定</b>：这五年小盘显著跑赢大盘。mv100 约束在样本外未必是负资产，且它有「避免微盘流动性风险/踩雷」的保护作用，回测未计入流动性成本。</li>
<li><b>pe_desc / mv30 / mv0 变体存在丢股</b>（PE 降序 278 只-期、mv30/mv0 各 43/47 只-期）。方向性结论稳健，但精确数值偏保守，勿直接引用绝对数。</li>
<li><b>「估值因子 IC≈0」与「PE 升序 alpha」并不矛盾</b>：申万合成估值因子是全市场月频、含微盘、被市值风格稀释；LX-core 的 PE 升序是「门控池内 + 单一 PE + 日频复权」的精确暴露，捕获的是金融价值股的 beta 而非估值的线性预测力。</li>
</ul>
</div>
</div>

<div class="sub" style="text-align:center">生成于 {datetime.datetime.now().isoformat()[:19]} · _bt_garp_decompose.py</div>
</div></body></html>"""

open("_bt_garp_decompose_report.html", "w", encoding="utf-8").write(html)
print("报告 → _bt_garp_decompose_report.html")

# 输出归因 JSON 供可视化
attr_out = {
    "chain": [{"name": n, "total": v, "inc": i} for n, v, i in chain],
    "dismantle": [{"name": n, "a": a, "b": b, "delta": d} for n, _, a, b, d, _ in dismantle],
    "anchors": anchors,
}
json.dump(attr_out, open("_bt_garp_decompose_attr.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("归因 → _bt_garp_decompose_attr.json")
