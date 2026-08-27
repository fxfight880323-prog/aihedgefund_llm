"""C-Score 一致预期策略 · 当前时点推荐 · 剔除金融版（银行+非银金融）。

在 _cs_now_recommend.py 基础上做且仅做一件事：
  在【池子构建阶段】剔除申万一级行业 = 银行 / 非银金融 的全部成分股
  （成分名单来自腾讯自选股 westock data_sector constituent, 2026-08-20），
  让非金融深度价值股补位进 top-100 池，再重算 BM 三分位、C-Score、权重。

诚实性说明：剔除金融是用户指定的偏好约束，+30.7% 的历史回测口径【含】银行股，
本名单属于"策略 + 行业约束"的衍生口径，回测证据不直接适用。
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.signals.c_score import (
    calculate_c_score, classify_consensus_expectation,
    consensus_conviction,
)
from _lx_now_screen import fetch_tencent

UNIV_FILE = "_bt_lx_now_universe.json"
VAL_FILE = "_bt_lx_now_valuation.json"
CONS_FILE = "_bt_lx_now_consensus.json"
OUT_JSON = "_cs_now_exfin_results.json"
OUT_CSV = "CScore策略_当前推荐A股_剔除金融.csv"
OUT_HTML = "_cs_now_exfin_report.html"

MIN_MV_YI = 50.0
PB_MAX = 2.0
PE_MAX = 20.0
POOL_TOP = 100
MAX_HOLDINGS = 20
PER_NAME_CAP = 0.06
GROSS_TARGET = 1.0
MOM_ROE_MIN = 8.0
AS_OF_YEAR = 2026

# ---- 申万一级 银行(42) + 非银金融 成分（腾讯自选股, 2026-08-20）----
FIN_BANK = {
    "601818.SH", "600926.SH", "002966.SZ", "600000.SH", "601166.SH",
    "603323.SH", "601328.SH", "601169.SH", "002807.SZ", "601128.SH",
    "002839.SZ", "601963.SH", "601528.SH", "001227.SZ", "601939.SH",
    "600015.SH", "600908.SH", "601916.SH", "601398.SH", "601009.SH",
    "601288.SH", "002142.SZ", "600036.SH", "601229.SH", "600016.SH",
    "600919.SH", "000001.SZ", "601998.SH", "002936.SZ", "002958.SZ",
    "601838.SH", "601860.SH", "601665.SH", "601825.SH", "601658.SH",
    "002948.SZ", "600928.SH", "601997.SH", "601988.SH", "601577.SH",
    "601187.SH", "601077.SH",
}
FIN_NONBANK = {
    "601198.SH", "000712.SZ", "600155.SH", "601628.SH", "601456.SH",
    "601696.SH", "002647.SZ", "600816.SH", "002736.SZ", "601066.SH",
    "601601.SH", "600095.SH", "600901.SH", "600918.SH", "002939.SZ",
    "601211.SH", "600120.SH", "600318.SH", "002945.SZ", "601788.SH",
    "600864.SH", "603300.SH", "601881.SH", "002670.SZ", "300773.SZ",
    "601236.SH", "002961.SZ", "000563.SZ", "601878.SH", "600390.SH",
    "600109.SH", "600999.SH", "600061.SH", "600053.SH", "600621.SH",
    "000750.SZ", "000166.SZ", "600958.SH", "601995.SH", "600517.SH",
    "601108.SH", "600927.SH", "601319.SH", "600830.SH", "600909.SH",
    "000686.SZ", "000415.SZ", "601336.SH", "300059.SZ", "000728.SZ",
    "002926.SZ", "001236.SZ", "002797.SZ", "603093.SH", "600369.SH",
    "601901.SH", "601099.SH", "000567.SZ", "002423.SZ", "601688.SH",
    "600906.SH", "000532.SZ", "000776.SZ", "601990.SH", "601162.SH",
    "000783.SZ", "601375.SH", "000617.SZ", "002673.SZ", "600030.SH",
    "601555.SH", "000935.SZ", "601059.SH", "600643.SH", "601318.SH",
    "601377.SH", "000987.SZ", "002500.SZ", "601136.SH",
}
FIN_CODES = FIN_BANK | FIN_NONBANK

# 名字兜底（SW 成分名单可能滞后于新股/改名）；金融街=地产, 白名单豁免
FIN_NAME_RE = re.compile("银行|证券|保险|信托|期货|金融|租赁")
NAME_WHITELIST = {"000402.SZ"}   # 金融街（申万=房地产）


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


def is_financial(tk, name=""):
    if tk in FIN_CODES:
        return True
    if tk in NAME_WHITELIST or tk not in FIN_CODES and not name:
        pass
    if name and FIN_NAME_RE.search(name) and tk not in NAME_WHITELIST:
        return True
    return False


def main():
    print("=" * 78)
    print("  C-Score 一致预期策略 · 当前推荐 · 剔除银行+非银金融")
    print("=" * 78)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    cons_raw, cons_asof = load_map(CONS_FILE)
    as_of = univ.get("as_of")
    members = univ.get("members", [])
    print(f"as_of={as_of} | univ={len(members)} | val={len(val)} | "
          f"cons={len(cons_raw)}")

    by_tk: dict[str, list] = {}
    for sc, r in cons_raw.items():
        tk = code_to_tk(sc)
        if tk:
            by_tk.setdefault(tk, []).append(r)
    cons = pick_consensus(by_tk)

    # ---- 深度价值池（先按 SW 代码剔金融）----
    stats = Counter()
    cands = []   # (tk, pb, pe, mv, c_rec)
    for sc in members:
        tk = code_to_tk(sc)
        if not tk:
            continue
        stats["univ"] += 1
        if is_financial(tk):
            stats["fin_sw"] += 1
            continue
        v = val.get(sc) or {}
        c = cons.get(tk) or {}
        pb = _num(v.get("pb"))
        pe = _num(v.get("pe_ttm"))
        mv = _num(v.get("total_mv"))
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
        cands.append((tk, pb, pe, mv, c))
    stats["pool"] = len(cands)

    # ---- 名字兜底剔金融（需要先拿名称）----
    tq_all = fetch_tencent(sorted({t for t, *_ in cands}))
    print(f"tencent 名称解析(池候选): {len(tq_all)}/{len(cands)}")
    cands = [(tk, pb, pe, mv, c) for tk, pb, pe, mv, c in cands
             if not is_financial(tk, tq_all.get(tk.split(".")[0], ("",))[0])]
    stats["fin_name"] = stats["pool"] - len(cands)
    stats["pool"] = len(cands)

    cands.sort(key=lambda x: x[1])          # PB 升序
    pool = cands[:POOL_TOP]
    stats["pool_top"] = len(pool)
    print(f"\n非金融深度价值池: {len(cands)} 只 → top{len(pool)} by PB")

    pbs = [p[1] for p in pool]
    pb_p33 = sorted(pbs)[len(pbs) // 3]
    pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]
    print(f"池 PB: min={min(pbs):.2f} p33={pb_p33:.2f} p67={pb_p67:.2f} "
          f"max={max(pbs):.2f}")

    # ---- C-Score 信号 ----
    sigs = []
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

    # ---- 预期动能榜（剔金融）----
    momentum = []
    for tk, rec in cons.items():
        if is_financial(tk):
            continue
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

    # 动能榜名称兜底（先取前 60 再按名称过滤补齐 20）
    mom_top = []
    for g, tk, rec, v in momentum:
        if len(mom_top) >= 20:
            break
        mom_top.append((g, tk, rec, v))

    # ---- 腾讯名称/现价 ----
    need = ({tk for _, tk, _ in sigs} | {tk for _, tk, _, _ in mom_top}
            | {tk for tk, *_ in cands[:POOL_TOP]})
    tq = fetch_tencent(sorted(need))
    print(f"tencent 名称解析(信号+动能+池): {len(tq)}/{len(need)}")

    # 动能榜名称兜底过滤，不足 20 从后续补
    mom_final = []
    idx = 0
    for g, tk, rec, v in momentum:
        if len(mom_final) >= 20:
            break
        name = tq.get(tk.split(".")[0], ("",))[0] if tk.split(".")[0] in tq \
            else fetch_tencent([tk]).get(tk.split(".")[0], ("",))[0]
        if is_financial(tk, name):
            continue
        mom_final.append((g, tk, rec, v, name))
        idx += 1

    # ---- 权重 ----
    total_conv = sum(s[0] for s in sigs)
    weights = {tk: min(conv / total_conv * GROSS_TARGET, PER_NAME_CAP)
               for conv, tk, _ in sigs}
    invested = sum(weights.values())
    print(f"权重: conv 加权 cap {PER_NAME_CAP:.0%} | 总仓位 {invested:.1%}")

    def enrich(sig_list):
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
                "weight": weights.get(tk, 0.0),
            })
        return rows

    rows = enrich(sigs)
    pick_rows = rows[:MAX_HOLDINGS]

    print(f"\n=== 剔除金融后 推荐 top-{len(pick_rows)}（conviction 加权，单票≤6%）===")
    for r in pick_rows:
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8} "
              f"C={r['c_score']} {r['expectation']:<11} "
              f"PB {r['pb']:>5.2f} PE {r['pe']:>5.1f} | "
              f"ROE {r['con_roe'] or 0:>5.1f} 增速 {r['con_np_yoy'] or 0:>6.1f}% "
              f"rev4w {r['rev4w'] or 0:>7.1f}% | w {r['weight']*100:.1f}%")

    mom_rows = []
    for i, (g, tk, rec, v, name) in enumerate(mom_final, 1):
        code = tk.split(".")[0]
        _, price, tmv = tq.get(code, ("", None, None))
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
    pool_dump = []
    for tk, pb, pe, mv, rec in pool:
        code = tk.split(".")[0]
        pool_dump.append({"tk": tk, "name": tq.get(code, ("",))[0],
                          "pb": pb, "pe": pe,
                          "c_score": calculate_c_score(rec)[0]})
    json.dump({
        "as_of": as_of, "univ_n": len(members),
        "variant": "ex-financial (SW 银行+非银金融 全剔除)",
        "stats": {k: v for k, v in stats.items()},
        "pool": pool_dump,
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
        cls = f' class="exp-{r["expectation"]}"'
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
<title>C-Score 一致预期策略 · 当前推荐 · 剔除金融（{as_of}）</title>
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

<h1>一致预期 C-Score 策略 · 当前推荐 A 股（剔除银行 + 非银金融）</h1>
<p class="sub">数据截至 <b>{as_of}</b> · 一致预期 = juzi PIT 快照（con_year 2026）
· 池子 = 万得全A(881001.WI) PIT 成分 {stats['univ']:,} 只
→ 剔除申万银行+非银金融（{stats.get('fin_sw', 0)} 只，另有
{stats.get('fin_name', 0)} 只按名称兜底剔除）
→ 深度价值池 {stats.get('pool_top', 0)} 只</p>

<div class="card">
<b>策略信号（4 项全数值化）：</b><br>
<span class="badge">C1</span> 预期ROE &gt; 12%
<span class="badge">C2</span> 预期净利增速 &gt; 0
<span class="badge">C3</span> 4周预期上修 &gt; 0
<span class="badge">C4</span> 13周预期上修 &gt; 0
→ <b>C-Score ∈ [0,4]</b><br>
<b>池子：</b>剔除金融后 PB&lt;2 ∩ PE&lt;20 ∩ 市值≥50亿，按 PB 升序取前 100 只
（池 PB 三分位 = {pb_p33:.2f} / {pb_p67:.2f}）。<br>
<b>期望矩阵：</b>C≥3 + 高BM = <span style="color:#c62828"><b>undervalued</b></span>（conv 0.5~0.7）← 核心推荐；
C≥3 + 中BM = moderate；C=2 + 高BM = speculative。<br>
<span class="kpi">参考回测（含银行口径，2021-08~2026-06）：<b>+30.7%</b> /
超额等权全A <b>+26.2pp</b></span>
</div>

<div class="card" style="border-left:4px solid #e65100">
<b>⚠️ 口径提示：</b>剔除金融是用户指定的行业约束，在<b>池子构建阶段</b>执行
（银行原本占据 PB 最低的十余个坑位，剔出后由非金融深度价值股补位，
BM 三分位随之重算）。+30.7% 的历史回测<b>包含</b>银行股，本名单是
"策略 + 行业约束"的衍生口径，回测证据不直接适用，需另行验证。
</div>

<h2>① 策略推荐组合 · top-{len(pick)}（conviction 加权，单票 ≤6%）</h2>
<p class="sub">买入信号共 {len(all_rows)} 只，权重 = conviction / Σconviction
（单票上限 6%）。总仓位 {w*100:.1f}%。✓ = 该项信号达标。</p>
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

<h2>③ 预期动能榜 · beat 且上涨最强 top-{len(mom_rows)}（剔金融，数据端视角）</h2>
<p class="sub">口径：有分析师覆盖 & 市值≥50亿 & PE&gt;0 & 预期ROE≥8%
& 4周上修&gt;0（beat 进行中），剔除申万银行+非银金融，
按一致预期净利增速 con_np_yoy 降序。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>预期增速%</th><th>预期ROE%</th><th>rev4w%</th>
<th>rev13w%</th><th>C-Score</th></tr>
{mom_tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 数据来自 juzi 估值面板 + 一致预期 PIT 快照
（{as_of}，全市场）与腾讯实时行情，金融成分名单来自腾讯自选股申万一级行业
（{as_of}），无合成数据；② 剔除在池子构建阶段执行（非事后从结果里划掉），
BM 分位在剔金融后的池内重算；③ C-Score 仅用符号方向，对上修幅度极端值稳健；
④ 无分析师覆盖的股票直接剔除（策略的真实暴露）；⑤ 本名单由数值化筛选器产生，
<b>不构成投资建议</b>；⑥ 过去表现不代表未来。</p>

</body></html>"""
    return html


if __name__ == "__main__":
    main()
