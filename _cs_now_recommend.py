"""C-Score 一致预期策略 · 当前时点推荐（juzi 数据 @ 2026-08-20）。

策略（来自 2026-08-19 全历史回测 examples/backtest_c_score.py）:
  纯一致预期组合 5年 +30.7% / 超额等权全A +26.2pp / 10期中8期跑赢 F-Score。

信号（4 项，全部数值化）:
  C1 con_roe > 12%         预期 ROE 达标
  C2 con_np_yoy > 0        预期净利正增长
  C3 np_revision_4w > 0    4周预期上修
  C4 np_revision_13w > 0   13周预期上修
  C-Score = C1+C2+C3+C4 ∈ [0,4]

池子（与回测一致）: 万得全A(881001.WI) 当前 PIT 成分 ∩ {PB<2, PE<20, 市值≥50亿},
  按 PB 升序取 top-100（深度价值池）; 池内 PB 三分位 → BM(1/PB) 分位。

Piotroski-So 式期望矩阵:
  C≥3 & BM高 → undervalued  (conv 0.5 / 0.7) ← 核心推荐
  C≥3 & BM中 → moderate     (conv 0.3 / 0.4)
  C=2 & BM高 → speculative  (conv 0.15)
组合: conviction>0 全部命中 → top-20 等权（单票 ≤5%）。

另附数据端「预期动能榜」：全市场有覆盖 & 市值≥50亿 & PE>0，
按 con_np_yoy 降序 top-20（回应"一致预期上涨最强"视角）。
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.signals.c_score import (
    calculate_c_score, classify_consensus_expectation,
    consensus_conviction, C_SCORE_BUY,
)
from _lx_now_screen import fetch_tencent, load_fin_set

UNIV_FILE = "_bt_lx_now_universe.json"
VAL_FILE = "_bt_lx_now_valuation.json"
CONS_FILE = "_bt_lx_now_consensus.json"
FIN_FILE = "_bt_sw_fin_universe.json"
OUT_JSON = "_cs_now_results.json"
OUT_CSV = "CScore策略_当前推荐A股.csv"
OUT_HTML = "_cs_now_report.html"

MIN_MV_YI = 50.0          # 池子最小市值（回测口径 ≥50亿）
PB_MAX = 2.0              # 深度价值池：PB < 2
PE_MAX = 20.0             # 深度价值池：PE < 20
POOL_TOP = 100            # 池内按 PB 升序取前 100（回测口径 top100 by PB）
MAX_HOLDINGS = 20         # 推荐组合上限
PER_NAME_CAP = 0.06       # 单票 ≤6%（回测口径）
GROSS_TARGET = 1.0        # 满仓目标（回测口径）
MOM_ROE_MIN = 8.0         # 动能榜质量门槛：预期ROE ≥ 8%
AS_OF_YEAR = 2026


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def code_to_tk(sc):
    if "." not in sc:
        return None
    code, mkt = sc.split(".")
    if code[0] == "6":
        return f"{code}.SH"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return f"{code}.BJ"


def load_map(path):
    d = json.loads(open(path, encoding="utf-8").read())
    return {r.get("stock_code"): r for r in d.get("records", [])}, d.get("as_of")


def pick_consensus(recs_by_tk):
    """{tk: rec} — 多 con_year 记录取最接近 as_of 年份的一条（同回测口径）。"""
    out = {}
    for tk, rs in recs_by_tk.items():
        best = None
        for r in rs:
            y = r.get("con_year") or 0
            dist = 0 if y == AS_OF_YEAR else (1 if y == AS_OF_YEAR + 1
                                              else 2 + abs(y - AS_OF_YEAR))
            if best is None or dist < best[0]:
                best = (dist, r)
        out[tk] = best[1]
    return out


def main():
    print("=" * 78)
    print("  C-Score 一致预期策略 · 当前时点推荐")
    print("  C1 con_roe>12 | C2 con_np_yoy>0 | C3 rev4w>0 | C4 rev13w>0")
    print("  池: 全A ∩ PB<2 PE<20 市值≥50亿 → top100 by PB | BM三分位")
    print("=" * 78)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    cons_raw, cons_asof = load_map(CONS_FILE)
    as_of = univ.get("as_of")
    members = univ.get("members", [])
    print(f"as_of={as_of} | univ={len(members)} | val={len(val)} | "
          f"cons={len(cons_raw)}")

    # ---- 金融剔除（用户铁律：所有筛选默认剔除银行/金融股）----
    fin_set = load_fin_set()
    members = [m for m in members if m not in fin_set]
    print(f"剔除金融后池子: {len(members)} 只")

    # ---- 一致预期按 tk 聚合去重 ----
    by_tk: dict[str, list] = {}
    for sc, r in cons_raw.items():
        tk = code_to_tk(sc)
        if tk:
            by_tk.setdefault(tk, []).append(r)
    cons = pick_consensus(by_tk)
    print(f"consensus 去重后 {len(cons)} 只")

    # ---- 深度价值池 ----
    stats = Counter()
    stats["univ"] = len(members)
    stats["fin_removed"] = len(fin_set)
    pool = []   # (tk, pb, pe, mv, c_rec)
    for sc in members:
        tk = code_to_tk(sc)
        if not tk:
            continue
        v = val.get(sc) or {}
        c = cons.get(tk) or {}
        pb = _num(v.get("pb"))
        pe = _num(v.get("pe_ttm"))
        mv = _num(v.get("total_mv"))   # 万元
        if pb is None or pb <= 0:
            stats["pb_missing"] += 1
            continue
        if pb >= PB_MAX:
            stats["pb_high"] += 1
            continue
        if pe is None or pe <= 0:
            stats["pe_nonpos"] += 1
            continue
        if pe >= PE_MAX:
            stats["pe_high"] += 1
            continue
        if mv is None or mv < MIN_MV_YI * 10000:
            stats["mv_low"] += 1
            continue
        if not c:
            stats["no_cover"] += 1
            continue
        pool.append((tk, pb, pe, mv, c))
    stats["pool"] = len(pool)

    pool.sort(key=lambda x: x[1])          # PB 升序
    pool = pool[:POOL_TOP]
    stats["pool_top"] = len(pool)
    print(f"\n深度价值池: {stats['pool']} 只 → top{len(pool)} by PB")

    # ---- 池内 BM 三分位 ----
    pbs = [p[1] for p in pool]
    pb_p33 = sorted(pbs)[len(pbs) // 3]
    pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]
    print(f"池 PB: min={min(pbs):.2f} p33={pb_p33:.2f} p67={pb_p67:.2f} "
          f"max={max(pbs):.2f}")

    # ---- C-Score 信号 ----
    sigs = []     # (conviction, tk, detail)
    for tk, pb, pe, mv, rec in pool:
        c_score, c_detail = calculate_c_score(rec)
        bm = 1.0 / pb
        bm_tercile = ("high" if pb <= pb_p33
                      else ("low" if pb >= pb_p67 else "mid"))
        expectation = classify_consensus_expectation(c_score, bm_tercile)
        conv = consensus_conviction(c_score, bm_tercile)
        if conv > 0:
            sigs.append((conv, tk, {
                "c_score": c_score, "c_detail": c_detail,
                "pb": pb, "pe": pe, "bm": bm, "bm_tercile": bm_tercile,
                "expectation": expectation, "conviction": conv,
                "con_roe": rec.get("con_roe"), "con_np_yoy": rec.get("con_np_yoy"),
                "con_pe": rec.get("con_pe"), "con_peg": rec.get("con_peg"),
                "rev4w": rec.get("np_revision_4w"), "rev13w": rec.get("np_revision_13w"),
                "mv": mv,
            }))
    sigs.sort(key=lambda s: (-s[0], -s[2]["bm"], s[2]["pe"]))
    print(f"买入信号(conv>0): {len(sigs)} 只 | "
          f"undervalued={sum(1 for s in sigs if s[2]['expectation']=='undervalued')} | "
          f"moderate={sum(1 for s in sigs if s[2]['expectation']=='moderate')} | "
          f"speculative={sum(1 for s in sigs if s[2]['expectation']=='speculative')}")

    # ---- 预期动能榜（数据端：beat + 上涨最强）----
    # 质量过滤: 预期ROE≥8% 且 4周上修>0(beat 中) 且 增速>0; 按 con_np_yoy 降序
    momentum = []
    for tk, rec in cons.items():
        v = val.get(tk) or {}
        g = _num(rec.get("con_np_yoy"))
        roe = _num(rec.get("con_roe"))
        rev4 = _num(rec.get("np_revision_4w"))
        pe = _num(v.get("pe_ttm"))
        mv = _num(v.get("total_mv"))
        if g is None or g <= 0:
            continue
        if roe is None or roe < MOM_ROE_MIN:
            continue
        if rev4 is None or rev4 <= 0:
            continue
        if mv is None or mv < MIN_MV_YI * 10000:
            continue
        if pe is not None and pe <= 0:
            continue
        momentum.append((g, tk, rec, v))
    momentum.sort(key=lambda x: -x[0])
    momentum = momentum[:20]

    # ---- 腾讯名称/现价（推荐 + 动能榜合并解析）----
    need = {tk for _, tk, _ in sigs} | {tk for _, tk, _, _ in momentum}
    tq = fetch_tencent(sorted(need))
    print(f"tencent 名称解析: {len(tq)}/{len(need)}")

    # ---- 组合权重：conviction 加权（回测 blend_weights 口径，cap 6%）----
    total_conv = sum(s[0] for s in sigs)
    weights = {tk: min(conv / total_conv * GROSS_TARGET, PER_NAME_CAP)
               for conv, tk, _ in sigs}
    invested = sum(weights.values())
    print(f"权重: conv 加权 cap {PER_NAME_CAP:.0%} | 总仓位 {invested:.1%}")

    def enrich(sig_list, weight_of):
        rows = []
        for i, (conv, tk, d) in enumerate(sig_list, 1):
            code = tk.split(".")[0]
            name, price, tmv = tq.get(code, ("", None, None))
            cd = d["c_detail"]
            rows.append({
                "rank": i, "code": tk, "name": name, "price": price,
                "mv_yi": round(d["mv"] / 10000, 1),
                "pe": round(d["pe"], 1), "pb": round(d["pb"], 2),
                "bm": round(d["bm"], 3), "bm_tercile": d["bm_tercile"],
                "c_score": d["c_score"],
                "c1": cd["c1_roe"], "c2": cd["c2_growth"],
                "c3": cd["c3_rev4w"], "c4": cd["c4_rev13w"],
                "con_roe": round(d["con_roe"], 1) if d["con_roe"] is not None else None,
                "con_np_yoy": round(d["con_np_yoy"], 1) if d["con_np_yoy"] is not None else None,
                "rev4w": round(d["rev4w"], 1) if d["rev4w"] is not None else None,
                "rev13w": round(d["rev13w"], 1) if d["rev13w"] is not None else None,
                "expectation": d["expectation"],
                "conviction": d["conviction"],
                "weight": weight_of(tk),
            })
        return rows

    rows = enrich(sigs, lambda tk: weights.get(tk, 0.0))
    pick_rows = rows[:MAX_HOLDINGS]

    print(f"\n=== 推荐 top-{len(pick_rows)}（conviction 加权，单票≤6%）===")
    for r in pick_rows:
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8} "
              f"C={r['c_score']} {r['expectation']:<11} "
              f"PB {r['pb']:>5.2f} PE {r['pe']:>5.1f} | "
              f"ROE {r['con_roe'] or 0:>5.1f} 增速 {r['con_np_yoy'] or 0:>6.1f}% "
              f"rev4w {r['rev4w'] or 0:>7.1f}% | w {r['weight']*100:.1f}%")

    # ---- 动能榜行组装（momentum 已在前方构建）----
    mom_rows = []
    for i, (g, tk, rec, v) in enumerate(momentum, 1):
        code = tk.split(".")[0]
        name, price, tmv = tq.get(code, ("", None, None))
        c_score, cd = calculate_c_score(rec)
        mom_rows.append({
            "rank": i, "code": tk, "name": name, "price": price,
            "mv_yi": round(_num(v.get("total_mv")) / 10000, 1),
            "pe": round(_num(v.get("pe_ttm")), 1) if _num(v.get("pe_ttm")) else None,
            "con_np_yoy": round(g, 1),
            "con_roe": round(_num(rec.get("con_roe")), 1) if _num(rec.get("con_roe")) is not None else None,
            "rev4w": round(_num(rec.get("np_revision_4w")), 1) if _num(rec.get("np_revision_4w")) is not None else None,
            "rev13w": round(_num(rec.get("np_revision_13w")), 1) if _num(rec.get("np_revision_13w")) is not None else None,
            "c_score": c_score,
        })

    # ---- CSV ----
    cols = ["rank", "code", "name", "price", "mv_yi", "pe", "pb", "bm",
            "bm_tercile", "c_score", "c1", "c2", "c3", "c4",
            "con_roe", "con_np_yoy", "rev4w", "rev13w",
            "expectation", "conviction", "weight"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"\nCSV → {OUT_CSV}")

    # ---- JSON ----
    json.dump({
        "as_of": as_of, "univ_n": len(members),
        "stats": {k: v for k, v in stats.items()},
        "pool": [{"tk": tk, "pb": pb, "pe": pe,
                  "c_score": calculate_c_score(rec)[0]}
                 for tk, pb, pe, mv, rec in pool],
        "pool_pb": {"p33": pb_p33, "p67": pb_p67},
        "recommend": pick_rows, "all_sigs": rows,
        "momentum": mom_rows,
        "weights": weights, "invested": invested,
    }, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON → {OUT_JSON}")

    # ---- HTML ----
    html = build_html(as_of, stats, pick_rows, rows, mom_rows, invested,
                      pb_p33, pb_p67)
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"报告 → {OUT_HTML}")


def build_html(as_of, stats, pick, all_rows, mom_rows, w, pb_p33, pb_p67):
    exp_color = {"undervalued": "#c62828", "moderate": "#e65100",
                 "speculative": "#6a1b9a"}

    def tr(r):
        cls = f' class="exp-{r["expectation"]}"' if "expectation" in r else ""
        c1 = "✓" if r["c1"] else "·"
        c2 = "✓" if r["c2"] else "·"
        c3 = "✓" if r["c3"] else "·"
        c4 = "✓" if r["c4"] else "·"
        return f"""<tr{cls}>
          <td>{r['rank']}</td><td class="l">{r['code']}</td>
          <td class="l"><b>{r['name'] or '—'}</b></td>
          <td>{r['price'] or '—'}</td><td>{r['mv_yi']:,.0f}</td>
          <td>{r['pe']}</td><td><b>{r['pb']:.2f}</b></td>
          <td>{c1}{c2}{c3}{c4}</td>
          <td><b>{r['c_score']}/4</b></td>
          <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
          <td>{r['con_np_yoy'] if r['con_np_yoy'] is not None else '—'}</td>
          <td>{r['rev4w'] if r['rev4w'] is not None else '—'}</td>
          <td>{r['rev13w'] if r['rev13w'] is not None else '—'}</td>
          <td><span style="color:{exp_color.get(r['expectation'],'#333')}"><b>{r['expectation']}</b></span></td>
          <td>{r['conviction']:.2f}</td><td>{r['weight']*100:.1f}%</td></tr>"""

    def mom_tr(r):
        return f"""<tr>
          <td>{r['rank']}</td><td class="l">{r['code']}</td>
          <td class="l"><b>{r['name'] or '—'}</b></td>
          <td>{r['price'] or '—'}</td><td>{r['mv_yi']:,.0f}</td>
          <td>{r['pe'] or '—'}</td>
          <td><b>{r['con_np_yoy']}</b></td>
          <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
          <td>{r['rev4w'] if r['rev4w'] is not None else '—'}</td>
          <td>{r['rev13w'] if r['rev13w'] is not None else '—'}</td>
          <td>{r['c_score']}/4</td></tr>"""

    pick_tbl = "".join(tr(r) for r in pick)
    all_tbl = "".join(tr(r) for r in all_rows)
    mom_tbl = "".join(mom_tr(r) for r in mom_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>C-Score 一致预期策略 · 当前推荐（{as_of}）</title>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px 36px;
        background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; margin-bottom: 4px; }}
 h2 {{ font-size: 16px; margin-top: 30px; border-left: 4px solid #c62828;
        padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 13px;
         background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 5px 9px; text-align: right;
           white-space: nowrap; }}
 th {{ background: #f0f0f0; position: sticky; top: 0; }}
 td.l {{ text-align: left; }}
 tr.exp-undervalued {{ background: #fdecea; }}
 tr.exp-moderate {{ background: #fff3e0; }}
 tr.exp-speculative {{ background: #f3e5f5; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 12px 16px; margin: 10px 0; font-size: 13.5px;
         line-height: 1.75; }}
 .badge {{ display: inline-block; background: #c62828; color: #fff;
           border-radius: 4px; padding: 1px 8px; font-size: 12px; }}
 .badge.g {{ background: #2e7d32; }}
 .note {{ color: #888; font-size: 12px; margin-top: 18px;
          border-top: 1px dashed #ccc; padding-top: 10px; }}
 .kpi {{ font-size: 15px; font-weight: 700; }}
 .kpi b {{ color: #c62828; font-size: 19px; }}
</style></head><body>

<h1>一致预期 C-Score 策略 · 当前推荐 A 股</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 一致预期 = juzi PIT 快照
（con_year 2026）· 池子 = 万得全A(881001.WI) 当前 PIT 成分
<b>{stats['univ'] + stats.get('fin_removed', 0):,}</b> 只，已剔除银行/非银金融
<b>{stats.get('fin_removed', 0):,}</b> 只（用户铁律）→ 筛选池 {stats['univ']:,} 只
→ 深度价值池 {stats.get('pool_top', 0)} 只</p>

<div class="card">
<b>策略信号（4 项全数值化，来自全历史回测实证）：</b><br>
<span class="badge">C1</span> 预期ROE &gt; 12%
<span class="badge">C2</span> 预期净利增速 &gt; 0
<span class="badge">C3</span> 4周预期上修 &gt; 0
<span class="badge">C4</span> 13周预期上修 &gt; 0
→ <b>C-Score ∈ [0,4]</b><br>
⓪ 金融剔除（用户铁律）：申万/中信一级 <b>银行 + 非银金融 + 综合金融</b> PIT 成分
共 {stats.get('fin_removed', 0):,} 只，在池子构建前剔除；<br>
<b>池子（与回测一致）：</b>PB&lt;2 ∩ PE&lt;20 ∩ 市值≥50亿，按 PB 升序取前 100 只
（池 PB 三分位 = {pb_p33:.2f} / {pb_p67:.2f}）→ BM 分位。<br>
<b>期望矩阵：</b>C≥3 + 高BM = <span style="color:#c62828"><b>undervalued</b></span>（conv 0.5~0.7）← 核心推荐；
C≥3 + 中BM = moderate；C=2 + 高BM = speculative。<br>
<span class="kpi">回测（2021-08~2026-06，半年调仓）：<b>+30.7%</b> / 超额等权全A
<b>+26.2pp</b> / 10 期中 8 期跑赢 F-Score(+12.6%)</span>
</div>

<h2>① 策略推荐组合 · top-{len(pick)}（conviction 加权，单票 ≤6%）</h2>
<p class="sub">买入信号共 {len(all_rows)} 只，权重 = conviction / Σconviction
（回测 blend_weights 口径，单票上限 6%）。总仓位 {w*100:.1f}%。✓ = 该项信号达标。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>PB</th><th>C1C2C3C4</th><th>C</th><th>预期ROE%</th>
<th>预期增速%</th><th>rev4w%</th><th>rev13w%</th><th>矩阵分类</th>
<th>conv</th><th>权重</th></tr>
{pick_tbl}
</table>

<h2>② 全部买入信号明细（{len(all_rows)} 只）</h2>
<p class="sub">红色=低估+强预期（undervalued），橙色=估值中性（moderate），
紫色=C=2 但深度低估（speculative）。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>PB</th><th>C1C2C3C4</th><th>C</th><th>预期ROE%</th>
<th>预期增速%</th><th>rev4w%</th><th>rev13w%</th><th>矩阵分类</th>
<th>conv</th><th>权重</th></tr>
{all_tbl}
</table>

<h2>③ 预期动能榜 · beat 且上涨最强 top-{len(mom_rows)}（数据端视角）</h2>
<p class="sub">口径：有分析师覆盖 & 市值≥50亿 & PE&gt;0 & 预期ROE≥8%
& 4周上修&gt;0（beat 进行中），按一致预期净利增速 con_np_yoy 降序。
C-Score 列标出该股的一致预期质量。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>预期增速%</th><th>预期ROE%</th><th>rev4w%</th>
<th>rev13w%</th><th>C-Score</th></tr>
{mom_tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 全部数据来自 juzi 估值面板 + 一致预期
PIT 快照（2026-08-24，全市场 5528 只）与腾讯实时行情，无合成数据；
② 深度价值池（PB&lt;2/PE&lt;20/市值≥50亿）与 2026-08-19 全历史回测口径一致，
BM 分位在池内计算；③ 剔除金融是用户指定的偏好约束（2026-08-25 定稿），
+30.7% 回测口径<b>含</b>银行股，本名单属"策略 + 行业约束"衍生口径，回测证据不直接适用；
④ C-Score 仅用符号方向（&gt;0/&gt;12%），对原始上修幅度的极端值稳健；
⑤ 无分析师覆盖的股票直接剔除（这是策略的真实暴露，不是缺陷）；
⑥ 本名单由数值化筛选器产生，<b>不构成投资建议</b>；⑦ 过去表现不代表未来。</p>

</body></html>"""
    return html


if __name__ == "__main__":
    main()
