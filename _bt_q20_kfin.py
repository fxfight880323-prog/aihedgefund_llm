# -*- coding: utf-8 -*-
"""q20 混合排序（0.8×PE便宜度 + 0.2×质量分）当前持股建议 — 含金融口径（KEEP-FIN）
================================================================================
输入: _lx_now_results_kfin.json（含金融 core-pass 池 221 只，as_of 2026-08-26）
口径: 与 _bt_qrelax.py 回测完全一致 —
         pe_pct  = 100 − 池内PE百分位（PE 越低越高）
         q_score = (gpm_pct + roe_pct + cet_pct) / 3  池内百分位均值
         q20     = 0.8*pe_pct + 0.2*q_score  → top40
band: juzi 5年日频估值 → PB/PE 自身历史分位（规避>WARN_PB 默认90 / 确认双低<30%）
      阈值可 --warn-pb 覆盖：80 更严（回测 +16.5pp / MDD14.5%，样本内），90 稳健（+11.4pp）
替补: 规避股按 q20 排名顺位递补（band 规避层回测正贡献）
输出: _bt_q20_kfin.json / _bt_q20_kfin.html
"""
from __future__ import annotations
import sys, os, json, io, time
import urllib.request
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
os.chdir(BASE)

SRC = BASE + "_lx_now_results_kfin.json"
FIN_FILE = BASE + "_bt_sw_fin_universe.json"
OUT_JSON = BASE + "_bt_q20_kfin.json"
OUT_HTML = BASE + "_bt_q20_kfin.html"

MAX_HOLDINGS = 40
BENCH_DEPTH = 30          # q20 替补深度（排名 41~70）
WARN_PB = 90              # band 规避阈值（PB 5年分位>WARN_PB 剔除），可 --warn-pb 覆盖
SAFE_PCT = 30

sys.path.insert(0, BASE)
from examples.fetch_consensus import JuziHTTP, load_creds


def _file_asof(p):
    """读 fetch 缓存 JSON 的 as_of（顶层或数组首条），用于报告元数据自动跟随数据更新。"""
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d.get("as_of") or (d[0].get("as_of") if isinstance(d, list) and d else None)
    except Exception:
        return None


CONS_ASOF = _file_asof(BASE + "_bt_lx_now_consensus.json") or "?"
FAC_ASOF = _file_asof(BASE + "_bt_lx_now_factors.json") or "?"


def pct_rank(values, v):
    """池内百分位 (0~100)，值越大越好。与 _bt_qrelax.py 一致。"""
    n = len(values)
    if n == 0:
        return 50.0
    return sum(1 for x in values if x < v) / n * 100.0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="q20 名单管线（含 band 规避层）")
    ap.add_argument("--warn-pb", type=int, default=90,
                    help="PB 5年分位规避阈值（默认90；可选更严80，回测 +16.5pp/MDD14.5%%）")
    args = ap.parse_args()
    global WARN_PB
    WARN_PB = args.warn_pb

    d = json.load(open(SRC, encoding="utf-8"))
    as_of = d["as_of"]
    rows = d["all"]                       # 221 只 core-pass（PE 升序）
    print(f"as_of={as_of} | 池子 {len(rows)} 只（含金融）")

    # ---- 池内百分位（与回测口径一致）----
    gpm_vals = [r["gpm"] for r in rows if r.get("gpm") is not None]
    roe_vals = [r["con_roe"] for r in rows if r.get("con_roe") is not None]
    cet_vals = [r["cetop"] for r in rows if r.get("cetop") is not None]
    pe_vals = [r["pe"] for r in rows if r.get("pe") is not None]

    for r in rows:
        r["gpm_pct"] = pct_rank(gpm_vals, r["gpm"]) if r.get("gpm") is not None else 0.0
        r["roe_pct"] = pct_rank(roe_vals, r["con_roe"]) if r.get("con_roe") is not None else 0.0
        r["cet_pct"] = pct_rank(cet_vals, r["cetop"]) if r.get("cetop") is not None else 0.0
        r["q_score"] = round((r["gpm_pct"] + r["roe_pct"] + r["cet_pct"]) / 3.0, 1)
        r["pe_pct"] = round(100.0 - pct_rank(pe_vals, r["pe"]), 1) if r.get("pe") is not None else 0.0
        r["blend20"] = round(0.8 * r["pe_pct"] + 0.2 * r["q_score"], 1)

    # ---- 三组名单 ----
    base40 = rows[:MAX_HOLDINGS]                                  # 纯PE基线（现有 core top40）
    by_blend = sorted(rows, key=lambda x: -x["blend20"])
    q20_40 = by_blend[:MAX_HOLDINGS]                              # q20 top40
    q20_bench = by_blend[MAX_HOLDINGS:MAX_HOLDINGS + BENCH_DEPTH] # q20 替补池

    base_codes = {r["code"] for r in base40}
    q20_codes = {r["code"] for r in q20_40}

    # ---- 行业标记 ----
    fin = json.load(open(FIN_FILE, encoding="utf-8"))
    banks = set(fin["银行"]["members"])
    nonbk = set(fin["非银金融"]["members"])
    def ind(code):
        if code in banks: return "银行"
        if code in nonbk: return "非银"
        return ""

    # ---- band 拉取（5年日频估值, 一次 parquet）----
    codes = [r["code"] for r in base40 + q20_40 + q20_bench]
    codes = list(dict.fromkeys(codes))
    print(f"band 拉取 {len(codes)} 只 × 5年日频...")
    cli = JuziHTTP(*load_creds())
    out = cli.call_tool("factor_get_valuation_panel", {
        "stock_codes": codes, "start_date": "2021-08-27",
        "end_date": as_of, "format": "parquet"})
    url = (out.get("download_url") or ((out.get("artifact") or {}).get("download_url")))
    raw = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    print(f"band parquet: {len(df)} 行, {df['stock_code'].nunique()} 只")

    def band(code, pe_now):
        g = df[df["stock_code"] == code].sort_values("date").dropna(subset=["pb"])
        if g.empty:
            return {"pb_pct": None, "pe_pct": None, "pb_now": None}
        pe = g["pe_ttm"].dropna(); pb = g["pb"]
        pe_pos = pe[pe > 0]; pb_pos = pb[pb > 0]
        cur_pb = float(pb.iloc[-1])
        pe_pct = pe_now if pe_now is not None and len(pe_pos) else None
        if pe_pct is None and len(pe_pos):
            pe_pct = float((pe_pos < float(pe.iloc[-1])).mean() * 100)
        pb_pct = float((pb_pos < cur_pb).mean() * 100) if len(pb_pos) else None
        return {"pb_pct": round(pb_pct, 1) if pb_pct is not None else None,
                "pe_pct": round(pe_pct, 1) if pe_pct is not None else None,
                "pb_now": round(cur_pb, 2)}

    def enrich(lst, tag):
        out = []
        for i, r in enumerate(lst, 1):
            b = band(r["code"], r.get("pe"))
            flag = ""
            if b["pb_pct"] is not None and b["pb_pct"] > WARN_PB: flag = "规避"
            elif (b["pb_pct"] is not None and b["pb_pct"] < SAFE_PCT
                  and b["pe_pct"] is not None and b["pe_pct"] < SAFE_PCT): flag = "确认"
            out.append({
                "rank": i, "code": r["code"], "name": r["name"] or "?",
                "price": r.get("price"), "mv_yi": r.get("mv_yi"),
                "pe": r["pe"], "pe_pct": r["pe_pct"], "gpm": r["gpm"],
                "con_roe": r["con_roe"], "cetop": r["cetop"],
                "q_score": r["q_score"], "blend": r["blend20"],
                "in_gm": r.get("in_gm", False),
                "is_new": r["code"] not in base_codes,
                "pb_pct": b["pb_pct"], "pe_pct_band": b["pe_pct"],
                "pb_now": b["pb_now"], "flag": flag,
                "industry": ind(r["code"]), "tag": tag,
                "weight": round(1.0 / MAX_HOLDINGS, 4),
            })
        return out

    base_out = enrich(base40, "base")
    q20_out = enrich(q20_40, "q20")
    q20_bench_out = enrich(q20_bench, "q20_bench")

    # ---- band 过滤后的最终建议名单（q20 剔除规避 → q20 替补顺位递补）----
    final = [dict(r) for r in q20_out if r["flag"] != "规避"]
    repl = [dict(r) for r in q20_bench_out if r["flag"] != "规避"]
    n_avoid_in_q20 = len(q20_out) - len(final)
    for r in repl[:n_avoid_in_q20]:
        r = dict(r); r["tag"] = "q20_final"
        final.append(r)
    final = final[:MAX_HOLDINGS]
    for i, r in enumerate(final, 1):
        r["rank"] = i
    n_bank = sum(1 for r in final if r["industry"] == "银行")
    n_nonbk = sum(1 for r in final if r["industry"] == "非银")
    n_confirm = sum(1 for r in final if r["flag"] == "确认")

    # ---- 变动明细：q20 vs 纯PE基线 ----
    q20_add = [r for r in q20_out if r["is_new"]]
    q20_drop = [r for r in base_out if r["code"] not in q20_codes]

    out = {
        "as_of": as_of,
        "pool_n": len(rows),
        "warn_pb": WARN_PB,
        "pool_desc": "万得全A PIT 含金融 core-pass（mv≥100亿 / PE>0 / L4 / L5-garp）",
        "fac_asof": FAC_ASOF + "(最后健康日,前向填充)",
        "cons_asof": CONS_ASOF,
        "method": "q20 = 0.8*pe_pct + 0.2*q_score, q_score=(gpm_pct+roe_pct+cet_pct)/3",
        "backtest_note": "q20 +3.40pp 增量验证于剔除金融口径(core_finex, 2021-08~2026-04 日频复权)",
        "base": base_out,
        "q20": q20_out,
        "q20_bench": q20_bench_out,
        "final": final,
        "meta": {
            "n_bank": n_bank, "n_nonbk": n_nonbk,
            "n_avoid_q20": n_avoid_in_q20, "n_confirm_final": n_confirm,
            "q20_add_n": len(q20_add), "q20_drop_n": len(q20_drop),
        },
        "changes": {
            "add": [{"code": r["code"], "name": r["name"], "pe": r["pe"],
                     "q_score": r["q_score"], "blend": r["blend"]} for r in q20_add],
            "drop": [{"code": r["code"], "name": r["name"], "pe": r["pe"],
                      "q_score": r["q_score"], "blend": r["blend"]} for r in q20_drop],
        },
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON → {OUT_JSON}")

    # ---- 控制台摘要 ----
    print(f"\n=== q20 top40（0.8×PE + 0.2×质量）@ {as_of} ===")
    for r in q20_out:
        nb = " ★新" if r["is_new"] else ""
        flag = f" [{r['flag']}]" if r["flag"] else ""
        ind2 = f"({r['industry']})" if r["industry"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name']:<8}{ind2:<5} "
              f"PE={r['pe']:>5.1f} pe_pct={r['pe_pct']:>4.0f} q={r['q_score']:>4.0f} "
              f"blend={r['blend']:>4.1f} PB分位={r['pb_pct'] if r['pb_pct'] is not None else '—'}{flag}{nb}")
    print(f"\n=== 最终建议名单（剔除规避+替补递补）：银行{n_bank} 非银{n_nonbk} 非金融{40-n_bank-n_nonbk} | 规避剔除{n_avoid_in_q20} | 双低确认{n_confirm} ===")
    for r in final:
        flag = f" [{r['flag']}]" if r["flag"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name']:<8} PE={r['pe']:>5.1f} blend={r['blend']:>4.1f} PB分位={r['pb_pct'] if r['pb_pct'] is not None else '—'}{flag}")
    print(f"\n=== q20 vs 纯PE基线变动：+{len(q20_add)} / -{len(q20_drop)} ===")
    for r in q20_add:
        print(f"  + {r['code']} {r['name']} PE={r['pe']} q={r['q_score']} blend={r['blend']}")
    for r in q20_drop:
        print(f"  - {r['code']} {r['name']} PE={r['pe']} q={r['q_score']} blend={r['blend']}")

    build_html(out)
    print(f"HTML → {OUT_HTML}")


def build_html(out):
    as_of = out["as_of"]

    def tr(r, show_new=True):
        gm = '<span style="background:#1e8449;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">GM</span>' if r["in_gm"] else ""
        nb = '<span style="background:#c62828;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">新</span>' if (show_new and r["is_new"]) else ""
        rp = '<span style="background:#f59e0b;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">替补</span>' if r.get("tag") == "q20_final" else ""
        ind2 = f'<span class="tag">{r["industry"]}</span>' if r["industry"] else ""
        pbp = f'{r["pb_pct"]:.0f}%' if r["pb_pct"] is not None else "—"
        pep = f'{r["pe_pct_band"]:.0f}%' if r["pe_pct_band"] is not None else "—"
        warn = ' style="background:#fdecea"' if r["flag"] == "规避" else (
            ' style="background:#e8f5e9"' if r["flag"] == "确认" else "")
        flag = f'<b style="color:#c0392b">规避</b>' if r["flag"] == "规避" else (
            f'<b style="color:#16a34a">确认</b>' if r["flag"] == "确认" else "—")
        pr = f'{r["price"]:.2f}' if r["price"] else "—"
        mv = f'{r["mv_yi"]:,.0f}' if r["mv_yi"] else "—"
        return f"""<tr{warn}>
        <td>{r['rank']}</td>
        <td class="l"><b>{r['name']}</b>{ind2} {nb} {gm} {rp}</td>
        <td class="l mono">{r['code']}</td>
        <td>{pr}</td><td>{mv}</td>
        <td class="pe"><b>{r['pe']}</b></td><td>{r['pe_pct']:.0f}</td>
        <td>{r['gpm'] if r['gpm'] is not None else '—'}</td>
        <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
        <td>{r['cetop'] if r['cetop'] is not None else '—'}</td>
        <td><b>{r['q_score']:.0f}</b></td>
        <td><b>{r['blend']:.1f}</b></td>
        <td>{pep}</td><td>{pbp}</td><td>{flag}</td>
        <td>{r['weight']*100:.1f}%</td></tr>"""

    q20_tbl = "".join(tr(r) for r in out["q20"])
    base_tbl = "".join(tr(r, show_new=False) for r in out["base"])
    final_tbl = "".join(tr(r) for r in out["final"])

    def diff_tr(r, add=True):
        cls = "add" if add else "drop"
        sign = "+" if add else "−"
        return f"""<tr class="{cls}"><td class="l">{sign} {r['name']}</td>
        <td class="l">{r['code']}</td><td>{r['pe']}</td><td>{r['q_score']:.0f}</td>
        <td>{r['blend']:.1f}</td></tr>"""
    diff_tbl = "".join(diff_tr(r, True) for r in out["changes"]["add"]) + \
               "".join(diff_tr(r, False) for r in out["changes"]["drop"])

    m = out["meta"]
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>q20 混合排序 · 8月调仓建议（{as_of}）</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui;margin:24px 32px;background:#fafafa;color:#222}}
h1{{font-size:22px;margin-bottom:4px}} h2{{font-size:16px;margin-top:28px;border-left:4px solid #c62828;padding-left:10px}}
.sub{{color:#666;font-size:13px;margin:6px 0 12px}}
table{{border-collapse:collapse;margin:10px 0;font-size:12.5px;background:#fff}}
th,td{{border:1px solid #ddd;padding:4px 8px;text-align:right;white-space:nowrap}}
th{{background:#f0f0f0;position:sticky;top:0}} td.l{{text-align:left}}
td.mono{{font-family:Consolas,monospace}} td.pe{{font-weight:700}}
.tag{{background:#7c3aed;color:#fff;border-radius:3px;font-size:10px;padding:1px 5px;margin-left:4px}}
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px;margin:10px 0;font-size:13.5px;line-height:1.8}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}}
.kpi{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:12px;text-align:center}}
.kpi b{{font-size:20px;display:block}} .kpi span{{color:#666;font-size:12px}}
tr.add td{{background:#e8f5e9}} tr.drop td{{background:#fce4ec}}
.note{{color:#888;font-size:12px;margin-top:18px;border-top:1px dashed #ccc;padding-top:10px}}
</style></head><body>

<h1>q20 混合排序（0.8×PE + 0.2×质量）· 8 月调仓建议</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 池子 = 万得全A PIT 成分 <b>含金融</b> core-pass {out['pool_n']:,} 只 ·
一致预期 @{out['cons_asof']} · HF因子 @{out['fac_asof']}（最后健康日，前向填充）</p>

<div class="grid">
<div class="kpi"><b>40</b><span>q20 top40 等权 2.5%</span></div>
<div class="kpi"><b style="color:#7c3aed">{m['n_bank']}</b><span>最终建议·银行</span></div>
<div class="kpi"><b style="color:#7c3aed">{m['n_nonbk']}</b><span>最终建议·非银</span></div>
<div class="kpi"><b style="color:#c0392b">{m['n_avoid_q20']}</b><span>规避剔除（PB分位&gt;{WARN_PB}%）</span></div>
<div class="kpi"><b style="color:#16a34a">{m['n_confirm_final']}</b><span>双低确认标记</span></div>
</div>

<div class="card">
<b>方法（与回测 <code>_bt_qrelax.py</code> 完全同口径）：</b><br>
· <b>pe_pct</b> = 池内便宜度百分位（PE 越低越高，0~100）<br>
· <b>q_score</b> = (毛利率 + 预期ROE + OCF/市值) 三者<b>池内百分位</b>均值<br>
· <b>q20 blend</b> = 0.8×pe_pct + 0.2×q_score —— 按 blend 降序取 top40<br>
· 回测验证（剔金融口径 core_finex，2021-08~2026-04 日频复权）：q20 相对纯PE基线
<b>+3.40pp</b>、回撤持平，为质量放松的唯一正贡献用法；<b>含金融口径下增量未单独回测</b>，
本名单为 q20 排序层在核心管线（core +55.55% / MDD -19.13%）上的落地展示。<br>
· band 规避层（PB 5年分位 &gt; {WARN_PB}% 剔除，回测 finex +29.45%→+34.48%）：红底=规避，绿底=PE&amp;PB 双低确认。
</div>

<h2>① q20 top40 · 8月调仓建议（等权 2.5%）</h2>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>便宜度</th><th>毛利%</th><th>ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PE分位</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{q20_tbl}
</table>

<h2>② 最终调仓名单（q20 剔除规避标记 → q20 替补池顺位递补）</h2>
<p class="sub">规避标记股 = PB 处于自身 5 年 {WARN_PB}% 分位以上（横截面便宜但自身历史高位），建议降仓或递补。
银行 {m['n_bank']} + 非银 {m['n_nonbk']} + 非金融 {40-m['n_bank']-m['n_nonbk']}。</p>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>便宜度</th><th>毛利%</th><th>ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PE分位</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{final_tbl}
</table>

<h2>③ 对照：纯 PE 升序基线 top40（当前核心管线口径）</h2>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE</th><th>便宜度</th><th>毛利%</th><th>ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PE分位</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{base_tbl}
</table>

<h2>④ q20 vs 纯PE基线 调仓变动（+{m['q20_add_n']} / −{m['q20_drop_n']}）</h2>
<table><tr><th>方向</th><th>名称</th><th>代码</th><th>PE</th><th>质量分</th><th>blend</th></tr>
{diff_tbl}
</table>

<div class="card">
<b>银行浓度说明（与您上一问的归因衔接）：</b>本名单按 q20 排序仍以银行为主体 —— 银行
PE 最便宜（pe_pct 接近满分），即使质量分拖累，blend 仍居前。回测归因显示银行贡献了
core 组合 5 年收益的 <b>76%</b>（+42.06pp / 总 +55.61pp，2021-06~2026-08），且银行等权组合
+53.4% vs 等权全A +41.1%、回撤 -17.4% vs -31.9%。q20 只做排序微调，不会改变银行主导
结构，也不会把组合变成"质量成长"组合。</div>

<p class="note"><b>方法诚实性：</b>① 名单数据 = juzi 估值/成分 @{as_of} + HF因子
@{out['fac_asof']} + 一致预期 @{out['cons_asof']}，腾讯行情现价，无合成；② q20 增量
+3.40pp 为剔金融口径回测，含金融口径未单独验证；③ PE 分位受盈利下滑污染，规避判定
一律以 <b>PB 分位</b>为准；④ band 覆盖仅限 top40+替补池；⑤ 本名单由数值化筛选器产生，
<b>不构成投资建议</b>。</p>
</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
