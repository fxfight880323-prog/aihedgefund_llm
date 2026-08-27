# -*- coding: utf-8 -*-
"""
Type D 诊断报告生成器：garp 系列回测合规审计
依据 docs/prompt_template_fund_framework.md v1.0（10 铁律 + ⑤ 自查清单）
读 _bt_garp_audit_results.json → _bt_garp_audit_report.html
"""
import json
import datetime

AU = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))

# ---------- 数据整理 ----------
meta = AU["meta"]
bm = AU["benchmarks"]
rerun = AU["rerun"]
anchors = AU["anchors"]
old_ceiling = AU["old_ceiling_results"]   # 旧增速上限实验（PEG≤1 系，丢股 bug 口径）
old_adopt = AU["old_adopt_results"]       # 旧采纳实验（PEG≤2 系 + 排序系，丢股 bug 口径）
bucket = AU["bucket_stats"]
intrusions = AU["intrusions"]
displaced = AU["displaced"]

FIN, FULL = rerun["finex"], rerun["full"]

# 变体显示顺序：PEG≤2 系 / PEG≤1 剂量系 / 排序混合系
ORDER = ["core", "g40p2", "g60p2", "g99",
         "g30", "g40", "g60", "g80", "g100", "g150", "nolimit",
         "peg_sort", "garp_q20", "garp_q50"]
GROUP = {"core": "基准", "g40p2": "PEG≤2 系", "g60p2": "PEG≤2 系", "g99": "PEG≤2 系",
         "g30": "PEG≤1 剂量系", "g40": "PEG≤1 剂量系", "g60": "PEG≤1 剂量系",
         "g80": "PEG≤1 剂量系", "g100": "PEG≤1 剂量系", "g150": "PEG≤1 剂量系",
         "nolimit": "PEG≤1 剂量系", "peg_sort": "排序系", "garp_q20": "排序系", "garp_q50": "排序系"}
DESC = {"core": "LX-core 基准（增速≤25% + PEG≤2）",
        "g40p2": "增速≤40% + PEG≤2", "g60p2": "增速≤60% + PEG≤2", "g99": "增速≤99% + PEG≤2",
        "g30": "增速≤30% + PEG≤1", "g40": "增速≤40% + PEG≤1", "g60": "增速≤60% + PEG≤1（=已采纳 garp 门控）",
        "g80": "增速≤80% + PEG≤1", "g100": "增速≤100% + PEG≤1", "g150": "增速≤150% + PEG≤1",
        "nolimit": "无增速上限 + PEG≤1",
        "peg_sort": "PEG 升序排序（替代 PE 排序）", "garp_q20": "0.8×PE + 0.2×质量", "garp_q50": "0.5×PE + 0.5×质量"}
# 旧实验数字映射：新变体名 → 旧实验变体名
OLD_MAP = {"g40p2": ("old_adopt", "g40"), "g60p2": ("old_adopt", "g60"), "g99": ("old_adopt", "g99"),
           "peg_sort": ("old_adopt", "peg_sort"), "garp_q20": ("old_adopt", "garp_q20"), "garp_q50": ("old_adopt", "garp_q50"),
           "g30": ("old_ceiling", "g30"), "g40": ("old_ceiling", "g40"), "g60": ("old_ceiling", "g60"),
           "g80": ("old_ceiling", "g80"), "g100": ("old_ceiling", "g100"), "g150": ("old_ceiling", "g150"),
           "nolimit": ("old_ceiling", "nolimit")}

EW_T = bm["ew_hold"]["total"]; IDX_T = bm["csi_all"]["total"]

def pct(x, nd=1, sign=False):
    if x is None: return "—"
    s = f"{x*100:+.{nd}f}" if sign else f"{x*100:.{nd}f}"
    return s + "%"

def cls(x, invert=False):
    """中式涨跌配色：正=红 负=绿"""
    if x is None: return ""
    good = x > 0 if not invert else x < 0
    if abs(x) < 1e-9: return ""
    return "pos" if good else "neg"

# ---------- 检查点表 ----------
checks = [
    ("铁律1", "真实数据，禁编造", "PASS", "PASS", "juzi 真实日K 497 只（含补拉 255 只），覆盖 2021-05-06 ~ 2026-08-24；估值/一致预期走 parquet 原始快照"),
    ("铁律2", "池子 = 万得全A PIT 成分", "PASS", "PASS", "10 期 PIT 成分 4441 → 5503 只；禁止手工精选股票池"),
    ("铁律3", "日频颗粒度统计", "PASS", "PASS", "1288 个交易日逐日推进；annual_periods=252"),
    ("铁律4", "复权价一致", "PASS", "PASS", f"抽样 {meta['adj_sample']['n']} 条中 {meta['adj_sample']['ratio_ne1']} 条 adj≠close（100% 存在复权调整）"),
    ("铁律5", "同口径基准", "FAIL", "PASS", f"原报告仅对中证全指；本审计接入双基准：半年调仓等权全A {pct(EW_T)} / 中证全指 {pct(IDX_T)}"),
    ("铁律6", "零未来函数", "PASS", "PASS", "T+1 撮合（N 期下单→N+1 期成交）；因子用 as_of 前一交易日；PIT 成分按调仓月取数"),
    ("铁律7", "IC≠alpha", "PASS", "PASS", "结论全部来自组合层回测；机制验证用前瞻收益（6M/12M）而非横截面 IC"),
    ("铁律8", "先对比等权池子再下结论", "FAIL", "PASS", "全部 28 组回测均附超等权全A 与超中证全指列；旧报告缺等权对比"),
    ("铁律9", "MDD = (peak−trough)/peak 日频全序列", "PASS", "PASS", "全部变体 MDD 由 1270 个日频净值点计算"),
    ("铁律10", "金融剔除只用于展示层，不进回测排序管线", "FAIL", "PASS", "原实验 excl_fin 贯穿全部变体基座；本审计增跑 full 基座（金融持仓每期 15~32 只），finex 仅保留作对照"),
    ("⑤自查", "持仓数量目标 = 实际", "FAIL", "PASS", "原实验丢股 bug：无行情股票被静默跳过变现金（peg_sort 每期丢 15~29 只）；修复后 497 只全覆盖、全部变体持仓均值 40.0"),
    ("锚点", "审计管线与已验证回测同口径", "—", "PASS", f"core/full = {pct(anchors['core_full_total'],2)} ≈ LX-core 历史值 {pct(anchors['lxcore_hist'],2)}；core/finex = {pct(anchors['core_finex_total'],2)} = finex 历史值 {pct(anchors['finex_hist'],2)}（双锚点精确复现）"),
]

# ---------- 违规卡片 ----------
violations = [
    ("V1", "铁律10", "金融剔除贯穿回测管线",
     "原 garp 采纳实验与增速上限实验的全部变体都构建在 excl_fin（剔除 123 只金融股）基座之上，违反『金融剔除只用于展示层』铁律。",
     "增跑 full 基座（全池含金融）× 14 变体，finex 基座保留作对照。金融/期持仓列验证金融股真实进入组合（每期 15~32 只）。",
     f"全池基座系统性抬升全部变体收益（core {pct(FIN['core']['total'])} → {pct(FULL['core']['total'])}），且剂量响应形态改变：finex 断崖陡峭（g40 {pct(FIN['g40']['total'])} vs nolimit {pct(FIN['nolimit']['total'])}），full 变为缓坡（g40 {pct(FULL['g40']['total'])} vs nolimit {pct(FULL['nolimit']['total'])}）——『>100% 断崖』的形态部分是剔除金融的产物。"),
    ("V2", "铁律5 + 8", "缺同口径等权基准",
     "原报告只对中证全指（价格指数，不含分红），未与『半年调仓等权全A』对比，无法区分 alpha 与池子 beta。",
     "接入 _bt_daily_ew_hold.py 产出的同口径基准（期初等权买 PIT 成分持有、权重漂移）。",
     f"等权全A {pct(EW_T)}/MDD {pct(bm['ew_hold']['mdd'])} 显著强于中证全指 {pct(IDX_T)}——只看指数会高估超额。全池最优变体 g30 超等权 {pct(FULL['g30']['excess_ew'],1,True)}pp。"),
    ("V3", "铁律1 + ⑤", "持仓丢股 bug（隐性变现金）",
     "原实验日K 仅覆盖 242 只，选股并集 496 只。引擎对无行情股票静默跳过 → 持仓变现金，且无任何告警。peg_sort 每期丢 15~29 只（丢股率最高），g30/g40 每期丢 1~19 只。",
     "补拉 255 只日K 合并为 _bt_daily_px_full.json（497 只），覆盖断言 cov_after_ok=True；持仓均值全部回到 40.0。",
     "丢股对高增速变体是双向失真：g30/g40 修复后 +11.2pp（丢的是后来上涨的股票），nolimit 修复后 −6.1pp（丢的高增速股下跌，现金化反而虚高）；garp_q50 修复后 +24.3pp、peg_sort +17.9pp——旧实验的相对排序整体失效。"),
]

# ---------- SVG 1: 剂量响应曲线 ----------
dose_x = [("25\n(core)", 25), ("30", 30), ("40", 40), ("60", 60), ("80", 80), ("100", 100), ("150", 150), ("∞", 1e9)]
dose_keys = ["core", "g30", "g40", "g60", "g80", "g100", "g150", "nolimit"]
W1, H1, L, R, T, B = 680, 360, 56, 16, 28, 66
px0, px1 = 60, 648
py0, py1 = 40, 300
ys_min, ys_max = 0, 80
def sx(i): return px0 + (px1 - px0) * i / (len(dose_x) - 1)
def sy(v): return py1 - (py1 - py0) * (v - ys_min) / (ys_max - ys_min)
pts_finex = " ".join(f"{sx(i)},{sy(FIN[k]['total']*100):.1f}" for i, k in enumerate(dose_keys))
pts_full = " ".join(f"{sx(i)},{sy(FULL[k]['total']*100):.1f}" for i, k in enumerate(dose_keys))
grid = "".join(f'<line x1="{px0}" y1="{sy(v):.0f}" x2="{px1}" y2="{sy(v):.0f}" stroke="#e8e8e8" stroke-width="1"/><text x="{px0-8}" y="{sy(v)+4:.0f}" text-anchor="end" font-size="11" fill="#888">{v}%</text>' for v in range(0, 81, 20))
xlabels = "".join(f'<text x="{sx(i)}" y="{py1+18}" text-anchor="middle" font-size="11" fill="#555">{lbl}</text>' for i, (lbl, _) in enumerate(dose_x))
dots_finex = "".join(f'<circle cx="{sx(i)}" cy="{sy(FIN[k]["total"]*100):.1f}" r="3.5" fill="#4a7dbe"/>' for i, k in enumerate(dose_keys))
dots_full = "".join(f'<circle cx="{sx(i)}" cy="{sy(FULL[k]["total"]*100):.1f}" r="3.5" fill="#c0392b"/>' for i, k in enumerate(dose_keys))
svg1 = f'''<svg viewBox="0 0 680 360" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:720px">
<text x="{px0}" y="20" font-size="13" fill="#333" font-weight="600">增速上限剂量响应（PEG≤1 系，总收益 %，2021-05 ~ 2026-08）</text>
{grid}
<line x1="{px0}" y1="{sy(ys_min)}" x2="{px1}" y2="{sy(ys_min)}" stroke="#999"/>
<line x1="{sx(1)}" y1="{py0}" x2="{sx(1)}" y2="{py1}" stroke="#eee" stroke-dasharray="3,3"/>
<line x1="{px0}" y1="{sy(EW_T*100)}" x2="{px1}" y2="{sy(EW_T*100)}" stroke="#8e44ad" stroke-dasharray="6,4" stroke-width="1.5"/>
<text x="{px1}" y="{sy(EW_T*100)-6}" text-anchor="end" font-size="11" fill="#8e44ad">等权全A {pct(EW_T)}</text>
<polyline points="{pts_finex}" fill="none" stroke="#4a7dbe" stroke-width="2.2"/>
<polyline points="{pts_full}" fill="none" stroke="#c0392b" stroke-width="2.6"/>
{dots_finex}{dots_full}
{xlabels}
<text x="{(px0+px1)/2}" y="{py1+40}" text-anchor="middle" font-size="11" fill="#777">增速上限（%，∞ = 无上限）</text>
<line x1="{px0}" y1="18" x2="{px0+26}" y2="18" stroke="#c0392b" stroke-width="2.6"/><text x="{px0+32}" y="22" font-size="11" fill="#c0392b">full 基座（全池含金融，铁律10 合规口径）</text>
<line x1="{px0}" y1="36" x2="{px0+26}" y2="36" stroke="#4a7dbe" stroke-width="2.2"/><text x="{px0+32}" y="40" font-size="11" fill="#4a7dbe">finex 基座（剔除金融，仅对照）</text>
<text x="{sx(2)-6}" y="{sy(FULL['g40']['total']*100)-10}" text-anchor="middle" font-size="10" fill="#c0392b">{pct(FULL['g40']['total'])}</text>
<text x="{sx(1)-4}" y="{sy(FULL['g30']['total']*100)-10}" text-anchor="middle" font-size="10" fill="#c0392b">{pct(FULL['g30']['total'])}</text>
<text x="{sx(7)+2}" y="{sy(FULL['nolimit']['total']*100)-10}" text-anchor="end" font-size="10" fill="#c0392b">{pct(FULL['nolimit']['total'])}</text>
</svg>'''

# ---------- SVG 2: 机制A 分桶前瞻收益 ----------
bk_order = ["0-30%", "30-60%", "60-100%", "100-200%", "200%+"]
W2, H2 = 680, 340
bx0, bx1, by0, by1 = 70, 650, 96, 280
bs_min, bs_max = -20, 15
def bx(i): return bx0 + (bx1 - bx0) * i / len(bk_order) + (bx1 - bx0) / len(bk_order) * 0.12
def by_(v): return by1 - (by1 - by0) * (v - bs_min) / (bs_max - bs_min)
bars = ""
bw = (bx1 - bx0) / len(bk_order) * 0.34
for i, bk in enumerate(bk_order):
    s = bucket[bk]
    r6, r12 = s["sum6"]/s["n6"]*100, s["sum12"]/s["n12"]*100
    x6 = bx0 + (bx1 - bx0) * i / len(bk_order) + (bx1 - bx0) / len(bk_order) * 0.10
    x12 = x6 + bw + 6
    c6 = "#d64541" if r6 >= 0 else "#2e8b57"
    c12 = "#e8968c" if r12 >= 0 else "#7cba8f"
    h6 = max(abs(by_(r6) - by_(0)), 1.5); h12 = max(abs(by_(r12) - by_(0)), 1.5)
    y6 = by_(0) if r6 >= 0 else by_(0) - h6
    y12 = by_(0) if r12 >= 0 else by_(0) - h12
    bars += f'<rect x="{x6:.0f}" y="{y6:.1f}" width="{bw:.0f}" height="{h6:.1f}" fill="{c6}" rx="2"/>'
    bars += f'<rect x="{x12:.0f}" y="{y12:.1f}" width="{bw:.0f}" height="{h12:.1f}" fill="{c12}" rx="2"/>'
    bars += f'<text x="{x6+bw/2:.0f}" y="{(y6-5) if r6>=0 else (y6+h6+14):.1f}" text-anchor="middle" font-size="10" fill="#333" font-weight="600">{r6:+.1f}</text>'
    bars += f'<text x="{x12+bw/2:.0f}" y="{(y12-5) if r12>=0 else (y12+h12+14):.1f}" text-anchor="middle" font-size="10" fill="#777">{r12:+.1f}</text>'
    xc = bx0 + (bx1 - bx0) * (i + 0.5) / len(bk_order)
    bars += f'<text x="{xc:.0f}" y="{by1+18}" text-anchor="middle" font-size="11" fill="#555" font-weight="600">{bk}</text>'
    bars += f'<text x="{xc:.0f}" y="{by1+34}" text-anchor="middle" font-size="9.5" fill="#999">n={s["n"]} 胜率{s["win6"]}/{s["n6"]}={s["win6"]/s["n6"]*100:.0f}%</text>'
grid2 = "".join(f'<line x1="{bx0}" y1="{by_(v):.0f}" x2="{bx1}" y2="{by_(v):.0f}" stroke="#e8e8e8"/><text x="{bx0-8}" y="{by_(v)+4:.0f}" text-anchor="end" font-size="11" fill="#888">{v}%</text>' for v in range(-20, 16, 5))
svg2 = f'''<svg viewBox="0 0 680 340" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:720px">
<text x="{bx0}" y="20" font-size="13" fill="#333" font-weight="600">PEG≤1 池内增速分桶 → 前瞻收益（全市场 5730 只面板，修复覆盖偏差后）</text>
<text x="{bx0}" y="40" font-size="11" fill="#888">10 个调仓期 × PEG≤1 池（240~400 只/期）；修复前仅 242 只覆盖（偏差样本）</text>
{grid2}
<line x1="{bx0}" y1="{by_(0)}" x2="{bx1}" y2="{by_(0)}" stroke="#999" stroke-width="1.2"/>
{bars}
<rect x="{bx0 + (bx1-bx0)*3/len(bk_order):.0f}" y="{by0-8}" width="{(bx1-bx0)*2/len(bk_order):.0f}" height="{by1-by0+44}" fill="#fdecea" opacity="0.55"/>
<text x="{bx0 + (bx1-bx0)*4/len(bk_order):.0f}" y="{by0-14}" text-anchor="middle" font-size="11" fill="#c0392b" font-weight="700">断崖区：12M 前瞻转负</text>
<rect x="{bx0}" y="64" width="14" height="10" fill="#d64541"/><text x="{bx0+20}" y="73" font-size="10.5" fill="#555">6M 前瞻均值</text>
<rect x="{bx0+90}" y="64" width="14" height="10" fill="#e8968c"/><text x="{bx0+110}" y="73" font-size="10.5" fill="#555">12M 前瞻均值</text>
</svg>'''

# ---------- HTML 组装 ----------
def variant_rows():
    rows = ""
    for k in ORDER:
        f, u = FIN[k], FULL[k]
        best = ' class="hl-best"' if k == "g30" else ""
        rows += f'''<tr{best}><td class="mono">{k}</td><td>{DESC[k]}</td><td>{GROUP[k]}</td>
<td class="mono {cls(f['total'])}">{pct(f['total'])}</td><td class="mono">{pct(f['mdd'])}</td>
<td class="mono {cls(f['excess_ew'])}">{pct(f['excess_ew'],1,True)}</td>
<td class="mono {cls(u['total'])}"><b>{pct(u['total'])}</b></td><td class="mono">{pct(u['ann'])}</td><td class="mono">{pct(u['mdd'])}</td>
<td class="mono {cls(u['excess_ew'])}">{pct(u['excess_ew'],1,True)}</td>
<td class="mono {cls(u['excess_idx'])}">{pct(u['excess_idx'],1,True)}</td></tr>'''
    return rows

def cmp_rows():
    rows = ""
    for k in ORDER:
        f, u = FIN[k], FULL[k]
        if k in OLD_MAP:
            src, ok = OLD_MAP[k]
            old = (old_adopt if src == "old_adopt" else old_ceiling)[ok]["total"]
            delta = f["total"] - old
            rows += f'''<tr><td class="mono">{k}</td><td>{DESC[k]}</td>
<td class="mono {cls(old)}">{pct(old)}</td><td class="mono {cls(f['total'])}">{pct(f['total'])}</td>
<td class="mono {cls(delta)}">{pct(delta,1,True)}</td>
<td class="mono {cls(u['total'])}"><b>{pct(u['total'])}</b></td>
<td class="mono {cls(u['total']-old)}">{pct(u['total']-old,1,True)}</td></tr>'''
        else:
            rows += f'''<tr><td class="mono">{k}</td><td>{DESC[k]}</td>
<td class="mono {cls(f['total'])}">{pct(f['total'])}</td><td class="mono {cls(f['total'])}">{pct(f['total'])}</td><td class="mono">0.0%</td>
<td class="mono {cls(u['total'])}"><b>{pct(u['total'])}</b></td>
<td class="mono {cls(u['total']-f['total'])}">{pct(u['total']-f['total'],1,True)}</td></tr>'''
    return rows

def check_rows():
    rows = ""
    for rid, rule, o, n, ev in checks:
        badge_o = f'<span class="b {"b-fail" if o=="FAIL" else "b-pass"}">{o}</span>'
        badge_n = f'<span class="b {"b-fail" if n=="FAIL" else "b-pass"}">{n}</span>'
        rows += f'<tr><td class="mono">{rid}</td><td>{rule}</td><td style="text-align:center">{badge_o}</td><td style="text-align:center">{badge_n}</td><td class="ev">{ev}</td></tr>'
    return rows

def viol_cards():
    cards = ""
    for vid, rule, title, prob, fix, impact in violations:
        cards += f'''<div class="vcard">
<div class="vhead"><span class="vid">{vid}</span><span class="vrule">违反 {rule}</span><b>{title}</b></div>
<div class="vbody"><p><b>问题</b>：{prob}</p><p><b>修复</b>：{fix}</p><p><b>影响</b>：{impact}</p></div></div>'''
    return cards

def intr_rows():
    rows = ""
    for x in intrusions[:12]:
        fw = "—" if x.get("fwd6") is None else pct(x["fwd6"],1,True)
        rows += f'''<tr><td class="mono">{x['month']}</td><td class="mono">{x['tk']}</td><td class="mono">{x['pe']:.1f}</td>
<td class="mono">{x['exp_g']:.0f}%</td><td class="mono">{x['peg']:.2f}</td><td class="mono {cls(x.get('fwd6'))}">{fw}</td></tr>'''
    return rows

def disp_rows():
    rows = ""
    for x in displaced[:12]:
        fw = "—" if x.get("fwd6") is None else pct(x["fwd6"],1,True)
        rows += f'''<tr><td class="mono">{x['month']}</td><td class="mono">{x['tk']}</td><td class="mono">{x['pe']:.1f}</td>
<td class="mono">{x['exp_g']:.0f}%</td><td class="mono">{x['peg']:.2f}</td><td class="mono {cls(x.get('fwd6'))}">{fw}</td></tr>'''
    return rows

# 机制B 汇总数字
intr_valid = [x for x in intrusions if x.get("fwd6") is not None]
disp_valid = [x for x in displaced if x.get("fwd6") is not None]
intr_avg = sum(x["fwd6"] for x in intr_valid) / len(intr_valid)
disp_avg = sum(x["fwd6"] for x in disp_valid) / len(disp_valid)
intr_win = sum(1 for x in intr_valid if x["fwd6"] > 0) / len(intr_valid)
disp_win = sum(1 for x in disp_valid if x["fwd6"] > 0) / len(disp_valid)

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Type D 合规审计 · garp 系列回测</title>
<style>
:root {{ --red:#c0392b; --green:#1e824c; --ink:#222; --muted:#777; --line:#e5e5e5; --bg:#fafafa; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; color:var(--ink); background:#fff; line-height:1.65; padding:28px 20px 60px; }}
.wrap {{ max-width:1060px; margin:0 auto; }}
h1 {{ font-size:22px; margin-bottom:4px; }}
h2 {{ font-size:17px; margin:34px 0 12px; padding-left:10px; border-left:4px solid var(--red); }}
h3 {{ font-size:14.5px; margin:16px 0 8px; color:#444; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:18px; }}
.meta-line {{ font-size:12.5px; color:#999; margin-bottom:14px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px; margin:10px 0 6px; }}
th,td {{ border:1px solid var(--line); padding:6px 8px; text-align:right; vertical-align:top; }}
th {{ background:#f4f6f8; font-weight:600; text-align:center; white-space:nowrap; }}
td:first-child, td:nth-child(2), td:nth-child(3) {{ text-align:left; }}
.mono {{ font-family:Consolas,Menlo,monospace; font-size:12px; }}
.pos {{ color:var(--red); font-weight:600; }}
.neg {{ color:var(--green); font-weight:600; }}
.ev {{ font-size:12px; color:#555; text-align:left !important; }}
.hl-best {{ background:#fdf3f2; }}
.b {{ display:inline-block; padding:1px 10px; border-radius:10px; font-size:11px; font-weight:700; }}
.b-pass {{ background:#e8f5e9; color:#1e824c; }}
.b-fail {{ background:#fdecea; color:#c0392b; }}
.verdict {{ border:2px solid var(--red); border-radius:10px; padding:18px 20px; background:#fff8f7; margin:14px 0 6px; }}
.verdict h2 {{ border:none; margin:0 0 10px; padding:0; color:var(--red); }}
.verdict ol {{ padding-left:22px; }}
.verdict li {{ margin:7px 0; font-size:13.5px; }}
.kpi {{ display:flex; gap:12px; flex-wrap:wrap; margin:14px 0; }}
.kpi div {{ flex:1; min-width:150px; border:1px solid var(--line); border-radius:8px; padding:10px 14px; background:#fff; }}
.kpi .k {{ font-size:11.5px; color:var(--muted); }}
.kpi .v {{ font-size:19px; font-weight:700; margin-top:2px; }}
.vcard {{ border:1px solid var(--line); border-left:5px solid var(--red); border-radius:8px; margin:12px 0; background:#fff; overflow:hidden; }}
.vhead {{ background:#fdecea; padding:8px 14px; font-size:13.5px; display:flex; gap:10px; align-items:center; }}
.vid {{ background:var(--red); color:#fff; border-radius:5px; padding:1px 9px; font-weight:700; font-size:12px; }}
.vrule {{ color:var(--red); font-size:12px; font-weight:600; }}
.vbody {{ padding:10px 16px; font-size:13px; }}
.vbody p {{ margin:5px 0; }}
.note {{ font-size:12px; color:var(--muted); margin:6px 0 0; }}
.flag {{ display:inline-block; background:#fff4e5; color:#b25e09; border-radius:5px; padding:1px 8px; font-size:11.5px; font-weight:600; margin-left:6px; }}
.two {{ display:flex; gap:16px; flex-wrap:wrap; }}
.two > div {{ flex:1; min-width:420px; }}
footer {{ margin-top:40px; padding-top:14px; border-top:1px solid var(--line); font-size:12px; color:#999; }}
.svgbox {{ border:1px solid var(--line); border-radius:10px; padding:12px; background:#fff; margin:10px 0; }}
</style>
</head>
<body><div class="wrap">

<h1>Type D 合规审计报告：garp 系列回测</h1>
<div class="sub">审计依据 <b>docs/prompt_template_fund_framework.md v1.0</b>（10 条铁律 + ⑤ 自查清单）· 审计对象：garp 采纳实验（_bt_garp.py）与增速上限实验（_bt_garp_ceiling.py）及其报告结论</div>
<div class="meta-line">运行 {meta['run_at']} · 数据窗口 {meta['window'][0]} ~ {meta['window'][1]} · 日K 覆盖 {meta['px_stocks']} 只（修复后全覆盖）· {len(ORDER)*2} 组回测（双基座 × {len(ORDER)} 变体）</div>

<div class="verdict">
<h2>裁决：三项违规 → 已修复复跑 → 结论重大修正</h2>
<ol>
<li><b>三项违规确认并全部修复</b>：V1 金融剔除贯穿回测管线（违反铁律10）→ 增跑全池基座；V2 缺同口径等权基准（违反铁律5/8）→ 接入双基准；V3 持仓丢股 bug（违反铁律1/⑤，选股并集 496 只中日K 仅覆盖 242 只，缺行情股票静默变现金）→ 补拉 255 只至 497 只全覆盖。</li>
<li><b>审计管线通过双锚点校验</b>：core/全池 = {pct(anchors['core_full_total'],2)}（= LX-core 已验证口径 {pct(anchors['lxcore_hist'],2)}）；core/finex = {pct(anchors['core_finex_total'],2)}（= 历史 finex 精确值）——修复未引入新偏差。</li>
<li><b>garp 门控采纳决策维持且强化</b>：合规口径（全池）下 g60（增速≤60% + PEG≤1）总收益 <b class="pos">{pct(FULL['g60']['total'])}</b> vs core {pct(FULL['core']['total'])}，增量 <b class="pos">{pct(FULL['g60']['total']-FULL['core']['total'],1,True)}pp</b>（旧口径仅 +5.12pp），MDD 16.67% vs 19.13% 双优。</li>
<li><b>参数结论修正</b>：旧『g60 平台期、&gt;100% 断崖』系丢股 bug + 金融剔除双重失真。全池口径下峰值移至 <b>g30（增速≤30%）{pct(FULL['g30']['total'])}</b>，且『断崖』变缓坡（nolimit 无上限仍有 {pct(FULL['nolimit']['total'])}）。机制A 分桶证实增速&gt;100% 前瞻收益确实转负（12M −4.2% / −14.7%），但组合层金融股缓冲使断崖变缓。</li>
<li><b>排序信念不动摇</b>：peg_sort（PEG 替代 PE 排序）修复丢股后仍全场最差（{pct(FULL['peg_sort']['total'])}/MDD {pct(FULL['peg_sort']['mdd'])}），确认无效清单条目。</li>
</ol>
</div>

<div class="kpi">
<div><div class="k">最优变体 g30（全池）</div><div class="v pos">{pct(FULL['g30']['total'])}</div><div class="k">超等权全A {pct(FULL['g30']['excess_ew'],1,True)}pp · MDD {pct(FULL['g30']['mdd'])}</div></div>
<div><div class="k">已采纳 garp（g60，全池）</div><div class="v pos">{pct(FULL['g60']['total'])}</div><div class="k">vs core +{pct(FULL['g60']['total']-FULL['core']['total'],1,True)}pp · MDD {pct(FULL['g60']['mdd'])}</div></div>
<div><div class="k">基准：等权全A（半年调仓）</div><div class="v">{pct(EW_T)}</div><div class="k">MDD {pct(bm['ew_hold']['mdd'])} · 中证全指 {pct(IDX_T)}</div></div>
<div><div class="k">断崖确认（增速&gt;100% 桶）</div><div class="v neg">12M −4.2% / −14.7%</div><div class="k">200%+ 桶胜率仅 23.4%</div></div>
</div>

<h2>§1 Type D 检查点（10 铁律 + ⑤ 自查 + 锚点）</h2>
<table>
<tr><th style="width:56px">编号</th><th style="width:170px">铁律 / 检查项</th><th style="width:70px">原实验</th><th style="width:70px">修复后</th><th>证据</th></tr>
{check_rows()}
</table>
<div class="note">『原实验』列指被审计的两份历史报告（_bt_garp_report.html / _bt_garp_ceiling_report.html）的合规状态；『修复后』列指本审计复跑管线的状态。</div>

<h2>§2 三项违规详情与影响量化</h2>
{viol_cards()}

<h2>§3 双基座 × 14 变体复跑总表（修复后）</h2>
<table>
<tr><th>变体</th><th>定义</th><th>系列</th>
<th colspan="3">finex 基座（剔除金融，仅对照）</th>
<th colspan="5">full 基座（全池含金融，铁律10 合规口径）</th></tr>
<tr><th></th><th></th><th></th><th>总收益</th><th>MDD</th><th>超EW</th><th>总收益</th><th>年化</th><th>MDD</th><th>超EW</th><th>超指数</th></tr>
{variant_rows()}
<tr style="background:#f4f6f8"><td class="mono">基准</td><td>半年调仓等权全A / 中证全指</td><td>—</td>
<td class="mono">{pct(EW_T)}</td><td class="mono">{pct(bm['ew_hold']['mdd'])}</td><td>—</td>
<td class="mono">{pct(EW_T)}</td><td class="mono">{pct(bm['ew_hold']['ann'])}</td><td class="mono">{pct(bm['ew_hold']['mdd'])}</td><td>—</td><td>—</td></tr>
</table>
<div class="note">超EW/超指数 = 变体总收益 − 等权全A/中证全指总收益（pp）。full 基座各变体金融持仓每期 15~32 只（详见 §5 数据），finex 基座全部为 0（验证剔除生效）。高亮行 = 全场最优 g30。</div>

<h2>§4 修正前后对照：旧失真数字 vs 修复后数字</h2>
<h3>PEG≤1 剂量系（对照旧增速上限实验）</h3>
<table>
<tr><th>变体</th><th>定义</th><th>旧（丢股 bug + finex）</th><th>修复后 finex</th><th>Δ</th><th>修复后 full</th><th>full − 旧</th></tr>
{cmp_rows()}
</table>
<div class="note">Δ 为同基座修复丢股前后的差值；『full − 旧』= 全部修复（丢股 + 金融剔除 + 双基准）后的总修正量。core 无丢股，其 finex 数字不变（锚点）；其 full 差值 100% 来自金融剔除违规的修复。</div>
<div class="note" style="color:var(--red)"><b>读法</b>：garp_q50（+24.3pp）、peg_sort（+17.9pp）、g30/g40（+11.2pp）修复后大幅上移——旧实验对这些变体的低估源于丢掉的股票后来上涨；nolimit（−6.1pp）反向——丢的高增速股下跌，现金化反而虚高。<b>旧实验的全部相对排序与『断崖』形态不可再引用。</b></div>

<h2>§5 剂量响应：断崖的真相</h2>
<div class="svgbox">{svg1}</div>
<div class="note">finex 基座（蓝）呈陡峭断崖：g40 峰值 {pct(FIN['g40']['total'])} → nolimit {pct(FIN['nolimit']['total'])}（−26.4pp）；full 基座（红）为缓坡：g40 {pct(FULL['g40']['total'])} → nolimit {pct(FULL['nolimit']['total'])}（仅 −2.2pp）。『增速上限断崖』的幅度约 80% 来自金融剔除后的组合结构，而非增速上限本身的组合层代价——机制层断崖（§6 前瞻收益）仍然真实存在。</div>

<h2>§6 机制A：增速分桶前瞻收益（全市场面板，修复覆盖偏差）</h2>
<div class="svgbox">{svg2}</div>
<div class="note">修复前仅 242 只覆盖（组合层选股），修复后用全市场 5730 只日收益宽表面板计算 PEG≤1 池内全部持仓的前瞻收益。0-60% 增速为甜蜜区（12M +10.4% ~ +10.7%）；&gt;100% 断崖真实存在（12M −4.2%，200%+ 桶 −14.7%、胜率 23.4%）。<b>增速上限的机制基础成立，但 0-30% 与 30-60% 桶前瞻收益几乎无差（10.42% vs 10.67%）——g30 组合层最优更多来自选股交互而非增速单调性，参数收紧不宜过激。</b></div>

<h2>§7 机制B：增速上限的侵入 / 挤出分析（finex 基座，nolimit vs g60）</h2>
<div class="kpi">
<div><div class="k">被 g60 上限挡出的股票</div><div class="v">{len(intr_valid)} 只-期</div><div class="k">前瞻6M 均值 <span class="neg">{pct(intr_avg,1,True)}</span> · 胜率 {intr_win*100:.0f}%</div></div>
<div><div class="k">因侵入被挤出 top40 的股票</div><div class="v">{len(disp_valid)} 只-期</div><div class="k">前瞻6M 均值 <span class="pos">{pct(disp_avg,1,True)}</span> · 胜率 {disp_win*100:.0f}%</div></div>
</div>
<div class="two">
<div>
<h3>被上限挡出 top40 的股票（增速&gt;60%，PEG≤1）<span class="flag">挡对了：前瞻 −1.87%</span></h3>
<table>
<tr><th>调仓月</th><th>代码</th><th>PE</th><th>一致预期增速</th><th>PEG</th><th>前瞻6M</th></tr>
{intr_rows()}
</table>
</div>
<div>
<h3>因侵入被挤出 top40 的股票（增速≤60%）<span class="flag">挤出代价：前瞻 +5.55%</span></h3>
<table>
<tr><th>调仓月</th><th>代码</th><th>PE</th><th>一致预期增速</th><th>PEG</th><th>前瞻6M</th></tr>
{disp_rows()}
</table>
</div>
</div>
<div class="note">上限挡出的是前瞻收益为负的高增速股（净收益为正），挤出的低成本股平均前瞻 +5.55%（净收益为负）。两个方向合并后 g60 相对 nolimit 的 finex 基座净增益 +16.2pp（{pct(FIN['g60']['total'])} vs {pct(FIN['nolimit']['total'])}）。</div>

<h2>§8 修正后结论与落档</h2>
<table>
<tr><th style="width:220px">结论项</th><th>旧结论（失真口径）</th><th>修正后结论（全池 + 全覆盖 + 双基准）</th></tr>
<tr><td><b>garp 门控采纳（L5 = 增速≤60% + PEG≤1）</b></td>
<td>8 变体最优 +34.57%/MDD 18.54%，增量 +5.12pp</td>
<td class="ev"><b class="pos">维持且强化</b>：全池 g60 {pct(FULL['g60']['total'])}/MDD {pct(FULL['g60']['mdd'])}，增量 {pct(FULL['g60']['total']-FULL['core']['total'],1,True)}pp；2022 熊市防御逻辑不变</td></tr>
<tr><td><b>增速上限参数</b></td><td>g60 为平台期最优，&gt;100% 断崖，nolimit 不可用</td>
<td class="ev">全池口径峰值移至 <b>g30 {pct(FULL['g30']['total'])}</b>（g40 {pct(FULL['g40']['total'])}），nolimit 仍有 {pct(FULL['nolimit']['total'])}——断崖变缓坡；但分桶前瞻收益 0-30% ≈ 30-60%，<b>建议维持 g60</b>（参数不依赖单一样本期交互），g30/g40 记为候选收紧方向，待样本外验证</td></tr>
<tr><td><b>PE 升序排序信念</b></td><td>peg_sort 最差 +6.90%</td>
<td class="ev"><b>确认有效</b>：修复丢股后 peg_sort 升至 {pct(FULL['peg_sort']['total'])} 仍全场最差（MDD {pct(FULL['peg_sort']['mdd'])}）——PE 排序不可被 PEG 排序替代</td></tr>
<tr><td><b>混合排序（garp_q20/q50）</b></td><td>稀释收益，q20 +32.14% &lt; 纯 PEG 系</td>
<td class="ev">方向不变：全池 garp_q20 {pct(FULL['garp_q20']['total'])} &lt; g60 {pct(FULL['g60']['total'])}；但 finex 修复后 garp_q50 {pct(FIN['garp_q50']['total'])} 反超 finex/g40——质量权重的价值依赖基座，全池口径下仍是稀释</td></tr>
<tr><td><b>金融剔除</b></td><td>excl_fin 贯穿全部变体</td>
<td class="ev"><b class="neg">违规确认</b>：全池 vs finex 系统性差 26pp（core 差 {pct(FULL['core']['total']-FIN['core']['total'],1,True)}pp）。金融剔除仅保留在『当前名单展示层』（_bt_sw_fin_universe.json 123 只），回测/排序管线一律全池</td></tr>
<tr><td><b>机制基础</b></td><td>增速&gt;100% 前瞻收益断崖（242 只覆盖）</td>
<td class="ev"><b>成立且更干净</b>：全市场 5730 只面板复验，&gt;100% 桶 12M −4.2%、200%+ 桶 −14.7%/胜率 23.4%；0-60% 甜蜜区 +10.4~10.7%</td></tr>
</table>

<h3>无效清单 / 认知框架更新</h3>
<div class="note" style="font-size:12.5px">
① 无效清单新增标注：『peg_sort（PEG 替代 PE 排序）——丢股修复后仍最差，维持无效』；<br>
② 投资认知框架（docs/投资认知框架.md v1.1）garp 段需按本报告修正：L5 门控增量从 +5.12pp 修正为 <b>+11.46pp（全池口径）</b>，并补记『断崖形态依赖金融剔除，全池下为缓坡』；<br>
③ Obsidian 09（投资认知框架）此前为 08-25 版，本次同步将补 garp 段修正；<br>
④ 历史报告 _bt_garp_report.html / _bt_garp_ceiling_report.html 中的全部对比数字标注为『旧口径（丢股 bug + 金融剔除 + 单基准）』，不再引用。
</div>

<footer>
数据：juzi-mcp（万得全A PIT 成分 / 估值 / 一致预期 / 日K 497 只）· 引擎：日频 T+1 撮合，佣金 5bp + 滑点 10bp · 基准：半年调仓等权全A（_bt_daily_ew_hold.py）+ 中证全指 000985.SH<br>
复现：_bt_garp_audit.py → _bt_garp_audit_results.json → _bt_garp_audit_report.py · 审计任务类型：Type D（模板 §检查点）· 生成于 {datetime.date.today().isoformat()}
</footer>
</div></body></html>'''

with open("_bt_garp_audit_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print("OK -> _bt_garp_audit_report.html", len(html), "chars")
