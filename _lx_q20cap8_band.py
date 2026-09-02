# -*- coding: utf-8 -*-
"""q20_cap8 持仓 × band 规避层 + 非金融对照。

在 _lx_q20cap8_now.py 的选股基础上追加：
  1. band 规避层：拉 40 持仓 + 替补池(排名41~70) 的 5 年日频估值，
     PB 5y 分位 >90% 剔除，替补顺位递补。
  2. 非金融对照：剔除银行/非银，q20 排序 + cap8 市值加权，看纯低PE制造业持仓。

数据：_bt_lx_now_*.json + juzi 估值 parquet + 腾讯行情。
"""
import json, os, sys, io, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

from examples.fetch_consensus import JuziHTTP, load_creds
import pandas as pd

PE_CEIL = 25.0
DIV_YIELD = 0.02
EXP_G_CEIL = 60.0
PEG_CEIL = 1.0
MIN_MV_YI = 100.0
MAX_HOLDINGS = 40
CAP = 0.08
BENCH_DEPTH = 30
WARN_PB = 90
SAFE_PCT = 30

VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"
UNIV_FILE = "_bt_lx_now_universe.json"
FIN_FILE = "_bt_sw_fin_universe.json"
OUT_JSON = "_lx_q20cap8_band.json"
OUT_HTML = "_lx_q20cap8_band.html"


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


def build_pool():
    """返回 [(code, dict)] 全市场 core-pass 池（含质量字段，未排序）。"""
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    fac, fac_asof = load_map(FAC_FILE)
    cons, cons_asof = load_map(CONS_FILE)
    members = univ.get("members", [])
    as_of = univ.get("as_of")
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
        if mv is None or mv < MIN_MV_YI * 10000:
            stats["drop"] += 1; continue
        if pe is None or pe <= 0:
            stats["drop"] += 1; continue
        if not (pe <= PE_CEIL or (dy is not None and dy >= DIV_YIELD)):
            stats["drop"] += 1; continue
        if not (exp_g is not None and exp_g <= EXP_G_CEIL
                and peg is not None and 0 < peg <= PEG_CEIL):
            stats["drop"] += 1; continue
        pool.append({"code": tk, "mv": mv, "pe": pe, "dy": dy, "exp_g": exp_g,
                     "peg": peg, "con_roe": con_roe, "cetop": cetop, "gpm": gpm})
    stats["core_pass"] = len(pool)
    # 池内百分位 + blend
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
    return pool, as_of, stats, val_asof, fac_asof, cons_asof


def sort_blend(pool):
    return sorted(pool, key=lambda s: -s["blend"])


def main():
    print("=" * 84)
    print("  q20_cap8 持仓 × band 规避层 + 非金融对照")
    print("=" * 84)

    pool, as_of, stats, val_asof, fac_asof, cons_asof = build_pool()
    fin_set = load_fin_set()
    print(f"as_of={as_of} | core-pass={stats['core_pass']} | 金融名单 {len(fin_set)}")

    sorted_pool = sort_blend(pool)
    top40 = sorted_pool[:MAX_HOLDINGS]
    bench = sorted_pool[MAX_HOLDINGS:MAX_HOLDINGS + BENCH_DEPTH]

    # ---- band 拉取：top40 + 替补池 5 年日频估值 ----
    need_codes = [s["code"] for s in top40 + bench]
    cli = JuziHTTP(*load_creds())
    out = cli.call_tool("factor_get_valuation_panel", {
        "stock_codes": need_codes, "start_date": "2021-08-27",
        "end_date": as_of, "format": "parquet"})
    url = (out.get("download_url") or ((out.get("artifact") or {}).get("download_url")))
    raw = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    print(f"band parquet: {len(df)} 行, {df['stock_code'].nunique()} 只")

    def band(code):
        g = df[df["stock_code"] == code].sort_values("date").dropna(subset=["pb"])
        if g.empty:
            return None
        pb = g["pb"]; pe = g["pe_ttm"].dropna()
        cur_pb = float(pb.iloc[-1])
        pb_pos = pb[pb > 0]; pe_pos = pe[pe > 0]
        pb_pct = float((pb_pos < cur_pb).mean() * 100) if len(pb_pos) else None
        pe_now = float(pe.iloc[-1]) if len(pe) else None
        pe_pct = float((pe_pos < pe_now).mean() * 100) if (pe_now and len(pe_pos)) else None
        return {"pb_pct": round(pb_pct, 1) if pb_pct is not None else None,
                "pe_pct_band": round(pe_pct, 1) if pe_pct is not None else None,
                "pb_now": round(cur_pb, 2)}

    for s in top40 + bench:
        b = band(s["code"])
        if b:
            s["pb_pct"] = b["pb_pct"]
            s["pe_pct_band"] = b["pe_pct_band"]
            s["pb_now"] = b["pb_now"]
            if b["pb_pct"] is not None and b["pb_pct"] > WARN_PB:
                s["flag"] = "规避"
            elif (b["pb_pct"] is not None and b["pb_pct"] < SAFE_PCT
                  and b["pe_pct_band"] is not None and b["pe_pct_band"] < SAFE_PCT):
                s["flag"] = "确认"
            else:
                s["flag"] = ""
        else:
            s["pb_pct"] = None; s["pe_pct_band"] = None; s["pb_now"] = None
            s["flag"] = ""

    # ---- 最终名单：top40 剔除规避 → 替补递补 ----
    final = [dict(s) for s in top40 if s["flag"] != "规避"]
    repl = [dict(s) for s in bench if s["flag"] != "规避"]
    n_avoid = len(top40) - len(final)
    for r in repl[:n_avoid]:
        r["tag"] = "替补"
        final.append(r)
    final = final[:MAX_HOLDINGS]
    w_final = cap_weight(final, CAP)

    # ---- 非金融对照 ----
    nonfin_pool = [s for s in sorted_pool if s["code"] not in fin_set]
    nonfin_top = nonfin_pool[:MAX_HOLDINGS]
    # 也做 band 标记（复用已拉的 parquet，若不在 need_codes 则跳过）
    for s in nonfin_top:
        if s["code"] in {x["code"] for x in top40 + bench}:
            continue
        b = band(s["code"])
        if b:
            s["pb_pct"] = b["pb_pct"]; s["pe_pct_band"] = b["pe_pct"]; s["pb_now"] = b["pb_now"]
            s["flag"] = "规避" if (b["pb_pct"] and b["pb_pct"] > WARN_PB) else ""
    w_nonfin = cap_weight(nonfin_top, CAP)

    # ---- 腾讯名称 ----
    all_codes = [s["code"] for s in final + nonfin_top]
    tq = fetch_tencent(sorted(set(all_codes)))

    def enrich(lst, wmap):
        rows = []
        for i, s in enumerate(lst, 1):
            code6 = s["code"].split(".")[0]
            name, price = tq.get(code6, ("", None))
            rows.append({
                "rank": i, "code": s["code"], "name": name, "price": price,
                "mv_yi": round(s["mv"] / 10000, 1),
                "pe": round(s["pe"], 1),
                "pe_pct": round(s["pe_pct"], 1),
                "q_score": round(s["q_score"], 1),
                "blend": round(s["blend"], 1),
                "pb_pct": s.get("pb_pct"),
                "pe_pct_band": s.get("pe_pct_band"),
                "dy": round(s["dy"] * 100, 2) if s["dy"] is not None else None,
                "exp_g": round(s["exp_g"], 1) if s["exp_g"] is not None else None,
                "peg": round(s["peg"], 2) if s["peg"] is not None else None,
                "con_roe": round(s["con_roe"], 1) if s["con_roe"] is not None else None,
                "gpm": round(s["gpm"], 1) if s["gpm"] is not None else None,
                "flag": s.get("flag", ""),
                "tag": s.get("tag", ""),
                "is_fin": s["code"] in fin_set,
                "weight": round(wmap[s["code"]], 4),
            })
        return rows

    final_rows = enrich(final, w_final)
    nonfin_rows = enrich(nonfin_top, w_nonfin)

    n_fin_final = sum(1 for r in final_rows if r["is_fin"])
    n_avoid_total = n_avoid
    n_confirm = sum(1 for r in final_rows if r["flag"] == "确认")

    print(f"\n=== 最终名单（band 规避后）：金融 {n_fin_final}/40 | 规避剔除 {n_avoid_total} | 确认 {n_confirm} ===")
    for r in final_rows:
        fin_tag = " [金融]" if r["is_fin"] else ""
        avoid = f" [{r['flag']}]" if r["flag"] else ""
        sub = " [替补]" if r["tag"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8}{fin_tag:<5}"
              f" PE={r['pe']:>5.1f} blend={r['blend']:>4.1f} PB分位={r['pb_pct'] if r['pb_pct'] is not None else '—'}"
              f" 权重={r['weight']*100:>4.1f}%{avoid}{sub}")

    print(f"\n=== 非金融对照 top-40（q20 + cap8）：===")
    n_fin_nf = sum(1 for r in nonfin_rows if r["is_fin"])
    print(f"（金融 {n_fin_nf} 只，应=0）")
    for r in nonfin_rows[:20]:
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8} PE={r['pe']:>5.1f} "
              f"blend={r['blend']:>4.1f} 权重={r['weight']*100:>4.1f}%")

    # 落盘
    out = {
        "as_of": as_of,
        "val_asof": val_asof, "fac_asof": fac_asof, "cons_asof": cons_asof,
        "stats": {k: v for k, v in stats.items()},
        "final": final_rows,
        "nonfin": nonfin_rows,
        "meta": {
            "n_avoid": n_avoid_total, "n_confirm": n_confirm,
            "n_fin_final": n_fin_final,
            "top3_w_final": round(sum(sorted(w_final.values(), reverse=True)[:3]), 4),
        },
        "avoided": [{"code": s["code"], "name": s.get("name", "?"), "pb_pct": s.get("pb_pct")}
                    for s in top40 if s["flag"] == "规避"],
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nJSON → {OUT_JSON}")

    build_html(out)
    print(f"HTML → {OUT_HTML}")


def build_html(out):
    as_of = out["as_of"]
    final = out["final"]
    nonfin = out["nonfin"]
    m = out["meta"]

    def tr(r):
        fin = '<span style="background:#1f5fa8;color:#fff;border-radius:3px;font-size:10px;padding:1px 5px">金融</span>' if r["is_fin"] else ""
        sub = '<span style="background:#f59e0b;color:#fff;border-radius:3px;font-size:10px;padding:1px 5px">替补</span>' if r.get("tag") else ""
        warn = ' style="background:#fdecea"' if r.get("flag") == "规避" else (
            ' style="background:#eafaf1"' if r.get("flag") == "确认" else "")
        flag = f'<b style="color:#c0392b">规避</b>' if r.get("flag") == "规避" else (
            f'<b style="color:#1e8449">确认</b>' if r.get("flag") == "确认" else "—")
        pr = f'{r["price"]:.2f}' if r["price"] else "—"
        pbp = f'{r["pb_pct"]:.0f}%' if r["pb_pct"] is not None else "—"
        return f"""<tr{warn}>
        <td>{r['rank']}</td><td class="l mono">{r['code']}</td>
        <td class="l"><b>{r['name'] or '—'}</b>{fin}{sub}</td>
        <td>{pr}</td><td>{r['mv_yi']:,.0f}</td>
        <td><b>{r['pe']}</b></td><td>{r['blend']:.1f}</td>
        <td>{pbp}</td><td>{flag}</td>
        <td>{r['weight']*100:.2f}%</td></tr>"""

    final_tbl = "".join(tr(r) for r in final)
    nonfin_tbl = "".join(tr(r) for r in nonfin)

    avoid_rows = "".join(
        f"<tr><td class='l mono'>{a['code']}</td><td class='l'>{a.get('name','?')}</td>"
        f"<td>{a['pb_pct']:.0f}%</td></tr>" for a in out["avoided"])

    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>q20_cap8 · 最终持仓（band规避后）· {as_of}</title>
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

<h1>q20_cap8 · 最终持仓（band 规避层后）</h1>
<p class="sub">数据截至 <b>{as_of}</b> · 估值@{out['val_asof']} · 因子@{out['fac_asof']} ·
一致预期@{out['cons_asof']}</p>

<div>
<div class="kpi"><b>{len(final)}</b><span>最终持仓</span></div>
<div class="kpi"><b style="color:#1f5fa8">{m['n_fin_final']}</b><span>金融股</span></div>
<div class="kpi"><b style="color:#c0392b">{m['n_avoid']}</b><span>规避剔除</span></div>
<div class="kpi"><b style="color:#1e8449">{m['n_confirm']}</b><span>双低确认</span></div>
<div class="kpi"><b>{m['top3_w_final']*100:.1f}%</b><span>前3权重</span></div>
</div>

<div class="card">
<b>策略（q20_cap8 + band 规避层）：</b><br>
· 选股：core-pass 池（mv≥100亿 + L4 + L5-garp）→ q20 排序（0.8×PE便宜度 + 0.2×质量分）→ top40<br>
· 加权：市值加权 + 单票上限 8%<br>
· band 规避：PB 自身 5 年分位 &gt; 90% 剔除，替补池顺位递补（回测 band 规避层正贡献）
</div>

<h2>① 最终持仓 top-40（band 规避后）</h2>
<p class="sub">红底 = 规避（已从最终剔除，仅展示原始名单）；绿底 = PE&amp;PB 双低确认。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>blend</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{final_tbl}
</table>

<h2>② 被规避剔除的个股（PB 5年分位 &gt; 90%）</h2>
<table>
<tr><th>代码</th><th>名称</th><th>PB分位</th></tr>
{avoid_rows}
</table>

<h2>③ 非金融对照 top-40（q20 排序 + cap8）</h2>
<p class="sub">剔除银行/非银金融，纯低PE制造业/周期持仓（回测提示降金融浓度=负贡献，此为对照展示）。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>blend</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{nonfin_tbl}
</table>

<p class="note"><b>方法诚实性：</b>① band 分位 = 当前 PB 在该股自身近 5 年日频分布中的位置（时间序列口径）；
② 规避判定以 PB 为准（PE 分位对盈利下滑股失真）；③ 非金融对照回测口径为负贡献（-29.7pp），
仅作行业暴露参考；④ 名单由数值化筛选器产生，<b>不构成投资建议</b>。</p>
</body></html>"""

    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
