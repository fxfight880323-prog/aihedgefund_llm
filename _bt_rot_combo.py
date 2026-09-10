# -*- coding: utf-8 -*-
"""
申万行业轮动因子 · 卫星仓历史回测 + 底仓组合层验证

设计（正交收益源，半年调仓对齐项目铁律 PIT_DATES）:
  1. 对每个调仓月末，拉 core-pass 池内个股的行业轮动因子值（广播到个股，同行业同分）
  2. 确定该月末前6个看好行业（因子值最高的6个唯一值）
  3. 在看好行业池内的 core-pass 股做 q20 排序 + cap8 加权 → 卫星仓
  4. 底仓 q20_cap8 净值 + 卫星仓净值按 80/20、70/30 等合成，验证正交叠加

诚实性：
  - 行业轮动因子 all_a 口径用静态行业映射，历史回测有轻微前视（个股行业归属用当前值回看过去），已获用户确认接受
  - 半年调仓（对齐 PIT_DATES），非月频——损失行业轮动月频优势，但保证与底仓同口径可干净合成
  - 因子值广播=行业选择，个股质量靠 q20 排序补齐
"""
import json, os, sys, datetime, statistics, time, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import load_all, load_bars, build_weights
from _bt_q20_cap import screen_q20, cap_weight, dep_best, yearly

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS = L.MAX_HOLDINGS
TOP_K = 6  # 前6个看好行业
CAP = 0.08

URL = "http://159.138.132.129/mcp/"
AUTH = "Bearer JKAW7A"


def rpc(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", AUTH)
    if sid:
        req.add_header("Mcp-Session-Id", sid)
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode("utf-8")
        nsid = r.headers.get("Mcp-Session-Id")
        ct = r.headers.get("Content-Type", "")
    objs = []
    if "text/event-stream" in ct:
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    objs.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
    elif body.strip():
        objs.append(json.loads(body))
    return objs, nsid


def get_text(msgs):
    for r in msgs:
        if "result" in r:
            for c in r["result"].get("content", []):
                if c.get("type") == "text":
                    return c["text"]
        if "error" in r:
            return "ERROR: " + json.dumps(r["error"], ensure_ascii=False)
    return None


def fetch_rot(codes, date, sid):
    """批量拉行业轮动因子值（每批≤100），返回 {tk: value}"""
    out = {}
    for i in range(0, len(codes), 100):
        batch = codes[i:i+100]
        for attempt in range(3):
            try:
                msgs, _ = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "get_factor_value",
                                          "arguments": {"factors": ["行业轮动"],
                                                        "ts_codes": batch, "date": date}}}, sid)
                txt = get_text(msgs)
                if txt and txt.startswith("ERROR"):
                    time.sleep(1)
                    continue
                obj = json.loads(txt)
                for rr in obj.get("records", []):
                    out[rr["ts_code"]] = rr["行业轮动"]
                break
            except Exception:
                time.sleep(1)
        time.sleep(0.1)
    return out


def main():
    print("=" * 88)
    print("  申万行业轮动因子 · 卫星仓历史回测 + 底仓组合层验证")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())

    # 初始化 MCP 会话
    msgs, sid = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "rot-bt", "version": "1.0"}}})
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)

    # 每期 core-pass 池（复用 screen_q20，full 基座含金融）
    pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        pools[month] = screen_q20(month, members, vv, ff, cc)
        print(f"  {month}: core-pass 池 {len(pools[month])} 只")

    # 每期拉行业轮动因子值（只拉 core-pass 池内股票）
    print("\n[拉取行业轮动因子值] 各调仓月末 …")
    rot_by_month = {}
    for month, as_of in PIT_DATES:
        codes = [s["tk"] for s in pools[month]]
        rot_map = fetch_rot(codes, as_of, sid)
        rot_by_month[month] = rot_map
        n = len(rot_map)
        uniq = len(set(rot_map.values())) if rot_map else 0
        print(f"  {month} ({as_of}): {n}/{len(codes)} 只有因子值，{uniq} 个唯一值(行业)")

    # 卫星仓选股：每期取前6个行业内的股票
    def sort_satellite(pool, rot_map):
        if not rot_map:
            return []
        uniq_vals = sorted(set(rot_map.values()), reverse=True)
        top_vals = set(uniq_vals[:TOP_K])
        cand = [s for s in pool if s["tk"] in rot_map and rot_map[s["tk"]] in top_vals]
        if not cand:
            return []
        # q20 排序（池内百分位，只在 cand 内）
        gpm_vals = [s["gpm"] for s in cand if s["gpm"]]
        roe_vals = [s["roe"] for s in cand if s["roe"]]
        cet_vals = [s["cetop"] for s in cand if s["cetop"]]
        pe_vals = [s["pe"] for s in cand]
        for s in cand:
            s["gpm_pct"] = _pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
            s["roe_pct"] = _pct_rank(roe_vals, s["roe"]) if s["roe"] else 0
            s["cet_pct"] = _pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
            s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0
            s["pe_pct"] = 100.0 - _pct_rank(pe_vals, s["pe"])
            s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_score"]
        cand.sort(key=lambda s: -s["blend"])
        return cand[:MAX_HOLDINGS]

    def _pct_rank(values, v):
        n = len(values)
        if n == 0:
            return 50.0
        return sum(1 for x in values if x < v) / n * 100.0

    # 回测卫星仓
    print("\n[回测] 卫星仓 …")
    w_by_dt = {}
    sat_cnt = []
    sat_fin = []
    for month, asof in PIT_DATES:
        picked = sort_satellite(pools[month], rot_by_month[month])
        if not picked:
            sat_cnt.append(0)
            sat_fin.append(0)
            continue
        w = cap_weight(picked, CAP)
        trig = max(d for d in all_dates if d <= asof)
        w_by_dt[trig] = w
        sat_cnt.append(len(picked))
        sat_fin.append(sum(1 for s in picked if s["tk"] in fin))

    sat = G.run("satellite", w_by_dt, bars)
    sat["yearly"] = yearly(sat["nav"])
    sat["dep"] = dep_best(sat["yearly"])

    # 底仓 q20_cap8（复用已算好的结果，但需要 nav 序列——重跑）
    print("[回测] 底仓 q20_cap8 …")
    def sort_q20(pool):
        return sorted(pool, key=lambda s: -s["blend"])[:MAX_HOLDINGS]

    base_w_by_dt = {}
    for month, asof in PIT_DATES:
        picked = sort_q20(pools[month])
        w = cap_weight(picked, CAP)
        trig = max(d for d in all_dates if d <= asof)
        base_w_by_dt[trig] = w
    base = G.run("base_q20_cap8", base_w_by_dt, bars)
    base["yearly"] = yearly(base["nav"])
    base["dep"] = dep_best(base["yearly"])

    print(f"\n[单策略] 底仓 q20_cap8: 总 {base['total']*100:+.1f}% "
          f"MDD {base['mdd']*100:.1f}% 依赖度 {base['dep']:.2f}")
    print(f"[单策略] 卫星仓: 总 {sat['total']*100:+.1f}% "
          f"MDD {sat['mdd']*100:.1f}% 依赖度 {sat['dep']:.2f} "
          f"(持仓 {statistics.mean(sat_cnt):.1f}只/期, 金融 {statistics.mean(sat_fin):.1f}/期)")

    # 组合合成（按日净值对齐）
    # 注意：G.run 的 nav 是账户余额(capital=1000000 起)，需各自归一化到首日=1.0 再合成
    b_dates = [x["date"] for x in base["nav"]]
    s_dates = [x["date"] for x in sat["nav"]]
    b0 = base["nav"][0]["nav"]
    s0 = sat["nav"][0]["nav"]
    base_nav = {x["date"]: x["nav"] / b0 for x in base["nav"]}
    sat_nav = {x["date"]: x["nav"] / s0 for x in sat["nav"]}
    combos = {}
    for frac in (0.0, 0.1, 0.2, 0.3, 0.5):
        wb, ws = 1 - frac, frac
        nav_list = []
        for dt in sorted(set(base_nav) | set(sat_nav)):
            nb = base_nav.get(dt)
            ns = sat_nav.get(dt)
            if nb is None or ns is None:
                continue
            nav_list.append({"date": dt, "nav": wb * nb + ws * ns})
        r = G.run("combo", {}, bars)  # 占位，手动算指标
        r["nav"] = nav_list
        r["total"] = nav_list[-1]["nav"] - 1.0
        # mdd
        peak, mdd = 1.0, 0.0
        for x in nav_list:
            peak = max(peak, x["nav"])
            mdd = max(mdd, 1.0 - x["nav"] / peak)
        r["mdd"] = mdd
        r["yearly"] = yearly(nav_list)
        r["dep"] = dep_best(r["yearly"])
        yrs = len(nav_list) / 252.0
        r["ann"] = (1 + r["total"]) ** (1 / yrs) - 1 if r["total"] > -1 else -1.0
        combos[f"{int(wb*100)}/{int(ws*100)}"] = r

    # 汇总
    print("\n[组合层验证] 底仓/卫星仓 合成:")
    print(f"{'配置':<10}{'总收益':>10}{'年化':>8}{'MDD':>8}{'依赖度':>8}")
    for name, r in combos.items():
        print(f"{name:<10}{r['total']*100:>9.1f}%{r['ann']*100:>7.1f}%"
              f"{r['mdd']*100:>7.1f}%{r['dep']:>7.2f}")

    # 分年度
    years = sorted(set(y for r in combos.values() for y in r["yearly"]))
    print("\n[分年度收益]（%）:")
    print(f"{'配置':<10}" + "".join(f"{y:>9}" for y in years))
    for name, r in combos.items():
        yl = r["yearly"]
        print(f"{name:<10}" + "".join(f"{yl.get(y,0)*100:>9.1f}" for y in years))

    # 保存
    def slim(r):
        return {"total": r["total"], "ann": r["ann"], "mdd": r["mdd"],
                "dep": r["dep"], "yearly": r["yearly"],
                "nav": r["nav"]}

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "freq": "日频+复权", "rebalance": "半年(PIT_DATES)",
                 "top_k_industry": TOP_K, "cap": CAP,
                 "note": "行业轮动因子all_a静态行业映射，历史有轻微前视(已获确认接受)"},
        "base": slim(base),
        "satellite": slim(sat),
        "satellite_holdings": {"cnt": sat_cnt, "fin": sat_fin},
        "combos": {k: slim(v) for k, v in combos.items()},
    }
    json.dump(out, open("_bt_rot_combo_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_rot_combo_results.json")


if __name__ == "__main__":
    main()
