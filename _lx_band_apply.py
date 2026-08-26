# -*- coding: utf-8 -*-
"""
_lx_band_apply.py — Band 规避层落地：最终推荐名单
==================================================
管线位置: score(评分) -> band(体检) -> **apply(本脚本: 剔除规避层)**

输入:
  _lx_now_scored.json  — 评分 top40（含 score_total）
  _lx_now_band.json    — band 体检（含 pb_pct / flag）
规则:
  规避层: PB 5y 分位 > 90%  -> 剔除出最终推荐（自身历史高位，周期顶风险）
  其余: 保留, 带 band 标记（安全边际/自身低位/中性/偏高）
输出:
  _lx_now_final.json  — 最终推荐名单（权重按保留数重算 1/n）
  _lx_now_final.csv
  _lx_now_final_report.html
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
SCORE_JSON = BASE + "_lx_now_scored.json"
BAND_JSON = BASE + "_lx_now_band.json"
OUT_JSON = BASE + "_lx_now_final.json"
OUT_CSV = BASE + "刘旭框架_最终推荐.csv"
OUT_HTML = BASE + "_lx_now_final_report.html"

FLAG_STYLE = {"规避": "#c0392b", "安全边际": "#1e8449", "自身低位": "#2874a6",
              "偏高": "#b9770e", "中性": "#566573"}


def main():
    score = json.load(open(SCORE_JSON, encoding="utf-8"))
    band = json.load(open(BAND_JSON, encoding="utf-8"))
    band_map = {r["code"]: r for r in band["rows"]}

    kept, dropped = [], []
    for s in score["top40"]:
        code = s["code"]
        b = band_map.get(code, {})
        flag = b.get("flag", "中性")
        if flag == "规避":
            dropped.append({**s, "band_flag": flag, "pb_pct": b.get("pb_pct"),
                            "pe_pct": b.get("pe_pct"), "drop_reason": "PB 5y分位>90% 自身历史高位"})
            continue
        kept.append({
            **s,
            "band_flag": flag,
            "pb_pct": b.get("pb_pct"),
            "pe_pct": b.get("pe_pct"),
        })

    w = round(1.0 / len(kept), 4)
    for k in kept:
        k["weight"] = w

    payload = {
        "as_of": score.get("as_of"),
        "method": "score_top40 - band_veto",
        "band_rule": "PB 5y pct > 90% -> drop",
        "n_score": len(score["top40"]),
        "n_dropped": len(dropped),
        "n_final": len(kept),
        "weight": w,
        "dropped": dropped,
        "final": kept,
    }
    json.dump(payload, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # CSV
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["排名", "名称", "代码", "总分", "PE", "PB", "PE分位%", "PB分位%", "band判定", "权重"])
        for k in kept:
            wr.writerow([k.get("score_rank"), k["name"], k["code"], k.get("score_total"),
                         k.get("pe"), k.get("pb"), k.get("pe_pct"), k.get("pb_pct"),
                         k.get("band_flag"), k.get("weight")])

    # HTML
    trs = []
    for k in sorted(kept, key=lambda x: x.get("score_rank") or 99):
        st = FLAG_STYLE.get(k.get("band_flag"), "#566573")
        trs.append(f"""<tr>
<td>{k.get("score_rank")}</td><td>{k["name"]}</td><td style="font-family:Consolas">{k["code"]}</td>
<td>{k.get("score_total")}</td><td>{k.get("pe")}</td><td>{k.get("pb")}</td>
<td>{k.get("pe_pct") if k.get("pe_pct") is not None else "—"}</td>
<td style="font-weight:600">{k.get("pb_pct")}</td>
<td><span style="background:{st};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{k.get("band_flag")}</span></td>
<td>{k.get("weight")}</td></tr>""")
    drop_trs = "".join(
        f'<tr><td>{d.get("score_rank")}</td><td>{d["name"]}</td><td style="font-family:Consolas">{d["code"]}</td>'
        f'<td>{d.get("score_total")}</td><td>{d.get("pb_pct")}%</td><td>{d.get("pe_pct")}%</td>'
        f'<td>{d.get("drop_reason")}</td></tr>' for d in dropped)
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>最终推荐名单（含 Band 规避层）</title><style>
body{{font-family:'Segoe UI',Microsoft YaHei,sans-serif;margin:24px;background:#fff;color:#222}}
h1{{font-size:20px}}h2{{font-size:15px;color:#444;margin-top:28px}}
.summary{{display:flex;gap:16px;margin:12px 0}}
.card{{background:#f4f6f8;border-radius:10px;padding:10px 18px}}.card b{{font-size:22px}}
.card.warn{{background:#fdecea}}.card.ok{{background:#eafaf1}}
table{{border-collapse:collapse;width:100%;margin-top:10px;font-size:13px}}
th,td{{border:1px solid #e0e0e0;padding:6px 8px;text-align:center}}
th{{background:#eef2f6}}
.note{{color:#666;font-size:12px;line-height:1.7;margin-top:14px;background:#f8f9fa;padding:10px 14px;border-left:4px solid #999}}
</style></head><body>
<h1>最终推荐名单 — 评分 top40 + Band 规避层</h1>
<p style="color:#555">as_of: {payload["as_of"]} ｜ 规则: PB 5年分位 &gt; 90% 剔除（自身历史高位）</p>
<div class="summary">
<div class="card ok">保留 <b>{payload["n_final"]}</b> 只</div>
<div class="card warn">剔除 <b style="color:#c0392b">{payload["n_dropped"]}</b> 只</div>
<div class="card">等权 <b>{w}</b></div>
</div>
<h2>最终推荐（{payload["n_final"]} 只）</h2>
<table>
<tr><th>排名</th><th>名称</th><th>代码</th><th>总分</th><th>PE</th><th>PB</th><th>PE分位</th><th>PB分位</th><th>band判定</th><th>权重</th></tr>
{''.join(trs)}
</table>
<h2>被 Band 规避层剔除（{payload["n_dropped"]} 只）</h2>
<table>
<tr><th>原排名</th><th>名称</th><th>代码</th><th>总分</th><th>PB分位</th><th>PE分位</th><th>剔除原因</th></tr>
{drop_trs}
</table>
<div class="note"><b>说明</b>：Band 规避层基于个股自身 5 年日频 PB 历史分位（时间序列口径）。PB &gt; 90% 意味着横截面虽便宜，但已处自身周期/估值高位——典型周期顶陷阱（如煤炭股盈利顶部 PE 被动压低、PB 却真实抬升）。安全边际 = PE&amp;PB 分位均 &lt; 30%。</div>
</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(html)

    print(f"评分 {payload['n_score']} -> 保留 {payload['n_final']} / 剔除 {payload['n_dropped']}")
    for d in dropped:
        print(f"  ✗ 剔除 {d['name']}({d['code']}) PB分位 {d.get('pb_pct')}% 总分 {d.get('score_total')}")
    print(f"JSON -> {OUT_JSON}")
    print(f"HTML -> {OUT_HTML}")


if __name__ == "__main__":
    main()
