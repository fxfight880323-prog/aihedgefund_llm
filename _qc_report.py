# -*- coding: utf-8 -*-
"""
高质量公司低估值买入 — 自包含 HTML 报告生成器
读取 _qc_results.json / _qc_quote.json / SQLite(consensus) → _bt_quality_cheap_entry.html
"""
import json, sqlite3
from datetime import datetime

R = json.load(open("_qc_results.json", encoding="utf-8"))
Q = json.load(open("_qc_quote.json", encoding="utf-8"))
con = sqlite3.connect("data/a_share_market.db")
cur = con.cursor()

def cval(code, field, month):
    """读取 consensus 正确字段"""
    cur.execute(f"select {field} from consensus where ticker=? and month=?",(code,month))
    r = cur.fetchone()
    return r[0] if r else None

def cline(code, months):
    out=[]
    for m in months:
        cur.execute("select con_pe, con_peg, con_roe, con_np_yoy from consensus where ticker=? and month=?",(code,m))
        r=cur.fetchone()
        out.append({"month":m, "con_pe":r[0] if r else None, "con_peg":r[1] if r else None,
                    "con_roe":r[2] if r else None, "con_np_yoy":r[3] if r else None})
    return out

# PIT 月份
PIT = [p[0] for p in R["pit_dates"]]
MONTHS = PIT  # 10 期

CODES = [("603259.SH","603259","药明康德","生物制药/CRO"),
         ("000333.SZ","000333","美的集团","家电/白电"),
         ("300750.SZ","300750","宁德时代","动力电池/新能源")]

# 中国股市配色: 涨红跌绿
RED="#c0392b"; RED_L="#e74c3c"; GREEN="#1e8449"; GREEN_L="#27ae60"
GREY="#7f8c8d"; PURPLE="#8e44ad"; BLUE="#2980b9"; ORANGE="#d35400"
BG="#faf9f7"; CARD="#ffffff"; BORDER="#e0ddd6"; TXT="#2c2c2c"; MUT="#6b6b6b"

def pct(x, d=1):
    if x is None: return "—"
    s=f"{x*100:+.{d}f}%"
    return s
def num(x, d=2):
    if x is None: return "—"
    return f"{x:.{d}f}"

# ---------- bar chart (horizontal) ----------
def zone_bars(zones, key="mean", label_suffix=""):
    vals = [abs(zones.get(k,{}).get(key,0) or 0) for k in ["0-20","20-40","40-60","60-80","80-100"]]
    mx = max(vals) if max(vals)>0 else 1
    rows=""
    for zname in ["0-20","20-40","40-60","60-80","80-100"]:
        z = zones.get(zname,{})
        v = z.get(key)
        n = z.get("n","—")
        win = z.get("win")
        med = z.get("med")
        bar_w = abs(v or 0)/mx*100
        col = RED if (v or 0)>0 else GREEN
        wtxt = f"胜率 {win*100:.0f}%" if win is not None else "—"
        mtxt = f"中位 {pct(med)}" if med is not None else ""
        rows+=f"""<tr>
        <td class="zlabel">{zname}</td>
        <td class="zbar"><div class="bar" style="width:{bar_w:.0f}%;background:{col}"></div></td>
        <td class="zval">{pct(v) if v is not None else '—'}</td>
        <td class="zn">n={n}</td>
        <td class="zsub">{wtxt}　{mtxt}</td></tr>"""
    return rows

# ---------- NAV line chart (SVG) ----------
def nav_chart(navs, rows):
    # x 轴: 起点 + 10 个 exit 日期
    labels = ["2021-09<br>起点"]
    for r in rows:
        e=r["exit"]
        labels.append(f"{e[2:7]}<br>{'末' if not r['partial'] else '今'}")
    series = {
        "low40":("质量池×PB<40%（低估入场）", RED, navs["low40"]["series"]),
        "high60":("质量池×PB>60%（高估入场）", GREEN, navs["high60"]["series"]),
        "pool_ew":("质量池等权", GREY, navs["pool_ew"]["series"]),
        "core":("LX-core 40只（PE升序排序）", PURPLE, navs["core"]["series"]),
        "idx":("中证全指 000985.SH", BLUE, navs["idx"]["series"]),
    }
    W,H=860,300; L=58; R_=20; T=20; B=44
    pw=W-L-R_; ph=H-T-B
    allv=[1.0]
    for s in series.values():
        allv+=s[2]
    ymin,ymax=min(allv)-0.05,max(allv)+0.05
    n=len(labels)
    def X(i): return L + (i/(n-1))*pw
    def Y(v): return T + (1-(v-ymin)/(ymax-ymin))*ph
    # grid
    grid=""
    steps=4
    for i in range(steps+1):
        v=ymin+(ymax-ymin)*i/steps
        y=Y(v)
        grid+=f'<line x1="{L}" y1="{y:.0f}" x2="{W-R_}" y2="{y:.0f}" stroke="#eee" stroke-width="1"/>'
        grid+=f'<text x="{L-6}" y="{y+4:.0f}" text-anchor="end" font-size="9" fill="{MUT}">{v:.2f}</text>'
    # x labels
    xlab=""
    for i,lb in enumerate(labels):
        x=X(i)
        xlab+=f'<text x="{x:.0f}" y="{H-26}" text-anchor="middle" font-size="8.5" fill="{MUT}">{lb}</text>'
    # axis baseline y=1
    y1=Y(1.0)
    grid+=f'<line x1="{L}" y1="{y1:.0f}" x2="{W-R_}" y2="{y1:.0f}" stroke="#bbb" stroke-width="1.2" stroke-dasharray="3,3"/>'
    # lines
    paths=""
    for key,(name,color,ser) in series.items():
        pts=[(X(0),Y(1.0))]+[(X(i+1),Y(v)) for i,v in enumerate(ser)]
        d=" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)
        w=2.6 if key in("low40","core") else 1.8
        paths+=f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{w}"/>'
        # 末点标注
        paths+=f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3" fill="{color}"/>'
    # legend
    leg=""
    lx=W-R_-130
    for i,(key,(name,color,_)) in enumerate(series.items()):
        ly=10+i*16
        leg+=f'<rect x="{lx}" y="{ly}" width="12" height="3" fill="{color}"/><text x="{lx+16}" y="{ly+4}" font-size="8.5" fill="{TXT}">{name}</text>'
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:860px"><rect width="{W}" height="{H}" fill="{CARD}"/>{grid}{paths}{xlab}{leg}</svg>'

# ---------- funnel ----------
def funnel():
    steps=[
        ("L6 基座", "万得全A PIT 成分（881001.WI）", "~5500 只", GREY, "剔除：ST/退市/停牌；市值<100亿；PE≤0"),
        ("L4 估值安全边际", "PE_TTM ≤ 25  或  股息率 ≥ 2%", "≈600 只", BLUE, "排除估值过贵的成长股"),
        ("L5 低预期逆向", "一致预期增速 ≤ 25%  且  0 < PEG ≤ 2", "≈200-350 只", ORANGE, "排除'共识过热'的高预期股票"),
        ("Band 低估入场层", "PB 5年分位 < 40% （建议<30%）", "≈120-200 只", RED, "在质量池内择低估时点"),
        ("持仓信念", "PE 升序取 Top40 等权（单票≤5%）", "40 只", PURPLE, "半年调仓；刘旭式排序信念"),
    ]
    w0=560; h_step=46; gap=6
    x0=70
    out=""
    for i,(t,d,n,c,note) in enumerate(steps):
        w=w0-i*30
        x=x0+(w0-w)//2
        y=20+i*(h_step+gap)
        out+=f'<rect x="{x}" y="{y}" width="{w}" height="{h_step}" rx="6" fill="{c}" opacity="0.92"/>'
        out+=f'<text x="{x+12}" y="{y+18}" font-size="12.5" font-weight="700" fill="#fff">{t}</text>'
        out+=f'<text x="{x+12}" y="{y+34}" font-size="9.5" fill="#fff" opacity="0.92">{d}</text>'
        out+=f'<text x="{x+w-10}" y="{y+18}" text-anchor="end" font-size="11" font-weight="700" fill="#fff">{n}</text>'
        out+=f'<text x="{x+w-10}" y="{y+34}" text-anchor="end" font-size="8.5" fill="#fff" opacity="0.85">{note}</text>'
    return f'<svg viewBox="0 0 700 290" style="width:100%;max-width:700px">{out}</svg>'

# ---------- 当前状态卡 ----------
def cur_card(code6, code_full, name, sector):
    pa=R["part_a"][code_full]
    cur=pa["current"]
    q=Q[code6]
    # 最近 PIT(2026-04) 在池?
    cip=R["part_b"]["case_in_pool"][code_full]
    last=cip[-1]
    in_pool="✅ 通过质量筛选" if last.get("in_pool") else "❌ 未通过质量筛选（L4/L5 否决）"
    # 当前估值判断
    pb5=cur["pb_pct_5y"]; pe5=cur["pe_pct_5y"]
    if pb5 is not None and pb5<40:
        est=f'<span style="color:{RED};font-weight:700">低估（PB 5y {pb5:.0f}%）</span>'
    elif pb5 is not None and pb5<60:
        est=f'<span style="color:{ORANGE};font-weight:700">中性（PB 5y {pb5:.0f}%）</span>'
    else:
        est=f'<span style="color:{GREEN};font-weight:700">高估（PB 5y {pb5:.0f}%）</span>'
    # 一致预期
    m2026="2026-08" if "2026-08" in PIT else PIT[-1]
    cg=cval(code_full,"con_np_yoy",m2026)
    cpeg=cval(code_full,"con_peg",m2026)
    cpe=cval(code_full,"con_pe",m2026)
    crowe=cval(code_full,"con_roe",m2026)
    return f"""
<div class="card curcard">
  <div class="cardhd"><span class="bigname">{name}</span><span class="code">{code_full}</span><span class="sector">{sector}</span></div>
  <table class="mtable">
    <tr><th>现价</th><td>{num(cur['price'])} 元</td>
        <th>总市值</th><td>{num(q['total_mv_yi'],0)} 亿</td></tr>
    <tr><th>PE_TTM</th><td>{num(cur['pe'])}</td>
        <th>PB</th><td>{num(cur['pb'])}</td></tr>
    <tr><th>PB 5年分位</th><td style="font-weight:700">{pb5:.1f}%</td>
        <th>PE 5年分位</th><td>{pe5:.1f}%</td></tr>
    <tr><th>距52周低</th><td>{cur['dist52_pct']:.1f}%</td>
        <th>PB 全历史分位</th><td>{cur['pb_pct_hist']:.1f}%</td></tr>
    <tr><th>一致预期增速</th><td>{num(cg) if cg is not None else '—'}%</td>
        <th>一致预期 PEG</th><td>{num(cpeg) if cpeg is not None else '—'}</td></tr>
    <tr><th>一致预期 ROE</th><td>{num(crowe) if crowe is not None else '—'}%</td>
        <th>一致预期 PE</th><td>{num(cpe) if cpe is not None else '—'}</td></tr>
  </table>
  <div class="verdict">
    <div><b>最近筛选（2026-04期）：</b>{in_pool}</div>
    <div><b>当前估值状态：</b>{est}</div>
  </div>
</div>"""

# ---------- 在池时间线 ----------
def pool_timeline(code_full):
    rows=R["part_b"]["case_in_pool"][code_full]
    h=""
    for r in rows:
        if r.get("in_pool"):
            cls="in"; ico="✅"
            pb=r.get("pb_pct"); pe=r.get("pe_pct"); fwd=r.get("fwd126")
            h+=f'<tr class="in"><td>{ico}</td><td>{r["month"]}</td><td>{num(r.get("pe"))}</td><td>{num(r.get("pb"))}</td><td>{pb:.1f}%</td><td>{pe:.1f}%</td><td style="color:{RED if (fwd or 0)>0 else GREEN};font-weight:700">{pct(fwd)}</td></tr>'
        else:
            h+=f'<tr class="out"><td>❌</td><td>{r["month"]}</td><td colspan="5" class="muted">未通过 L4/L5 质量筛选</td></tr>'
    return h

# ---------- episode 表 ----------
def episode_table(code_full):
    eps=R["part_a"][code_full]["episodes"]
    h=""
    for e in eps:
        f6=e.get("fwd6m"); f12=e.get("fwd12m")
        c6 = RED if (f6 or 0)>0 else (GREEN if f6 is not None else GREY)
        c12 = RED if (f12 or 0)>0 else (GREEN if f12 is not None else GREY)
        d=e["days"]
        # 长陷阱标记
        tag=""
        if d>=180 and (f6 is None or f6<0) and (f12 is None or f12<0):
            tag=' <span class="trap">⚠ 价值陷阱</span>'
        elif d>=365:
            tag=' <span class="long">长低估期</span>'
        h+=f'<tr><td>{e["start"]}</td><td>{e["end"]}</td><td>{d}{tag}</td><td>{num(e["pb_start"])}</td><td>{num(e["pb_min"])}</td><td>{e["pb_pct_min"]:.1f}%</td><td style="color:{c6};font-weight:600">{f6 if f6 is None else f"{f6:+.1f}%"}</td><td style="color:{c12};font-weight:600">{f12 if f12 is None else f"{f12:+.1f}%"}</td></tr>'
    return h

# ---------- 质量轨迹 ----------
def quality_trend_table(code_full):
    cl=cline(code_full, MONTHS[-4:])
    h=""
    for c in cl:
        cg=c["con_np_yoy"]; cpeg=c["con_peg"]; croe=c["con_roe"]; cpe=c["con_pe"]
        # L5 判断
        l5=""
        if cg is not None and cpeg is not None:
            if cg<=0 or cpeg<=0:
                l5=f'<span style="color:{GREEN}">否决(增速≤0/PEG≤0)</span>'
            elif cg>25:
                l5=f'<span style="color:{GREEN}">否决(增速{cg:.1f}%>25%)</span>'
            elif cpeg>2:
                l5=f'<span style="color:{GREEN}">否决(PEG {cpeg:.2f}>2)</span>'
            else:
                l5=f'<span style="color:{RED}">通过</span>'
        h+=f'<tr><td>{c["month"]}</td><td>{num(cg) if cg is not None else "—"}%</td><td>{num(cpeg) if cpeg is not None else "—"}</td><td>{num(croe) if croe is not None else "—"}%</td><td>{num(cpe) if cpe is not None else "—"}</td><td>{l5}</td></tr>'
    return h

# ---------- 个股 PB 分区 ----------
def stock_zone_table(code_full):
    zs=R["part_a"][code_full]["zone_stats"]
    h=""
    for zname in ["0-20","20-40","40-60","60-80","80-100"]:
        z=zs.get(zname,{})
        m6=z.get("mean6"); w6=z.get("win6"); m12=z.get("mean12"); w12=z.get("win12")
        n6=z.get("n6",0); n12=z.get("n12",0)
        c6=RED if (m6 or 0)>0 else GREEN
        c12=RED if (m12 or 0)>0 else GREEN
        h+=f'<tr><td>{zname}</td><td>{n6}</td><td style="color:{c6};font-weight:600">{m6*100 if m6 else 0:+.1f}%</td><td>{w6*100:.0f}%</td><td>{n12}</td><td style="color:{c12};font-weight:600">{m12*100 if m12 else 0:+.1f}%</td><td>{w12*100:.0f}%</td></tr>'
    return h

# ---------- 逐期 NAV 表 ----------
def nav_period_table():
    rows=R["part_b"]["nav_rows"]
    h=""
    for r in rows:
        h+=f'<tr><td>{r["entry"][:7]}</td><td>{r["exit"][:7]}</td>'
        for k in ["low40","high60","pool_ew","core"]:
            v=r[k]["ret"]; n=r[k]["n"]
            c=RED if (v or 0)>0 else GREEN
            tag=" ⚠部分期" if r["partial"] else ""
            h+=f'<td style="color:{c}">{pct(v)}<span class="muted"> ({n})</span></td>'
        v=r["idx"]; c=RED if (v or 0)>0 else GREEN
        h+=f'<td style="color:{c}">{pct(v)}</td></tr>'
    return h

# ---------- core band 分布 ----------
def core_dist_table():
    rows=R["part_b"]["core_rows"]
    h=""
    for r in rows:
        dist=r.get("dist",{})
        cells=""
        for z in ["0-20","20-40","40-60","60-80","80-100"]:
            v=dist.get(z,0)
            cells+=f'<td class="distcell">{v if v else "—"}</td>'
        cf=r["fwd"]; pa_=r["pool_avg"]
        cc=RED if (cf or 0)>0 else GREEN
        cp=RED if (pa_ or 0)>0 else GREEN
        h+=f'<tr><td>{r["month"]}</td>{cells}<td style="color:{cc};font-weight:600">{pct(cf)}</td><td style="color:{cp}">{pct(pa_)}</td></tr>'
    return h

# ---------- 组装 HTML ----------
s=R["part_b"]["summary"]
navs=R["part_b"]["navs"]
low40_f=navs["low40"]["final"]; high60_f=navs["high60"]["final"]
pool_f=navs["pool_ew"]["final"]; core_f=navs["core"]["final"]; idx_f=navs["idx"]["final"]

z0=s["pb_zones"]["0-20"]; z4=s["pb_zones"]["80-100"]
zn0=s["pb_zones_nonfin"]["0-20"]
pe0=s["pe_zones"]["0-20"]; pe4=s["pe_zones"]["80-100"]
dl=s["dual_low"]; dr=s["dual_rest"]
pool_all=s["pool_all"]; idx_all=s["idx_all"]; core_all=s["core_all"]

now_str=datetime.now().strftime("%Y-%m-%d %H:%M")

html=f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>高质量×低估值买入框架 — 实证研究</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:{BG};color:{TXT};line-height:1.6;padding:18px;max-width:980px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;margin-bottom:4px}}
h2{{font-size:17px;font-weight:700;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid {BORDER};color:{PURPLE}}}
h3{{font-size:14.5px;font-weight:700;margin:18px 0 8px;color:{TXT}}}
.sub{{font-size:12px;color:{MUT};margin-bottom:14px}}
.banner{{background:linear-gradient(135deg,#8e44ad,#6c3483);color:#fff;padding:18px 22px;border-radius:10px;margin:12px 0;box-shadow:0 2px 8px rgba(142,68,173,.25)}}
.banner .b1{{font-size:15.5px;font-weight:700;line-height:1.5}}
.banner .b2{{font-size:12.5px;opacity:.92;margin-top:6px}}
.grid4{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}}
.card{{background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.card .ct{{font-size:12.5px;color:{MUT};margin-bottom:6px;font-weight:600}}
.card .cv{{font-size:22px;font-weight:800}}
.card .cd{{font-size:11.5px;color:{MUT};margin-top:4px}}
.card .cv.r{{color:{RED}}} .card .cv.g{{color:{GREEN}}} .card .cv.p{{color:{PURPLE}}} .card .cv.b{{color:{BLUE}}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}}
th,td{{padding:5px 8px;text-align:left;border-bottom:1px solid {BORDER}}}
th{{background:#f4f1ec;font-weight:700;font-size:11.5px;color:{MUT}}}
tr.in td{{background:#fef9f6}} tr.out td{{color:{MUT}}}
.muted{{color:{MUT};font-size:11px}}
.trap{{color:#fff;background:{GREEN};padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700}}
.long{{color:#fff;background:{ORANGE};padding:1px 5px;border-radius:3px;font-size:10px}}
.ztable{{}} .zlabel{{font-weight:700;width:60px}} .zbar{{width:38%}}
.bar{{height:14px;border-radius:3px;min-width:2px}} .zval{{width:13%;font-weight:700}}
.zn{{width:10%;color:{MUT};font-size:11px}} .zsub{{font-size:11px;color:{MUT}}}
.mtable th{{width:22%}} .mtable td{{font-weight:600}}
.curcard{{margin:10px 0}}
.cardhd{{display:flex;align-items:baseline;gap:10px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid {BORDER}}}
.bigname{{font-size:16px;font-weight:800}} .code{{font-size:12px;color:{MUT}}} .sector{{font-size:11px;color:{MUT};margin-left:auto}}
.verdict{{margin-top:8px;padding:8px;background:#f8f6f2;border-radius:5px;font-size:12px}}
.verdict div{{margin:3px 0}}
.check{{background:{CARD};border-left:4px solid {RED};padding:12px 16px;margin:8px 0;border-radius:0 6px 6px 0;font-size:13px}}
.check .h{{font-weight:800;color:{RED};margin-bottom:2px}}
.check .d{{color:{MUT};font-size:11.5px}}
.pitbox{{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}}
.pit{{background:#f0ede8;padding:3px 8px;border-radius:10px;font-size:11px}}
.warn{{background:#fdf2f0;border:1px solid #f5c6cb;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:12px}}
.warn b{{color:{RED}}}
.note{{background:#eef6fb;border:1px solid #bcdff1;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:12px}}
.note b{{color:{BLUE}}}
footer{{margin-top:30px;padding-top:14px;border-top:1px solid {BORDER};font-size:11px;color:{MUT};line-height:1.8}}
.tag{{display:inline-block;background:#f0ede8;padding:1px 7px;border-radius:3px;font-size:10.5px;margin:0 3px}}
.red{{color:{RED}}} .green{{color:{GREEN}}}
</style>
</head>
<body>

<h1>高质量公司×低估值时点买入 — 实证框架</h1>
<div class="sub">
  数据口径：万得全A(881001.WI) PIT 成分池 · 日频复权价 · 10 个半年调仓期（2021-08~2026-04）· 前瞻 126 个交易日（6M）与 252 日（12M）·
  估值分位 = PB/PE 相对自身 5 年日频历史的前置分位（不偷看未来）· 报告生成：{now_str}
</div>

<div class="banner">
  <div class="b1">结论先行：在"高质量公司"池子里"等低估时点"再买，是有效的——质量池×PB 5年分位&lt;40% 等权，5 年累计 <span style="color:#fff;font-weight:900">+45.9%</span>，
  跑赢同池等权 +34.0%（增量 <b>+11.9pp</b>）与高估入场 −13.8%（价差 <b>59.7pp</b>）；PB 分位 0-20 区前瞻 6M 均值 <b>+10.3%/胜率 62.6%</b>，
  80-100 区仅 <b>+0.83%/胜率 43.3%</b>，近乎单调。<b>PB 优于 PE</b>（PE 分区区分度平坦 8.6%→4.9%），与"PE 被盈利下滑污染"一致。</div>
  <div class="b2">但"低估不是催化剂"——2022 年美的 PB 分位 9.3% 入场仍 -22.2%；药明 2022-07~2025-08 低估陷阱长达 760 天。
  LX-core（PE 升序排序 Top40）+52.7% 仍为最强基准（排序信念 > 估值择时）。<b>买点 = 质量未破坏 + PB 低分位 + 12 个月耐心</b>。</div>
</div>

<h2>一、核心发现</h2>
<div class="grid4">
  <div class="card"><div class="ct">PB 分位单调性（全池）</div><div class="cv r">{z0['mean']*100:.1f}%</div>
    <div class="cd">0-20 区前瞻 6M 均值（n={z0['n']}，胜率 {z0['win']*100:.0f}%） vs 80-100 区 {z4['mean']*100:.1f}%（{z4['win']*100:.0f}%）</div></div>
  <div class="card"><div class="ct">净值模拟价差</div><div class="cv r">+59.7pp</div>
    <div class="cd">低估入场 {low40_f*100:.1f}% − 高估入场 {high60_f*100:.1f}%（同质量池）</div></div>
  <div class="card"><div class="ct">非金融子集更强</div><div class="cv p">{zn0['mean']*100:.1f}%</div>
    <div class="cd">非金融 0-20 区 6M 均值（n={zn0['n']}，胜率 {zn0['win']*100:.0f}%），金融子集该区仅 {s['pb_zones_fin']['0-20']['mean']*100:.1f}%</div></div>
  <div class="card"><div class="ct">LX-core 排序最强</div><div class="cv b">+52.7%</div>
    <div class="cd">PE 升序 Top40 半年调仓（期边界无成本口径）；官方含成本口径 +55.55%/年化 9.16%</div></div>
</div>

<h2>二、框架：高质量×低估值买入的完整流程</h2>
<p class="sub">这套流程 = <b>LX-core 质量筛选</b>（刘旭式，排除层→估值安全边际→低预期逆向→排序信念）× <b>Band 估值择时层</b>（PB 5年分位）。质量筛选确定"买什么"，band 层确定"何时买"。</p>
{funnel()}
<table>
  <tr><th>层级</th><th>规则</th><th>参数</th><th>作用</th></tr>
  <tr><td><b>L6 排除层</b></td><td>市值≥100亿 + PE_TTM>0；剔除 ST/退市/停牌</td><td>mv_floor=100亿</td><td>排除微盘股与亏损股的噪音</td></tr>
  <tr><td><b>L4 估值安全边际</b></td><td>PE_TTM ≤ 25  <b>或</b>  股息率 ≥ 2%</td><td>PE_CEIL=25, DIV_YIELD=2%</td><td>排除估值过贵的成长股（"好公司不等于好价格"）</td></tr>
  <tr><td><b>L5 低预期逆向</b></td><td>一致预期增速 ≤ 25%  且  0 &lt; PEG ≤ 2</td><td>EXP_G_CEIL=25%, PEG_CEIL=2.0</td><td>排除"共识过热"（预期已被 price-in）；负增长（PEG≤0）直接否决</td></tr>
  <tr><td><b>Band 入场层</b></td><td>PB 5年分位 &lt; 40%（建议&lt;30%更安全）</td><td>—</td><td>在质量池内择"相对自身历史便宜"的时点</td></tr>
  <tr><td><b>排序信念</b></td><td>PE 升序取 Top40 等权（单票≤5%）</td><td>MAX_HOLDINGS=40</td><td>刘旭式信念：越便宜权重越高</td></tr>
</table>
<div class="note"><b>为什么用 PB 而不是 PE 做入场分位？</b>　实证：PE 分位 0-20 区前瞻 6M {pe0['mean']*100:.1f}%，80-100 区 {pe4['mean']*100:.1f}%，价差仅 {(pe0['mean']-pe4['mean'])*100:.1f}pp（PB 价差 {(z0['mean']-z4['mean'])*100:.1f}pp）。
原因：盈利下滑时 PE 会被动降低（分母变小），"低 PE 分位"可能是<b>价值陷阱</b>而非低估；PB 对资产更稳定。例如格力 PE 5y 分位 61.7% vs PB 仅 8.7%。</div>

<h2>三、组合层证据（2596 个股-期样本）</h2>

<h3>3.1 PB 5年分位 × 前瞻 126 日收益（全池）</h3>
<table class="ztable">
  <tr><th>分位区</th><th>━━━━━ 前瞻 6M 均值 ━━━━━</th><th>均值</th><th>样本</th><th>胜率/中位</th></tr>
  {zone_bars(s["pb_zones"])}
</table>
<p class="muted">全池 {sum(z['n'] for z in s['pb_zones'].values())} 个股-期样本，9 个完整期（2026-04 期前瞻窗口不完整已剔除）。均值从 0-20 区 {z0['mean']*100:.1f}% 单调下降至 80-100 区 {z4['mean']*100:.1f}%，中位从 +5.19% 降至 −3.43%。</p>

<h3>3.2 非金融子集（更纯净的低估信号）</h3>
<table class="ztable">
  <tr><th>分位区</th><th>━━━━━ 前瞻 6M 均值 ━━━━━</th><th>均值</th><th>样本</th><th>胜率/中位</th></tr>
  {zone_bars(s["pb_zones_nonfin"])}
</table>
<div class="warn"><b>金融子集低分位区反而弱</b>：金融 0-20 区 6M 仅 {s['pb_zones_fin']['0-20']['mean']*100:.1f}%（n={s['pb_zones_fin']['0-20']['n']}），
非金融该区 {zn0['mean']*100:.1f}%。印证"金融剔除"对低估择时是正贡献——金融股 PB 低常是常态而非低估信号。这也是项目内回测验证的"金融剔除用于展示层"铁律的微观证据。</div>

<h3>3.3 双低条件（PE&PB 分位双 &lt; 30%）</h3>
<table>
  <tr><th>条件</th><th>样本</th><th>前瞻6M 均值</th><th>胜率</th><th>中位</th></tr>
  <tr><td><b>双低</b>（PE&amp;PB 分位均&lt;30%）</td><td>{dl['n']}</td><td style="color:{RED};font-weight:700">{dl['mean']*100:.1f}%</td><td>{dl['win']*100:.0f}%</td><td>{dl['med']*100:.1f}%</td></tr>
  <tr><td>其余</td><td>{dr['n']}</td><td>{dr['mean']*100:.1f}%</td><td>{dr['win']*100:.0f}%</td><td>{dr['med']*100:.1f}%</td></tr>
</table>
<p class="muted">双低 vs 其余：均值 {(dl['mean']-dr['mean'])*100:.1f}pp，胜率 {(dl['win']-dr['win'])*100:.1f}pp。叠加 PE 分位边际有效，但主力贡献仍来自 PB。</p>

<h3>3.4 净值模拟（2021-09 ~ 2026-08，半年调仓期边界持有，无成本）</h3>
{nav_chart(navs, R["part_b"]["nav_rows"])}
<table>
  <tr><th>入场期</th><th>出场期</th><th>低估入场(PB&lt;40%)</th><th>高估入场(PB&gt;60%)</th><th>池等权</th><th>LX-core</th><th>中证全指</th></tr>
  {nav_period_table()}
</table>
<div class="pitbox">
  <span class="tag">低估入场累计 {low40_f*100:.1f}%</span>
  <span class="tag green">高估入场累计 {high60_f*100:.1f}%</span>
  <span class="tag">池等权 {pool_f*100:.1f}%</span>
  <span class="tag" style="color:{PURPLE}">LX-core {core_f*100:.1f}%</span>
  <span class="tag" style="color:{BLUE}">中证全指 {idx_f*100:.1f}%</span>
</div>
<div class="note"><b>口径差异说明</b>：本净值模拟为"期边界 adj_close 等权持有、无交易成本"，与 LX-core 官方回测口径（含成本、日频撮合）+55.55%/年化 9.16%/MDD −19.13% 略有差异，
但两者方向一致、排名一致。<b>低估入场 +45.9% vs 高估入场 −13.8% 的 59.7pp 价差</b>是该口径下低估择时价值的直接度量。</div>

<h3>3.5 LX-core 持仓的 band 分布演化</h3>
<table>
  <tr><th>调仓月</th><th>0-20</th><th>20-40</th><th>40-60</th><th>60-80</th><th>80-100</th><th>core 前瞻6M</th><th>池均值</th></tr>
  {core_dist_table()}
</table>
<p class="muted">早期（2021-08）core 持仓 39/40 集中在 0-20 低分位区；2025-08 仅 8/40 在 0-20 区（低分位拥挤化），
同期 core 前瞻 +4.6% vs 池均值 +16.8%——<b>排序信念超额收敛</b>，因可买到的"便宜"变少。这是 PE 升序策略在低分位稀缺期的天然局限。</p>

<h2>四、案例股深拆</h2>
<p class="sub">三只均为市场公认"高质量公司"。通过它们的在池时间线、低估 episode 与个股 PB 分区，可直接看到框架如何运作。</p>

{''.join(cur_card(c[1],c[0],c[2],c[3]) for c in CODES)}

<h3>4.1 药明康德 603259.SH — 在池时间线</h3>
<table>
  <tr><th>✓</th><th>调仓月</th><th>PE</th><th>PB</th><th>PB分位</th><th>PE分位</th><th>前瞻6M</th></tr>
  {pool_timeline('603259.SH')}
</table>
<p class="muted">10 期中仅 3 期通过质量筛选，<b>3 期全部正收益</b>（+34.6%/+33.1%/+65.8%）。2021-22 泡沫期（PE 60-142）与 2026-04（一致预期增速 −5.8%、PEG 3.66&gt;2）被 L4/L5 正确排除。</p>

<h3>4.2 药明康德 — 低估 episode（PB 分位&lt;20% 连续≥10 日）</h3>
<table>
  <tr><th>起始</th><th>结束</th><th>天数</th><th>PB起</th><th>PB最低</th><th>分位最低</th><th>前瞻6M</th><th>前瞻12M</th></tr>
  {episode_table('603259.SH')}
</table>
<p class="muted">2019-05 短低估期 +88.5%/+105.9%；2022 Q1-Q3 三次低估"诱饵"全部负收益（−8%~-33%）；
<b>2022-07~2025-08 长达 760 天的价值陷阱</b>（6M −10.3%/12M −34.9%）——生物安全法案恐慌+CXO 行业景气下行，PB 跌至 1.98 但持续下跌。这是"低估不是催化剂"最典型的案例。</p>

<h3>4.3 药明康德 — 个股 PB 分区 × 前瞻收益</h3>
<table>
  <tr><th>分位区</th><th>n(6M)</th><th>6M均值</th><th>胜率</th><th>n(12M)</th><th>12M均值</th><th>胜率</th></tr>
  {stock_zone_table('603259.SH')}
</table>
<p class="muted">药明个股层 0-20 区 6M +11.8%/胜率 58%；但 40-60/60-80 区反而更高（+32.7%/+20.7%）——2019-2021 成长期动量残留，低估反而错过主升浪。个股层不如组合层单调，<b>印证低估择时需在组合层面而非单股择时</b>。</p>

<h3>4.4 美的集团 000333.SZ — 在池时间线</h3>
<table>
  <tr><th>✓</th><th>调仓月</th><th>PE</th><th>PB</th><th>PB分位</th><th>PE分位</th><th>前瞻6M</th></tr>
  {pool_timeline('000333.SZ')}
</table>
<p class="muted"><b>10 期全部在池</b>（股息率 2.4-3.5% 持续满足 L4）。但 2022-04 PB 分位 9.3% 入场前瞻 6M <span class="green">−22.2%</span>——
"低估不是催化剂"的微观证据；2022-08 PB 分位 0.5%（极低估）入场仍 −2.2%。正收益集中在 2023-08 之后（+13.4%/+7.9%/+11.0%/+9.7%/+4.9%）。</p>

<h3>4.5 美的集团 — 低估 episode</h3>
<table>
  <tr><th>起始</th><th>结束</th><th>天数</th><th>PB起</th><th>PB最低</th><th>分位最低</th><th>前瞻6M</th><th>前瞻12M</th></tr>
  {episode_table('000333.SZ')}
</table>
<p class="muted">2020-03 新冠底 39 天 +46.6%/+82.6%（经典低估反转）；2022-03~2024-05 长低估陷阱 533 天（6M −22.3%/12M −28.4%）；
2024-05~09 +6.9%/+15.7%；2025-2026 多次短低估期小幅正收益。<b>美的低估后 12M 转正概率高于 6M</b>——耐心是低估策略的必要成本。</p>

<h3>4.6 美的集团 — 个股 PB 分区（最完美的单调）</h3>
<table>
  <tr><th>分位区</th><th>n(6M)</th><th>6M均值</th><th>胜率</th><th>n(12M)</th><th>12M均值</th><th>胜率</th></tr>
  {stock_zone_table('000333.SZ')}
</table>
<p class="muted">0-20 区 6M +12.6%/胜率 <b>78%</b>，12M +25.3%/胜率 <b>98%</b>；80-100 区 6M <span class="green">−11.5%</span>/胜率 26%、12M <span class="green">−23.6%</span>/胜率 12%。
<b>个股层近乎完美单调</b>——美的这类稳定消费白马，PB 分位择时信号最可靠。</p>

<h3>4.7 宁德时代 300750.SZ — 在池时间线</h3>
<table>
  <tr><th>✓</th><th>调仓月</th><th>PE</th><th>PB</th><th>PB分位</th><th>PE分位</th><th>前瞻6M</th></tr>
  {pool_timeline('300750.SZ')}
</table>
<p class="muted">仅 2 期通过质量筛选：<b>2024-04（PB 分位 20.2%）+29.7%、2024-08（7.8%）+42.8%</b>，均在 2024 年锂电估值出清后的修复期。
2021-23 PE 24-142 被 L4 排除（泡沫期）；2025+ 一致预期增速 29-33%&gt;25% 被 L5 排除（预期过热）。</p>

<h3>4.8 宁德时代 — 低估 episode</h3>
<table>
  <tr><th>起始</th><th>结束</th><th>天数</th><th>PB起</th><th>PB最低</th><th>分位最低</th><th>前瞻6M</th><th>前瞻12M</th></tr>
  {episode_table('300750.SZ')}
</table>
<p class="muted">2019 三次低估期 6M +105%/+209%/+152%，12M 高达 <b>+490.6%</b>（成长股低估+主升浪戴维斯双击）；
2023-24 episode 6M 多为负（−4.6%~-26%）但 <b>12M 转正</b>（+44.9%~+58.9%）——低估买入需要 12 个月以上耐心；
2025-03~09 +42.5%/+53.6%（最新低估反转）。</p>

<h3>4.9 宁德时代 — 个股 PB 分区（含幸存期效应警告）</h3>
<table>
  <tr><th>分位区</th><th>n(6M)</th><th>6M均值</th><th>胜率</th><th>n(12M)</th><th>12M均值</th><th>胜率</th></tr>
  {stock_zone_table('300750.SZ')}
</table>
<div class="warn"><b>⚠ 幸存期效应标注</b>：宁德 80-100 区 6M 均值 +52.1%/胜率 75%——这<b>不是</b>"高估也能涨"，而是 2021 年泡沫期（PB 8-15 倍）叠加新能源主升浪的动量残留。
该区样本集中在 2021-2022，之后宁德泡沫破裂。高估区的高收益是<b>特定历史窗口的幸存</b>，不可外推。0-20 区 +53.4%/96% 胜率同样主要来自 2019 早期成长，样本结构特殊。</div>

<h3>4.10 三只案例股 — 一致预期质量轨迹（最近 4 期）</h3>
<p class="sub">字段：一致预期净利润增速 / 一致预期PEG / 一致预期ROE / 一致预期PE。L5 判断列展示框架对该期的筛选裁决。</p>
<h3>药明康德</h3>
<table><tr><th>月份</th><th>预期增速</th><th>预期PEG</th><th>预期ROE</th><th>预期PE</th><th>L5 判断</th></tr>{quality_trend_table('603259.SH')}</table>
<h3>美的集团</h3>
<table><tr><th>月份</th><th>预期增速</th><th>预期PEG</th><th>预期ROE</th><th>预期PE</th><th>L5 判断</th></tr>{quality_trend_table('000333.SZ')}</table>
<h3>宁德时代</h3>
<table><tr><th>月份</th><th>预期增速</th><th>预期PEG</th><th>预期ROE</th><th>预期PE</th><th>L5 判断</th></tr>{quality_trend_table('300750.SZ')}</table>

<h2>五、可执行买入规则（Checklist）</h2>
<div class="check"><div class="h">① 质量未破坏（必要条件）</div>
  <div class="d">公司须通过 L6→L4→L5 全流程：市值≥100亿 + (PE≤25 或 股息率≥2%) + (一致预期增速≤25% 且 0&lt;PEG≤2)。<b>负增长直接否决</b>（PEG 无意义）。
  对应案例：药明 2026-04 因预期增速 −5.8%/PEG 3.66 被 L5 否决；宁德 2025+ 因预期增速 33%&gt;25% 被否决——即使 PB 已低，预期过热也排除。</div></div>
<div class="check"><div class="h">② PB 5年分位入场（择时信号）</div>
  <div class="d">在质量池内，仅当 <b>PB 5年分位 &lt; 40%</b>（理想 &lt;30% 双低）时建仓。实证：0-20 区前瞻 6M +10.3%/胜率 63%，80-100 区 +0.83%/43%。
  对应案例：药明 2023-04（分位 0.2%）/2024-04（0.9%）入场均获 +33%~+35%；宁德 2024-08（7.8%）+42.8%。</div></div>
<div class="check"><div class="h">③ 12 个月耐心（持有周期）</div>
  <div class="d">低估买入的胜率随持有期提升：宁德 2024 Q4 episode 6M 多负但 12M +45-59%；美的 0-20 区 6M 胜率 78%→12M <b>98%</b>。
  6M 内低估"诱饵"频繁出现（药明 2022 Q1-Q3 三连负）。<b>建仓后至少持有 12 个月</b>，不要在 6M 负收益时止损。</div></div>
<div class="check"><div class="h">④ 仓位与分散（组合纪律）</div>
  <div class="d">单票≤5%，Top40 等权，半年调仓。低估择时在<b>组合层</b>有效（59.7pp 价差），在<b>单股层</b>不可靠（药明个股 0-20 区不如 40-60 区）。
  不要"一把梭"单只低估股——美的 2022-08 PB 分位 0.5% 极低估入场仍 −2.2%。</div></div>
<div class="check"><div class="h">⑤ 排序信念 &gt; 估值择时（终极配置）</div>
  <div class="d">LX-core（PE 升序 Top40）+52.7% 仍强于纯低估入场 +45.9%（+6.8pp）。最优做法：<b>核心仓用 LX-core 排序</b>，<b>卫星仓用低估择时</b>做增强。
  不要用估值择时替代排序——排序信念（72pp 差距，便宜优先完胜质量优先）是项目回测反复验证的更强 alpha 源。</div></div>

<h2>六、陷阱与边界条件</h2>
<div class="warn"><b>陷阱①：低估 ≠ 催化剂</b>　PB 低分位是"便宜"的度量，不是"会涨"的信号。药明 760 天价值陷阱、美的 2022-04 极低估 −22.2% 均证明：低估可以持续低估，甚至更低估。
真正的反转需要基本面催化（行业景气、政策、业绩拐点），低估只是提供"安全边际"而非"催化剂"。</div>
<div class="warn"><b>陷阱②：PE 分位被盈利下滑污染</b>　盈利下滑→EPS 降低→PE 被动升高→"PE 分位低"是假低估。实证 PE 分区区分度平坦（8.6%→4.9%），PB 价差 9.4pp vs PE 3.7pp。
<b>入场分位一律以 PB 为准</b>；PE 分位仅作双低条件辅助。</div>
<div class="warn"><b>陷阱③：2026-04 期前瞻窗口不完整</b>　该期至 2026-08-25 不足 126 个交易日，前瞻收益不可比，已从前瞻统计中自然剔除（9 个完整期入样）。该期净值为"部分期"标记。</div>
<div class="warn"><b>陷阱④：宁德 80-100 区高收益是幸存期效应</b>　宁德个股层高估区 6M +52.1% 来自 2021 泡沫期+新能源主升浪的动量残留，样本集中在特定历史窗口，<b>不可外推</b>为"高估也能买"。</div>
<div class="warn"><b>陷阱⑤：口径差异</b>　本报告净值模拟为"期边界无成本持有"，LX-core 官方口径为"含成本日频撮合" +55.55%/年化 9.16%/MDD −19.13%。两者方向一致，绝对值因成本与颗粒度不同略有差异。</div>
<div class="warn"><b>陷阱⑥：低分位拥挤化</b>　2025-08 期 core 仅 8/40 在 0-20 区，可买"便宜"变少，排序超额收敛。低估择时在熊市/出清期最有效，在牛市末期效果衰减。</div>

<h2>七、当前三只案例股的买点裁决</h2>
<table>
  <tr><th>股票</th><th>质量筛选(2026-04)</th><th>PB 5y分位</th><th>距52周低</th><th>裁决</th></tr>
  <tr><td><b>药明康德</b></td><td>❌ L5否决(PEG 3.66&gt;2)</td><td>{R['part_a']['603259.SH']['current']['pb_pct_5y']:.0f}%</td><td>{R['part_a']['603259.SH']['current']['dist52_pct']:.1f}%</td>
      <td><b>非买点</b>：估值中性偏贵（PB 5y 74%），接近52周高点（4.1%），且一致预期增速转负。等 PB 5y 降至 &lt;30% + 预期企稳。</td></tr>
  <tr><td><b>美的集团</b></td><td>✅ 通过</td><td>{R['part_a']['000333.SZ']['current']['pb_pct_5y']:.0f}%</td><td>{R['part_a']['000333.SZ']['current']['dist52_pct']:.1f}%</td>
      <td><b>非买点</b>：质量持续在池，但 PB 5y 82% 处于历史高位（估值贵），距52周低 2.5%（接近高点）。质量公司但非低估时点。</td></tr>
  <tr><td><b>宁德时代</b></td><td>❌ L5否决(增速33%&gt;25%)</td><td>{R['part_a']['300750.SZ']['current']['pb_pct_5y']:.1f}%</td><td>{R['part_a']['300750.SZ']['current']['dist52_pct']:.1f}%</td>
      <td><b>三只中最接近买点</b>：PB 5y 25%/PE 5y 21% 已低估，距52周低 18%。但一致预期增速 33.75%&gt;25% 被 L5 否决（预期过热）。若增速预期回落至 ≤25% 且 PEG≤2，则为低估买点。</td></tr>
</table>
<div class="note"><b>关键洞察</b>：三只"高质量公司"当前<b>无一</b>同时满足"高质量通过 + 低估入场"。这正是框架的价值——它强迫你在"质量"和"估值"两个维度上都拿到入场券，而不是因为"公司好"就在任何价格买入。</div>

<footer>
  <b>数据来源</b>：juzi-mcp（万得全A PIT 成分 / 日频估值面板 / 收益面板）、腾讯 qt.gtimg.cn（实时行情/日K复权）、SQLite data/a_share_market.db（factor_panel/consensus）<br>
  <b>脚本链</b>：_qc_fetch.py（行情+日K）→ _qc_pool.py（质量池推导+band分位）→ _qc_study.py（Part A个股层+Part B组合层）→ _qc_report.py（本报告）<br>
  <b>口径铁律</b>：池子=万得全A PIT 成分 · 日频复权价 · PB/PE 5年前置分位（不偷看未来）· 半年调仓期边界持有 · 2026-04 部分期已标注<br>
  <b>关联</b>：LX-core 回测 _bt_daily_report.html · Band 规避层 _bt_band_report.html · 6 策略对比 _six_now_compare.html · 投资认知框架 docs/投资认知框架.md<br>
  <b>生成时间</b>：{now_str}
</footer>
</body>
</html>"""

open("_bt_quality_cheap_entry.html","w",encoding="utf-8").write(html)
print("OK -> _bt_quality_cheap_entry.html", len(html), "chars")
