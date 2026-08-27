# -*- coding: utf-8 -*-
"""以 q20 最终名单 _bt_q20_kfin.json（final）等权建仓（100 万、碎股口径、15bp 成本）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_q20_engine as Q
import _sim_q20_report as R


def main():
    data = Q.jload(Q.LIST_FILE)
    assert data and data.get("final"), "读不到名单 _bt_q20_kfin.json"
    stocks = data["final"]
    n = len(stocks)
    tcodes = [Q.tx_code(s["code"]) for s in stocks] + [Q.BM_CODE]
    q = Q.fetch_quotes(tcodes)
    bm = q[Q.BM_CODE]
    date = bm["ts_date"]
    assert date, "行情无日期"

    budget = Q.CAPITAL / n / (1 + Q.FEE)   # 每只目标投入（含费）
    port = {
        "config": {
            "name": "Q20·质衡优选 模拟组合",
            "created": date,
            "capital": Q.CAPITAL,
            "list_as_of": data.get("as_of"),
            "list_method": data.get("method"),
            "pool": data.get("pool_desc"),
            "backtest_note": data.get("backtest_note"),
            "fee": Q.FEE,
            "rebalance": "半年（每年4月末/8月末，对齐回测 PIT_DATES）",
            "next_rebalance": Q.next_rebalance(date),
            "benchmark": "中证全指 000985.SH（价格指数，不含分红）",
            "mirror": "暂未镜像（本地账本为准）",
            "quote_source": "qt.gtimg.cn 腾讯实时行情",
        },
        "cash": Q.CAPITAL,
        "positions": [],
    }
    trades = []
    for s in stocks:
        tc = Q.tx_code(s["code"])
        qq = q[tc]
        price = qq["price"]
        shares = round(budget / price, 4)
        amount = shares * price
        fee = amount * Q.FEE
        port["cash"] -= amount + fee
        name = qq["name"] or s["name"]
        flag = s.get("flag") or "中性"
        port["positions"].append({
            "code": s["code"], "tcode": tc, "name": name,
            "shares": shares, "cost": price, "cost_amount": round(amount, 2),
            "init_date": date, "score_rank": s.get("rank"),
            "pe": s.get("pe"), "q_score": s.get("q_score"), "blend": s.get("blend"),
            "band_flag": flag,
        })
        trades.append({"date": date, "type": "建仓", "code": s["code"], "name": name,
                       "shares": shares, "price": price, "amount": round(amount, 2),
                       "fee": round(fee, 2), "reason": f"q20 建仓 rank={s.get('rank')}"})

    mv, nav, _ = Q.port_value(port, q)
    nav_list = Q.upsert_nav([], {
        "date": date, "nav": round(nav, 2), "mv": round(mv, 2), "cash": round(port["cash"], 2),
        "day_ret": 0.0, "cum_ret": round(nav / Q.CAPITAL - 1, 6),
        "bm_close": bm["price"], "bm_idx": 1.0, "bm_cum": 0.0, "ts": bm["ts"],
    })
    Q.jdump(port, Q.PORT_FILE)
    Q.jdump(trades, Q.TRADE_FILE)
    Q.jdump(nav_list, Q.NAV_FILE)
    R.gen_report(quotes=q)
    print(f"建仓完成 {date}: {n} 只 等权 | 现金 {port['cash']:,.2f} | 净值 {nav:,.2f} ({nav / Q.CAPITAL - 1:+.2%})")
    print(f"基准 {Q.BM_NAME} {bm['price']} @ {bm['ts']} | 下次调仓 {port['config']['next_rebalance']}")


if __name__ == "__main__":
    main()
