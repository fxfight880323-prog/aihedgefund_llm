# -*- coding: utf-8 -*-
"""core vs LX-gm(质量过滤版) 名单重现 + 对齐校验。

用历史期全市场数据（universe/valuation/factors/consensus，10期）+ garp 门控
（与 _lx_now_screen_kfin.py 完全同条件）重现每期 core 全命中列表，
与官方 _bt_band_results.json weights.core 的 top40 对齐校验，
然后生成 gm（core + gpm≥全市场中位数）版 top40 名单。

输出:
  _bt_gm_weights.json  { 'core': {period:[tk...]}, 'gm': {period:[tk...]},
                         'meta': 每期漏斗+中位数+重叠 }
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter

PE_CEIL = 25.0
DIV_YIELD = 0.02
EXP_G_CEIL = 60.0
PEG_CEIL = 1.0
MIN_MV_YI = 100.0
MAX_HOLDINGS = 40

UNIV = "_bt_winda_universe.json"
VAL = "_bt_lx_allA_valuation.json"
FAC = "_bt_lx_allA_factors.json"
CONS = "_bt_winda_consensus.json"
OFFICIAL = "_bt_band_results.json"


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def tk_of(sc: str) -> str:
    if "." not in sc:
        return ""
    code, mkt = sc.split(".")
    if code[0] == "6":
        return f"{code}.SH"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return f"{code}.BJ"


def load_map(path: str) -> dict[str, dict[str, dict]]:
    d = json.loads(open(path, encoding="utf-8").read())
    out = {}
    for month, m in d.items():
        rec = {}
        for r in m.get("records", []):
            sc = r.get("stock_code", "")
            tk = tk_of(sc)
            if tk:
                rec[tk] = r
        out[month] = rec
    return out


def load_consensus() -> dict[str, dict[str, dict]]:
    cons = json.loads(open(CONS, encoding="utf-8").read())
    out = {}
    for month, d in cons.items():
        as_of_year = int(month[:4])
        best = {}
        for r in d.get("records", []):
            tk = tk_of(r.get("stock_code", ""))
            if not tk:
                continue
            cy = r.get("con_year") or 0
            def dist(y):
                if y == as_of_year:
                    return 0
                if y == as_of_year + 1:
                    return 1
                return 2 + abs((y or 0) - as_of_year)
            if tk not in best or dist(cy) < dist(best[tk].get("con_year") or 0):
                best[tk] = r
        out[month] = best
    return out


def screen_period(month: str, univ_members: list[str], val: dict, fac: dict,
                  cons: dict) -> dict:
    stats = Counter()
    stats["univ"] = len(univ_members)
    passed = []
    gpm_vals = []
    for sc in univ_members:
        tk = tk_of(sc)
        if not tk:
            continue
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}
        mv = _num(v.get("total_mv"))
        pe = _num(v.get("pe_ttm"))
        dy = _num(f.get("dtop5"))
        if dy is not None and dy >= 0.5:
            dy = None
        exp_g = _num(c.get("con_np_yoy"))
        peg = _num(c.get("con_peg"))
        gpm = _num(f.get("gpm"))
        if mv is None or mv < MIN_MV_YI * 10000:
            continue
        if pe is None or pe <= 0:
            continue
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            continue
        l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
              and peg is not None and 0 < peg <= PEG_CEIL)
        if not l5:
            continue
        if gpm is None:
            stats["gpm_missing"] += 1
            continue
        gpm_vals.append(gpm)
        passed.append((tk, {"mv": mv, "pe": pe, "dy": dy, "exp_g": exp_g,
                            "peg": peg, "gpm": gpm}))
    gmed = statistics.median(gpm_vals) if gpm_vals else None
    passed.sort(key=lambda x: x[1]["pe"])
    passed_gm = [p for p in passed if p[1]["gpm"] >= gmed]
    stats["core_pass"] = len(passed)
    stats["gm_pass"] = len(passed_gm)
    stats["gpm_median"] = gmed
    return {
        "core": [tk for tk, _ in passed[:MAX_HOLDINGS]],
        "gm": [tk for tk, _ in passed_gm[:MAX_HOLDINGS]],
        "stats": dict(stats),
    }


def main():
    univ = json.loads(open(UNIV, encoding="utf-8").read())
    val = load_map(VAL)
    fac = load_map(FAC)
    cons = load_consensus()

    official = json.loads(open(OFFICIAL, encoding="utf-8").read())
    off_core = official["weights"]["core"]
    periods = sorted(off_core.keys())

    out = {"core": {}, "gm": {}, "meta": {}}
    print(f"{'期':<9} {'命中':>4} {'gm':>4} {'gpm中位':>7} "
          f"{'core40∩官方':>9} {'gm40∩core40':>11}")
    tot_inter = tot_gm_inter = 0
    for p in periods:
        members = univ.get(p, {}).get("members", [])
        r = screen_period(p, members, val[p], fac[p], cons[p])
        out["core"][p] = r["core"]
        out["gm"][p] = r["gm"]
        out["meta"][p] = r["stats"]
        off40 = set(off_core.get(p, []))
        inter = len(set(r["core"]) & off40)
        gm_inter = len(set(r["gm"]) & set(r["core"]))
        tot_inter += inter
        tot_gm_inter += gm_inter
        s = r["stats"]
        print(f"{p:<9} {s['core_pass']:>4} {s['gm_pass']:>4} "
              f"{s['gpm_median']:>7.2f} {inter:>7}/40 {gm_inter:>9}/40")
    print(f"\n平均: core∩官方 {tot_inter/len(periods):.1f}/40 | gm∩core {tot_gm_inter/len(periods):.1f}/40")
    json.dump(out, open("_bt_gm_weights.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("saved _bt_gm_weights.json")


if __name__ == "__main__":
    main()
