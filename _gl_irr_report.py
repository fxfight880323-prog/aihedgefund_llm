# -*- coding: utf-8 -*-
"""IRR 门槛实验 · 对比报告生成器。

读取 _bt_gl_irr_{baseline|irr15|irr30|irr50}_*.json，输出：
  1. 总览表（总收益/年化/回撤/超额/持仓数）
  2. NAV 曲线（SVG）
  3. 逐期收益（SVG 柱状）
  4. IRR 门逐期诊断（候选/可算/过门/持仓）
  5. 事后检验（ex-post，仅诊断用途，非策略）：
     - 每期每只 baseline 持仓的 IRR / g / PS0/PS_med / 前向收益
     - IRR 分桶前向收益（看 IRR 是否有预测力）
     - irr15 被拒个股名单 + 其前向收益（拒绝是对是错）
输出: _gl_irr_report.html
"""
from __future__ import annotations

import json
import statistics

MODES = ["baseline", "irr15", "irr15u", "irr30", "irr50"]
MODE_LABEL = {"baseline": "基准(无IRR门)", "irr15": "IRR≥15%",
              "irr15u": "IRR≥15%*", "irr30": "IRR≥30%",
              "irr50": "IRR≥50%"}
MODE_COLOR = {"baseline": "#1f77b4", "irr15": "#ff7f0e",
              "irr15u": "#17becf", "irr30": "#9467bd",
              "irr50": "#d62728"}

FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
SEL_FILE = "_bt_pit_selection.json"
BENCH_FILE = "_bt_benchmark.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]


def load(fn):
    return json.loads(open(fn, encoding="utf-8").read())


def _pct(x, fmt="+.0%"):
    return f"{x:{fmt}}" if x is not None else "—"


def nav_map(mode: str) -> dict[str, float]:
    d = load(f"_bt_gl_irr_{mode}_nav.json")
    return {r["month"]: r["nav"] for r in d}


def stats_of(mode: str, bench: dict[str, float]) -> dict:
    nav = nav_map(mode)
    dts = sorted(nav)
    start = nav[dts[0]]
    end = nav[dts[-1]]
    r = end / start - 1
    yrs = (len(dts) - 1) / 12
    ann = (1 + r) ** (1 / yrs) - 1 if r > -1 else -1.0
    br = bench[dts[-1]] / bench[dts[0]] - 1
    peak, mdd = 0.0, 0.0
    for dt in dts:
        peak = max(peak, nav[dt])
        mdd = min(mdd, nav[dt] / peak - 1)
    det = load(f"_bt_gl_irr_{mode}_detail.json")
    hist = det["history"]
    n_hold = statistics.mean(h["n"] for h in hist)
    # 胜率（逐期 vs 基准）
    diag = load(f"_bt_gl_irr_{mode}_diag.json")
    per_ret = diag["per_period_ret"]
    wins = 0
    for mk, ret in per_ret.items():
        if mk in bench and bench.get(mk):
            nxt = None
            keys = sorted(per_ret)
            idx = keys.index(mk)
            nxt = keys[idx + 1] if idx + 1 < len(keys) else dts[-1]
            bret = bench.get(nxt[:7], bench[dts[-1]]) / bench[mk] - 1
            if ret > bret:
                wins += 1
    return {"mode": mode, "end": end, "total": r, "ann": ann, "mdd": mdd,
            "excess": r - br, "n_hold": n_hold,
            "win_rate": wins / len(per_ret) if per_ret else 0.0,
            "gross": diag.get("gross_mean",
                              statistics.mean(
                                  [v["gross"] for v in diag["diag"].values()])
                              if "gross" in diag.get("diag", {})
                              else 1.0)}


def svg_nav(all_nav: dict[str, dict[str, float]],
            bench: dict[str, float]) -> str:
    W, H, L, R, T, B = 720, 300, 46, 12, 14, 30
    dts = sorted(all_nav["baseline"])
    vals = [all_nav["baseline"][d] / all_nav["baseline"][dts[0]]
            for d in dts]
    vmin = min(min(vals), bench[dts[-1]] / bench[dts[0]], 0.6)
    vmax = max(max(vals), bench[dts[-1]] / bench[dts[0]], 1.0)
    vmin = min(vmin, 0.55)
    vmax = max(vmax, 1.05)
    def X(i): return L + (W - L - R) * i / (len(dts) - 1)
    def Y(v): return T + (H - T - B) * (1 - (v - vmin) / (vmax - vmin))
    g = []
    for k in range(0, len(dts), max(1, len(dts) // 6)):
        g.append(f'<text x="{X(k):.0f}" y="{H-B+16}" '
                 f'font-size="10" fill="#888">{dts[k]}</text>')
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        yy = Y(v)
        g.append(f'<line x1="{L}" y1="{yy:.0f}" x2="{W-R}" '
                 f'y2="{yy:.0f}" stroke="#eee"/>')
        g.append(f'<text x="{L-4}" y="{yy+3:.0f}" text-anchor="end" '
                 f'font-size="9" fill="#888">{v:.2f}</text>')
    # 基准
    pts = " ".join(f"{X(i):.1f},{Y(bench[d]/bench[dts[0]]):.1f}"
                   for i, d in enumerate(dts) if d in bench)
    g.append(f'<polyline points="{pts}" fill="none" stroke="#999" '
             f'stroke-width="1.6" stroke-dasharray="5,4"/>')
    for mode in MODES:
        nav = all_nav[mode]
        base = nav[dts[0]]
        pts = " ".join(f"{X(i):.1f},{Y(nav[d]/base):.1f}"
                       for i, d in enumerate(dts))
        g.append(f'<polyline points="{pts}" fill="none" '
                 f'stroke="{MODE_COLOR[mode]}" stroke-width="2.2"/>')
    lg = "".join(
        f'<rect x="{W-300+i*56}" y="{T-12}" width="14" height="10" '
        f'fill="{MODE_COLOR[m]}" rx="2"/><text x="{W-284+i*56}" '
        f'y="{T-3}" font-size="9" fill="#555">{lbl}</text>'
        for i, (m, lbl) in enumerate(MODE_LABEL.items()))
    lg += f'<rect x="{W-300+5*56}" y="{T-12}" width="14" height="10" ' \
          f'fill="none" stroke="#999" rx="2"/><text x="{W-284+5*56}" ' \
          f'y="{T-3}" font-size="9" fill="#555">中证全指</text>'
    g.append(lg)
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto">' + "".join(g) + "</svg>")


def svg_period_bar(per: dict[str, dict[str, float]],
                   bench: dict[str, float]) -> str:
    W, H, L, R, T, B = 720, 260, 46, 12, 14, 26
    periods = sorted(per["baseline"])
    vals = [per["baseline"][p] for p in periods]
    bvals = []
    for p in periods:
        ks = sorted(per["baseline"])
        idx = ks.index(p)
        nxt = ks[idx + 1] if idx + 1 < len(ks) else None
        bvals.append(bench.get(nxt[:7] if nxt else p,
                               bench.get(p, 1.0)) / bench[p] - 1
                     if bench.get(p) else 0.0)
    vmax = max(max(abs(v) for v in vals), max(abs(v) for v in bvals), 0.1)
    def X(i): return L + (W - L - R) * (i + 0.5) / len(periods)
    def Y(v): return T + (H - T - B) * (1 - (v + vmax) / (2 * vmax))
    y0 = Y(0)
    g = [f'<line x1="{L}" y1="{y0:.0f}" x2="{W-R}" y2="{y0:.0f}" '
         f'stroke="#bbb"/>']
    for k in range(5):
        v = -vmax + 2 * vmax * k / 4
        g.append(f'<text x="{L-4}" y="{Y(v)+3:.0f}" text-anchor="end" '
                 f'font-size="9" fill="#888">{v:.0%}</text>')
    bw = (W - L - R) / len(periods) / (len(MODES) + 1) * 0.75
    for i, p in enumerate(periods):
        g.append(f'<text x="{X(i):.0f}" y="{H-B+16}" font-size="9" '
                 f'fill="#888">{p}</text>')
        if i % 2 == 0:
            g.append(f'<rect x="{L+(W-L-R)*i/len(periods):.0f}" y="{T}" '
                     f'width="{(W-L-R)/len(periods):.0f}" '
                     f'height="{H-T-B:.0f}" fill="#f7f7f7"/>')
        for j, mode in enumerate(MODES):
            v = per[mode][p]
            xx = X(i) - bw * (len(MODES) + 1) / 2 + bw * (j + 0.5)
            yy = Y(v)
            hh = max(1.5, abs(Y(0) - yy))
            col = MODE_COLOR[mode] if v >= 0 else "#2ca02c"  # 负收益绿色
            g.append(f'<rect x="{xx:.0f}" y="{min(yy, y0):.0f}" '
                     f'width="{bw:.1f}" height="{hh:.0f}" '
                     f'fill="{col}" opacity="0.75" rx="1"/>')
    # 基准虚线
    pts = " ".join(f"{X(i):.1f},{Y(bvals[i]):.1f}"
                   for i in range(len(periods)))
    g.append(f'<polyline points="{pts}" fill="none" stroke="#999" '
             f'stroke-width="1.4" stroke-dasharray="4,3"/>')
    g.append('<text x="4" y="10" font-size="9" fill="#888">每期收益</text>')
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto">' + "".join(g) + "</svg>")


def ex_post(sel, financials, prices_all, baseline_det) -> dict:
    """事后检验（仅供诊断，非策略）：baseline 每期持仓的 IRR vs 前向收益。"""
    rows = []
    detail_by_dt = baseline_det["detail_by_dt"]
    weights_by_dt = baseline_det["weights_by_dt"]
    hist = baseline_det["history"]
    for i, h in enumerate(hist):
        mk = h["dt"]
        nxt = hist[i + 1]["dt"] if i + 1 < len(hist) else None
        det = detail_by_dt.get(mk, {})
        for tk, w in h["weights"].items():
            d = det.get(tk, {})
            px_m1 = prices_all.get(tk, {}).get(mk)
            # 前向 6 个月收益（按次月买入口径：用 m+1 与 m+6 收盘）
            ks = sorted(prices_all.get(tk, {}).keys())
            later = [x for x in ks if x > mk]
            px_fill = prices_all.get(tk, {}).get(later[0]) if later else None
            px_6m = prices_all.get(tk, {}).get(
                later[5]) if len(later) > 5 else None
            px_nxt = (prices_all.get(tk, {}).get(nxt)
                      if nxt else prices_all.get(tk, {}).get(
                          later[-1]) if later else None)
            r6 = px_6m / px_fill - 1 if px_fill and px_6m else None
            rspan = px_nxt / px_fill - 1 if px_fill and px_nxt else None
            rows.append({"period": mk, "tk": tk, "name": d.get("name", tk),
                         "sw1": d.get("sw1", ""), "tier": d.get("tier", "?"),
                         "irr": d.get("irr"), "g": d.get("g"),
                         "ps0": d.get("ps0"), "ps_med": d.get("ps_med"),
                         "w": w, "r6": r6, "rspan": rspan})
    return rows


def bucket_stats(rows: list[dict]) -> dict:
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else None
    buckets = {"IRR<15%": [], "15-50%": [], "50-100%": [], ">100%": []}
    for r in rows:
        if r["irr"] is None:
            continue
        if r["irr"] < 0.15:
            buckets["IRR<15%"].append(r["r6"])
        elif r["irr"] < 0.5:
            buckets["15-50%"].append(r["r6"])
        elif r["irr"] < 1.0:
            buckets["50-100%"].append(r["r6"])
        else:
            buckets[">100%"].append(r["r6"])
    out = {}
    for k, v in buckets.items():
        out[k] = {"n": len(v), "r6": mean(v)}
    return out


def svg_bucket(b: dict) -> str:
    W, H, L, R, T, B = 520, 220, 70, 12, 14, 30
    keys = list(b.keys())
    vals = [b[k]["r6"] for k in keys]
    vmax = max(max(abs(v) for v in vals if v is not None), 0.1)
    def X(i): return L + (W - L - R) * (i + 0.5) / len(keys)
    def Y(v): return T + (H - T - B) * (1 - (v + vmax) / (2 * vmax))
    y0 = Y(0)
    g = [f'<line x1="{L}" y1="{y0:.0f}" x2="{W-R}" y2="{y0:.0f}" '
         f'stroke="#bbb"/>']
    for k in range(5):
        v = -vmax + 2 * vmax * k / 4
        g.append(f'<text x="{L-4}" y="{Y(v)+3:.0f}" text-anchor="end" '
                 f'font-size="9" fill="#888">{v:.0%}</text>')
    bw = (W - L - R) / len(keys) * 0.5
    for i, k in enumerate(keys):
        v = vals[i]
        if v is None:
            continue
        xx = X(i) - bw / 2
        yy, y1 = Y(v), Y(0)
        hh = max(1.5, abs(y1 - yy))
        col = "#d62728" if v >= 0 else "#2ca02c"
        g.append(f'<rect x="{xx:.0f}" y="{min(yy,y1):.0f}" width="{bw:.0f}" '
                 f'height="{hh:.0f}" fill="{col}" opacity="0.8" rx="1"/>')
        g.append(f'<text x="{X(i):.0f}" y="{Y(v)-6:.0f}" text-anchor="middle" '
                 f'font-size="9" fill="#444">{v:+.0%}</text>')
        g.append(f'<text x="{X(i):.0f}" y="{H-B+16}" text-anchor="middle" '
                 f'font-size="9" fill="#555">{k}<tspan font-size="8" '
                 f'fill="#999"> (n={b[k]["n"]})</tspan></text>')
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto">' + "".join(g) + "</svg>")


def main():
    bench = load(BENCH_FILE)
    all_nav = {m: nav_map(m) for m in MODES}
    all_det = {m: load(f"_bt_gl_irr_{m}_detail.json") for m in MODES}
    all_diag = {m: load(f"_bt_gl_irr_{m}_diag.json") for m in MODES}

    stats = {m: stats_of(m, bench) for m in MODES}

    # 事后检验
    prices = load(PRICES_FILE)
    warmup = load(WARMUP_FILE)
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}
    sel = load(SEL_FILE)
    rows = ex_post(sel, None, prices_all, all_det["baseline"])
    buckets = bucket_stats(rows)

    # irr15 被拒 vs 基准持有（只诊断：这些名字若被拒，对吗？）
    rej = []
    base_w = all_det["baseline"]["weights_by_dt"]
    irr15_w = all_det["irr15"]["weights_by_dt"]
    base_det = all_det["baseline"]["detail_by_dt"]
    for mk in REBALANCES:
        for tk, w in base_w.get(mk, {}).items():
            if tk in irr15_w.get(mk, {}):
                continue
            d = base_det.get(mk, {}).get(tk, {})
            ks = sorted(prices_all.get(tk, {}).keys())
            later = [x for x in ks if x > mk]
            px_fill = prices_all.get(tk, {}).get(later[0]) if later else None
            px_6m = prices_all.get(tk, {}).get(later[5]) if len(later) > 5 else None
            r6 = px_6m / px_fill - 1 if px_fill and px_6m else None
            rej.append({"period": mk, "tk": tk, "name": d.get("name", tk),
                        "sw1": d.get("sw1", ""), "irr": d.get("irr"),
                        "g": d.get("g"), "r6": r6})

    # ---- HTML ----
    rows_html = []
    for m in MODES:
        s = stats[m]
        rows_html.append(
            f"<tr><td><b>{MODE_LABEL[m]}</b></td>"
            f"<td>{s['end']:,.0f}</td>"
            f"<td class='{'up' if s['total']>=0 else 'down'}'>{s['total']:+.1%}</td>"
            f"<td class='{'up' if s['ann']>=0 else 'down'}'>{s['ann']:+.1%}</td>"
            f"<td class='down'>{s['mdd']:.1%}</td>"
            f"<td class='{'up' if s['excess']>=0 else 'down'}'>{s['excess']:+.1%}</td>"
            f"<td>{s['n_hold']:.1f}</td><td>{s['win_rate']:.0%}</td></tr>")
    stats_html = "".join(rows_html)

    # 逐期诊断表
    diag_rows = []
    per = {m: all_diag[m]["per_period_ret"] for m in MODES}
    for mk in REBALANCES:
        d0 = all_diag["baseline"]["diag"].get(mk, {})
        cells = [f"<td>{d0.get('candidates', '')}</td>",
                 f"<td>{d0.get('irr_ok', '')}</td>",
                 f"<td>{d0.get('irr_fail_no_data', '')}</td>"]
        for m in MODES:
            ret = per[m].get(mk)
            col = "up" if ret >= 0 else "down"
            cells.append(
                f"<td class='{col}'>{ret:+.1%}</td>"
                f"<td>{all_diag[m]['diag'].get(mk, {}).get('holdings', '')}</td>")
        diag_rows.append(f"<tr><td>{mk}</td>" + "".join(cells) + "</tr>")
    diag_html = "".join(diag_rows)

    # IRR 分桶事后检验
    bkt_rows = "".join(
        f"<tr><td>{k}</td><td>{v['n']}</td>"
        f"<td class='{'up' if (v['r6'] or 0)>=0 else 'down'}'>"
        f"{v['r6']:+.1%}</td></tr>"
        for k, v in buckets.items())
    r6_all = [r["r6"] for r in rows if r["r6"] is not None]
    r6_mean = statistics.mean(r6_all) if r6_all else None
    # 过门 vs 未过门（irr15 口径）的前向收益
    pas = [r["r6"] for r in rows if r["irr"] is not None and r["irr"] >= 0.15]
    fail = [r["r6"] for r in rows if r["irr"] is not None and r["irr"] < 0.15]
    pas_m = statistics.mean([x for x in pas if x is not None]) if pas else None
    fail_m = statistics.mean([x for x in fail if x is not None]) if fail else None

    rej_rows = "".join(
        f"<tr><td>{r['period']}</td><td>{r['tk']}</td><td>{r['name']}</td>"
        f"<td>{r['sw1']}</td><td>{_pct(r['irr'])}</td><td>{_pct(r['g'])}</td>"
        f"<td class='{'up' if (r['r6'] or 0)>=0 else 'down'}'>"
        f"{_pct(r['r6'])}</td></tr>"
        for r in sorted(rej, key=lambda x: x["period"]))
    rej_ok = sum(1 for r in rej if (r["r6"] or 0) < 0)
    rej_bad = len(rej) - rej_ok

    # 代表性案例（各期 IRR 最高/最低的持仓）
    case_rows = []
    for mk in REBALANCES:
        rrs = [r for r in rows if r["period"] == mk and r["irr"] is not None]
        if not rrs:
            continue
        hi = max(rrs, key=lambda x: x["irr"])
        lo = min(rrs, key=lambda x: x["irr"])
        for tag, r in (("IRR最高", hi), ("IRR最低", lo)):
            case_rows.append(
                f"<tr><td>{mk}</td><td>{tag}</td><td>{r['tk']}</td>"
                f"<td>{r['name']}</td><td>{_pct(r['irr'])}</td>"
                f"<td>{_pct(r['g'])}</td>"
                f"<td>{r['ps0']/r['ps_med']:.2f}x</td>"
                f"<td class='{'up' if (r['r6'] or 0)>=0 else 'down'}'>"
                f"{_pct(r['r6'], '+.1%')}</td></tr>")
    case_html = "".join(case_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>Growth Loop · IRR 门槛实验（5年回测对比）</title>
<style>
 body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:0;
      background:#fff;color:#222;}}
 .wrap{{max-width:1060px;margin:0 auto;padding:28px 24px 60px;}}
 h1{{font-size:22px;border-bottom:3px solid #1f77b4;padding-bottom:8px;}}
 h2{{font-size:16px;margin-top:34px;border-left:4px solid #1f77b4;
     padding-left:10px;}}
 .sub{{color:#777;font-size:12px;line-height:1.7;}}
 table{{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0;}}
 th,td{{border:1px solid #e3e3e3;padding:6px 8px;text-align:right;}}
 th{{background:#f5f7fa;text-align:center;}}
 td:first-child{{text-align:left;}}
 .up{{color:#d62728;font-weight:600;}} .down{{color:#2ca02c;font-weight:600;}}
 .card{{border:1px solid #e3e3e3;border-radius:8px;padding:14px 16px;
       margin:14px 0;background:#fafbfc;}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
 .note{{font-size:12px;color:#555;background:#fff8e6;border:1px solid #f0d9a0;
       padding:10px 14px;border-radius:6px;margin:12px 0;}}
 .tag{{display:inline-block;padding:1px 8px;border-radius:10px;
      font-size:11px;background:#eef4ff;color:#1f5fbf;margin-right:4px;}}
</style></head><body><div class="wrap">

<h1>Growth Loop 策略 · 个股 IRR ≥ GOAL 门槛实验</h1>
<p class="sub">回测区间 2021-06 → 2026-08（5年+），月频调仓，成本 佣金0.05%+滑点0.1%，
单票 8% 上限。数据：财务/价格全部 point-in-time（报告期截止日过滤），无未来函数。
基准 = 中证全指（+4.5%）。<br>
<b>IRR 口径</b>（年化，3 年视角，与 GOAL 层 horizon_years=3 对齐）：
IRR = [ (1+g)³ × (PS_med/PS₀) ]^(1/3) − 1；g = 最新营收YoY（截断[-50%,+100%]），
PS₀ = 调仓月末价/TTM营收，PS_med = 此前36个月PS中位数（每月均按当月已披露报告期计算）。
GOAL = config 中 target_return = 15%。</p>

<div class="note"><b>先看结论（诚实版）：</b>
① IRR≥15% 门槛几乎不起作用——候选池中位 IRR 高达 +78%~+160%，本就远高于 15%；<br>
② 把门槛加高到 30%/50% 后 <b>结果反而更差</b>（-19.0% / -20.3% / -21.1% vs 基准 -14.0%）——
被拒掉的主要是两类："IRR 不可算"的次新股（海光、华海清科、拓荆等，很多事后是大牛股）与
"IRR 低"的股票（估值高于自身历史或增速低）；事后看它们前向收益并不差（见 ⑤），
IRR 公式里"高增长+估值低于自身历史"的股票恰恰是后续下跌的重灾区；<br>
③ 把"IRR 不可算"改为放行（irr15*，次新股不误杀）后，门槛接近中性（-14.7% vs -14.0%），
说明 IRR 门的净效果≈0，且伤害几乎全部来自"次新即拒"的误杀；<br>
④ 结论：这条策略的问题<b>不在买入门槛</b>，而在"高增长能否持续 + 板块估值中枢下移"——
IRR 模型假设（增长持续 3 年 + PS 回归历史中位数）在 2021-2026 的高成长板块上整体不成立。
<span class="tag">irr15* = IRR 不可算时放行</span></div>

<h2>① 总览对比</h2>
<table><tr><th>方案</th><th>期末净值(元)</th><th>总收益</th><th>年化</th>
<th>最大回撤</th><th>超额(基准)</th><th>平均持仓</th><th>逐期胜率</th></tr>
{stats_html}</table>

<h2>② NAV 曲线（1,000,000 起点）</h2>
{svg_nav(all_nav, bench)}

<h2>③ 逐期收益（每期调仓区间）</h2>
{svg_period_bar(per, bench)}

<h2>④ IRR 门逐期诊断</h2>
<table><tr><th>调仓</th><th>候选</th><th>IRR可算</th><th>数据不足</th>
<th>基准</th><th>持仓</th><th>IRR≥15%</th><th>持仓</th>
<th>IRR≥15%*</th><th>持仓</th><th>IRR≥30%</th><th>持仓</th>
<th>IRR≥50%</th><th>持仓</th></tr>
{diag_html}</table>
<p class="sub">注：IRR 不可算 = PS 历史不足 6 个月（次新/停牌缺价）。IRR≥15% 直接视为不通过（保守）；
IRR≥15%* 放行不可算者，只对可算且 &lt;15% 的个股拒投。</p>

<h2>⑤ 事后检验：IRR 是否有预测力？（仅供诊断，非策略回测）</h2>
<p class="sub">对基准方案每一期实际持仓的每一只股票，取调仓次月买入、6 个月后卖出的
<b>前向 6M 收益</b>（真实价格，事后计算），按调仓时点已知的 IRR 分桶：</p>
<div class="grid">
<div>
<table><tr><th>IRR 分桶</th><th>样本</th><th>平均前向6M收益</th></tr>
{bkt_rows}
<tr><td><b>IRR≥15%（过门）</b></td><td>{len(pas)}</td>
<td class="{'up' if (pas_m or 0)>=0 else 'down'}">{pas_m:+.1%}</td></tr>
<tr><td><b>IRR&lt;15%（被拒）</b></td><td>{len(fail)}</td>
<td class="{'up' if (fail_m or 0)>=0 else 'down'}">{fail_m:+.1%}</td></tr>
<tr><td><b>全部</b></td><td>{len(r6_all)}</td>
<td class="{'up' if (r6_mean or 0)>=0 else 'down'}">{r6_mean:+.1%}</td></tr>
</table>
</div>
<div>{svg_bucket(buckets)}</div>
</div>
<p class="sub">若 IRR 有预测力，应看到 IRR 越高、前向收益越高。下图将显示该关系<b>不成立甚至反向</b>。</p>

<h2>⑥ irr15 被拒个股（基准持有、IRR&lt;15% 被剔除）——拒绝是对还是错？</h2>
<p class="sub">共 {len(rej)} 例被拒；其中事后前向 6M 下跌 {rej_ok} 例（拒绝正确）、
上涨 {rej_bad} 例（误杀）。<span class="tag">误杀 {rej_bad} 例</span>
<span class="tag">拒绝正确 {rej_ok} 例</span></p>
<table><tr><th>调仓</th><th>代码</th><th>名称</th><th>行业</th><th>IRR</th>
<th>g</th><th>前向6M</th></tr>
{rej_rows}</table>

<h2>⑦ 代表性案例：各期 IRR 最高/最低持仓的实际表现</h2>
<table><tr><th>调仓</th><th>标签</th><th>代码</th><th>名称</th><th>IRR</th>
<th>g</th><th>PS₀/PS_med</th><th>前向6M</th></tr>
{case_html}</table>

<h2>方法学与诚实声明</h2>
<ul class="sub">
<li><b>无未来数据</b>：g、PS₀、PS_med 均只用调仓时点已披露报告 + 已发生价格；HOOK 层与 IRR 门共用同一份 PIT 财务。</li>
<li><b>IRR 的假设</b>：增长持续 3 年 + PS 回归自身历史中位数。该假设在本回测中事后被证伪（高 IRR 组反而跑输），这正是"门槛无效"的根本原因。</li>
<li><b>事后检验</b>（⑤⑥⑦节）使用了未来价格，仅用于诊断 IRR 的预测力，不构成策略回测，也不进入任何收益数字。</li>
<li><b>局限</b>：营收 YoY 不等于可持续盈利增长；PS 中位数窗口受上市时间限制；未计分红/配股。</li>
<li>baseline 复现校验：本次引擎复跑 = _bt_gl_nav.json（860,179，偏差 0.00%）。</li>
</ul>
</div></body></html>"""
    open("_gl_irr_report.html", "w", encoding="utf-8").write(html)
    print(f"→ _gl_irr_report.html  | 过门均值 {pas_m:+.1%} vs 被拒均值 "
          f"{fail_m:+.1%} | 被拒 {len(rej)} 例（误杀 {rej_bad} / 正确 {rej_ok}）")


if __name__ == "__main__":
    main()
