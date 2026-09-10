# -*- coding: utf-8 -*-
"""
申万行业轮动因子 · 卫星仓落地（月频口径，as_of 2026-08-31 月末快照）

设计（正交收益源，卫星仓定位）:
  1. 读全市场个股「行业轮动」因子 z-score（_sw_industry_rotation_values.json，5005只/30个唯一值=30个一级行业）
  2. 取因子值最高的前 K 个行业作为「看好行业池」（行业轮动信号 = 行业选择层）
  3. 在看好行业池内，复用 q20_cap8 的 core-pass 筛选 + q20 排序 + 市值加权 cap8（个股选择层）
  4. 输出卫星仓持仓，并与价值底仓（_lx_q20cap8_now.json 全行业低PE）做互补性对照

关键诚实性：
  - 行业轮动因子是月频（月末取值次月生效），本脚本用 2026-08-31 快照
  - 因子 alpha 集中在 2022后/2025H2，MDD~33%，T2 卫星仓定位，不替代价值底仓
  - 因子值广播到个股（同行业同分），所以是「行业选择」而非「个股选择」
"""
import json, os, sys, urllib.request
from collections import Counter, defaultdict

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
TOP_K_INDUSTRY = 6  # 取因子值最高的前6个行业

# 因子值 -> 申万一级行业名（westock data_profile 交叉验证 + get_factor_industry_decomposition 一致）
ROT2IND = {
    1.9333: "电子", 1.8791: "通信", 1.5262: "电力设备",
    1.1190: "机械设备", 0.9482: "计算机", 0.9248: "基础化工",
}

VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"
UNIV_FILE = "_bt_lx_now_universe.json"
FIN_FILE = "_bt_sw_fin_universe.json"
ROT_FILE = "_sw_industry_rotation_values.json"
OUT_JSON = "_sw_industry_rotation_satellite.json"
OUT_HTML = "_sw_industry_rotation_satellite.html"


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
    print("  申万行业轮动因子 · 卫星仓落地（月频 as_of 2026-08-31）")
    print("=" * 80)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    fac, fac_asof = load_map(FAC_FILE)
    cons, cons_asof = load_map(CONS_FILE)
    members = univ.get("members", [])
    as_of = univ.get("as_of")
    fin_set = load_fin_set()

    # 行业轮动因子值
    rot = json.loads(open(ROT_FILE, encoding="utf-8").read())
    rot_map = {r["ts_code"]: r["行业轮动"] for r in rot["records"]}
    print(f"行业轮动因子: {len(rot_map)} 只个股 | 唯一值(行业数) = "
          f"{len(set(rot_map.values()))}")

    # 30个唯一值 -> 排序
    uniq_vals = sorted(set(rot_map.values()), reverse=True)
    print(f"因子值范围: {uniq_vals[0]:+.4f} ~ {uniq_vals[-1]:+.4f}")
    top_vals = uniq_vals[:TOP_K_INDUSTRY]
    print(f"看好行业池 = 因子值前 {TOP_K_INDUSTRY} 个: "
          f"{[f'{v:+.3f}' for v in top_vals]}")

    # core-pass 筛选（复用 q20_cap8）
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

        pool.append({
            "code": tk, "mv": mv, "pe": pe, "dy": dy, "exp_g": exp_g,
            "peg": peg, "con_roe": con_roe, "cetop": cetop, "gpm": gpm,
            "rot": rot_map.get(tk),  # 行业轮动因子值（可能缺失）
        })

    stats["core_pass"] = len(pool)
    n_with_rot = sum(1 for s in pool if s["rot"] is not None)
    print(f"\ncore-pass 池 {len(pool)} 只，其中 {n_with_rot} 只有行业轮动因子值")

    # 卫星仓 = 看好行业池内的 core-pass 股
    satellite_pool = [s for s in pool if s["rot"] is not None and s["rot"] in top_vals]
    print(f"卫星仓候选（看好行业池内 core-pass）: {len(satellite_pool)} 只")

    # q20 排序（只在卫星仓候选内做池内百分位）
    gpm_vals = [s["gpm"] for s in satellite_pool if s["gpm"] is not None]
    roe_vals = [s["con_roe"] for s in satellite_pool if s["con_roe"] is not None]
    cet_vals = [s["cetop"] for s in satellite_pool if s["cetop"] is not None]
    pe_vals = [s["pe"] for s in satellite_pool]
    for s in satellite_pool:
        s["gpm_pct"] = pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
        s["roe_pct"] = pct_rank(roe_vals, s["con_roe"]) if s["con_roe"] else 0
        s["cet_pct"] = pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
        s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0
        s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])
        s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_score"]

    satellite_pool.sort(key=lambda s: -s["blend"])
    picked = satellite_pool[:MAX_HOLDINGS]
    w = cap_weight(picked, CAP) if picked else {}

    # 腾讯名称
    codes = [s["code"] for s in picked]
    tq = fetch_tencent(codes)

    fin_set_tk = {c for c in fin_set if "." in c}

    def is_fin(code):
        return code in fin_set_tk

    rows = []
    for i, s in enumerate(picked, 1):
        code6 = s["code"].split(".")[0]
        name, price = tq.get(code6, ("", None))
        weight = w.get(s["code"], 0)
        rows.append({
            "rank": i, "code": s["code"], "name": name, "price": price,
            "mv_yi": round(s["mv"] / 10000, 1), "pe": round(s["pe"], 1),
            "dy": round(s["dy"] * 100, 2) if s["dy"] is not None else None,
            "exp_g": round(s["exp_g"], 1) if s["exp_g"] is not None else None,
            "peg": round(s["peg"], 2) if s["peg"] is not None else None,
            "gpm": round(s["gpm"], 1) if s["gpm"] is not None else None,
            "pe_pct": round(s["pe_pct"], 1), "q_score": round(s["q_score"], 1),
            "blend": round(s["blend"], 1),
            "rot": round(s["rot"], 4) if s["rot"] is not None else None,
            "industry": ROT2IND.get(round(s["rot"], 4) if s["rot"] is not None else 0, ""),
            "weight": round(weight, 4),
            "is_fin": is_fin(s["code"]),
        })

    n_fin = sum(1 for r in rows if r["is_fin"])
    top3_w = sum(sorted(w.values(), reverse=True)[:3]) if w else 0
    hhi = sum(x * x for x in w.values()) if w else 0

    # 行业分布
    ind_dist = Counter(r["industry"] for r in rows)

    print(f"\n=== 卫星仓 top-{len(rows)} ===")
    print(f"金融 {n_fin}/{len(rows)} | top3 {top3_w:.1%} | N_eff {1/hhi:.1f}")
    print(f"行业分布: {dict(ind_dist)}")
    for r in rows:
        fin_tag = " [金融]" if r["is_fin"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8}{fin_tag:<5}"
              f" {r['industry']:<6} PE={r['pe']:>5.1f} blend={r['blend']:>4.1f} "
              f"rot={r['rot']:+.2f} 权重={r['weight']*100:>4.1f}%")

    out = {
        "as_of": as_of, "rot_asof": rot.get("date"),
        "strategy": "申万行业轮动因子 卫星仓（看好行业池 + q20_cap8 选股）",
        "val_asof": val_asof, "fac_asof": fac_asof, "cons_asof": cons_asof,
        "top_k_industry": TOP_K_INDUSTRY,
        "top_industry_vals": top_vals,
        "top_industry_names": [ROT2IND.get(round(v, 4), "") for v in top_vals],
        "uniq_industry_vals": uniq_vals,
        "industry_dist": dict(ind_dist),
        "stats": {k: v for k, v in stats.items()},
        "n_core_pass": len(pool),
        "n_satellite_cand": len(satellite_pool),
        "holdings": rows,
        "conc": {"n_fin": n_fin, "top3_w": round(top3_w, 4),
                 "hhi": round(hhi, 4), "n_eff": round(1 / hhi, 1) if hhi else 0},
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nJSON → {OUT_JSON}")

    build_html(out)
    print(f"HTML → {OUT_HTML}")


def build_html(out):
    rows = out["holdings"]
    c = out["conc"]
    top_vals = out["top_industry_vals"]

    def tr(r):
        fin = '<span style="background:#1f5fa8;color:#fff;border-radius:3px;font-size:10px;padding:1px 5px">金融</span>' if r["is_fin"] else ""
        pr = f'{r["price"]:.2f}' if r["price"] else "—"
        dy = f'{r["dy"]:.2f}%' if r["dy"] is not None else "—"
        return f"""<tr>
        <td>{r['rank']}</td><td class="l mono">{r['code']}</td>
        <td class="l"><b>{r['name'] or '—'}</b>{fin}</td>
        <td class="l">{r['industry']}</td>
        <td>{pr}</td><td>{r['mv_yi']:,.0f}</td>
        <td><b>{r['pe']}</b></td><td>{r['pe_pct']:.0f}</td>
        <td>{r['q_score']:.0f}</td><td><b>{r['blend']:.1f}</b></td>
        <td style="color:#b45309;font-weight:600">{r['rot']:+.2f}</td>
        <td>{dy}</td><td>{r['exp_g'] if r['exp_g'] is not None else '—'}</td>
        <td>{r['peg'] if r['peg'] is not None else '—'}</td>
        <td>{r['gpm'] if r['gpm'] is not None else '—'}</td>
        <td>{r['weight']*100:.2f}%</td></tr>"""

    tbl = "".join(tr(r) for r in rows)
    tv = "、".join(f"{ROT2IND.get(round(v,4),'')}({v:+.2f})" for v in top_vals)

    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>申万行业轮动因子 · 卫星仓（{out['as_of']}）</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui;margin:24px 32px;background:#f5f6f8;color:#1a1d24}}
h1{{font-size:22px;margin-bottom:4px}} h2{{font-size:16px;margin-top:28px;border-left:4px solid #b45309;padding-left:10px}}
.sub{{color:#6b7280;font-size:13px;margin:6px 0 12px}}
table{{border-collapse:collapse;margin:10px 0;font-size:13px;background:#fff;width:100%}}
th,td{{border:1px solid #e5e7eb;padding:6px 9px;text-align:right;white-space:nowrap}}
th{{background:#fafbfc;position:sticky;top:0;color:#6b7280;font-weight:600}}
td.l{{text-align:left}} td.mono{{font-family:Consolas,monospace}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;margin:12px 0;font-size:13.5px;line-height:1.8}}
.kpi{{display:inline-block;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 20px;margin:6px 8px 6px 0;text-align:center}}
.kpi b{{font-size:20px;display:block}} .kpi span{{color:#6b7280;font-size:12px}}
.note{{color:#888;font-size:12px;margin-top:18px;border-top:1px dashed #ccc;padding-top:10px}}
.warn{{background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:10px 14px;margin:10px 0;font-size:13px}}
</style></head><body>

<h1>申万行业轮动因子 · 卫星仓</h1>
<p class="sub">数据截至 <b>{out['as_of']}</b>（价值底仓口径）· 行业轮动因子 @{out['rot_asof']}（月末快照）
· 估值@{out['val_asof']} · 因子@{out['fac_asof']} · 一致预期@{out['cons_asof']}</p>

<div class="warn"><b>卫星仓定位（诚实标注）：</b>行业轮动因子（T2 级，全库唯一完全独立源 |ρ|&lt;0.03）多空收益
+12.6%/年，但 alpha 集中在 2022 后/2025H2、MDD~33%。这里是作为<b>价值底仓（q20_cap8 低PE大盘价值）之外的正交收益源</b>，
建议仓位占比 10~20%，月频调仓（月末取值、次月生效）。</div>

<div class="card">
<b>落地逻辑（月频因子原生口径）：</b><br>
· <b>行业选择层</b>：申万「行业轮动」因子（基本面+技术面+资金面等权合成，30 个申万一级行业综合得分，广播到个股同行业同分），
取得分最高的前 {out['top_k_industry']} 个行业作为看好行业池（因子值 {tv}）<br>
· <b>个股选择层</b>：在看好行业池内复用 q20_cap8 —— core-pass（mv≥100亿 + PE&gt;0 + L4估值 + L5-garp 门控）+ q20 排序（0.8×PE便宜度+0.2×质量分）+ 市值加权 cap8<br>
· <b>与底仓正交</b>：价值底仓吃「低PE大盘价值 beta」（全行业、金融浓度高），卫星仓吃「行业轮动 alpha」（被看好的行业），两者信息源独立。
</div>

<div>
<div class="kpi"><b>{len(rows)}</b><span>卫星仓持仓</span></div>
<div class="kpi"><b>{out['top_k_industry']}</b><span>看好行业数</span></div>
<div class="kpi"><b style="color:#b45309">{c['n_fin']}</b><span>金融股</span></div>
<div class="kpi"><b>{c['top3_w']*100:.1f}%</b><span>前3权重</span></div>
<div class="kpi"><b>{c['n_eff']}</b><span>有效持仓数</span></div>
<div class="kpi"><b>{out['n_satellite_cand']}</b><span>卫星仓候选</span></div>
</div>

<h2>卫星仓持仓（看好行业内 q20 排序 + cap8 加权）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>行业</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>便宜度</th><th>质量分</th><th>blend</th><th>行业得分</th>
<th>股息%</th><th>增速%</th><th>PEG</th><th>毛利%</th><th>权重</th></tr>
{tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 行业轮动因子值 = 申万 MCP get_factor_value 广播结果，同行业同分，
唯一值恰好 30 个 = 30 个申万一级行业（除综合）；② 因子是月频，月末取值次月生效，本表为 2026-08-31 快照；
③ 卫星仓候选数 = 看好行业池 ∩ core-pass，可能不足 40 只（高得分行业多为成长/题材，与低PE价值筛选天然冲突，见下）；④ 名单由数值化筛选器产生，<b>不构成投资建议</b>。</p>
</body></html>"""

    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
