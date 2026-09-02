# -*- coding: utf-8 -*-
"""q20_cap8 策略 · 当前时点最新持仓（含金融口径，市值加权 cap8）。

策略（来自 _bt_q20_cap.py 回测验证，full 基座）:
  筛选 core-pass: mv≥100亿 + PE>0 + L4(PE≤25 或 股息率≥2%) + L5(增速≤60% & 0<PEG≤1)
  排序 q20     : blend = 0.8×pe_pct + 0.2×q_score，降序
                q_score = (gpm_pct + con_roe_pct + cetop_pct)/3  池内百分位
  加权 cap8    : 市值加权 + 单票上限 8%（迭代 waterfall）

回测锚点: q20_cap8 5年 +118.5%（g60 +67.0%），MDD 15.6%，依赖度 0.46。

数据: _bt_lx_now_*.json（juzi PIT 快照）+ 腾讯实时行情。
"""
import json, os, sys, statistics, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

PE_CEIL = 25.0
DIV_YIELD = 0.02
EXP_G_CEIL = 60.0
PEG_CEIL = 1.0
MIN_MV_YI = 100.0
MAX_HOLDINGS = 40
CAP = 0.08

VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"
UNIV_FILE = "_bt_lx_now_universe.json"
FIN_FILE = "_bt_sw_fin_universe.json"
OUT_JSON = "_lx_q20cap8_now.json"
OUT_HTML = "_lx_q20cap8_now.html"


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
    for k, v in d.items():
        if isinstance(v, dict):
            out |= set(v.get("members", []))
    return out


def pct_rank(values, v):
    n = len(values)
    if n == 0:
        return 50.0
    return sum(1 for x in values if x < v) / n * 100.0


def cap_weight(picked, cap):
    mv = {s["code"]: s["mv"] for s in picked}
    tot = sum(mv.values())
    w = {tk: m / tot for tk, m in mv.items()}
    for _ in range(200):
        over = {tk: wv - cap for tk, wv in w.items() if wv > cap + 1e-12}
        if not over:
            break
        excess = sum(over.values())
        under = {tk: mv[tk] for tk in w if w[tk] <= cap + 1e-12}
        if not under:
            break
        utot = sum(under.values())
        for tk in over:
            w[tk] = cap
        for tk in under:
            w[tk] += excess * under[tk] / utot
    return w


def fetch_tencent(codes, batch=100):
    def _prefix(c):
        if c.startswith(("6", "9")):
            return "sh"
        if c.startswith(("8", "4")):
            return "bj"
        return "sz"
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
    print("=" * 80)
    print("  q20_cap8 策略 · 当前时点最新持仓（含金融 · 市值加权 cap8）")
    print("=" * 80)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    fac, fac_asof = load_map(FAC_FILE)
    cons, cons_asof = load_map(CONS_FILE)
    members = univ.get("members", [])
    as_of = univ.get("as_of")
    fin_set = load_fin_set()
    print(f"as_of={as_of} | univ={len(members)} | val={len(val)}@{val_asof} "
          f"| fac={len(fac)}@{fac_asof} | cons={len(cons)}@{cons_asof}")

    # ---- core-pass 筛选 + 质量字段 ----
    stats = Counter()
    stats["univ"] = len(members)
    pool = []
    for sc in members:
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

        if mv is None:
            stats["mv_missing"] += 1; continue
        if mv < MIN_MV_YI * 10000:
            stats["mv_low"] += 1; continue
        if pe is None or pe <= 0:
            stats["pe_nonpos"] += 1; continue
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            stats["l4"] += 1; continue
        l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
              and peg is not None and 0 < peg <= PEG_CEIL)
        if not l5:
            stats["l5"] += 1; continue

        pool.append({
            "code": tk, "mv": mv, "pe": pe, "dy": dy, "exp_g": exp_g,
            "peg": peg, "con_roe": con_roe, "cetop": cetop, "gpm": gpm,
        })

    stats["core_pass"] = len(pool)
    print(f"\n漏斗: univ={stats['univ']} | mv<100亿={stats['mv_low']} | "
          f"PE<=0={stats['pe_nonpos']} | L4={stats['l4']} | L5={stats['l5']} | "
          f"core-pass={stats['core_pass']}")

    # ---- 池内百分位 + q20 排序 ----
    gpm_vals = [s["gpm"] for s in pool if s["gpm"] is not None]
    roe_vals = [s["con_roe"] for s in pool if s["con_roe"] is not None]
    cet_vals = [s["cetop"] for s in pool if s["cetop"] is not None]
    pe_vals = [s["pe"] for s in pool]
    for s in pool:
        s["gpm_pct"] = pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
        s["roe_pct"] = pct_rank(roe_vals, s["con_roe"]) if s["con_roe"] else 0
        s["cet_pct"] = pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
        s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0
        s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])
        s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_score"]

    pool.sort(key=lambda s: -s["blend"])
    picked = pool[:MAX_HOLDINGS]
    w = cap_weight(picked, CAP)

    # ---- 腾讯名称/现价 ----
    codes = [s["code"] for s in picked]
    tq = fetch_tencent(codes)
    print(f"tencent 名称解析: {len(tq)}/{len(codes)}")

    # ---- 行业标记（金融）----
    fin_set_tk = {c for c in fin_set if "." in c}
    # fin 名单里的 code 格式可能是 "000001.SZ"
    def is_fin(code):
        return code in fin_set_tk

    rows = []
    for i, s in enumerate(picked, 1):
        code6 = s["code"].split(".")[0]
        name, price = tq.get(code6, ("", None))
        weight = w[s["code"]]
        rows.append({
            "rank": i, "code": s["code"], "name": name,
            "price": price,
            "mv_yi": round(s["mv"] / 10000, 1),
            "pe": round(s["pe"], 1),
            "dy": round(s["dy"] * 100, 2) if s["dy"] is not None else None,
            "exp_g": round(s["exp_g"], 1) if s["exp_g"] is not None else None,
            "peg": round(s["peg"], 2) if s["peg"] is not None else None,
            "con_roe": round(s["con_roe"], 1) if s["con_roe"] is not None else None,
            "gpm": round(s["gpm"], 1) if s["gpm"] is not None else None,
            "cetop": round(s["cetop"] * 100, 2) if s["cetop"] is not None else None,
            "pe_pct": round(s["pe_pct"], 1),
            "q_score": round(s["q_score"], 1),
            "blend": round(s["blend"], 1),
            "weight": round(weight, 4),
            "is_fin": is_fin(s["code"]),
        })

    n_fin = sum(1 for r in rows if r["is_fin"])
    top3_w = sum(sorted(w.values(), reverse=True)[:3])
    hhi = sum(x * x for x in w.values())

    # 打印
    print(f"\n=== q20_cap8 最新持仓 top-{len(rows)} @ {as_of} ===")
    print(f"金融 {n_fin}/40 | top3权重 {top3_w:.1%} | HHI {hhi:.3f} (N_eff {1/hhi:.1f})")
    for r in rows:
        fin_tag = " [金融]" if r["is_fin"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8}{fin_tag:<5}"
              f" PE={r['pe']:>5.1f} blend={r['blend']:>4.1f} "
              f"q={r['q_score']:>4.1f} 权重={r['weight']*100:>4.1f}%")

    # ---- 落盘 JSON ----
    out = {
        "as_of": as_of,
        "strategy": "q20_cap8（q20排序 + 市值加权cap8，含金融）",
        "val_asof": val_asof, "fac_asof": fac_asof, "cons_asof": cons_asof,
        "stats": {k: v for k, v in stats.items()},
        "holdings": rows,
        "conc": {"n_fin": n_fin, "top3_w": round(top3_w, 4),
                 "hhi": round(hhi, 4), "n_eff": round(1 / hhi, 1)},
        "method": "blend=0.8*pe_pct+0.2*q_score; q_score=(gpm_pct+con_roe_pct+cetop_pct)/3; 市值加权cap8",
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nJSON → {OUT_JSON}")

    build_html(out)
    print(f"HTML → {OUT_HTML}")


def build_html(out):
    as_of = out["as_of"]
    rows = out["holdings"]
    c = out["conc"]
    s = out["stats"]

    def tr(r):
        fin = '<span style="background:#1f5fa8;color:#fff;border-radius:3px;font-size:10px;padding:1px 5px">金融</span>' if r["is_fin"] else ""
        pr = f'{r["price"]:.2f}' if r["price"] else "—"
        dy = f'{r["dy"]:.2f}%' if r["dy"] is not None else "—"
        return f"""<tr>
        <td>{r['rank']}</td>
        <td class="l mono">{r['code']}</td>
        <td class="l"><b>{r['name'] or '—'}</b>{fin}</td>
        <td>{pr}</td><td>{r['mv_yi']:,.0f}</td>
        <td><b>{r['pe']}</b></td><td>{r['pe_pct']:.0f}</td>
        <td>{r['q_score']:.0f}</td><td><b>{r['blend']:.1f}</b></td>
        <td>{dy}</td><td>{r['exp_g'] if r['exp_g'] is not None else '—'}</td>
        <td>{r['peg'] if r['peg'] is not None else '—'}</td>
        <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
        <td>{r['gpm'] if r['gpm'] is not None else '—'}</td>
        <td>{r['weight']*100:.2f}%</td></tr>"""

    tbl = "".join(tr(r) for r in rows)

    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>q20_cap8 · 最新持仓（{as_of}）</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui;margin:24px 32px;background:#f5f6f8;color:#1a1d24}}
h1{{font-size:22px;margin-bottom:4px}} h2{{font-size:16px;margin-top:28px;border-left:4px solid #1f5fa8;padding-left:10px}}
.sub{{color:#6b7280;font-size:13px;margin:6px 0 12px}}
table{{border-collapse:collapse;margin:10px 0;font-size:13px;background:#fff;width:100%}}
th,td{{border:1px solid #e5e7eb;padding:6px 9px;text-align:right;white-space:nowrap}}
th{{background:#fafbfc;position:sticky;top:0;color:#6b7280;font-weight:600}}
td.l{{text-align:left}} td.mono{{font-family:Consolas,monospace}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;margin:12px 0;font-size:13.5px;line-height:1.8}}
.kpi{{display:inline-block;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 20px;margin:6px 8px 6px 0;text-align:center}}
.kpi b{{font-size:20px;display:block}} .kpi span{{color:#6b7280;font-size:12px}}
.note{{color:#888;font-size:12px;margin-top:18px;border-top:1px dashed #ccc;padding-top:10px}}
</style></head><body>

<h1>q20_cap8 · 当前时点最新持仓</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 估值@{out['val_asof']} · 因子@{out['fac_asof']} ·
一致预期@{out['cons_asof']} · 万得全A PIT 成分 {s['univ']:,} 只</p>

<div class="card">
<b>策略（q20_cap8，回测 5 年 +118.5% / MDD 15.6% / 依赖度 0.46）：</b><br>
· 筛选 core-pass：mv≥100亿 + PE&gt;0 + L4(PE≤25 或 股息率≥2%) + L5(增速≤60% 且 0&lt;PEG≤1)<br>
· 排序 q20：blend = <b>0.8×PE便宜度 + 0.2×质量分</b>（质量分 = 毛利/ROE/OCF 三指标池内百分位均值）<br>
· 加权 cap8：市值加权 + 单票上限 <b>8%</b>（迭代 waterfall，控集中度）<br>
· 含金融（银行/非银保留），回测归因显示低PE大盘价值 beta 是主要收益来源。
</div>

<div>
<div class="kpi"><b>{len(rows)}</b><span>持仓数</span></div>
<div class="kpi"><b style="color:#1f5fa8">{c['n_fin']}</b><span>金融股</span></div>
<div class="kpi"><b>{c['top3_w']*100:.1f}%</b><span>前3权重</span></div>
<div class="kpi"><b>{c['n_eff']}</b><span>有效持仓数</span></div>
<div class="kpi"><b>{s['core_pass']}</b><span>core-pass 池</span></div>
</div>

<h2>最新持仓（按 blend 降序，市值加权 cap8）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>便宜度</th><th>质量分</th><th>blend</th><th>股息%</th>
<th>增速%</th><th>PEG</th><th>ROE%</th><th>毛利%</th><th>权重</th></tr>
{tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 数据 = juzi 估值/成分/一致预期 PIT 快照 + 腾讯实时行情，无合成；
② 因子 as_of 可能落后估值日（基本面因子前向填充，可接受）；③ 市值加权 cap8 下 top3 权重≈24%
（3×8% 顶格），仍集中大盘价值龙头；④ 名单由数值化筛选器产生，<b>不构成投资建议</b>。</p>
</body></html>"""

    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
