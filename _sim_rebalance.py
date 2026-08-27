# -*- coding: utf-8 -*-
"""半年调仓：把持仓重置为新名单（默认 _lx_now_final.json）等权。

流程：先重跑名单管线（_lx_now_fetch → screen → score → band → apply，刷新
CANDIDATE_DATES 为最新交易日），再运行本脚本。
逻辑：卖出剔除股 → 以调仓时净值等权重置（买入新增 + 保留股权重回补/削减），
15bp 单边成本，全部记录流水，更新净值与报告。
用法:
  python _sim_rebalance.py            # 正式调仓
  python _sim_rebalance.py --dry      # 只打印调仓计划不落盘
  python _sim_rebalance.py --list _lx_now_final.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E
import _sim_report as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default="_lx_now_final.json")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    list_file = os.path.join(E.BASE, args.list)

    data = E.jload(list_file)
    assert data and data.get("final"), f"读不到名单 {args.list}"
    port = E.jload(E.PORT_FILE)
    assert port and port.get("positions"), "无持仓，请先 _sim_init.py"

    stocks = data["final"]
    n_new = len(stocks)
    new_map = {E.tx_code(s["code"]): s for s in stocks}
    old_map = {p["tcode"]: p for p in port["positions"]}

    tcodes = list(new_map) + [t for t in old_map if t not in new_map] + [E.BM_CODE]
    q = E.fetch_quotes(tcodes)
    bm = q[E.BM_CODE]
    date = bm["ts_date"]
    assert date, "行情无日期"

    removed = [t for t in old_map if t not in new_map]
    added = [t for t in new_map if t not in old_map]
    trades = E.jload(E.TRADE_FILE, []) or []

    # 1) 卖出剔除股
    for t in removed:
        p = old_map[t]
        price = q[t]["price"]
        amount = p["shares"] * price
        proceeds = amount * (1 - E.FEE)
        port["cash"] += proceeds
        trades.append({"date": date, "type": "调仓卖出", "code": p["code"], "name": p["name"],
                       "shares": p["shares"], "price": price, "amount": round(amount, 2),
                       "fee": round(amount * E.FEE, 2), "reason": "调仓:剔除(跌出新名单)"})

    # 2) 调仓时净值 → 等权目标
    mv_kept = sum(old_map[t]["shares"] * q[t]["price"] for t in new_map if t in old_map)
    nav2 = mv_kept + port["cash"]
    target = nav2 / n_new

    # 3) 调整到等权（新增买入 / 保留股回补或削减）
    positions = []
    n_buy = n_sell_adj = 0
    for tc, s in new_map.items():
        price = q[tc]["price"]
        old = old_map.get(tc)
        cur_mv = old["shares"] * price if old else 0.0
        delta = target - cur_mv
        shares = old["shares"] if old else 0.0
        if delta > 1:
            shares_add = delta / ((1 + E.FEE) * price)
            amount = shares_add * price
            port["cash"] -= amount * (1 + E.FEE)
            trades.append({"date": date, "type": "调仓买入", "code": s["code"], "name": q[tc]["name"],
                           "shares": round(shares_add, 4), "price": price, "amount": round(amount, 2),
                           "fee": round(amount * E.FEE, 2),
                           "reason": "调仓:新入选" if not old else "调仓:权重回补"})
            shares += shares_add
            n_buy += 1
        elif delta < -1 and old:
            shares_cut = min(-delta / price, old["shares"])
            amount = shares_cut * price
            port["cash"] += amount * (1 - E.FEE)
            trades.append({"date": date, "type": "调仓卖出", "code": s["code"], "name": q[tc]["name"],
                           "shares": round(shares_cut, 4), "price": price, "amount": round(amount, 2),
                           "fee": round(amount * E.FEE, 2), "reason": "调仓:权重削减"})
            shares -= shares_cut
            n_sell_adj += 1
        positions.append({
            "code": s["code"], "tcode": tc, "name": q[tc]["name"] or s["name"],
            "shares": round(shares, 4), "cost": price, "cost_amount": round(shares * price, 2),
            "init_date": date, "score_rank": s.get("score_rank"),
            "pe": s.get("pe"), "peg": s.get("peg"), "band_flag": s.get("band_flag"),
        })

    mv, nav, _ = E.port_value({"positions": positions, "cash": port["cash"]}, q)
    nav_list = E.jload(E.NAV_FILE, []) or []
    base_bm = nav_list[0]["bm_close"] if nav_list else bm["price"]
    prevs = [e for e in nav_list if e["date"] < date]
    prev = prevs[-1] if prevs else None
    day_ret = (nav / prev["nav"] - 1) if prev else None
    entry = {
        "date": date, "nav": round(nav, 2), "mv": round(mv, 2), "cash": round(port["cash"], 2),
        "day_ret": round(day_ret, 6) if day_ret is not None else 0.0,
        "cum_ret": round(nav / E.CAPITAL - 1, 6),
        "bm_close": bm["price"], "bm_idx": round(bm["price"] / base_bm, 6),
        "bm_cum": round(bm["price"] / base_bm - 1, 6), "ts": bm["ts"], "rebalanced": True,
    }

    # 汇总
    print(f"== 调仓计划 {date}（新名单 as_of {data.get('as_of')}，{n_new} 只）==")
    print(f"剔除 {len(removed)} 只: {[old_map[t]['name'] for t in removed]}")
    print(f"新进 {len(added)} 只: {[new_map[t]['name'] for t in added]}")
    print(f"等权目标 {target:,.0f} 元/只 | 买入 {n_buy} 笔 | 削减 {n_sell_adj} 笔")
    print(f"调仓后: 现金 {port['cash']:,.2f} | 净值 {nav:,.2f} ({nav / E.CAPITAL - 1:+.2%})")
    print(f"提醒: 腾讯自选股镜像需手工/自动化同步（portfolio_paper_trade 卖剔除买新增，100股取整）")

    if args.dry:
        print("DRY 模式，未落盘")
        return
    port["positions"] = positions
    port["config"]["list_as_of"] = data.get("as_of")
    port["config"]["next_rebalance"] = E.next_rebalance(date)
    E.jdump(port, E.PORT_FILE)
    E.jdump(trades, E.TRADE_FILE)
    E.jdump(E.upsert_nav(nav_list, entry), E.NAV_FILE)
    R.gen_report(quotes=q)
    print(f"已落盘并更新报告 _sim_report.html | 下次调仓 {port['config']['next_rebalance']}")


if __name__ == "__main__":
    main()
