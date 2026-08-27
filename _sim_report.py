# -*- coding: utf-8 -*-
"""生成 _sim_report.html：净值曲线 SVG + 持仓明细 + 交易流水 + 口径说明。"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E

REPORT_PATH = os.path.join(E.BASE, "_sim_report.html")

CSS = """<style>
body{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:#f4f5f7;margin:0;color:#2c3e50;}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 60px;}
h1{font-size:22px;margin:0 0 4px;}
.sub{color:#7f8c8d;font-size:12.5px;margin-bottom:18px;line-height:1.7;}
.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px;}
.card{background:#fff;border:1px solid #e3e7ec;border-radius:10px;padding:12px 14px;}
.card .k{font-size:11.5px;color:#8a95a1;}
.card .v{font-size:18px;font-weight:650;margin-top:4px;white-space:nowrap;}
.card .s{font-size:11px;color:#8a95a1;margin-top:2px;}
.panel{background:#fff;border:1px solid #e3e7ec;border-radius:10px;padding:16px 18px;margin-bottom:18px;}
.panel h2{font-size:15px;margin:0 0 10px;}
table{border-collapse:collapse;width:100%;font-size:12.5px;}
th{background:#f0f3f6;text-align:right;padding:6px 8px;font-weight:600;white-space:nowrap;position:sticky;top:0;}
td{padding:5px 8px;text-align:right;border-bottom:1px solid #eef1f4;white-space:nowrap;}
th:first-child,td:first-child{text-align:center;}
td.l,th.l{text-align:left;}
.up{color:#c0392b;} .dn{color:#0e7c3a;} .flat{color:#5d6d7e;}
.note{font-size:12px;color:#7f8c8d;line-height:1.9;}
.scroll{max-height:430px;overflow:auto;border-radius:6px;}
.legend{font-size:12px;color:#5d6d7e;margin-top:8px;}
.badge{display:inline-block;background:#eef3fb;color:#2c5cc5;border-radius:4px;padding:0 6px;font-size:11px;margin-left:6px;}
.tot td{font-weight:650;background:#fafbfc;}
</style>"""


def _d(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}" if yyyymmdd and len(yyyymmdd) == 8 else (yyyymmdd or "")


def _cls(v):
    return "up" if v > 0 else ("dn" if v < 0 else "flat")


def _chart(nav, reb_dates):
    W, H = 980, 270
    L, R, T, B = 70, 18, 16, 34
    pw, ph = W - L - R, H - T - B
    n = len(nav)
    if n == 0:
        return "<div class='note'>无净值数据</div>"
    nav_idx = [e["nav"] / E.CAPITAL for e in nav]
    bm_idx = [e.get("bm_idx") or 1.0 for e in nav]
    lo = min(min(nav_idx), min(bm_idx))
    hi = max(max(nav_idx), max(bm_idx))
    if hi - lo < 1e-9:
        lo, hi = lo - 0.01, hi + 0.01
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def X(i):
        return L + pw * i / (n - 1 if n > 1 else 1)

    def Y(v):
        return T + ph * (1 - (v - lo) / (hi - lo))

    parts = [f"<svg viewBox='0 0 {W} {H}' style='width:100%;background:#fff'>"]
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        parts.append(f"<line x1='{L}' y1='{y:.1f}' x2='{W - R}' y2='{y:.1f}' stroke='#eef1f4'/>")
        parts.append(f"<text x='{L - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' fill='#8a95a1'>{v - 1:+.1%}</text>")
    if n > 1:
        pts2 = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(bm_idx))
        pts1 = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(nav_idx))
        parts.append(f"<polyline points='{pts2}' fill='none' stroke='#95a5a6' stroke-width='1.6' stroke-dasharray='5,4'/>")
        parts.append(f"<polyline points='{pts1}' fill='none' stroke='#c0392b' stroke-width='2.2'/>")
        for i, e in enumerate(nav):
            if e["date"] in reb_dates:
                x = X(i)
                parts.append(f"<line x1='{x:.1f}' y1='{T}' x2='{x:.1f}' y2='{T + ph:.1f}' stroke='#2c5cc5' stroke-dasharray='3,3' opacity='.45'/>")
        for i in (0, n // 2, n - 1):
            parts.append(f"<text x='{X(i):.1f}' y='{H - 10}' text-anchor='middle' font-size='11' fill='#8a95a1'>{_d(nav[i]['date'])}</text>")
    else:
        y = Y(nav_idx[0])
        parts.append(f"<line x1='{L}' y1='{y:.1f}' x2='{W - R}' y2='{y:.1f}' stroke='#c0392b' stroke-width='2'/>")
        parts.append(f"<text x='{L + 12}' y='{y - 8:.1f}' font-size='12' fill='#8a95a1'>建仓首日 · 净值曲线将随每日跟踪生长</text>")
    parts.append("</svg>")
    return "".join(parts)


def gen_report(quotes=None):
    port = E.jload(E.PORT_FILE)
    if not port:
        return
    nav = E.jload(E.NAV_FILE, []) or []
    trades = E.jload(E.TRADE_FILE, []) or []
    cfg = port["config"]
    if quotes is None:
        quotes = E.fetch_quotes([p["tcode"] for p in port["positions"]] + [E.BM_CODE])
    bm = quotes.get(E.BM_CODE, {})
    latest = nav[-1] if nav else {}

    rows, tot_mv, tot_pnl = [], 0.0, 0.0
    for p in sorted(port["positions"], key=lambda x: x.get("score_rank") or 999):
        q = quotes.get(p["tcode"])
        price = q["price"] if q else p["cost"]
        pct = q.get("pct") if q else None
        mv = p["shares"] * price
        pnl = mv - p["cost_amount"]
        pnl_pct = pnl / p["cost_amount"] if p["cost_amount"] else 0.0
        tot_mv += mv
        tot_pnl += pnl
        rows.append((p, price, pct, mv, pnl, pnl_pct))

    navv = latest.get("nav", tot_mv + port["cash"])
    cum = navv / E.CAPITAL - 1
    day = latest.get("day_ret")
    bm_cum = latest.get("bm_cum", 0.0)
    exc = cum - bm_cum
    reb_dates = {t["date"] for t in trades if str(t.get("type", "")).startswith("调仓")}

    # ---- 持仓表 ----
    pos_html = []
    for i, (p, price, pct, mv, pnl, pnl_pct) in enumerate(rows, 1):
        pct_h = (f"<span class='{_cls(pct)}'>{pct:+.2f}%</span>" if pct is not None else "—")
        flag = p.get("band_flag")
        flag_h = f"<span class='badge'>{flag}</span>" if flag and flag != "中性" else ""
        pos_html.append(
            f"<tr><td>{i}</td><td class='l'>{p['code']} {p['name']}{flag_h}</td>"
            f"<td>{_d(p['init_date'])}</td><td>{p['cost']:.2f}</td>"
            f"<td>{price:.2f}</td><td>{pct_h}</td><td>{p['shares']:.1f}</td>"
            f"<td>{mv / 1e4:.2f}</td><td>{mv / tot_mv * 100:.1f}%</td>"
            f"<td class='{_cls(pnl)}'>{pnl:+,.0f}</td><td class='{_cls(pnl_pct)}'>{pnl_pct:+.2%}</td></tr>")
    pos_html.append(
        f"<tr class='tot'><td></td><td class='l'>合计 {len(rows)} 只</td><td></td><td></td><td></td><td></td><td></td>"
        f"<td>{tot_mv / 1e4:.2f}</td><td>100%</td>"
        f"<td class='{_cls(tot_pnl)}'>{tot_pnl:+,.0f}</td>"
        f"<td class='{_cls(cum)}'>{cum:+.2%}</td></tr>")

    # ---- 流水表 ----
    tr_html = []
    for t in reversed(trades):
        tr_html.append(
            f"<tr><td>{_d(t['date'])}</td><td>{t['type']}</td><td class='l'>{t['code']} {t['name']}</td>"
            f"<td>{t['shares']:.1f}</td><td>{t['price']:.2f}</td><td>{t['amount']:,.0f}</td>"
            f"<td>{t['fee']:.0f}</td><td class='l'>{t.get('reason', '')}</td></tr>")

    day_h = f"<span class='{_cls(day)}'>{day:+.2%}</span>" if day is not None else "—"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{cfg['name']} · 每日净值跟踪</title>{CSS}</head><body><div class="wrap">
<h1>{cfg['name']} · 每日净值跟踪</h1>
<div class="sub">建仓 {_d(cfg['created'])} ｜ 初始资金 {cfg['capital']:,.0f} 元 ｜ 名单 as_of {_d(cfg.get('list_as_of', ''))}（{cfg.get('list_method', '')}）
<br>调仓 {cfg['rebalance']}，下次 <b>{cfg.get('next_rebalance', '')}</b> ｜ 基准 {cfg['benchmark']} ｜ 行情 {cfg.get('quote_source', '')}</div>

<div class="cards">
<div class="card"><div class="k">最新净值</div><div class="v">{navv:,.0f}</div><div class="s">指数 {navv / E.CAPITAL:.4f}</div></div>
<div class="card"><div class="k">累计收益</div><div class="v {_cls(cum)}">{cum:+.2%}</div><div class="s">自建仓起</div></div>
<div class="card"><div class="k">当日涨跌</div><div class="v">{day_h}</div><div class="s">{_d(latest.get('date', ''))}</div></div>
<div class="card"><div class="k">超额中证全指</div><div class="v {_cls(exc)}">{exc:+.2%}</div><div class="s">基准同期 {bm_cum:+.2%}</div></div>
<div class="card"><div class="k">持仓市值</div><div class="v">{tot_mv / 1e4:,.1f}万</div><div class="s">{len(rows)} 只</div></div>
<div class="card"><div class="k">现金</div><div class="v">{port['cash']:,.0f}</div><div class="s">含建仓成本</div></div>
</div>

<div class="panel"><h2>净值曲线（vs 中证全指）</h2>
{_chart(nav, reb_dates)}
<div class="legend">━ 组合净值指数（初始资金=1）&nbsp;&nbsp;╌╌ 中证全指（归一）&nbsp;&nbsp;┆ 蓝色虚线 = 调仓日</div></div>

<div class="panel"><h2>持仓明细（按评分排名，碎股等权口径）</h2>
<div class="scroll"><table>
<tr><th>#</th><th class="l">代码/名称</th><th>建仓日</th><th>成本价</th><th>现价</th><th>今日</th><th>持股</th><th>市值(万)</th><th>权重</th><th>浮动盈亏(元)</th><th>盈亏率</th></tr>
{"".join(pos_html)}</table></div></div>

<div class="panel"><h2>交易流水（最新在前，共 {len(trades)} 笔）</h2>
<div class="scroll"><table>
<tr><th>日期</th><th>类型</th><th class="l">代码/名称</th><th>股数</th><th>价格</th><th>金额(元)</th><th>费用</th><th class="l">备注</th></tr>
{"".join(tr_html)}</table></div></div>

<div class="panel"><h2>口径说明</h2><div class="note">
· <b>名单</b>：_lx_now_final.json —— 评分 top40（价值50%+质量25%+安全25%）+ PB 5年分位&gt;90% 规避，L5 为 garp 门控（增速≤60% 且 0&lt;PEG≤1），无金融股。<br>
· <b>建仓口径</b>：等权 2.5 万/只、碎股（与回测一致）；单边成本 15bp（佣金5bp+冲击10bp）已计入，故建仓日净值≈ -0.15%。<br>
· <b>调仓</b>：每年 4 月末 / 8 月末（对齐回测 PIT_DATES），按当期新名单等权重置；剔除卖出、新进买入、保留股权重回补。<br>
· <b>净值</b>：Σ持股×腾讯实时价 + 现金。未复权现价、未跟踪分红到账（除权日净值自然回落）——长期相对含分红口径略有低估，与价格指数基准口径一致性较好。<br>
· <b>基准</b>：中证全指 000985.SH 价格指数（不含分红），超额 = 累计收益差；严格同口径基准（半年调仓等权全A）无法日频跟踪，仅回测中使用。<br>
· <b>镜像</b>：{cfg.get('mirror', '')}；净值与调仓以本地账本（_sim_portfolio.json）为权威。<br>
· <b>引擎</b>：_sim_engine.py（行情/账本）· _sim_init.py（建仓）· _sim_daily.py（每日净值）· _sim_rebalance.py（半年调仓）· 每日 15:35 自动化运行 _sim_daily.py。
</div></div>

<div class="sub" style="margin-top:6px">报告生成 {now} ｜ 行情时间 {bm.get('ts', '')} ｜ 仅供研究，不构成投资建议</div>
</div></body></html>"""

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(html)
    return REPORT_PATH


if __name__ == "__main__":
    print(gen_report())
