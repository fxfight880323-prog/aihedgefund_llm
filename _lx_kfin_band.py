# -*- coding: utf-8 -*-
"""
_lx_kfin_band.py — KEEP-FIN LX-core top40 估值 band 体检 + 最终持股建议报告
============================================================================
输入: _lx_now_results_kfin.json（含金融 core 口径 top40 + all 完整漏斗名单）
数据: juzi factor_get_valuation_panel 5年日频 pe_ttm/pb（一次 parquet 全拉）
输出: _lx_kfin_final.json / _lx_kfin_final_report.html

层口径（项目铁律）:
  - 规避层: PB 5y 分位 > 90%（横截面便宜但自身历史高位，周期顶风险）
  - 确认层: PE & PB 5y 分位均 < 30%（双低安全边际）
  - PE 分位仅参考（盈利下滑股 PE 被动抬升失真），规避以 PB 为准
替补: 规避股由 all 名单按 PE 升序顺位递补（仍为 core 口径）
"""
import sys, os, json, io, time
import pandas as pd
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
SRC = BASE + "_lx_now_results_kfin.json"
FIN_FILE = BASE + "_bt_sw_fin_universe.json"
OUT_JSON = BASE + "_lx_kfin_final.json"
OUT_HTML = BASE + "_lx_kfin_final_report.html"

N_TOP = 40
N_BENCH = 10          # 替补深度
WARN_PB = 90
SAFE_PCT = 30

sys.path.insert(0, BASE)
from examples.fetch_consensus import JuziHTTP, load_creds


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    as_of = d["as_of"]
    core = d["core"]                # top40（已 PE 升序）
    allr = d["all"]                 # 完整漏斗 PE 升序
    core_codes = {r["code"] for r in core}
    bench = [r for r in allr if r["code"] not in core_codes][:N_BENCH]

    # 行业标记
    fin = json.load(open(FIN_FILE, encoding="utf-8"))
    banks = set(fin["银行"]["members"])
    nonbk = set(fin["非银金融"]["members"])
    def ind(code):
        if code in banks: return "银行"
        if code in nonbk: return "非银"
        return ""

    codes = [r["code"] for r in core] + [r["code"] for r in bench]
    print(f"as_of={as_of} | core top{len(core)} + 替补{len(bench)} | 拉取 5y 日频估值...")

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
    print(f"parquet: {len(df)} 行, {df['stock_code'].nunique()} 只")

    def band(code, pe_now):
        g = df[df["stock_code"] == code].sort_values("date").dropna(subset=["pb"])
        if g.empty:
            return {"pb_pct": None, "pe_pct": None, "pb_now": None, "err": "no data"}
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

    rows = []
    for r in core:
        b = band(r["code"], r.get("pe"))
        flag = ""
        if b["pb_pct"] is not None and b["pb_pct"] > WARN_PB: flag = "规避"
        elif (b["pb_pct"] is not None and b["pb_pct"] < SAFE_PCT
              and b["pe_pct"] is not None and b["pe_pct"] < SAFE_PCT): flag = "确认"
        rows.append({**r, **b, "flag": flag, "industry": ind(r["code"]), "role": "core"})
    for r in bench:
        b = band(r["code"], r.get("pe"))
        flag = ""
        if b["pb_pct"] is not None and b["pb_pct"] > WARN_PB: flag = "规避"
        elif (b["pb_pct"] is not None and b["pb_pct"] < SAFE_PCT
              and b["pe_pct"] is not None and b["pe_pct"] < SAFE_PCT): flag = "确认"
        rows.append({**r, **b, "flag": flag, "industry": ind(r["code"]), "role": "bench"})

    n_avoid = sum(1 for r in rows if r["role"] == "core" and r["flag"] == "规避")
    n_confirm = sum(1 for r in rows if r["role"] == "core" and r["flag"] == "确认")
    n_bank = sum(1 for r in core if r["code"] in banks)
    n_nonbk = sum(1 for r in core if r["code"] in nonbk)
    print(f"core40: 银行 {n_bank} + 非银 {n_nonbk} + 非金融 {40-n_bank-n_nonbk}"
          f" | 规避 {n_avoid} | 确认 {n_confirm}")

    json.dump({"as_of": as_of, "rows": rows,
               "meta": {"n_bank": n_bank, "n_nonbk": n_nonbk,
                        "n_avoid": n_avoid, "n_confirm": n_confirm,
                        "fac_asof": "2026-08-19(最后健康日,前向填充)",
                        "cons_asof": "2026-08-24"}},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    build_html(as_of, rows, n_bank, n_nonbk, n_avoid, n_confirm)
    print(f"JSON → {OUT_JSON}\n报告 → {OUT_HTML}")


def build_html(as_of, rows, n_bank, n_nonbk, n_avoid, n_confirm):
    def tr(r):
        c = "rgba(220,38,38,.12)" if r["flag"] == "规避" else (
            "rgba(22,163,74,.10)" if r["flag"] == "确认" else "")
        pbp = f"{r['pb_pct']:.0f}%" if r.get("pb_pct") is not None else "—"
        pep = f"{r['pe_pct']:.0f}%" if r.get("pe_pct") is not None else "—"
        pbn = f"{r['pb_now']:.2f}" if r.get("pb_now") is not None else "—"
        dy = f'{r["dy"]:.1f}%' if r.get("dy") is not None else "—"
        eg = f'{r["exp_g"]:.1f}%' if r.get("exp_g") is not None else "—"
        pg = f'{r["peg"]:.2f}' if r.get("peg") is not None else "—"
        pe_v = f'{r["pe"]:.1f}' if r.get("pe") is not None else "—"
        pr = f'{r["price"]:.2f}' if r.get("price") is not None else "—"
        role = "" if r["role"] == "core" else ' <span style="color:#888">替补</span>'
        ind = f'<span class="tag">{r["industry"]}</span>' if r["industry"] else ""
        return (f'<tr style="background:{c}"><td>{r["rank"]}</td>'
                f'<td class="l">{r["code"]} {r["name"]}{role} {ind}</td>'
                f'<td>{pr}</td><td>{pe_v}</td><td>{pbn}</td>'
                f'<td>{dy}</td><td>{eg}</td>'
                f'<td>{pg}</td><td>{pep}</td><td>{pbp}</td>'
                f'<td>{r["flag"] or "—"}</td></tr>')
    tbl = "".join(tr(r) for r in rows)
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>LX-core 含金融 当前持股建议 @ {as_of}</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui;margin:24px;background:#fafafa;color:#222}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px}}
table{{border-collapse:collapse;font-size:12.5px;width:100%;background:#fff}}
td,th{{border:1px solid #ddd;padding:5px 8px;text-align:center}}
th{{background:#1e3a5f;color:#fff;position:sticky;top:0}}
td.l{{text-align:left}} .tag{{background:#7c3aed;color:#fff;border-radius:3px;
font-size:10px;padding:1px 5px;margin-left:4px}}
.sub{{color:#666;font-size:13px;margin:6px 0 14px}}
.card{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:14px 18px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.kpi{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:12px;text-align:center}}
.kpi b{{font-size:22px;display:block}} .kpi span{{color:#666;font-size:12px}}
</style></head><body>
<h1>LX-core 含金融版 · 当前持股建议（top40 等权 2.5%）</h1>
<p class="sub">as_of {as_of} · 口径 = 回测 core 变体（+55.55%/5年, MDD -19.13%）：
万得全A PIT → mv≥100亿 → PE&gt;0 → L4(PE≤25 或 股息≥2%) → L5-garp(增速≤60% 且 0&lt;PEG≤1) → PE 升序 top40。<b>不剔除金融</b>。
一致预期 @08-24、HF因子 @08-19（juzi 08-20 起污染，最后健康日前向填充）。</p>

<div class="grid">
<div class="kpi"><b>{n_bank}</b><span>银行股</span></div>
<div class="kpi"><b>{n_nonbk}</b><span>非银金融</span></div>
<div class="kpi"><b style="color:#dc2626">{n_avoid}</b><span>PB分位&gt;90% 规避标记</span></div>
<div class="kpi"><b style="color:#16a34a">{n_confirm}</b><span>双低确认标记</span></div>
</div>

<h2>① 持股名单（PE 升序，红色=规避标记 绿色=双低确认，末尾 10 只为替补池）</h2>
<table><tr><th>#</th><th>代码/名称</th><th>现价</th><th>PE</th><th>PB</th>
<th>股息%</th><th>预期增速%</th><th>PEG</th><th>PE分位</th><th>PB分位</th><th>标记</th></tr>
{tbl}</table>

<div class="card"><b>读法：</b><br>
· 规避标记 = 该股 PB 处于自身 5 年 90% 分位以上——横截面便宜但自身历史高位（周期顶/修复到位风险）。
band 规避层在回测中为正贡献（finex +29.45%→+34.48%），建议对标记股降低仓位或用替补池顺位递补。<br>
· 确认标记 = PE&amp;PB 双双处于自身 5 年 30% 分位以下，安全边际最高。<br>
· 银行/非银为 PE 升序规则的必然产物（回测银行贡献 76% 收益），非行业主动判断——若估值修复，规则将自动离开。</div>

<h2>② 与既有口径的关系</h2>
<div class="card">
本名单 = 回测验证的 alpha 规则（PE 升序信念）原样落地；与"评分 top40"（价值50+质量25+安全25，展示口径，剔金融）互不替代。
模拟持仓账本 _sim_portfolio.json 沿用评分口径，本报告不改变既有账本。</div>

<p class="sub">数据: juzi 估值面板/一致预期 · 腾讯行情 · band=自身5年日频分位 | 仅供参考，非投资建议</p>
</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    main()
