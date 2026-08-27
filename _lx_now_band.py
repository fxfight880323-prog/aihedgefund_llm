# -*- coding: utf-8 -*-
"""
_lx_now_band.py — 估值 band 体检层（自身历史分位）
====================================================
输入: 推荐名单 JSON（含 code/name/pe）+ 5 年日频估值 parquet URL
输出: band 分位表 + 规避层(PB>90%) / 确认层(PE&PB<30%) 标记 + HTML 报告

口径说明:
  - band = 该股自身 5 年日频 pe_ttm/pb 的历史分位（时间序列均值回归）
  - 规避层: PB 5y 分位 > 90%  → 横截面便宜但自身历史高位（周期顶/泡沫顶风险）
  - 确认层: PE & PB 5y 分位均 < 30% → 双维度自身低位（安全边际）
  - PE 分位仅参考（盈利下滑股 PE 被动抬升失真），规避以 PB 为准
用法:
  python _lx_now_band.py <parquet_url> [src_json]
"""
import sys, os, json, io
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
SRC_JSON = BASE + "_lx_now_scored.json"     # 评分 top40 名单
OUT_JSON = BASE + "_lx_now_band.json"
OUT_HTML = BASE + "_lx_now_band_report.html"

WARN_PB_PCT = 90   # 规避阈值
SAFE_PCT = 30      # 确认阈值


def load_universe(src_json):
    d = json.load(open(src_json, encoding="utf-8"))
    rows = d["top40"]
    univ = {}
    for r in rows:
        code = r.get("code") or r.get("stock_code")
        univ[code] = {"name": r.get("name", code), "pe_now": r.get("pe"),
                      "score_total": r.get("score_total"), "score_rank": r.get("score_rank")}
    return univ


def calc_band(df, univ):
    df["date"] = pd.to_datetime(df["date"])
    out = []
    for code, info in sorted(univ.items()):
        g = df[df["stock_code"] == code].sort_values("date")
        if g.empty:
            out.append({**info, "code": code, "err": "no data"})
            continue
        g = g.dropna(subset=["pb"])
        if g.empty:
            out.append({**info, "code": code, "err": "no pb"})
            continue
        pe = g["pe_ttm"].dropna()
        pb = g["pb"]
        cur_pe = info.get("pe_now") or (float(pe.iloc[-1]) if len(pe) else None)
        cur_pb = float(pb.iloc[-1])
        # 只统计>0的历史（PE<=0 无意义，PB<=0 异常）
        pe_pos = pe[pe > 0]
        pb_pos = pb[pb > 0]

        def pct(v, s):
            if v is None or len(s) == 0:
                return None
            return float((s < v).mean() * 100)

        def qs(s, qs=[0.10, 0.25, 0.50, 0.75, 0.90]):
            if len(s) == 0:
                return [None] * len(qs)
            return [round(float(x), 2) for x in s.quantile(qs)]

        pe_pct = pct(cur_pe, pe_pos) if cur_pe and cur_pe > 0 else None
        pb_pct = pct(cur_pb, pb_pos)

        # 标记
        flags = []
        if pb_pct is not None and pb_pct > WARN_PB_PCT:
            flags.append("规避")
        elif pe_pct is not None and pb_pct is not None and pe_pct < SAFE_PCT and pb_pct < SAFE_PCT:
            flags.append("安全边际")
        elif pb_pct is not None and pb_pct < SAFE_PCT:
            flags.append("自身低位")
        elif pb_pct is not None and pb_pct > 70:
            flags.append("偏高")
        else:
            flags.append("中性")

        out.append({
            "code": code, "name": info["name"],
            "score_rank": info.get("score_rank"), "score_total": info.get("score_total"),
            "pe_now": round(cur_pe, 2) if cur_pe else None,
            "pb_now": round(cur_pb, 2),
            "pe_pct": round(pe_pct, 1) if pe_pct is not None else None,
            "pb_pct": round(pb_pct, 1),
            "pe_q": qs(pe_pos), "pb_q": qs(pb_pos),
            "n_days": len(g), "flag": flags[0],
            "last_date": str(g["date"].iloc[-1].date()),
        })
    return out


def build_html(as_of, rows):
    n = len(rows)
    n_warn = sum(1 for r in rows if r.get("flag") == "规避")
    n_safe = sum(1 for r in rows if r.get("flag") == "安全边际")

    def flag_cell(f):
        color = {"规避": "#c0392b", "安全边际": "#1e8449", "自身低位": "#2874a6",
                 "偏高": "#b9770e", "中性": "#566573"}.get(f, "#566573")
        return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{f}</span>'

    def band_cell(r):
        pe, pb = r.get("pe_pct"), r.get("pb_pct")
        pe_s = f"{pe:.0f}%" if pe is not None else "—"
        pb_s = f"{pb:.0f}%" if pb is not None else "—"
        return f'<td>{pe_s}</td><td style="font-weight:600">{pb_s}</td>'

    def q_cell(r):
        def f(s):
            if not s or not any(s):
                return "—"
            return " / ".join(str(x) for x in s)
        return f'<td style="font-size:11px;color:#555">{f(r.get("pe_q"))}</td>' \
               f'<td style="font-size:11px;color:#555">{f(r.get("pb_q"))}</td>'

    rows_sorted = sorted(rows, key=lambda r: (r.get("flag") != "规避", r.get("flag") != "安全边际", r.get("score_rank") or 999))
    trs = []
    for r in rows_sorted:
        trs.append(f"""<tr>
<td>{r.get("score_rank", "—")}</td><td>{r["name"]}</td><td style="font-family:Consolas">{r["code"]}</td>
<td>{r.get("pe_now", "—")}</td><td>{r.get("pb_now", "—")}</td>
{band_cell(r)}{q_cell(r)}
<td>{r.get("n_days", "—")}</td><td>{flag_cell(r.get("flag", "—"))}</td></tr>""")
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>估值 Band 体检（自身 5 年历史分位）</title>
<style>
body{{font-family:'Segoe UI',Microsoft YaHei,sans-serif;margin:24px;background:#fff;color:#222}}
h1{{font-size:20px}}h2{{font-size:15px;color:#444;margin-top:28px}}
.summary{{display:flex;gap:16px;margin:12px 0}}
.card{{background:#f4f6f8;border-radius:10px;padding:10px 18px}}
.card b{{font-size:22px}}
table{{border-collapse:collapse;width:100%;margin-top:10px;font-size:13px}}
th,td{{border:1px solid #e0e0e0;padding:6px 8px;text-align:center}}
th{{background:#eef2f6}}
tr.warn{{background:#fdecea}}
tr.safe{{background:#eafaf1}}
.note{{color:#666;font-size:12px;line-height:1.7;margin-top:14px;background:#f8f9fa;padding:10px 14px;border-left:4px solid #999}}
</style></head><body>
<h1>推荐名单估值 Band 体检 — 自身 5 年历史分位</h1>
<p style="color:#555">as_of: {as_of} ｜ 数据源: juzi 日频估值 2021-08 ~ 2026-08 ｜ 样本: 推荐 top40</p>
<div class="summary">
<div class="card">样本数 <b>{n}</b></div>
<div class="card" style="background:#fdecea">⚠ 规避层(PB>90%) <b style="color:#c0392b">{n_warn}</b></div>
<div class="card" style="background:#eafaf1">✓ 安全边际(PE&PB<30%) <b style="color:#1e8449">{n_safe}</b></div>
</div>
<table>
<tr><th>排名</th><th>名称</th><th>代码</th><th>当前PE</th><th>当前PB</th>
<th>PE分位</th><th>PB分位</th><th>PE分位点(10/25/50/75/90)</th><th>PB分位点(10/25/50/75/90)</th><th>样本天数</th><th>判定</th></tr>
{''.join(trs)}
</table>
<div class="note">
<b>口径说明</b>：分位 = 当前 PE/PB 在该股自身近 5 年日频分布中的位置（时间序列口径，与横截面排序互补）。<br>
<b>规避层</b>（PB 5y 分位 &gt; 90%）：横截面可能仍便宜，但自身已处历史高位——周期顶/泡沫顶信号，建议剔除或减配。<br>
<b>安全边际</b>（PE &amp; PB 分位均 &lt; 30%）：相对自身历史双重低估，可加分。<br>
<b>注意</b>：PE 分位对盈利下滑股失真（PE 被动抬升，见格力案例），规避判定以 PB 为准；盈利为负时 PE 分位置 "—"。
</div>
</body></html>"""


def main():
    parquet_url = sys.argv[1] if len(sys.argv) > 1 else None
    src = sys.argv[2] if len(sys.argv) > 2 else SRC_JSON
    univ = load_universe(src)
    if parquet_url:
        df = pd.read_parquet(parquet_url)
    else:
        # 读上次缓存
        old = json.load(open(OUT_JSON, encoding="utf-8"))
        as_of_old, rows = old["as_of"], old["rows"]
        html = build_html(as_of_old, rows)
        open(OUT_HTML, "w", encoding="utf-8").write(html)
        print(f"HTML -> {OUT_HTML}")
        return
    rows = calc_band(df, univ)
    as_of = "2026-08-24"
    payload = {"as_of": as_of, "method": "self_5y_band_pct", "n": len(rows),
               "warn_pb_pct": WARN_PB_PCT, "safe_pct": SAFE_PCT, "rows": rows}
    json.dump(payload, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    html = build_html(as_of, rows)
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    # 控制台摘要
    warn = [r for r in rows if r.get("flag") == "规避"]
    safe = [r for r in rows if r.get("flag") == "安全边际"]
    print(f"样本 {len(rows)} ｜ 规避 {len(warn)} ｜ 安全边际 {len(safe)}")
    for r in warn:
        print(f"  ⚠ 规避 {r['name']}({r['code']}) PB分位 {r['pb_pct']}% 当前PB {r['pb_now']} PE分位 {r.get('pe_pct')}%")
    for r in safe:
        print(f"  ✓ 安全 {r['name']}({r['code']}) PB分位 {r['pb_pct']}% PE分位 {r.get('pe_pct')}%")
    print(f"JSON -> {OUT_JSON}")
    print(f"HTML -> {OUT_HTML}")


if __name__ == "__main__":
    main()
