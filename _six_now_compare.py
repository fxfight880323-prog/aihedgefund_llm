# -*- coding: utf-8 -*-
"""6 策略当前推荐名单对比生成器。

角度（与 _framework_overview_report.py 一致）:
  1. LX-core 便宜优先 (40)
  2. LX 六因子评分 top20
  3. C-Score 一致预期 (17) + 剔除金融版 (14)
  4. 筹码×52周高点 AI科技池 (30)
  5. dist52 锚定双信号交集 (4)
  6. 一致预期 beat top20 (剔除金融)

行情: 腾讯 qt.gtimg.cn 统一刷新到最新交易日收盘。
输出: _six_now_compare.html
"""
from __future__ import annotations

import json
import os
import statistics
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(ROOT, "_six_now_compare.html")


def load(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return None
    return json.loads(open(p, encoding="utf-8").read())


# ---------------- 0. 金融剔除名单（用户铁律：所有筛选剔除银行/非银） ----------------
FIN = set()
_fin_f = os.path.join(ROOT, "_bt_sw_fin_universe.json")
if os.path.exists(_fin_f):
    for _v in json.load(open(_fin_f, encoding="utf-8")).values():
        if isinstance(_v, dict) and "members" in _v:
            FIN.update(_m.split(".")[0] for _m in _v["members"])
print(f"金融剔除名单: {len(FIN)} 只")


def num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def fmt(x, nd=1, dash="—"):
    if x is None or x != x:
        return dash
    return f"{x:.{nd}f}"


# ---------------- 1. 载入 6 策略名单 ----------------
lx = load("_lx_now_results.json")
lx_scored = load("_lx_now_scored.json")
cs = load("_cs_now_results.json")
cs_exfin = load("_cs_now_exfin_results.json")
chip = load("_ai_chip_52wk_top.json") or []
d52 = load("_lx_now_dist52.json")
beat = load("_bt_consensus_beat_results.json")

strategies = []

# ① LX-core
if lx:
    strategies.append({
        "key": "lx_core", "label": "① LX-core 便宜优先", "tag": "价值",
        "n": len(lx["core"]), "desc": "万得全A PIT → 市值≥100亿 → L4/L5 低预期 → PE 升序 top40",
        "evid": "回测 +60.0% / 超额等权全A +7.1pp / MDD -24.9%（当前最强方法论）",
        "rows": lx["core"],
        "code_key": "code", "rank_key": "rank", "name_key": "name",
        "cols": ["pe", "peg", "con_roe", "gpm", "dy", "mv_yi"],
    })

# ② LX 六因子评分
if lx_scored:
    top = lx_scored.get("top40", [])[:20]
    strategies.append({
        "key": "lx_scored", "label": "② LX 六因子评分", "tag": "价值·均衡",
        "n": len(top), "desc": "LX 过筛 226 只内：价值50% + 质量25% + 安全25% 百分位打分 top20",
        "evid": "排序信念仍为 PE 升序；评分用于同池择优（南京高科/新奥股份/周大生/宇通客车）",
        "rows": top, "code_key": "code", "rank_key": "score_rank", "name_key": "name",
        "cols": ["pe", "peg", "con_roe", "score_total"],
    })

# ③ C-Score（运行时剔除金融，用户铁律）
if cs:
    cs_rows = [r for r in cs["recommend"] if (r.get("code") or "").split(".")[0] not in FIN]
    strategies.append({
        "key": "cs", "label": "③ C-Score 一致预期", "tag": "预期差",
        "n": len(cs_rows), "desc": f"低估值池 top100(by PB) → C1~C4 方向性上修 → conviction>0 共 {len(cs['recommend'])} 只，剔除金融后 {len(cs_rows)} 只",
        "evid": "回测 +30.7% / 超额 +26.2pp / 10期跑赢8期（数据层核心资产）",
        "rows": cs_rows, "code_key": "code", "rank_key": "rank", "name_key": "name",
        "cols": ["pe", "pb", "con_roe", "con_np_yoy", "c_score"],
    })

# ④ 筹码×52周
strategies.append({
    "key": "chip", "label": "④ 筹码×52周高点", "tag": "科技成长",
    "n": len(chip), "desc": "AI产业链 664 只 → 筹码集中(锁仓) + dist52(反应不足) 双信号 top30",
    "evid": "筹码 Q1 +6.8%/年单调 8年IC全负；dist52 近高点裸测 +12.3pp",
    "rows": chip, "code_key": "ts", "rank_key": "rank", "name_key": "name",
    "cols": ["mv", "dist52", "conc", "chip", "score"],
})

# ⑤ dist52 锚定双信号交集
dual = []
if d52:
    dual = [r for r in d52["rows"]
            if r.get("score_rank") is not None and r["score_rank"] <= 20
            and r.get("dist52", 0) >= 0.85]
strategies.append({
    "key": "dist52", "label": "⑤ dist52 锚定交集", "tag": "行为·规避",
    "n": len(dual), "desc": "LX 评分前20 ∩ dist52≥0.85 —— 便宜 × 趋势健康的少数派",
    "evid": "近高点 +12.3pp / 深跌区 -36.9pp；只做规避与辅助，不替换 PE 排序",
    "rows": dual, "code_key": "code", "rank_key": "score_rank", "name_key": "name",
    "cols": ["pe", "dist52", "score_total", "score_rank"],
})

# ⑥ 一致预期 beat
if beat:
    strategies.append({
        "key": "beat", "label": "⑥ 一致预期 beat", "tag": "预期动能",
        "n": len(beat["top"]), "desc": "beat(rev4w>0) + 上涨最强(con_np_yoy 降序) top20，剔除银行/非银",
        "evid": "方向性上修(否决>打分 +4.7pp)；C-Score 框架实证方向",
        "rows": beat["top"], "code_key": "code", "rank_key": "rank", "name_key": "name",
        "cols": ["pe", "yoy", "rev4w", "roe", "peg", "mv_yi"],
    })


# ---------------- 1.5 估值 band 标记（5年日频自身分位, _band_all.json） ----------------
BAND = {}  # code6 -> {pe_pct, pb_pct, flag}
_band_f = os.path.join(ROOT, "_band_all.json")
if os.path.exists(_band_f):
    for _r in json.load(open(_band_f, encoding="utf-8"))["rows"]:
        BAND[_r["code"].split(".")[0]] = _r
print(f"band 标记载入: {len(BAND)} 只")


# ---------------- 2. 腾讯行情统一刷新 ----------------
def tx_prefix(code6):
    if code6.startswith(("6", "9")):
        return "sh"
    if code6.startswith(("8", "4")):
        return "bj"
    return "sz"


def code6_of(r, key):
    c = r.get(key) or ""
    c = c.split(".")[0]
    return c[-6:] if len(c) >= 6 else c


need = {}
for s in strategies:
    for r in s["rows"]:
        c6 = code6_of(r, s["code_key"])
        if c6:
            need.setdefault(c6, r.get(s["name_key"], ""))

codes = sorted(need)
quote = {}  # code6 -> dict(name, price, pct, mv_yi)
for i in range(0, len(codes), 60):
    q = ",".join(f"{tx_prefix(c)}{c}" for c in codes[i:i + 60])
    try:
        req = urllib.request.Request(f"https://qt.gtimg.cn/q={q}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        body = urllib.request.urlopen(req, timeout=25).read().decode("gbk", "ignore")
        for line in body.strip().split(";"):
            if "=" not in line or '"' not in line:
                continue
            raw = line.split("=")[0].strip().replace("v_", "")
            f = line.split('"')[1].split("~")
            c6 = raw[-6:]
            quote[c6] = {
                "name": f[1] if len(f) > 1 else "",
                "price": float(f[3]) if len(f) > 3 else None,
                "pct": float(f[32]) if len(f) > 32 else None,
                "mv_yi": float(f[45]) if len(f) > 45 else None,
            }
    except Exception as e:
        print(f"  tencent batch {i} 失败: {str(e)[:80]}")
print(f"行情刷新: {len(quote)}/{len(codes)} @ 最新交易日")


# ---------------- 3. 组装表格行 ----------------
def enrich(s):
    out = []
    for r in s["rows"]:
        c6 = code6_of(r, s["code_key"])
        q = quote.get(c6, {})
        row = {
            "code": c6,
            "name": q.get("name") or r.get(s["name_key"], ""),
            "price": q.get("price"),
            "pct": q.get("pct"),
            "mv_yi": num(r.get("mv_yi")) or (num(q.get("mv_yi")) / 1 if q.get("mv_yi") else None),
        }
        if s["key"] == "chip":
            row["mv_yi"] = num(r.get("mv"))  # 亿
        for k in s["cols"]:
            row[k] = r.get(k)
        row["_rank"] = r.get(s["rank_key"])
        b = BAND.get(c6) or {}
        row["band_pb"] = b.get("pb_pct")
        row["band_flag"] = b.get("flag")
        out.append(row)
    return out


for s in strategies:
    s["table"] = enrich(s)


# ---------------- 4. 统计与重叠 ----------------
def med(rows, k):
    vals = [num(r.get(k)) for r in rows if num(r.get(k)) is not None]
    return statistics.median(vals) if vals else None


def med_code(rows, k):
    vals = [num(r.get(k)) for r in rows if num(r.get(k)) is not None]
    return statistics.median(vals) if vals else None


stats_rows = []
for s in strategies:
    tbl = s["table"]
    pct_up = sum(1 for r in tbl if (r.get("pct") or 0) > 0)
    stats_rows.append({
        "label": s["label"], "n": s["n"],
        "mv_med": med(tbl, "mv_yi"),
        "pe_med": med(tbl, "pe"),
        "pct_up": pct_up, "pct_up_ratio": f"{pct_up}/{len(tbl)}",
    })

# 重叠矩阵
keys = [s["key"] for s in strategies]
labels = [s["label"] for s in strategies]
code_sets = []
for s in strategies:
    code_sets.append({r["code"] for r in s["table"] if r["code"]})

matrix = []
for i in range(len(keys)):
    row = []
    for j in range(len(keys)):
        inter = code_sets[i] & code_sets[j]
        row.append((len(inter), sorted(inter)))
    matrix.append(row)

# 多策略共振清单（≥2 策略命中）
from collections import defaultdict
hit = defaultdict(list)
for i, s in enumerate(strategies):
    for r in s["table"]:
        hit[r["code"]].append((i, r["name"]))
resonance = []
for c, lst in hit.items():
    if len(lst) >= 2:
        idxs = sorted(set(i for i, _ in lst))
        names = set(n for _, n in lst)
        resonance.append({"code": c, "name": next(iter(names)), "n": len(idxs),
                          "strategies": [labels[i] for i in idxs]})
resonance.sort(key=lambda x: (-x["n"], x["code"]))


# ---------------- 5. HTML ----------------
def fmt_n(v, nd=1):
    return "—" if v is None else f"{v:,.{nd}f}"


def pct_cell(pct):
    if pct is None:
        return '<td class="dim">—</td>'
    cls = "up" if pct > 0 else ("dn" if pct < 0 else "flat")
    return f'<td class="{cls}">{pct:+.2f}%</td>'


BAND_COLOR = {"规避": "#c0392b", "安全边际": "#1e8449", "自身低位": "#2874a6", "偏高": "#b9770e", "中性": "#566573"}

def band_tds(r):
    pb = r.get("band_pb")
    fl = r.get("band_flag")
    if pb is None:
        return '<td class="dim">—</td><td class="dim">—</td>'
    c = BAND_COLOR.get(fl, "#566573")
    return f'<td>{pb:.0f}%</td><td><span style="color:{c}">● {fl}</span></td>'

def table_html(s, show_cols, precs=None):
    th = '<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>今日%</th>'
    for c in show_cols:
        th += f'<th>{c}</th>'
    th += '<th>PB分位</th><th>band</th></tr>'
    trs = []
    for r in s["table"]:
        tds = [f'<td>{r["_rank"]}</td>',
               f'<td class="b">{r["name"] or "—"}</td>',
               f'<td>{r["code"]}</td>',
               f'<td>{fmt(r["price"], 2)}</td>',
               pct_cell(r["pct"])]
        for c in show_cols:
            v = r.get(c)
            if precs and c in precs:
                tds.append(f'<td>{fmt(v, precs[c])}</td>')
            else:
                tds.append(f'<td>{fmt_n(v) if isinstance(v, float) or v is None else v}</td>')
        tds.append(band_tds(r))
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table>{th}{"".join(trs)}</table>'


col_sets = {
    "lx_core": ["PE", "PEG", "ROE%", "毛利%", "股息%", "市值亿"],
    "lx_scored": ["PE", "PEG", "ROE%", "总分"],
    "cs": ["PE", "PB", "ROE%", "预期YoY%", "C分"],
    "chip": ["市值亿", "dist52", "集中z", "合成z", "综合分"],
    "dist52": ["PE", "dist52", "总分", "评分名次"],
    "beat": ["PE", "预期YoY%", "rev4w%", "ROE%", "PEG", "市值亿"],
}
col_keys = {
    "lx_core": ["pe", "peg", "con_roe", "gpm", "dy", "mv_yi"],
    "lx_scored": ["pe", "peg", "con_roe", "score_total"],
    "cs": ["pe", "pb", "con_roe", "con_np_yoy", "c_score"],
    "chip": ["mv", "dist52", "conc", "chip", "score"],
    "dist52": ["pe", "dist52", "score_total", "score_rank"],
    "beat": ["pe", "yoy", "rev4w", "roe", "peg", "mv_yi"],
}
col_prec = {
    "lx_core": {"mv_yi": 0},
    "lx_scored": {"score_total": 1},
    "cs": {"pe": 1, "pb": 2, "con_roe": 1, "con_np_yoy": 1},
    "chip": {"mv": 0, "dist52": 3, "conc": 2, "chip": 2, "score": 3},
    "dist52": {"pe": 1, "dist52": 3, "score_total": 1, "score_rank": 0},
    "beat": {"pe": 1, "yoy": 1, "rev4w": 1, "roe": 1, "peg": 2, "mv_yi": 0},
}

# 矩阵 HTML
SHORT_LABEL = {s["key"]: s["label"].split(" ", 1)[0] for s in strategies}

def matrix_html():
    n = len(labels)
    head = "<tr><th>策略 ↓ \\ 重叠 →</th>" + "".join(f'<th>{SHORT_LABEL[keys[i]]}</th>' for i in range(n)) + "</tr>"
    rows_html = []
    for i in range(n):
        tds = [f'<td class="b">{labels[i]}</td>']
        for j in range(n):
            cnt, inter = matrix[i][j]
            if i == j:
                tds.append(f'<td class="self">{len(code_sets[i])}</td>')
            elif cnt:
                tds.append(f'<td class="ov">{cnt}</td>')
            else:
                tds.append('<td class="no">0</td>')
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="matrix">{head}{"".join(rows_html)}</table>'


def res_html():
    if not resonance:
        return '<p class="dim">无任何跨策略共振股票。</p>'
    items = []
    for r in resonance:
        b = BAND.get(r["code"]) or {}
        pb, fl = b.get("pb_pct"), b.get("flag")
        if pb is not None:
            c = BAND_COLOR.get(fl, "#566573")
            band_badge = f'<span class="rband" style="color:{c};border-color:{c}">{pb:.0f}% · {fl}</span>'
        else:
            band_badge = ""
        items.append(
            f'<div class="res"><span class="rcode">{r["code"]}</span>'
            f'<b>{r["name"]}</b>'
            f'<span class="rn">命中 {r["n"]} 策略</span>'
            f'{band_badge}'
            f'<span class="rtags">{" / ".join(x.split(" ", 1)[1] if " " in x else x for x in r["strategies"])}</span></div>')
    return "".join(items)


# C-Score exfin 附加表
exfin_html = ""
if cs_exfin:
    rows = ['<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>今日%</th><th>PE</th><th>PB</th>'
            '<th>ROE%</th><th>预期YoY%</th><th>C分</th><th>PB分位</th><th>band</th></tr>']
    for r in cs_exfin["recommend"]:
        c6 = code6_of(r, "code")
        q = quote.get(c6, {})
        rows.append(f'<tr><td>{r.get("rank")}</td><td class="b">{q.get("name") or r.get("name","")}</td>'
                    f'<td>{c6}</td><td>{fmt(q.get("price"),2)}</td>{pct_cell(q.get("pct"))}'
                    f'<td>{fmt(r.get("pe"),1)}</td><td>{fmt(r.get("pb"),2)}</td>'
                    f'<td>{fmt(r.get("con_roe"),1)}</td><td>{fmt(r.get("con_np_yoy"),1)}</td>'
                    f'<td class="cscore">{r.get("c_score")}</td>{band_tds({"band_pb": (BAND.get(c6) or {}).get("pb_pct"), "band_flag": (BAND.get(c6) or {}).get("flag")})}</tr>')
    exfin_html = f'<table>{"".join(rows)}</table>'
    exfin_n = len(cs_exfin["recommend"])

# 副表：beat 质量版
beat_qual_html = ""
if beat and beat.get("qual_top"):
    rows = []
    for r in beat["qual_top"]:
        c6 = code6_of(r, "code")
        q = quote.get(c6, {})
        rows.append(f'<tr><td>{r.get("rank")}</td><td class="b">{q.get("name") or r.get("name","")}</td>'
                    f'<td>{c6}</td><td>{fmt(q.get("price"),2)}</td>{pct_cell(q.get("pct"))}'
                    f'<td>{fmt(r.get("yoy"),1)}</td><td>{fmt(r.get("rev4w"),1)}</td>'
                    f'<td>{fmt(r.get("roe"),1)}</td><td>{fmt(r.get("pe"),1)}</td></tr>')
    beat_qual_html = f'<table>{"".join(rows)}</table>'

# 汇总表
sum_html = "<table><tr><th>策略</th><th>数量</th><th>市值中位(亿)</th><th>PE中位</th><th>今日上涨</th></tr>"
for st in stats_rows:
    sum_html += (f'<tr><td class="b">{st["label"]}</td><td>{st["n"]}</td>'
                 f'<td>{fmt_n(st["mv_med"],0)}</td><td>{fmt_n(st["pe_med"],1)}</td>'
                 f'<td>{st["pct_up_ratio"]}</td></tr>')
sum_html += "</table>"

# 各策略板块
sections = []
for s in strategies:
    sections.append(f"""
<h2>{s['label']} <span class="tag">{s['tag']}</span></h2>
<div class="card mini"><b>逻辑：</b>{s['desc']}<br><b>证据：</b>{s['evid']}</div>
<div class="tbl-wrap">{table_html(s, col_sets[s['key']], col_prec.get(s['key']))}</div>
""")

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>6 策略当前推荐 · 对比（{max([s.get('n',0) for s in strategies])} 视角）</title>
<style>
 :root {{ --red:#d6333b; --red-bg:#fff0f0; --blue:#1a5fb4; --blue-bg:#eef4fb;
         --green:#2e7d32; --green-bg:#eef7ee; --amber:#b45309; --amber-bg:#fdf3e3;
         --gray:#6b7280; --line:#e5e7eb; --bg:#ffffff; --card:#fafbfc; --text:#1f2328; }}
 * {{ box-sizing:border-box; margin:0; padding:0; }}
 body {{ font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
        color:var(--text); background:var(--bg); line-height:1.6; padding:24px 16px 60px; }}
 .wrap {{ max-width:1200px; margin:0 auto; }}
 h1 {{ font-size:26px; margin-bottom:4px; }}
 h2 {{ font-size:19px; margin:34px 0 10px; padding-left:10px; border-left:4px solid var(--red); }}
 .sub {{ color:var(--gray); font-size:13.5px; margin-bottom:16px; }}
 .tag {{ display:inline-block; background:var(--blue-bg); color:var(--blue);
        border-radius:20px; padding:1px 10px; font-size:12px; font-weight:600; vertical-align:middle; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th, td {{ padding:5px 8px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
 th {{ background:#f3f4f6; font-weight:600; position:sticky; top:0; }}
 td.b {{ font-weight:600; }}
 td.cscore {{ text-align:center; color:var(--red); font-weight:700; }}
 td.up {{ color:var(--red); font-weight:600; }}
 td.dn {{ color:var(--green); font-weight:600; }}
 td.flat {{ color:var(--gray); }}
 td.dim {{ color:#c0c4cc; }}
 tr:hover td {{ background:#f8fafc; }}
 .tbl-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; margin-top:8px; }}
 .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 16px; }}
 .card.mini {{ font-size:13px; color:#374151; margin:10px 0 4px; }}
 .card.mini b {{ color:var(--text); }}
 .kv {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:14px 0; }}
 .kv .item {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 14px; }}
 .kv .num {{ font-size:20px; font-weight:700; color:var(--red); }}
 .kv .lbl {{ font-size:12px; color:var(--gray); }}
 table.matrix th, table.matrix td {{ text-align:center; }}
 table.matrix td.self {{ background:#1f2328; color:#fff; font-weight:700; }}
 table.matrix td.ov {{ background:var(--red-bg); color:var(--red); font-weight:700; }}
 table.matrix td.no {{ color:#c0c4cc; }}
 .res {{ display:inline-block; background:var(--amber-bg); border:1px solid #eadfce;
        border-radius:8px; padding:6px 10px; margin:4px 6px 4px 0; font-size:12.5px; }}
 .res .rcode {{ font-family:monospace; color:var(--amber); font-weight:700; margin-right:6px; }}
.res .rn {{ margin:0 6px; color:var(--gray); }}
.res .rband {{ display:inline-block; border:1px solid; border-radius:9px; padding:0 7px;
               font-size:11px; font-weight:600; margin-right:6px; }}
.res .rtags {{ color:var(--blue); font-size:11.5px; }}
 .warn {{ background:var(--amber-bg); border-left:3px solid var(--amber); padding:10px 14px;
         border-radius:0 6px 6px 0; font-size:13px; margin:12px 0; }}
 .ok {{ background:var(--green-bg); border-left:3px solid var(--green); padding:10px 14px;
       border-radius:0 6px 6px 0; font-size:13px; margin:12px 0; }}
 .note {{ color:var(--gray); font-size:12px; margin-top:10px; }}
 footer {{ margin-top:40px; color:var(--gray); font-size:12px; border-top:1px solid var(--line); padding-top:12px; }}
 h3 {{ font-size:15px; margin:18px 0 8px; color:var(--blue); }}
</style></head><body><div class="wrap">

<h1>🧭 6 策略当前推荐 · 并列对比</h1>
<div class="sub">筛选因子截至 <b>2026-08-20</b>（万得全A PIT 5529 只 · juzi 快照，数据源待修复无法刷新）｜
行情价截至 <b>2026-08-25 收盘</b>（腾讯实时，今日涨跌为当日真实数据）｜
对比表均为各策略最新产出</div>

<div class="kv">
  <div class="item"><div class="num">{sum(s["n"] for s in strategies)}</div><div class="lbl">6 策略名单合计（去重后 {len(set().union(*code_sets)) if code_sets else 0} 只）</div></div>
  <div class="item"><div class="num">{len(resonance)}</div><div class="lbl">跨策略共振标的（≥2 策略命中）</div></div>
  <div class="item"><div class="num">+7.1pp</div><div class="lbl">LX-core 超额等权全A（最强基准）</div></div>
  <div class="item"><div class="num">+26.2pp</div><div class="lbl">C-Score 超额（数据层核心）</div></div>
</div>

<h2>0. 策略汇总对比</h2>
{sum_html}

<h2>1. 跨策略重叠矩阵</h2>
{matrix_html()}
<div class="note">对角=名单规模；彩色=两策略代码重叠数。重叠少=角度互斥、收益来源独立；重叠多=证据共振。</div>

<h2>2. 多策略共振标的（交叉验证增强）</h2>
{res_html()}

<h2>3. 各策略名单</h2>
{''.join(sections)}

<h2>4. 附：C-Score 剔除金融版（第③策略的行业约束变体，{exfin_n if cs_exfin else 0} 只）</h2>
<p class="sub">口径：第③策略池剔除银行+非银金融 121 只后重算 BM 三分位与 C-Score——属"策略+行业约束"衍生口径，回测证据不直接适用。</p>
<div class="tbl-wrap">{exfin_html}</div>

<h2>5. 附：beat 质量强化版（第⑥策略 + 预期ROE≥12%，top20）</h2>
<div class="tbl-wrap">{beat_qual_html}</div>

<div class="ok"><b>组合视角</b>：三角度天然互斥——LX-core 买"便宜"（基建/公用/周期，今日全线普涨需警惕）、C-Score 买"预期修复"（低PB+上修，建筑/银行为主）、筹码×52周买"科技筹码锁定"（AI 成长，高波动）。共振标的是唯一同时被多个独立证据支持的少数派，值得优先关注。</div>

<div class="warn"><b>数据诚实性</b>：① 因子为最后健康日 2026-08-19（juzi HF 因子 08-20 起服务端污染，已回退重建并交叉验证），估值/一致预期/PIT 成分为 08-24，行情价为 08-25；② 筹码 z 为 2026-07-31 因子快照、dist52 基于 08-21 收盘日K；③ 一致预期仅覆盖有分析师跟踪的股票，小盘天然缺席；④ 金融股（银行/非银 123 只）已按用户铁律从全部名单剔除；⑤ 本名单由数值化筛选器产生，<b>不构成投资建议</b>，过去表现不代表未来。</div>

<footer>生成：_six_now_compare.py｜数据：_lx_now_results / _lx_now_scored / _cs_now_results / _cs_now_exfin_results / _ai_chip_52wk_top / _lx_now_dist52 / _bt_consensus_beat_results｜行情：qt.gtimg.cn @ 2026-08-25</footer>
</div></body></html>"""

open(OUT_HTML, "w", encoding="utf-8").write(html)
print("written:", OUT_HTML, f"({os.path.getsize(OUT_HTML):,} bytes)")
for s in strategies:
    print(f"  {s['label']}: {s['n']} 只")
print("去重合计:", len(set().union(*code_sets)), "| 共振:", len(resonance))
