# -*- coding: utf-8 -*-
"""光模块(光通信概念) + 申万半导体 × dist52 锚定检查 + 刘旭框架适配
数据: 腾讯真实行情(日K前复权 + 实时快照), 刘旭面板缓存 as_of 2026-08-20
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "C:/Users/xfugm/.workbuddy/workspace/files/199120/04e4ceba-d58a-4c80-b97b-91489245c977/"

# ---- 光通信概念成分(聚源, 2026-08-23, 81只) ----
OPTICAL = """sh603991,sh600498,sh600522,sh688498,sz002428,sh688195,sh603042,sh688400,
sz300565,sh688048,sz300408,sh688685,sh688172,sz300292,sh603052,sh688808,sz300757,
sz300395,sz300217,sz300698,sz002436,sz002222,sh603083,sz000936,sz002860,sz000988,
sh600103,sh600345,sz300447,sz301486,sz000586,sz002579,sz300265,sz002281,sz002313,
sz000070,sz003031,sh603688,sz002309,sh688609,sh688418,sz001309,sh603690,sz300843,
sh688313,sh600353,sz300504,sz000801,sh600246,sz300710,sz002962,sz300570,sh603618,
sz300738,sz300502,sz300252,sh600105,sz300548,sz002491,sz300394,sz300620,sz300308,
sz002902,sh601869,sz002988,sh600330,sz300123,sz002025,sz002792,sz002725,sh603803,
sz300814,sh688205,sz000063,sz002179,sh600703,sh688025,sh600487,sz301183,sz300184,sz002897"""

# ---- 申万二级行业 半导体 成分(186只, 2026-08-23) ----
SEMI = """sh688593,sh688807,sh688072,sz300053,sz300661,sh688601,sh688689,sz003043,sz301717,
sh688396,sh688729,sh688825,sh688809,sz300373,sh688380,sz002119,sh600206,sh688401,
sh688605,sh688049,sh688766,sh688052,sh688608,sh688325,sh688469,sh600641,sh688153,
sh688515,sh688372,sh688802,sh688409,sh603316,sh688416,sh603005,sh688728,sz300672,
sh688146,sh688478,sh688702,sh688530,sz300623,sh688797,sh688249,sh688795,sh688419,
sh688368,sh688002,sh688785,sh688484,sh600171,sz002213,sh688200,sh688262,sh688138,
sz002077,sh688508,sh688048,sh688709,sh688449,sh688361,sh603501,sh603893,sh688018,
sz300604,sh688727,sh688691,sh688981,sh605111,sh688498,sz002049,sh688045,sh688279,
sz301348,sh688220,sz301678,sh688783,sh688012,sh603068,sh688535,sz001309,sh603690,
sh688234,sh688008,sz301308,sh603986,sz301666,sh600877,sz002409,sz300456,sh688107,
sh688521,sz300666,sh688123,sh603991,sh688167,sh688525,sz301583,sh688286,sh688486,
sh688362,sh688653,sh688591,sz002185,sh688820,sh688391,sh688595,sh688270,sz301297,
sh688582,sh688352,sz301629,sh688037,sh688209,sh688233,sh688061,sh603290,sh688720,
sh688711,sz300782,sh688332,sz300077,sh603061,sh688261,sh688652,sh688135,sz301536,
sh603160,sz300327,sh600460,sz300831,sh688512,sz003026,sz300613,sh688661,sh688126,
sh688385,sh688536,sh688347,sh688721,sh688432,sz002371,sh605358,sh688584,sh688041,
sh688082,sh600360,sz300223,sz300706,sh688252,sh600745,sz301611,sh688693,sh688099,
sz301369,sh688110,sh688230,sh688047,sh688172,sh688173,sh688699,sz002156,sz300671,
sh688141,sh688213,sh688790,sh688458,sh688130,sh688256,sh688381,sh688216,sh600584,
sz300458,sz300046,sh603375,sh688120,sh688403,sh688798,sh688259,sh688620,sh688589"""

# 光模块主链核心(人工标注)
OPTICAL_CORE = {"300308", "300502", "300394", "002281", "000988", "603083", "300570",
                "688205", "301205", "688313", "300548", "300620", "688498", "002902",
                "688195", "301183", "688807", "688808", "003031", "300757"}


def to_tk(sym):
    mkt, code = sym[:2], sym[2:]
    suf = {"sh": ".SH", "sz": ".SZ", "bj": ".BJ"}[mkt]
    return code + suf


opt_syms = [s.strip() for s in OPTICAL.replace("\n", "").split(",") if s.strip()]
semi_syms = [s.strip() for s in SEMI.replace("\n", "").split(",") if s.strip()]
print(f"光通信概念 {len(opt_syms)} 只, 申万半导体 {len(semi_syms)} 只")

# ---------- 1. 腾讯快照: 名称/现价/PE/总市值 ----------
def fetch_quote(syms):
    out = {}
    for i in range(0, len(syms), 60):
        q = ",".join(syms[i:i + 60])
        try:
            req = urllib.request.Request(f"https://qt.gtimg.cn/q={q}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("gbk", "ignore")
            for line in body.strip().split(";"):
                if "=" not in line or '"' not in line:
                    continue
                sym = line.split("=")[0].strip().replace("v_", "")
                f = line.split('"')[1].split("~")
                if len(f) < 46:
                    continue
                def num(idx):
                    try:
                        return float(f[idx])
                    except Exception:
                        return None
                out[sym] = {"name": f[1], "price": num(3), "pe": num(39),
                            "mv_yi": num(45), "pct_chg": num(32)}
        except Exception as e:
            print(f"  quote batch {i} fail: {str(e)[:60]}")
    return out


quotes = fetch_quote(opt_syms + semi_syms)
print(f"quotes: {len(quotes)}")

# ---------- 2. 日K → dist52 ----------
def fetch_k(sym):
    url = (f"https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,,,270,qfq")
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15)
            data = json.loads(r.read().decode("utf-8"))["data"][sym]
            rows = data.get("qfqday") or data.get("day") or []
            if not rows:
                return sym, None
            rows = rows[-250:]
            highs = [float(x[3]) for x in rows]
            lows = [float(x[4]) for x in rows]
            closes = [float(x[2]) for x in rows]
            hi52, lo52, cur = max(highs), min(lows), closes[-1]
            return sym, {"hi52": hi52, "lo52": lo52, "cur": cur,
                         "dist52": cur / hi52 if hi52 > 0 else None,
                         "last_date": rows[-1][0]}
        except Exception:
            if attempt == 2:
                return sym, None
            time.sleep(1)


kdata = {}
all_syms = sorted(set(opt_syms + semi_syms))
with ThreadPoolExecutor(max_workers=10) as ex:
    futs = {ex.submit(fetch_k, s): s for s in all_syms}
    for i, f in enumerate(as_completed(futs), 1):
        s, v = f.result()
        if v:
            kdata[s] = v
        if i % 50 == 0:
            print(f"  kline {i}/{len(all_syms)}")
print(f"kline ok: {len(kdata)}/{len(all_syms)}")

# ---------- 3. 刘旭面板(as_of 2026-08-20) 检查 LX-core 适配 ----------
def load_map(path):
    d = json.loads(open(BASE + path, encoding="utf-8").read())
    return {r.get("stock_code"): r for r in d.get("records", [])}

val = load_map("_bt_lx_now_valuation.json")
fac = load_map("_bt_lx_now_factors.json")
cons = load_map("_bt_lx_now_consensus.json")

def num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None

def lx_check(tk):
    """返回 (通过与否, 卡在哪层, 关键数据)"""
    v = val.get(tk) or {}
    f = fac.get(tk) or {}
    c = cons.get(tk) or {}
    mv = num(v.get("total_mv"))
    pe = num(v.get("pe_ttm"))
    dy = num(f.get("dtop5"))
    exp_g = num(c.get("con_np_yoy"))
    peg = num(c.get("con_peg"))
    if mv is None:
        return False, "无数据", {}
    if mv < 100 * 10000:
        return False, "市值<100亿", {}
    if pe is None or pe <= 0:
        return False, "PE≤0", {}
    if not (pe <= 25 or (dy is not None and dy >= 0.02)):
        return False, "L4估值", {}
    if not (exp_g is not None and exp_g <= 25 and peg is not None and 0 < peg <= 2):
        return False, "L5预期", {}
    return True, "PASS", {"pe": pe, "dy": dy, "exp_g": exp_g, "peg": peg}


# ---------- 4. 汇总 ----------
def tier(d):
    if d is None:
        return "?"
    if d >= 0.95: return "贴近高点"
    if d >= 0.85: return "较近"
    if d >= 0.70: return "中等"
    return "过远"

def build(syms, sector):
    rows = []
    for sym in syms:
        q = quotes.get(sym, {})
        k = kdata.get(sym)
        if not k or not k.get("dist52"):
            continue
        tk = to_tk(sym)
        ok, stage, lx = lx_check(tk)
        rows.append({
            "sym": sym, "code": tk, "name": q.get("name", ""),
            "is_core": sym[2:] in OPTICAL_CORE if sector == "光模块/光通信" else False,
            "price": k["cur"], "hi52": k["hi52"], "lo52": k["lo52"],
            "dist52": k["dist52"], "tier": tier(k["dist52"]),
            "pe": q.get("pe"), "mv_yi": q.get("mv_yi"),
            "lx_pass": ok, "lx_stage": stage,
            "lx_pe": lx.get("pe"), "lx_dy": lx.get("dy"),
            "lx_exp_g": lx.get("exp_g"), "lx_peg": lx.get("peg"),
            "last_date": k["last_date"],
        })
    rows.sort(key=lambda r: -r["dist52"])
    return rows

opt_rows = build(opt_syms, "光模块/光通信")
semi_rows = build(semi_syms, "半导体")

def stats(rows):
    out = {}
    for t in ["贴近高点", "较近", "中等", "过远"]:
        out[t] = sum(1 for r in rows if r["tier"] == t)
    ds = sorted(r["dist52"] for r in rows)
    out["median"] = ds[len(ds) // 2]
    out["n"] = len(rows)
    return out

out = {"sector_optical": {"rows": opt_rows, "stats": stats(opt_rows)},
       "sector_semi": {"rows": semi_rows, "stats": stats(semi_rows)}}
json.dump(out, open(BASE + "_sector_dist52.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

for nm, sec in [("光模块/光通信", out["sector_optical"]), ("半导体", out["sector_semi"])]:
    s = sec["stats"]
    lx_n = sum(1 for r in sec["rows"] if r["lx_pass"])
    print(f"\n== {nm}: n={s['n']} 中位dist52={s['median']:.2f} | "
          f"贴近{s['贴近高点']} 较近{s['较近']} 中等{s['中等']} 过远{s['过远']} | LX-core通过 {lx_n}")
    for r in sec["rows"][:8]:
        tag = "[核心]" if r["is_core"] else ""
        print(f"  {r['code']} {r['name']:<6}{tag} d52={r['dist52']:.2f} "
              f"pe={r['pe']} mv={r['mv_yi']:.0f}亿 lx={r['lx_stage']}")
print("\nsaved _sector_dist52.json")
