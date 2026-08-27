"""刘旭式框架推荐名单 — 多因子综合评分排序。

在已通过 LX-core 筛选的 226 只股票中，按六维度百分位打分：
  Value  50%: PE(30%) + PEG(20%)     — 便宜优先，回测实证决定性变量
  Quality 25%: con_roe(15%) + gpm(10%)  — 质量保护层
  Safety  25%: dy(15%) + cetop(10%)      — 股息 + 现金流安全边际

输出: 评分排名 HTML + CSV + JSON
"""
from __future__ import annotations

import csv
import json
import os
import statistics

SRC_JSON = "_lx_now_results.json"
OUT_JSON = "_lx_now_scored.json"
OUT_CSV = "刘旭框架_评分排名.csv"
OUT_HTML = "_lx_now_scored_report.html"

# 维度权重
W_VALUE = 0.50
W_QUALITY = 0.25
W_SAFETY = 0.25
# 子因子权重（维度内）
W_PE, W_PEG = 0.30, 0.20
W_ROE, W_GPM = 0.15, 0.10
W_DY, W_CETOP = 0.15, 0.10


def pct_rank(values, v, higher_better=True):
    """百分位排名（0-100）。values 为同组样本列表，v 为当前值。"""
    clean = [x for x in values if x is not None and x == x]
    if not clean or v is None or v != v:
        return 50.0  # 缺失值给中位数分
    if higher_better:
        return sum(1 for x in clean if x < v) / len(clean) * 100
    else:
        return sum(1 for x in clean if x > v) / len(clean) * 100


def main():
    data = json.loads(open(SRC_JSON, encoding="utf-8").read())
    all_stocks = data["all"]
    stats = data["stats"]
    as_of = data["as_of"]
    print(f"载入 {len(all_stocks)} 只通过 core 的股票 | as_of={as_of}")

    # 收集各因子全集（用于百分位计算）
    pe_all = [s["pe"] for s in all_stocks]
    peg_all = [s["peg"] for s in all_stocks]
    roe_all = [s["con_roe"] for s in all_stocks]
    gpm_all = [s["gpm"] for s in all_stocks]
    dy_all = [s["dy"] for s in all_stocks]
    cetop_all = [s["cetop"] for s in all_stocks]

    # 打分
    scored = []
    for s in all_stocks:
        pe_s = pct_rank(pe_all, s["pe"], higher_better=False)
        peg_s = pct_rank(peg_all, s["peg"], higher_better=False)
        roe_s = pct_rank(roe_all, s["con_roe"], higher_better=True)
        gpm_s = pct_rank(gpm_all, s["gpm"], higher_better=True)
        dy_s = pct_rank(dy_all, s["dy"], higher_better=True)
        cet_s = pct_rank(cetop_all, s["cetop"], higher_better=True)

        value = pe_s * (W_PE / W_VALUE) + peg_s * (W_PEG / W_VALUE)
        quality = roe_s * (W_ROE / W_QUALITY) + gpm_s * (W_GPM / W_QUALITY)
        safety = dy_s * (W_DY / W_SAFETY) + cet_s * (W_CETOP / W_SAFETY)

        total = value * W_VALUE + quality * W_QUALITY + safety * W_SAFETY

        scored.append({
            **s,
            "score_pe": round(pe_s, 1),
            "score_peg": round(peg_s, 1),
            "score_roe": round(roe_s, 1),
            "score_gpm": round(gpm_s, 1),
            "score_dy": round(dy_s, 1),
            "score_cet": round(cet_s, 1),
            "score_value": round(value, 1),
            "score_quality": round(quality, 1),
            "score_safety": round(safety, 1),
            "score_total": round(total, 1),
        })

    # 按总分降序
    scored.sort(key=lambda x: -x["score_total"])
    for i, s in enumerate(scored, 1):
        s["score_rank"] = i

    # 取 top-40 为推荐组合
    top40 = scored[:40]
    w = round(1.0 / 40, 4)
    for s in top40:
        s["weight"] = w

    # 输出 JSON
    json.dump({
        "as_of": as_of,
        "method": "percentile_rank_6factor",
        "weights": {
            "value": W_VALUE, "quality": W_QUALITY, "safety": W_SAFETY,
            "pe": W_PE, "peg": W_PEG, "roe": W_ROE,
            "gpm": W_GPM, "dy": W_DY, "cetop": W_CETOP,
        },
        "univ_n": data["univ_n"],
        "core_pass": len(all_stocks),
        "gm_median": stats["gpm_median"],
        "top40": top40,
        "all": scored,
    }, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON -> {OUT_JSON}")

    # 输出 CSV
    cols = ["score_rank", "code", "name", "score_total", "score_value",
            "score_quality", "score_safety", "score_pe", "score_peg",
            "score_roe", "score_gpm", "score_dy", "score_cet",
            "pe", "peg", "con_roe", "gpm", "dy", "cetop",
            "exp_g", "mv_yi", "price", "in_gm", "weight"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(scored)
    print(f"CSV -> {OUT_CSV}")

    # 输出 HTML
    html = build_html(as_of, stats, scored, top40, w)
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"报告 -> {OUT_HTML}")

    # 控制台预览
    print(f"\n{'='*90}")
    print(f"  评分排名 Top 20（{as_of}，共 {len(scored)} 只通过 core 筛选）")
    print(f"{'='*90}")
    print(f"{'#':>3} {'代码':<11} {'名称':<8} {'总分':>5} {'价值':>5} {'质量':>5} {'安全':>5}"
          f" | {'PE':>5} {'PEG':>4} {'ROE':>5} {'毛利':>5} {'息率':>5} {'OCF':>5}"
          f" | {'市值':>7} {'gm'}")
    print("-" * 90)
    for s in scored[:20]:
        gm_mark = "★" if s.get("in_gm") else " "
        print(f"{s['score_rank']:>3} {s['code']:<11} {s['name'] or '?':<8} "
              f"{s['score_total']:>5.1f} {s['score_value']:>5.1f} "
              f"{s['score_quality']:>5.1f} {s['score_safety']:>5.1f}"
              f" | {s['pe'] or 0:>5.1f} {s['peg'] or 0:>4.1f} "
              f"{s['con_roe'] or 0:>5.1f} {s['gpm'] or 0:>5.1f} "
              f"{s['dy'] or 0:>5.1f} {s['cetop'] or 0:>5.1f}"
              f" | {s['mv_yi']:>6.0f}亿 {gm_mark}")
    print(f"\n★ = 同时通过 gm 质量层（毛利率≥中位数 {stats['gpm_median']:.1f}%）")


def build_html(as_of, stats, scored, top40, w):
    def bar(v, color="#c62828"):
        c = max(0, min(100, v))
        return (f'<div class="bar"><div class="bar-fill" style="width:{c}%;'
                f'background:{color}"></div><span>{v:.0f}</span></div>')

    def tr(s, hl=False):
        gm = " gm" if s.get("in_gm") else ""
        return f"""<tr class="{gm}">
        <td>{s['score_rank']}</td><td class="l">{s['code']}</td>
        <td class="l"><b>{s['name'] or '—'}</b></td>
        <td><b class="score">{s['score_total']:.1f}</b></td>
        <td>{bar(s['score_value'])}</td>
        <td>{bar(s['score_quality'],'#1565c0')}</td>
        <td>{bar(s['score_safety'],'#2e7d32')}</td>
        <td>{s['pe'] or '—'}</td><td>{s['peg'] or '—'}</td>
        <td>{s['con_roe'] or '—'}</td><td>{s['gpm'] or '—'}</td>
        <td>{s['dy'] if s['dy'] is not None else '—'}</td>
        <td>{s['cetop'] if s['cetop'] is not None else '—'}</td>
        <td>{s['exp_g'] if s['exp_g'] is not None else '—'}</td>
        <td>{s['mv_yi']:,.0f}</td><td>{'★' if s.get('in_gm') else ''}</td></tr>"""

    top_tbl = "".join(tr(s) for s in top40)
    all_tbl = "".join(tr(s) for s in scored)

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>刘旭式框架 · 评分排名（{as_of}）</title>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 20px 28px;
        background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; margin-bottom: 4px; }}
 h2 {{ font-size: 16px; margin-top: 28px; border-left: 4px solid #c62828;
        padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; margin-bottom: 10px; }}
 table {{ border-collapse: collapse; margin: 8px 0; font-size: 12.5px;
         background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 4px 7px; text-align: right;
           white-space: nowrap; }}
 th {{ background: #f0f0f0; position: sticky; top: 0; z-index: 1; }}
 td.l {{ text-align: left; }}
 tr.gm {{ background: #fff8e1; }}
 tr:hover {{ background: #e3f2fd !important; }}
 .score {{ font-size: 14px; color: #c62828; }}
 .bar {{ position: relative; width: 60px; height: 16px; background: #eee;
         border-radius: 3px; overflow: hidden; display: inline-block; }}
 .bar-fill {{ height: 100%; border-radius: 3px; }}
 .bar span {{ position: absolute; right: 3px; top: 0; font-size: 11px;
              color: #333; line-height: 16px; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 12px 16px; margin: 10px 0; font-size: 13.5px;
         line-height: 1.75; }}
 .badge {{ display: inline-block; background: #c62828; color: #fff;
           border-radius: 4px; padding: 1px 8px; font-size: 12px; }}
 .legend {{ font-size: 12px; color: #888; margin: 6px 0; }}
 .legend span {{ display: inline-block; margin-right: 16px; }}
 .legend .dot {{ display: inline-block; width: 10px; height: 10px;
                border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
 .note {{ color: #888; font-size: 12px; margin-top: 18px;
          border-top: 1px dashed #ccc; padding-top: 10px; }}
</style></head><body>

<h1>刘旭式框架 · 评分排名推荐</h1>
<p class="sub">数据截至 <b>{as_of}</b> · 池子 = 万得全A PIT 成分 {stats['univ']:,} 只 ·
通过 core 筛选 {len(scored)} 只 · 评分维度权重：价值50% + 质量25% + 安全25%</p>

<div class="card">
<b>评分方法：</b>对通过 LX-core 筛选的全部 {len(scored)} 只股票，
按 6 个因子在组内百分位排名（0-100），加权合成总分：<br>
<table style="margin-top:8px;font-size:12px;border:none;">
<tr style="background:none;border:none;">
<td style="border:none;"><span class="dot" style="display:inline-block;width:10px;height:10px;background:#c62828;border-radius:2px;vertical-align:middle;"></span>
<b>价值 50%</b>：PE(30%, 低=好) + PEG(20%, 低=好)</td>
<td style="border:none;"><span class="dot" style="display:inline-block;width:10px;height:10px;background:#1565c0;border-radius:2px;vertical-align:middle;"></span>
<b>质量 25%</b>：预期ROE(15%, 高=好) + 毛利率(10%, 高=好)</td>
<td style="border:none;"><span class="dot" style="display:inline-block;width:10px;height:10px;background:#2e7d32;border-radius:2px;vertical-align:middle;"></span>
<b>安全 25%</b>：股息率(15%, 高=好) + OCF/市值(10%, 高=好)</td>
</tr></table>
<br>
排序信念来自回测实证：同一筛选器 PE 升序 +60% vs 质量优先 -12%，
价值维度权重因此最高。★ 标记 = 同时通过 gm 质量层（毛利率≥{stats['gpm_median']:.1f}%）。
</div>

<div class="legend">
<span><span class="dot" style="background:#fff8e1;border:1px solid #ddd;"></span>黄色行 = 通过 gm 层</span>
<span>百分位条 = 该因子在 {len(scored)} 只候选股中的相对位置</span>
</div>

<h2>① 综合评分 Top 40（推荐组合，等权 {w:.1%}）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>总分</th>
<th>价值分</th><th>质量分</th><th>安全分</th>
<th>PE</th><th>PEG</th><th>ROE%</th><th>毛利%</th><th>息率%</th><th>OCF%</th>
<th>预期增速%</th><th>市值(亿)</th><th>gm</th></tr>
{top_tbl}
</table>

<h2>② 全部评分排名（{len(scored)} 只）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>总分</th>
<th>价值分</th><th>质量分</th><th>安全分</th>
<th>PE</th><th>PEG</th><th>ROE%</th><th>毛利%</th><th>息率%</th><th>OCF%</th>
<th>预期增速%</th><th>市值(亿)</th><th>gm</th></tr>
{all_tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 评分是对已通过刘旭框架筛选的候选池内排序，
不改变筛选标准；② 因子百分位在候选池内计算（非全市场），反映相对优劣；
③ 数据来自 juzi PIT 快照 + 腾讯行情，无合成；④ 本名单不构成投资建议；
⑤ 回测区间 2021-08~2026-06 超额等权全A +7.1pp（core）/ MDD -13.9%（gm）。</p>

</body></html>"""


if __name__ == "__main__":
    main()
