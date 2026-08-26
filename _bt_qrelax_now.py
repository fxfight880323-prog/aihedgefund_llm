# -*- coding: utf-8 -*-
"""当前时点 (2026-08-24) q20 / q50 混合排序推荐名单。

复用 _lx_now_results.json 的 226 只 core-pass 池（万得全A PIT 成分，剔除金融，
as_of 2026-08-24，腾讯行情已解析），按 _bt_qrelax.py 回测完全相同的口径计算:

  pe_pct   = 100 - 池内PE百分位（PE 越低越高）
  q_score  = (gpm_pct + roe_pct + cet_pct) / 3  池内百分位均值
  q20      = 0.8*pe_pct + 0.2*q_score   → top40
  q50      = 0.5*pe_pct + 0.5*q_score   → top40

输出 _bt_qrelax_now.json / _bt_qrelax_now.html
"""
import json
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

MAX_HOLDINGS = 40
PER_NAME_CAP = 0.05

RESULTS_FILE = "_lx_now_results.json"
BAND_FILE = "_band_all.json"
OUT_JSON = "_bt_qrelax_now.json"
OUT_HTML = "_bt_qrelax_now.html"


def pct_rank(values, v):
    """池内百分位 (0~100)，值越大越好。与 _bt_qrelax.py 完全一致。"""
    n = len(values)
    if n == 0:
        return 50.0
    below = sum(1 for x in values if x < v)
    return below / n * 100.0


def main():
    d = json.load(open(RESULTS_FILE, encoding="utf-8"))
    as_of = d["as_of"]
    rows = d["all"]  # 226 只 core-pass，含名称/现价

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
        r["blend50"] = round(0.5 * r["pe_pct"] + 0.5 * r["q_score"], 1)

    # ---- 三组 top40 ----
    def pick(key):
        s = sorted(rows, key=lambda x: -x[key])
        return s[:MAX_HOLDINGS]

    base = sorted(rows, key=lambda x: x["pe"])[:MAX_HOLDINGS]  # 纯PE基线（PE升序）
    q20 = pick("blend20")
    q50 = pick("blend50")

    base_codes = {r["code"] for r in base}
    q20_codes = {r["code"] for r in q20}
    q50_codes = {r["code"] for r in q50}

    # ---- band 数据（PB 5年分位，有则参考）----
    band = {}
    try:
        b = json.load(open(BAND_FILE, encoding="utf-8"))
        for r in b.get("rows", []):
            band[r["code"]] = r
    except Exception:
        pass

    def enrich(lst, key):
        out = []
        for i, r in enumerate(lst, 1):
            bd = band.get(r["code"], {})
            out.append({
                "rank": i,
                "code": r["code"],
                "name": r["name"] or "?",
                "price": r.get("price"),
                "mv_yi": r.get("mv_yi"),
                "pe": r["pe"],
                "pe_pct": r["pe_pct"],       # 便宜度：PE 越低越高
                "gpm": r["gpm"],
                "con_roe": r["con_roe"],
                "cetop": r["cetop"],
                "q_score": r["q_score"],
                "blend": r[key],
                "in_gm": r.get("in_gm", False),
                "is_new": r["code"] not in base_codes,
                "pb_pct": bd.get("pb_pct"),
                "band_flag": bd.get("flag"),
                "weight": round(min(1.0 / MAX_HOLDINGS, PER_NAME_CAP), 4),
            })
        return out

    base_out = enrich(base, "blend20")
    q20_out = enrich(q20, "blend20")
    q50_out = enrich(q50, "blend50")

    # ---- 变动明细 ----
    def changes(new_lst, key):
        new_codes = {r["code"] for r in new_lst}
        add = [r for r in new_lst if r["code"] not in base_codes]
        drop = [r for r in base if r["code"] not in new_codes]
        return add, drop

    q20_add, q20_drop = changes(q20, "blend20")
    q50_add, q50_drop = changes(q50, "blend50")

    out = {
        "as_of": as_of,
        "pool_n": len(rows),
        "base": base_out,          # 纯PE基线 top40（对照）
        "q20": q20_out,
        "q50": q50_out,
        "q20_changes": {"add": [r["code"] for r in q20_add],
                        "drop": [r["code"] for r in q20_drop]},
        "q50_changes": {"add": [r["code"] for r in q50_add],
                        "drop": [r["code"] for r in q50_drop]},
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON → {OUT_JSON}")

    # ---- 控制台摘要 ----
    print(f"as_of={as_of} | 池子 {len(rows)} 只 | 各取 top{MAX_HOLDINGS}")
    print(f"\n=== q20 (80%PE + 20%质量) ===")
    for r in q20_out:
        flag = "  ★新增" if r["is_new"] else ""
        gm = " GM" if r["in_gm"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name']:<7} PE={r['pe']:>5.1f} "
              f"pe_pct={r['pe_pct']:>4.0f} q={r['q_score']:>4.0f} blend={r['blend']:>4.1f}"
              f"{gm}{flag}")
    print(f"\n=== q50 (50%PE + 50%质量) ===")
    for r in q50_out:
        flag = "  ★新增" if r["is_new"] else ""
        gm = " GM" if r["in_gm"] else ""
        print(f"  {r['rank']:>2}. {r['code']:<11} {r['name']:<7} PE={r['pe']:>5.1f} "
              f"pe_pct={r['pe_pct']:>4.0f} q={r['q_score']:>4.0f} blend={r['blend']:>4.1f}"
              f"{gm}{flag}")

    print(f"\n=== 与纯PE基线差异 ===")
    print(f"q20: +{len(q20_add)} 只 | -{len(q20_drop)} 只")
    for r in q20_add:
        print(f"  +{r['code']} {r['name']} PE={r['pe']} q={r['q_score']}")
    for r in q20_drop:
        print(f"  -{r['code']} {r['name']} PE={r['pe']} q={r['q_score']}")
    print(f"q50: +{len(q50_add)} 只 | -{len(q50_drop)} 只")
    for r in q50_add:
        print(f"  +{r['code']} {r['name']} PE={r['pe']} q={r['q_score']}")
    for r in q50_drop:
        print(f"  -{r['code']} {r['name']} PE={r['pe']} q={r['q_score']}")

    build_html(out)
    print(f"HTML → {OUT_HTML}")


def build_html(out):
    as_of = out["as_of"]

    def tr(r, key):
        gm_badge = '<span style="background:#1e8449;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">GM</span>' if r["in_gm"] else ""
        new_badge = '<span style="background:#c62828;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">新</span>' if r["is_new"] else ""
        pb = f'{r["pb_pct"]:.0f}%' if r["pb_pct"] is not None else "—"
        band_flag = r["band_flag"] or ""
        warn = ' style="background:#fdecea"' if (r["pb_pct"] is not None and r["pb_pct"] > 90) else ""
        return f"""<tr{warn}>
        <td>{r['rank']}</td>
        <td class="l"><b>{r['name']}</b> {new_badge} {gm_badge}</td>
        <td class="l mono">{r['code']}</td>
        <td>{r['price'] if r['price'] else '—'}</td>
        <td>{r['mv_yi']:,.0f}</td>
        <td class="pe"><b>{r['pe']}</b></td>
        <td>{r['pe_pct']:.0f}</td>
        <td>{r['gpm'] if r['gpm'] is not None else '—'}</td>
        <td>{r['con_roe'] if r['con_roe'] is not None else '—'}</td>
        <td>{r['cetop'] if r['cetop'] is not None else '—'}</td>
        <td><b>{r['q_score']:.0f}</b></td>
        <td><b>{r['blend']:.1f}</b></td>
        <td>{pb}</td>
        <td>{band_flag}</td>
        <td>{r['weight']*100:.1f}%</td>
        </tr>"""

    def table(lst, key):
        return "".join(tr(r, key) for r in lst)

    q20_tbl = table(out["q20"], "blend20")
    q50_tbl = table(out["q50"], "blend50")
    base_tbl = table(out["base"], "blend20")

    # 差异表
    def diff_tbl(add_list, drop_list):
        rows = ""
        for r in add_list:
            rows += f"""<tr class="add"><td class="l">+ {r['name']}</td><td class="l">{r['code']}</td>
            <td>{r['pe']}</td><td>{r['gpm']}</td><td>{r['con_roe']}</td><td>{r['q_score']:.0f}</td>
            <td>{r['blend']:.1f}</td></tr>"""
        for r in drop_list:
            rows += f"""<tr class="drop"><td class="l">− {r['name']}</td><td class="l">{r['code']}</td>
            <td>{r['pe']}</td><td>{r['gpm']}</td><td>{r['con_roe']}</td><td>{r['q_score']:.0f}</td>
            <td>—</td></tr>"""
        return rows

    q20_diff = diff_tbl(
        [r for r in out["q20"] if r["is_new"]],
        [r for r in out["base"] if r["code"] in out["q20_changes"]["drop"]])

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>质量放松PE排序 · 当前推荐（{as_of}）</title>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px 36px; background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; margin-bottom: 4px; }}
 h2 {{ font-size: 16px; margin-top: 28px; border-left: 4px solid #c62828; padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 12.5px; background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: right; white-space: nowrap; }}
 th {{ background: #f0f0f0; position: sticky; top: 0; }}
 td.l {{ text-align: left; }}
 td.mono {{ font-family: Consolas, monospace; }}
 td.pe {{ font-weight: 700; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 16px;
         margin: 10px 0; font-size: 13.5px; line-height: 1.75; }}
 .badge {{ display: inline-block; background: #c62828; color: #fff; border-radius: 4px;
           padding: 1px 8px; font-size: 12px; }}
 .kpi {{ font-size: 15px; font-weight: 700; }}
 tr.add td {{ background: #e8f5e9; }}
 tr.drop td {{ background: #fce4ec; }}
 .note {{ color: #888; font-size: 12px; margin-top: 18px; border-top: 1px dashed #ccc; padding-top: 10px; }}
 .legend span {{ margin-right: 14px; font-size: 12px; }}
</style></head><body>

<h1>质量放松 PE 排序 · 当前推荐 A 股</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 池子 = 万得全A PIT 成分（剔除金融）
{out['pool_n']:,} 只 core 命中 · 排序口径与回测 <code>_bt_qrelax.py</code> 完全一致</p>

<div class="card">
<b>两个变体的定义（回测验证结果）：</b><br>
<span class="badge">q20</span> <b>80%PE + 20%质量</b>：blend = 0.8×pe_pct + 0.2×q_score —— 回测
<b>+3.40pp</b>（vs 纯PE基线），回撤持平（22.03% vs 22.12%），增量最优 ✅<br>
<span class="badge">q50</span> <b>50%PE + 50%质量</b>：blend = 0.5×pe_pct + 0.5×q_score —— 回测
<b>+1.08pp</b>，MDD 降至 <b>19.05%</b>（-3.1pp），风险控制最佳 ⚠️<br>
质量分 q_score = 毛利率 / 预期ROE / OCF市值比 三者<b>池内百分位</b>均值（0~100）。
pe_pct = 池内便宜度百分位（PE 越低越高）。<br>
<span class="legend">
<span style="color:#c62828">■ 新</span> 相对纯PE基线新增（基线踢出同数量）　
<span style="color:#1e8449">■ GM</span> 通过毛利率≥市场中位数质量层　
<span style="color:#c0392b">■ 红底</span> PB 5年分位 &gt; 90%（估值偏高警示，band 参考层）
</span>
</div>

<h2>① q20 · 80%PE + 20%质量 · top40（等权 2.5%，单票 ≤5%）</h2>
<p class="sub">回测增量最优变体：每期仅替换 1~6 只，踢出"便宜但低质"，换入"稍贵但高质"。</p>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>便宜度</th><th>毛利率%</th><th>预期ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{q20_tbl}
</table>

<h2>② q50 · 50%PE + 50%质量 · top40（等权 2.5%，单票 ≤5%）</h2>
<p class="sub">回测风险控制最佳变体：MDD -3.1pp，收益微增。</p>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>便宜度</th><th>毛利率%</th><th>预期ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{q50_tbl}
</table>

<h2>③ 对照：纯 PE 升序基线 top40（当前线上口径）</h2>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>便宜度</th><th>毛利率%</th><th>预期ROE%</th><th>OCF/市值%</th>
<th>质量分</th><th>blend</th><th>PB分位</th><th>Band</th><th>权重</th></tr>
{base_tbl}
</table>

<h2>④ 变体 vs 基线的换手明细</h2>
<h3>q20 · +{len([r for r in out['q20'] if r['is_new']])} 只 / −{len(out['q20_changes']['drop'])} 只</h3>
<table>
<tr><th>方向</th><th>名称</th><th>代码</th><th>PE</th><th>毛利率%</th><th>ROE%</th><th>质量分</th><th>blend</th></tr>
{q20_diff}
</table>
<h3>q50 · +{len([r for r in out['q50'] if r['is_new']])} 只 / −{len(out['q50_changes']['drop'])} 只</h3>
<table>
<tr><th>方向</th><th>名称</th><th>代码</th><th>PE</th><th>毛利率%</th><th>ROE%</th><th>质量分</th><th>blend</th></tr>
{diff_tbl([r for r in out['q50'] if r['is_new']], [r for r in out['base'] if r['code'] in out['q50_changes']['drop']])}
</table>

<p class="note"><b>方法诚实性：</b>① 本名单为 2026-08-24 最新时点数据（juzi 估值/HF因子/一致预期
PIT 快照 + 腾讯行情），非回测快照；② 回测结果（q20 +3.40pp / q50 +1.08pp）来自
2021-08~2026-04 日频+复权区间，样本外表现不确定；③ 福耀玻璃（600660.SH）在此两变体
pool 中 PE 排 ~130/226，即使 q50 blend 仍不足以进 top40（上轮已证实）；④ PB 分位为
band 参考层（_band_all.json，仅覆盖 77 只），非本排序组成部分；⑤ 本名单由数值化筛选器
产生，<b>不构成投资建议</b>。</p>

</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
