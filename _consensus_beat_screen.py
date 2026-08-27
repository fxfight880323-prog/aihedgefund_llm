# -*- coding: utf-8 -*-
"""一致预期 beat + 上涨最强 → 当前推荐 top-20（剔除银行/非银金融）。

数据对齐 @ 2026-08-20（最新交易日，juzi PIT 快照）:
  - 池子: 万得全A 881001.WI PIT 成分 (_bt_lx_now_universe.json, 5529 只)
  - 一致预期: _bt_lx_now_consensus.json (5528 只, con_np_yoy / np_revision_4w/13w/26w / con_roe / con_peg)
  - 估值: _bt_lx_now_valuation.json (pe_ttm / total_mv)
  - 剔除: _bt_sw_fin_universe.json (申万 银行+非银金融 PIT 成分)

筛选逻辑:
  beat    = np_revision_4w > 0（近4周一致预期净利润上修, 分析师方向性上调）
  上涨强  = con_np_yoy > 0 且按 con_np_yoy 降序（一致预期净利同比增速最高）
  质量版  = 主榜 + con_roe >= 12（C-Score 实证阈值）
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UNIV_FILE = "_bt_lx_now_universe.json"
CONS_FILE = "_bt_lx_now_consensus.json"
VAL_FILE = "_bt_lx_now_valuation.json"
FIN_FILE = "_bt_sw_fin_universe.json"
# fallback: 若申万 PIT 金融成分文件缺失，复用 exfin 脚本内置的银行+非银名单（同口径）
try:
    from _cs_now_recommend_exfin import FIN_CODES as _FIN_CODES_FALLBACK
except Exception:
    _FIN_CODES_FALLBACK = set()
OUT_JSON = "_bt_consensus_beat_results.json"
OUT_CSV = "一致预期beat_上涨最强_top20.csv"
OUT_HTML = "_consensus_beat_report.html"

TOP_N = 20
MIN_ROE_QUAL = 12.0


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def load_map(path):
    d = json.loads(open(path, encoding="utf-8").read())
    return {r.get("stock_code"): r for r in d.get("records", [])}, d.get("as_of")


def fetch_tencent(codes, batch=100):
    """腾讯行情: 名称/现价。返回 {code: (name, price)}"""
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
            body = urllib.request.urlopen(req, timeout=25).read().decode("gbk", "ignore")
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
    print("=" * 78)
    print("  一致预期 beat + 上涨最强 · 当前推荐 top-20（剔除银行/非银金融）")
    print("=" * 78)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    members = univ.get("members", [])
    as_of = univ.get("as_of")
    cons, cons_asof = load_map(CONS_FILE)
    val, val_asof = load_map(VAL_FILE)
    print(f"as_of={as_of} | univ={len(members)} | cons={len(cons)} "
          f"@ {cons_asof} | val={len(val)} @ {val_asof}")

    # ---- 金融剔除 ----
    fin = None
    if os.path.exists(FIN_FILE):
        fin = json.loads(open(FIN_FILE, encoding="utf-8").read())
    if fin:
        fin_set = set()
        for k, v in fin.items():
            fin_set |= set(v.get("members", []))
            print(f"  剔除 {k}: {v.get('index')} {len(v.get('members', []))} 只")
    else:
        # fallback: 硬编码银行+非银 121 只（与 _cs_now_recommend_exfin 同口径）
        fin_set = set(_FIN_CODES_FALLBACK)
        print(f"  [fallback] 未找到 {FIN_FILE}，复用 exfin 内置银行+非银名单 {len(fin_set)} 只")
    core = [m for m in members if m not in fin_set]
    print(f"剔除金融后池子: {len(members)} - {len(fin_set)} = {len(core)} 只")

    # ---- 筛选 ----
    rows = []
    for sc in core:
        c = cons.get(sc) or {}
        v = val.get(sc) or {}
        rev4w = _num(c.get("np_revision_4w"))
        rev13w = _num(c.get("np_revision_13w"))
        rev26w = _num(c.get("np_revision_26w"))
        yoy = _num(c.get("con_np_yoy"))
        roe = _num(c.get("con_roe"))
        peg = _num(c.get("con_peg"))
        pe = _num(v.get("pe_ttm"))
        mv = _num(v.get("total_mv"))
        if rev4w is None or yoy is None:
            continue
        if rev4w <= 0 or yoy <= 0:      # beat 且 增长
            continue
        rows.append({
            "code": sc, "rev4w": rev4w, "rev13w": rev13w, "rev26w": rev26w,
            "yoy": yoy, "roe": roe, "peg": peg, "pe": pe, "mv": mv,
        })

    # ---- 排序: 上涨最强 = con_np_yoy 降序, 并列按 rev4w 降序 ----
    rows.sort(key=lambda r: (r["yoy"], r["rev4w"]), reverse=True)
    print(f"\nbeat+上涨 命中 {len(rows)} 只（金融外）")

    qual = [r for r in rows if r["roe"] is not None and r["roe"] >= MIN_ROE_QUAL]
    print(f"其中 con_roe≥{MIN_ROE_QUAL}% 质量版 {len(qual)} 只")

    top = rows[:TOP_N]
    qual_top = qual[:TOP_N]

    # ---- 名称/现价 ----
    need = {r["code"] for r in rows}
    tq = fetch_tencent(sorted(need))
    print(f"tencent 名称解析: {len(tq)}/{len(need)}")

    def build(lst, tag):
        out = []
        for i, r in enumerate(lst, 1):
            code = r["code"].split(".")[0]
            name, price = tq.get(code, ("", None))
            out.append({
                "rank": i, "code": r["code"], "name": name,
                "price": round(price, 2) if price else None,
                "mv_yi": round((r["mv"] or 0) / 10000, 1),
                "pe": round(r["pe"], 1) if r["pe"] else None,
                "yoy": round(r["yoy"], 1),
                "rev4w": round(r["rev4w"], 1),
                "rev13w": round(r["rev13w"], 1) if r["rev13w"] is not None else None,
                "rev26w": round(r["rev26w"], 1) if r["rev26w"] is not None else None,
                "roe": round(r["roe"], 1) if r["roe"] is not None else None,
                "peg": round(r["peg"], 2) if r["peg"] is not None else None,
                "tag": tag,
            })
        return out

    top_rows = build(top, "main")
    qual_rows = build(qual_top, "qual")

    # ---- 输出 ----
    json.dump({
        "as_of": as_of, "cons_asof": cons_asof,
        "univ_n": len(members), "fin_removed": len(fin_set),
        "pool_n": len(core), "hit_n": len(rows), "qual_n": len(qual),
        "top": top_rows, "qual_top": qual_rows,
    }, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"JSON → {OUT_JSON}")

    cols = ["rank", "code", "name", "price", "mv_yi", "pe", "yoy", "rev4w",
            "rev13w", "rev26w", "roe", "peg"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(top_rows)
    print(f"CSV → {OUT_CSV}")

    open(OUT_HTML, "w", encoding="utf-8").write(
        build_html(as_of, cons_asof, members, fin_set, core, rows, qual,
                   top_rows, qual_rows))
    print(f"HTML → {OUT_HTML}")


def build_html(as_of, cons_asof, members, fin_set, core, rows, qual, top, qual_top):
    def tr(r):
        return f"""<tr>
          <td>{r['rank']}</td><td class="l">{r['code']}</td>
          <td class="l"><b>{r['name'] or '—'}</b></td>
          <td>{r['price'] or '—'}</td><td>{r['mv_yi']:,.0f}</td>
          <td>{r['pe'] or '—'}</td>
          <td><b style="color:#c62828">{r['yoy']}</b></td>
          <td><b style="color:#1565c0">{r['rev4w']}</b></td>
          <td>{r['rev13w'] if r['rev13w'] is not None else '—'}</td>
          <td>{r['rev26w'] if r['rev26w'] is not None else '—'}</td>
          <td>{r['roe'] if r['roe'] is not None else '—'}</td>
          <td>{r['peg'] if r['peg'] is not None else '—'}</td></tr>"""

    main_tbl = "".join(tr(r) for r in top)
    qual_tbl = "".join(tr(r) for r in qual_top)
    roe_med = statistics.median([r["roe"] for r in rows if r["roe"] is not None]) \
        if any(r["roe"] is not None for r in rows) else None

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>一致预期 beat · 上涨最强 top-20（{as_of}）</title>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px 36px;
        background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; margin-bottom: 4px; }}
 h2 {{ font-size: 16px; margin-top: 28px; border-left: 4px solid #c62828;
        padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 13px;
         background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 5px 9px; text-align: right;
           white-space: nowrap; }}
 th {{ background: #f0f0f0; position: sticky; top: 0; }}
 td.l {{ text-align: left; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 12px 16px; margin: 10px 0; font-size: 13.5px;
         line-height: 1.8; }}
 .kpi {{ font-size: 15px; font-weight: 700; color: #c62828; }}
 .note {{ color: #888; font-size: 12px; margin-top: 18px;
          border-top: 1px dashed #ccc; padding-top: 10px; }}
</style></head><body>

<h1>一致预期 beat · 上涨最强 · 当前推荐 A 股 top-20</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）· 一致预期 PIT 快照 @ {cons_asof} ·
池子 = 万得全A(881001.WI) 成分 {len(members):,} 只，剔除申万银行+非银金融
{len(fin_set):,} 只 → {len(core):,} 只</p>

<div class="card">
<b>策略逻辑（基于 juzi 一致预期数据，C-Score 框架实证方向）：</b><br>
① <b>beat</b>：近4周一致预期净利润上修 <span class="kpi">np_revision_4w &gt; 0</span>
——分析师在最近一个月内<b>方向性上调</b>盈利预期（预期差信息的"方向变动"维度，
此前回测证明比水平排序更有信息量）；<br>
② <b>上涨最强</b>：一致预期净利同比增速 <span class="kpi">con_np_yoy &gt; 0</span>，
并按 <span class="kpi">con_np_yoy 降序</span>取前 {TOP_N}（预期盈利弹性最高）；<br>
③ 金融剔除：申万一级 <b>银行(801780.SI)</b> + <b>非银金融(801790.SI)</b> PIT 成分
（券商/保险/多元金融一并剔除）。<br>
当前命中 <b>{len(rows):,}</b> 只；质量强化版（另加 con_roe ≥ 12%）命中
<b>{len(qual):,}</b> 只。
</div>

<h2>① 主榜 · beat + 上涨最强 top-{len(top)}</h2>
<p class="sub">按一致预期净利增速降序；红=预期增速%，蓝=4周上修幅度%。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>预期增速%</th><th>4周上修%</th><th>13周上修%</th>
<th>26周上修%</th><th>预期ROE%</th><th>PEG</th></tr>
{main_tbl}
</table>

<h2>② 质量强化版 · 另加 con_roe ≥ {MIN_ROE_QUAL:.0f}% top-{len(qual_top)}</h2>
<p class="sub">在 beat+上涨 之上要求一致预期 ROE ≥ {MIN_ROE_QUAL:.0f}%（C-Score 实证质量阈值，
命中 {len(qual):,} 只）。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>市值(亿)</th>
<th>PE(TTM)</th><th>预期增速%</th><th>4周上修%</th><th>13周上修%</th>
<th>26周上修%</th><th>预期ROE%</th><th>PEG</th></tr>
{qual_tbl}
</table>

<p class="note"><b>方法诚实性：</b>① 数据全部来自 juzi 一致预期 PIT 快照 + 估值面板
+ 腾讯实时行情，无合成数据；② np_revision 为分析师对当年净利的预期修正幅度（%），
正数=上调，是"预期被 beat"的方向信号，非实际财报 beat；③ 一致预期仅覆盖有分析师
覆盖的股票，小盘无覆盖股天然缺席（这是数据端的真实暴露）；④ 本名单由数值化筛选器
产生，<b>不构成投资建议</b>；⑤ C-Score 一致预期策略回测（2021-08 起）年化超额等权
全A +26pp，过去表现不代表未来。</p>

</body></html>"""


if __name__ == "__main__":
    main()
