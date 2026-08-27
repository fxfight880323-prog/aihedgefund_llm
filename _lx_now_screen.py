"""刘旭式框架当前时点筛选 — 应用 LX-core(+gm) 生成推荐名单 + 报告。

标准（来自全A回测 _lx_allA_variant.py / _bt_garp.py 实证，2021-08~2026-06）:
  LX-core  市值≥100亿 + PE>0 + L4(PE_TTM≤25 或 股息率≥2%)
           + L5-garp(一致预期净利增速≤60% 且 0<PEG≤1)，信念=PE升序(便宜优先)
  LX-gm    core + 毛利率≥全市场中位数（唯一既保值又显著降险的质量层）
  【2026-08-26 采纳 garp 门控】_bt_garp.py 8变体回测: garp 总收益+34.57%
   最优（vs 原 L5 增速≤25%+PEG≤2 的 +29.45%，+5.12pp），MDD 18.54% vs 22.12%
   (-3.6pp)，收益+风险双维最优；超额主要来自 2022 熊市少亏 6.2pp（PEG≤1 避高估低质）

用户铁律（2026-08-25 定稿）: 所有筛选默认剔除银行/金融股
  （读 _bt_sw_fin_universe.json 正式名单，缺失时 fallback exfin 内置 121 只）。

输出: 推荐名单 top-40（等权 2.5%，单票≤5%）+ 全部命中明细 + 漏斗统计。
"""
from __future__ import annotations

import csv
import io
import json
import os
import statistics
import urllib.request
from collections import Counter

PE_CEIL = 25.0
DIV_YIELD = 0.02
EXP_G_CEIL = 60.0  # garp: 增速≤60%（原 25%）
PEG_CEIL = 1.0     # garp: 0<PEG≤1（原 2.0，更严的估值匹配补偿更宽增速）
MIN_MV_YI = 100.0
MAX_HOLDINGS = 40
PER_NAME_CAP = 0.05

VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"
UNIV_FILE = "_bt_lx_now_universe.json"
FIN_FILE = "_bt_sw_fin_universe.json"
OUT_JSON = "_lx_now_results.json"
OUT_CSV = "刘旭框架_当前推荐A股.csv"
OUT_HTML = "_lx_now_report.html"

# fallback: 若正式金融名单缺失，复用 exfin 脚本内置的银行+非银名单（同口径）
try:
    from _cs_now_recommend_exfin import FIN_CODES as _FIN_CODES_FALLBACK
except Exception:
    _FIN_CODES_FALLBACK = set()


def load_fin_set():
    """读取金融剔除名单（juzi 中信行业 ∪ exfin 申万，∩PIT 成分）。"""
    fin = None
    if os.path.exists(FIN_FILE):
        try:
            fin = json.loads(open(FIN_FILE, encoding="utf-8").read())
        except Exception:
            fin = None
    if fin:
        fin_set = set()
        for k, v in fin.items():
            if isinstance(v, dict):
                fin_set |= set(v.get("members", []))
        if fin_set:
            print(f"  金融剔除名单(正式, {fin.get('as_of', '?')}): {len(fin_set)} 只")
            return fin_set
    fallback = set(_FIN_CODES_FALLBACK)
    print(f"  [fallback] 未找到 {FIN_FILE}，复用 exfin 内置银行+非银名单 "
          f"{len(fallback)} 只")
    return fallback


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


def fetch_tencent(codes, batch=100):
    """腾讯行情: 名称/现价/总市值。返回 {code: (name, price, total_mv_yi)}"""
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
                total_mv = float(f[45]) if len(f) > 45 else 0.0
                out[code] = (name, price, total_mv)
        except Exception as e:
            print(f"  tencent batch {i} 失败: {str(e)[:80]}")
    return out


def main():
    print("=" * 78)
    print("  刘旭式框架 × 当前时点全A筛选（as_of 最新交易日）")
    print("=" * 78)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    val, val_asof = load_map(VAL_FILE)
    fac, fac_asof = load_map(FAC_FILE)
    cons, cons_asof = load_map(CONS_FILE)
    as_of = univ.get("as_of")
    members = univ.get("members", [])
    print(f"as_of={as_of} | univ={len(members)} | val={len(val)} | "
          f"fac={len(fac)} | cons={len(cons)}")

    # ---- 金融剔除（用户铁律：所有筛选默认剔除银行/金融股）----
    fin_set = load_fin_set()
    members = [m for m in members if m not in fin_set]
    print(f"剔除金融后池子: {len(members)} 只")

    # ---- 筛选漏斗 ----
    stats = Counter()
    stats["univ"] = len(members)
    stats["fin_removed"] = len(fin_set)
    passed = []          # (ticker, dict) 通过 core
    gpm_vals = []        # 通过 L4+L5 且有 gpm 的（gm 中位数口径，同回测）
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
        # 数据清洗: dtop5 正常范围 <50% (特别分红也极少 >30%);
        # juzi 健康数据中偶见 3.2/10.1 等荒谬值(322%/1012%), 置 None 防污染 L4 与评分
        if dy is not None and dy >= 0.5:
            dy = None
        exp_g = _num(c.get("con_np_yoy"))
        peg = _num(c.get("con_peg"))
        con_roe = _num(c.get("con_roe"))
        cetop = _num(f.get("cetop"))
        gpm = _num(f.get("gpm"))
        npyoy = _num(f.get("npyoy"))

        if mv is None:
            stats["mv_missing"] += 1
            continue
        if mv < MIN_MV_YI * 10000:
            stats["mv_low"] += 1
            continue
        if pe is None or pe <= 0:
            stats["pe_nonpos"] += 1
            continue
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            stats["l4"] += 1
            continue
        l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
              and peg is not None and 0 < peg <= PEG_CEIL)
        if not l5:
            stats["l5"] += 1
            continue
        if gpm is not None:
            gpm_vals.append(gpm)
        else:
            stats["gpm_missing"] += 1
            continue
        passed.append((tk, {
            "mv": mv, "pe": pe, "dy": dy, "exp_g": exp_g, "peg": peg,
            "con_roe": con_roe, "cetop": cetop, "gpm": gpm, "npyoy": npyoy,
        }))

    gmed = statistics.median(gpm_vals) if gpm_vals else None
    stats["gpm_median"] = gmed
    passed_gm = [(tk, d) for tk, d in passed if d["gpm"] >= gmed]
    stats["core_pass"] = len(passed)
    stats["gm_pass"] = len(passed_gm)
    stats["gm_drop"] = len(passed) - len(passed_gm)

    # ---- 排序：PE 升序（便宜优先）----
    passed.sort(key=lambda x: x[1]["pe"])
    passed_gm.sort(key=lambda x: x[1]["pe"])

    def build_portfolio(lst):
        picked = lst[:MAX_HOLDINGS]
        w = 1.0 / len(picked) if picked else 0.0
        w = min(w, PER_NAME_CAP)
        return picked, round(w, 4)

    core_pick, core_w = build_portfolio(passed)
    gm_pick, gm_w = build_portfolio(passed_gm)

    # ---- 腾讯名称/现价 ----
    need = {tk for tk, _ in passed}
    tq = fetch_tencent(sorted(need))
    print(f"tencent 名称解析: {len(tq)}/{len(need)}")

    def enrich(pick):
        rows = []
        for i, (tk, d) in enumerate(pick, 1):
            code = tk.split(".")[0]
            name, price, tmv = tq.get(code, ("", None, None))
            rows.append({
                "rank": i, "code": tk, "name": name,
                "price": price, "mv_yi": round((d["mv"] or 0) / 10000, 1),
                "pe": round(d["pe"], 1) if d["pe"] else None,
                "dy": round(d["dy"] * 100, 2) if d["dy"] is not None else None,  # dtop5 为小数(0.038=3.8%), *100 转百分数
                "exp_g": round(d["exp_g"], 1) if d["exp_g"] is not None else None,
                "peg": round(d["peg"], 2) if d["peg"] is not None else None,
                "con_roe": round(d["con_roe"], 1) if d["con_roe"] is not None else None,
                "gpm": round(d["gpm"], 1) if d["gpm"] is not None else None,  # gpm 已是百分数
                "cetop": round(d["cetop"] * 100, 2) if d["cetop"] is not None else None,
                "weight": core_w,
            })
        return rows

    core_rows = enrich(core_pick)
    gm_rows = enrich(gm_pick)

    # 全部命中（core 完整明细，含排名）
    all_rows = []
    for i, (tk, d) in enumerate(passed, 1):
        code = tk.split(".")[0]
        name, price, tmv = tq.get(code, ("", None, None))
        all_rows.append({
            "rank": i, "code": tk, "name": name,
            "price": price, "mv_yi": round((d["mv"] or 0) / 10000, 1),
            "pe": round(d["pe"], 1) if d["pe"] else None,
            "dy": round(d["dy"] * 100, 2) if d["dy"] is not None else None,
            "exp_g": round(d["exp_g"], 1) if d["exp_g"] is not None else None,
            "peg": round(d["peg"], 2) if d["peg"] is not None else None,
            "con_roe": round(d["con_roe"], 1) if d["con_roe"] is not None else None,
            "gpm": round(d["gpm"], 1) if d["gpm"] is not None else None,
            "cetop": round(d["cetop"] * 100, 2) if d["cetop"] is not None else None,
            "weight": core_w,
            "in_gm": tk in {t for t, _ in passed_gm},
        })

    print(f"\n漏斗: univ={stats['univ']} | 剔除金融={stats.get('fin_removed', 0)} | "
          f"mv<100亿={stats['mv_low']} | "
          f"PE<=0={stats['pe_nonpos']} | L4不满足={stats['l4']} | "
          f"L5不满足={stats['l5']} | gpm缺失={stats['gpm_missing']}")
    print(f"core 通过 {stats['core_pass']} 只 (top-{len(core_pick)}) | "
          f"gm 通过 {stats['gm_pass']} 只 (top-{len(gm_pick)}) | "
          f"gpm中位数={gmed:.3f}")
    print(f"\n=== LX-core 推荐 top-{len(core_pick)}（等权 {core_w:.1%}）===")
    for r in core_rows[:20]:
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name'] or '?':<8} "
              f"PE {r['pe'] or 0:>6.1f} | MV {r['mv_yi']:>7.0f}亿 | "
              f"股息 {r['dy'] or 0:>4.1f}% | 预期增速 {r['exp_g'] or 0:>5.1f}% | "
              f"PEG {r['peg'] or 0:>4.1f} | ROE {r['con_roe'] or 0:>4.1f} | "
              f"毛利 {r['gpm'] or 0:>4.1f}%")

    # ---- CSV ----
    cols = ["rank", "code", "name", "price", "mv_yi", "pe", "dy", "exp_g",
            "peg", "con_roe", "gpm", "cetop", "weight", "in_gm"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nCSV → {OUT_CSV}")

    # ---- 结果 JSON ----
    json.dump({
        "as_of": as_of, "univ_n": len(members),
        "stats": {k: (round(v, 4) if isinstance(v, float) else v)
                  for k, v in stats.items()},
        "core": core_rows, "gm": gm_rows, "all": all_rows,
        "core_weight": core_w, "gm_weight": gm_w,
    }, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON → {OUT_JSON}")

    # ---- HTML ----
    html = build_html(as_of, stats, core_rows, gm_rows, all_rows,
                      core_w, gm_w, gmed)
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"报告 → {OUT_HTML}")


def build_html(as_of, stats, core, gm, all_rows, core_w, gm_w, gmed):
    def tr(r, hl=False):
        return f"""<tr{' class="gm"' if hl else ''}>
          <td>{r['rank']}</td><td class="l">{r['code']}</td>
          <td class="l"><b>{r['name'] or '—'}</b></td>
          <td>{r['price'] or '—'}</td>
          <td>{r['mv_yi']:,.0f}</td>
          <td><b>{r['pe']}</b></td>
          <td>{r['dy'] if r['dy'] is not None else '—'}</td>
          <td>{r['exp_g'] if r['exp_g'] is not None else '—'}</td>
          <td>{r['peg'] if r['peg'] is not None else '—'}</td>
          <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
          <td>{r['gpm'] if r['gpm'] is not None else '—'}</td>
          <td>{r['cetop'] if r['cetop'] is not None else '—'}</td>
          <td>{r['weight'] * 100:.1f}%</td></tr>"""

    core_tbl = "".join(tr(r) for r in core)
    gm_set = {r["code"] for r in gm}
    all_tbl = "".join(tr(r, hl=r["code"] in gm_set) for r in all_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>刘旭式框架 · 当前推荐A股（{as_of}）</title>
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
 tr.gm {{ background: #fff8e1; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 12px 16px; margin: 10px 0; font-size: 13.5px;
         line-height: 1.75; }}
 .badge {{ display: inline-block; background: #c62828; color: #fff;
           border-radius: 4px; padding: 1px 8px; font-size: 12px; }}
 .note {{ color: #888; font-size: 12px; margin-top: 18px;
          border-top: 1px dashed #ccc; padding-top: 10px; }}
 .kpi {{ font-size: 15px; font-weight: 700; }}
</style></head><body>

<h1>刘旭式框架 · 当前推荐 A 股</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 池子 = 万得全A(881001.WI)
当前 PIT 成分 <b>{stats['univ'] + stats.get('fin_removed', 0):,}</b> 只，已剔除
银行/非银金融 <b>{stats.get('fin_removed', 0):,}</b> 只（用户铁律）→ 筛选池
{stats['univ']:,} 只 · 一致预期为 PIT 快照</p>

<div class="card">
<b>筛选标准（LX-core，来自全A回测实证）：</b><br>
⓪ 金融剔除：申万/中信一级 <b>银行 + 非银金融 + 综合金融</b> PIT 成分
（juzi 中信行业 ∪ exfin 申万，共 {stats.get('fin_removed', 0):,} 只）——用户指定偏好约束；
① 市值 ≥ 100亿　② PE(TTM) &gt; 0　③ L4 估值安全边际：PE ≤ 25 <u>或</u> 股息率 ≥ 2%
　④ L5-garp 低预期逆向（2026-08-26 采纳）：一致预期净利增速 ≤ 60% 且 0 &lt; PEG ≤ 1<br>
排序信念：<b>PE 升序（便宜优先）</b>——回测显示这决定成败：同一筛选器 PE 升序 +60%
vs 质量优先 -12%。<br>
可选质量层 <span class="badge">LX-gm</span>：毛利率 ≥ 全市场中位数
（{gmed:.1f}%）——回测中唯一"收益持平、回撤砍半"的质量层（MDD -24.9% → -13.9%）。
</div>

<h2>① 核心推荐 LX-core · top-{len(core)}（等权 {core_w:.1%}，单票 ≤5%）</h2>
<p class="sub">按 PE 升序（便宜优先）排列。当前时点命中 {stats['core_pass']:,} 只，
组合取前 {len(core)} 只等权。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>股息率%</th><th>预期增速%</th><th>PEG</th>
<th>预期ROE%</th><th>毛利率%</th><th>OCF/市值%</th><th>权重</th></tr>
{core_tbl}
</table>

<h2>② 质量过滤版 LX-gm · top-{len(gm)}（等权 {gm_w:.1%}）</h2>
<p class="sub">在 core 之上要求毛利率 ≥ 市场中位数（{gmed:.1f}%），
命中 {stats['gm_pass']:,} 只。回测口径下该层的价值是<b>砍回撤而非增收益</b>。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>股息率%</th><th>预期增速%</th><th>PEG</th>
<th>预期ROE%</th><th>毛利率%</th><th>OCF/市值%</th><th>权重</th></tr>
{''.join(tr(r) for r in gm)}
</table>

<h2>③ 全部命中明细（{len(all_rows)} 只，黄色 = 同时通过 gm 层）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>股息率%</th><th>预期增速%</th><th>PEG</th>
<th>预期ROE%</th><th>毛利率%</th><th>OCF/市值%</th><th>权重</th></tr>
{all_tbl}
</table>

<h2>④ 筛选漏斗</h2>
<table>
<tr><th>步骤</th><th>剩余</th><th>淘汰</th></tr>
<tr><td class="l">万得全A 当前成分</td>
<td>{stats['univ'] + stats.get('fin_removed', 0):,}</td><td>—</td></tr>
<tr><td class="l">剔除银行/非银金融（铁律）</td>
<td>{stats['univ']:,}</td><td>{stats.get('fin_removed', 0):,}</td></tr>
<tr><td class="l">剔除市值缺失</td><td>{stats['univ'] - stats.get('mv_missing', 0):,}</td>
<td>{stats.get('mv_missing', 0):,}</td></tr>
<tr><td class="l">市值 ≥ 100亿</td>
<td>{stats['univ'] - stats.get('mv_missing', 0) - stats.get('mv_low', 0):,}</td>
<td>{stats.get('mv_low', 0):,}</td></tr>
<tr><td class="l">PE &gt; 0</td><td>{stats['core_pass'] + stats['l4'] + stats['l5'] + stats.get('gpm_missing', 0) + stats.get('pe_nonpos', 0) - stats.get('pe_nonpos', 0):,}</td><td>{stats.get('pe_nonpos', 0):,}</td></tr>
<tr><td class="l">L4 估值安全边际</td><td>{stats['core_pass'] + stats['l5'] + stats.get('gpm_missing', 0):,}</td>
<td>{stats.get('l4', 0):,}</td></tr>
<tr><td class="l">L5 低预期逆向</td><td>{stats['core_pass'] + stats.get('gpm_missing', 0):,}</td>
<td>{stats.get('l5', 0):,}</td></tr>
<tr><td class="l">毛利率 ≥ 市场中位数（gm 层）</td><td>{stats['gm_pass']:,}</td>
<td>{stats.get('gm_drop', 0):,}</td></tr>
</table>

<p class="note"><b>方法诚实性：</b>① 数据全部来自 juzi 估值面板 / HF 因子 /
一致预期 PIT 快照 + 腾讯实时行情，无合成数据；② con_roe / con_np_yoy / con_peg
为分析师一致预期，小盘无覆盖股在 L5 层即被剔除（这是框架的真实暴露）；
③ 毛利率中位数用<b>全市场</b>口径（非行业中位数），与回测一致；
④ 剔除金融是用户指定的偏好约束（2026-08-25 定稿），+7.1pp 回测口径<b>含</b>银行股，
本名单属"策略 + 行业约束"衍生口径，回测证据不直接适用；
⑤ 本名单由数值化筛选器产生，<b>不构成投资建议</b>；⑥ 框架回测区间 2021-08~2026-06
超额等权全A +7.1pp（core）/ MDD -13.9%（gm），过去表现不代表未来。</p>

</body></html>"""
    return html


if __name__ == "__main__":
    main()
