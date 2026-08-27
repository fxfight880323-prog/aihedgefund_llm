# -*- coding: utf-8 -*-
"""管线一致性审计 — screen 全链产物 vs 模拟组合账本
================================================================================
校验点:
  A. q20 final 名单（_bt_q20_kfin.json）与 Q20 模拟组合（_sim_q20_portfolio.json）持仓一致性
  B. 主轨 final 名单（_lx_now_final.json）40 只 + 行业构成
  C. KFIN final 名单（_lx_kfin_final.json）40 只 + 行业构成
  D. 各名单数量/无重复/权重合法性
输出: 控制台摘要 + _pipeline_audit_report.html
"""
from __future__ import annotations
import sys, os, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
os.chdir(BASE)

FIN_FILE = BASE + "_bt_sw_fin_universe.json"
Q20_JSON = BASE + "_bt_q20_kfin.json"
SIM_Q20 = BASE + "_sim_q20_portfolio.json"
LX_FINAL = BASE + "_lx_now_final.json"
KFIN_FINAL = BASE + "_lx_kfin_final.json"
OUT_HTML = BASE + "_pipeline_audit_report.html"

MAX = 40


def load(p):
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def ind_of(code, fin):
    banks = set(fin.get("银行", {}).get("members", []))
    nonbk = set(fin.get("非银金融", {}).get("members", []))
    if code in banks:
        return "银行"
    if code in nonbk:
        return "非银"
    return "非金融"


def industry_stats(codes, fin):
    from collections import Counter
    c = Counter(ind_of(x, fin) for x in codes)
    return c.get("银行", 0), c.get("非银", 0), c.get("非金融", 0)


def main():
    fin = load(FIN_FILE)
    if not fin:
        print("!! 缺 _bt_sw_fin_universe.json（申万金融成分）")
        return 1

    checks = []

    # ---------- A. q20 final vs Q20 模拟组合 ----------
    q20 = load(Q20_JSON)
    sim = load(SIM_Q20)
    if q20 and sim:
        final_codes = [r["code"] for r in q20["final"]]
        sim_codes = [p["code"] for p in sim["positions"]]
        set_f, set_s = set(final_codes), set(sim_codes)
        missing = sorted(set_f - set_s)   # 名单有而账本无
        extra = sorted(set_s - set_f)     # 账本有而名单无
        dup = len(final_codes) != len(set_f)
        checks.append(("A.q20 final vs 模拟组合持仓",
                       len(final_codes) == MAX and len(sim_codes) == MAX and not missing and not extra and not dup,
                       f"final {len(final_codes)} 只 / 账本 {len(sim_codes)} 只 | 缺 {len(missing)} 多 {len(extra)} | 重复 {dup}"))
        if missing:
            checks.append(("  A1.名单有账本无", False, str(missing)))
        if extra:
            checks.append(("  A2.账本有名单无", False, str(extra)))
        nb, nnb, nf = industry_stats(sim_codes, fin)
        checks.append(("A3.Q20组合行业构成", nb + nnb + nf == 40, f"银行 {nb} + 非银 {nnb} + 非金融 {nf}"))
        # 权重合法性：等权 2.5% × 40，建仓时每笔扣 15bp 单边费用 → 成本合计 ≈ capital×(1−fee)
        w = [p.get("weight", p["cost_amount"]) for p in sim["positions"]]
        wsum = sum(w)
        wsum_ok = 0.95 * 1_000_000 <= wsum <= 1_000_000
        checks.append(("A4.Q20账本资金使用率", wsum_ok,
                       f"成本合计 {wsum:,.2f}（扣 15bp 单边费用后净投入，目标 ≈998,500）"))

    # ---------- B. 主轨 final（剔金融口径） ----------
    lx = load(LX_FINAL)
    if lx:
        lst = lx.get("final", lx.get("ranked", []))
        codes = [r["code"] for r in lst]
        nb, nnb, nf = industry_stats(codes, fin)
        checks.append(("B.主轨 final 名单", len(codes) == MAX and len(set(codes)) == MAX,
                       f"{len(codes)} 只 | 银行 {nb} + 非银 {nnb} + 非金融 {nf}（应无金融）"))

    # ---------- C. KFIN final ----------
    kf = load(KFIN_FINAL)
    if kf:
        lst = kf.get("rows") or kf.get("final") or kf.get("ranked", [])
        codes = [r["code"] for r in lst][:MAX]
        nb, nnb, nf = industry_stats(codes, fin)
        m = kf.get("meta", {})
        m_ok = (m.get("n_bank") == nb and m.get("n_nonbk") == nnb)
        checks.append(("C.KFIN final 名单", len(codes) == MAX and len(set(codes)) == MAX,
                       f"{len(codes)} 只 | 银行 {nb} + 非银 {nnb} + 非金融 {nf}（规避剔除 {m.get('n_avoid','?')} / 确认 {m.get('n_confirm','?')}）"))

    # ---------- 输出 ----------
    npass = sum(1 for _, ok, _ in checks if ok)
    print(f"\n=== 一致性审计：{npass}/{len(checks)} 通过 ===\n")
    for name, ok, msg in checks:
        print(f"  {'✔' if ok else '✘'} {name}: {msg}")

    # ---------- HTML ----------
    rows = "".join(
        f"<tr>{'<td style=\"color:#16a34a\">✔</td>' if ok else '<td style=\"color:#c62828\">✘</td>'}"
        f"<td class='l'>{name}</td><td class='l'>{msg}</td></tr>"
        for name, ok, msg in checks)
    q20_final_table = ""
    if q20:
        q20_final_table = "".join(
            f"<tr><td>{r['rank']}</td><td class='l'>{r['name']}</td><td class='l mono'>{r['code']}</td>"
            f"<td>{r['pe']}</td><td>{r['q_score']:.0f}</td><td>{r['blend']:.1f}</td>"
            f"<td>{r.get('pb_pct') if r.get('pb_pct') is not None else '—'}</td>"
            f"<td>{r.get('flag') or '—'}</td></tr>"
            for r in q20["final"])
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>管线一致性审计 · {q20.get('as_of', '') if q20 else ''}</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui;margin:24px 32px;background:#fafafa;color:#222}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:26px;border-left:4px solid #1565c0;padding-left:10px}}
table{{border-collapse:collapse;margin:10px 0;font-size:12.5px;background:#fff}}
th,td{{border:1px solid #ddd;padding:4px 8px;text-align:right;white-space:nowrap}}
th{{background:#f0f0f0}} td.l{{text-align:left}} td.mono{{font-family:Consolas,monospace}}
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px;margin:10px 0;font-size:13.5px;line-height:1.8}}
.kpi{{display:inline-block;background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:10px 18px;margin-right:10px;text-align:center}}
.kpi b{{font-size:20px;display:block}}
</style></head><body>
<h1>管线一致性审计（run.py screen 全链）</h1>
<p style="color:#666;font-size:13px">校验 q20 名单 ↔ Q20·质衡优选模拟组合账本 · 行业构成 · 权重合法性</p>
<div class="kpi"><b style="color:{'#16a34a' if npass==len(checks) else '#c62828'}">{npass}/{len(checks)}</b><span>检查项通过</span></div>
<div class="kpi"><b>{q20['pool_n'] if q20 else '—'}</b><span>含金融池子</span></div>
<div class="kpi"><b>{q20['meta']['n_bank'] if q20 else '—'}</b><span>q20 银行</span></div>
<div class="kpi"><b>{q20['meta']['n_nonbk'] if q20 else '—'}</b><span>q20 非银</span></div>
<h2>① 检查结果</h2>
<table><tr><th>结果</th><th>检查项</th><th>说明</th></tr>{rows}</table>
<h2>② Q20 最终名单（{len(q20['final']) if q20 else 0} 只）</h2>
<table>
<tr><th>#</th><th>名称</th><th>代码</th><th>PE</th><th>质量分</th><th>blend</th><th>PB分位%</th><th>Band</th></tr>
{q20_final_table}
</table>
<div class="card"><b>审计口径：</b>名单来自 <code>_bt_q20_kfin.json</code>（q20 = 0.8×pe_pct + 0.2×q_score，
band 规避 PB分位&gt;90% 剔除 + 替补顺位递补）；账本来自 <code>_sim_q20_portfolio.json</code>（100万/40只等权 2.5%）。
不一致时优先以 <b>回测验证口径（纯PE 排序信念）</b>为准，q20 为展示层排序微调。</div>
</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"\nHTML → {OUT_HTML}")
    return 0 if npass == len(checks) else 2


if __name__ == "__main__":
    sys.exit(main())
