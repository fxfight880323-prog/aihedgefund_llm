# -*- coding: utf-8 -*-
"""L5 增速门控放松 × 当前时点 (2026-08-24) 名单。
复用 _lx_now_screen.py 的当前时点数据文件，重跑 g40 / garp 两个最优门控变体，
检查紫金矿业 (601899.SH) 的位置，输出 top40 推荐名单。
"""
import json, os, sys, statistics

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"
UNIV_FILE = "_bt_lx_now_universe.json"
FIN_FILE = "_bt_sw_fin_universe.json"

PE_CEIL = 25.0
DIV_YIELD = 0.02
PEG_CEIL = 2.0
MIN_MV_YI = 100.0
MAX_HOLDINGS = 40

# 变体 → (增速上限, PEG上限, 名称, 排序键)
VARIANTS = {
    "core_finex": (25.0, 2.0, "基线 core_finex (L5 增速≤25% + PEG≤2)", "pe"),
    "g40":        (40.0, 2.0, "g40 (增速≤40% + PEG≤2)", "pe"),
    "garp":       (60.0, 1.0, "garp (增速≤60% + PEG≤1)", "pe"),
    "garp_q20":   (60.0, 1.0, "garp+q20 (增速≤60% + PEG≤1, 80%PE+20%质量)", "blend20"),
}


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
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


def load_fin_set():
    d = json.loads(open(FIN_FILE, encoding="utf-8").read())
    out = set()
    for sec, info in d.items():
        if isinstance(info, dict) and isinstance(info.get("members"), list):
            out.update(info["members"])
    return out


def fetch_tencent(codes, batch=100):
    def _prefix(c):
        if c.startswith(("6", "9")):
            return "sh"
        if c.startswith(("8", "4")):
            return "bj"
        return "sz"
    import urllib.request
    out = {}
    for i in range(0, len(codes), batch):
        q = ",".join(f"{_prefix(c)}{c.split('.')[0]}" for c in codes[i:i + batch])
        try:
            req = urllib.request.Request(f"https://qt.gtimg.cn/q={q}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("gbk", "ignore")
            for line in body.strip().split(";"):
                if "=" not in line or '"' not in line:
                    continue
                raw = line.split("=")[0].strip().replace("v_", "")
                for p in ("sh", "sz", "bj"):
                    if raw.startswith(p):
                        code = raw[len(p):]
                        break
                else:
                    code = raw
                f = line.split('"')[1].split("~")
                name = f[1] if len(f) > 1 else ""
                price = float(f[3]) if len(f) > 3 else 0.0
                out[code] = (name, price)
        except Exception as e:
            print(f"  tencent batch {i} 失败: {str(e)[:80]}")
    return out


def main():
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    fac, fac_asof = load_map(FAC_FILE)
    cons, cons_asof = load_map(CONS_FILE)
    as_of = univ.get("as_of")
    members = univ.get("members", [])
    fin_set = load_fin_set()
    print(f"as_of={as_of} | univ={len(members)} | 金融剔除={len(fin_set)}")

    # ---- 筛选：每个变体独立的 L5 门控 ----
    pools = {v: [] for v in VARIANTS}   # v -> list of dict
    stats = {v: {} for v in VARIANTS}
    gpm_vals_all = []
    for sc in members:
        if sc in fin_set:
            continue
        tk = code_to_tk(sc)
        if not tk:
            continue
        v = val.get(sc) or {}
        f = fac.get(sc) or {}
        c = cons.get(sc) or {}

        mv = _num(v.get("total_mv"))
        pe = _num(v.get("pe_ttm"))
        dy = _num(f.get("dtop5"))
        if dy is not None and dy >= 0.5:
            dy = None
        exp_g = _num(c.get("con_np_yoy"))
        peg = _num(c.get("con_peg"))
        con_roe = _num(c.get("con_roe"))
        cetop = _num(f.get("cetop"))
        gpm = _num(f.get("gpm"))

        if mv is None or mv < MIN_MV_YI * 10000:
            continue
        if pe is None or pe <= 0:
            continue
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            continue
        # 无 gpm 或 cetop 的跳过（评分/质量需要）
        if gpm is not None:
            gpm_vals_all.append(gpm)

        row = {"tk": tk, "code": sc, "mv": mv, "pe": pe, "dy": dy,
               "exp_g": exp_g, "peg": peg, "con_roe": con_roe,
               "cetop": cetop, "gpm": gpm}

        for v, (g_ceil, peg_ceil, _, sort_key) in VARIANTS.items():
            l5 = (exp_g is not None and exp_g <= g_ceil
                  and peg is not None and 0 < peg <= peg_ceil)
            if l5:
                pools[v].append(row)

    gmed = statistics.median(gpm_vals_all) if gpm_vals_all else None
    print(f"gpm 中位数(全市场): {gmed:.1f}%")

    # ---- 每变体: 排序 top40 ----
    tq = fetch_tencent(sorted({r["code"] for v in pools for r in pools[v]}))
    print(f"tencent 名称: {len(tq)}")

    # 混合排序需要池内百分位
    def pct_rank(vals, v):
        vals = [x for x in vals if x is not None]
        n = len(vals)
        if n == 0 or v is None:
            return 50.0
        return sum(1 for x in vals if x < v) / n * 100.0

    results = {}
    for v, (g_ceil, peg_ceil, label, sort_key) in VARIANTS.items():
        pool = pools[v]
        if sort_key == "blend20":
            gpm_v = [r["gpm"] for r in pool]
            roe_v = [r["con_roe"] for r in pool]
            cet_v = [r["cetop"] for r in pool]
            pe_v = [r["pe"] for r in pool]
            for r in pool:
                q = (pct_rank(gpm_v, r["gpm"]) + pct_rank(roe_v, r["con_roe"])
                     + pct_rank(cet_v, r["cetop"])) / 3.0
                r["q_score"] = q
                r["pe_pct"] = 100.0 - pct_rank(pe_v, r["pe"])
                r["blend20"] = 0.8 * r["pe_pct"] + 0.2 * q
            pool.sort(key=lambda r: -r["blend20"])
        else:
            pool.sort(key=lambda r: r["pe"])
        n_pool = len(pool)
        picked = pool[:MAX_HOLDINGS]
        # 紫金矿业位置
        zj_rank = None
        for i, r in enumerate(pool, 1):
            if "601899" in r["code"]:
                zj_rank = i
                break
        rows = []
        for i, r in enumerate(picked, 1):
            code = r["code"].split(".")[0]
            name, price = tq.get(code, ("", None))
            rows.append({
                "rank": i, "code": r["code"], "name": name, "price": price,
                "mv_yi": round(r["mv"] / 10000, 1),
                "pe": round(r["pe"], 1),
                "dy": round(r["dy"] * 100, 2) if r["dy"] is not None else None,
                "exp_g": round(r["exp_g"], 1) if r["exp_g"] is not None else None,
                "peg": round(r["peg"], 2) if r["peg"] is not None else None,
                "con_roe": round(r["con_roe"], 1) if r["con_roe"] is not None else None,
                "gpm": round(r["gpm"], 1) if r["gpm"] is not None else None,
                "cetop": round(r["cetop"] * 100, 2) if r["cetop"] is not None else None,
                "in_gm": r["gpm"] is not None and r["gpm"] >= gmed,
            })
        results[v] = {"label": label, "g_ceil": g_ceil, "peg_ceil": peg_ceil,
                      "n_pool": n_pool, "n_pick": len(rows), "rows": rows,
                      "zj_rank": zj_rank}
        print(f"\n=== {v} ({label}) — 池 {n_pool} 只 | top{len(rows)} ===")
        if zj_rank:
            print(f"  紫金矿业 池内排名: {zj_rank}/{n_pool} "
                  f"{'✅ 进 top40' if zj_rank <= 40 else '❌ 未进'}")
        for r in rows[:15]:
            print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8} "
                  f"PE {r['pe']:>6.1f} | 增速 {r['exp_g'] or 0:>5.1f}% | "
                  f"PEG {r['peg'] or 0:>4.2f} | ROE {r['con_roe'] or 0:>4.1f} | "
                  f"毛利 {r['gpm'] or 0:>4.1f}%")

    # 紫金矿业全档案
    print(f"\n=== 紫金矿业 (601899.SH) 档案 ===")
    for sc, r in val.items():
        if "601899" in sc:
            print(f"  估值: PE_TTM={r.get('pe_ttm'):.2f} PB={r.get('pb'):.2f} "
                  f"总市值={r.get('total_mv')/10000:.0f}亿")
    for sc, r in fac.items():
        if "601899" in sc:
            print(f"  因子: gpm={r.get('gpm'):.2f}% cetop={r.get('cetop')*100:.2f}% "
                  f"npyoy={r.get('npyoy')*100:.1f}% dy={r.get('dtop5')*100:.2f}%")
    for sc, r in cons.items():
        if "601899" in sc:
            print(f"  一致预期: con_roe={r.get('con_roe'):.2f}% "
                  f"增速={r.get('con_np_yoy'):.1f}% PEG={r.get('con_peg'):.2f} "
                  f"con_pe={r.get('con_pe'):.2f}")

    out = {"as_of": as_of, "variants": results}
    json.dump(out, open("_bt_garp_now.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n→ _bt_garp_now.json")


if __name__ == "__main__":
    main()
