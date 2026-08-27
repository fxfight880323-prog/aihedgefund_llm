# -*- coding: utf-8 -*-
"""以当前推荐名单 _lx_now_final.json 等权建仓（100 万、碎股口径、15bp 成本）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E
import _sim_report as R

LIST_FILE = os.path.join(E.BASE, "_lx_now_final.json")


def main():
    data = E.jload(LIST_FILE)
    assert data and data.get("final"), "读不到名单 _lx_now_final.json"
    stocks = data["final"]
    n = len(stocks)
    tcodes = [E.tx_code(s["code"]) for s in stocks] + [E.BM_CODE]
    q = E.fetch_quotes(tcodes)
    bm = q[E.BM_CODE]
    date = bm["ts_date"]
    assert date, "行情无日期"

    budget = E.CAPITAL / n / (1 + E.FEE)   # 每只目标投入（含费）
    port = {
        "config": {
            "name": "LX-top40 模拟组合",
            "created": date,
            "capital": E.CAPITAL,
            "list_as_of": data.get("as_of"),
            "list_method": data.get("method"),
            "fee": E.FEE,
            "rebalance": "半年（每年4月末/8月末，对齐回测 PIT_DATES）",
            "next_rebalance": E.next_rebalance(date),
            "benchmark": "中证全指 000985.SH（价格指数，不含分红）",
            "mirror": "腾讯自选股·练习赛组合（100股取整近似镜像，App端可视化）",
            "quote_source": "qt.gtimg.cn 腾讯实时行情",
        },
        "cash": E.CAPITAL,
        "positions": [],
    }
    trades = []
    for s in stocks:
        tc = E.tx_code(s["code"])
        qq = q[tc]
        price = qq["price"]
        shares = round(budget / price, 4)
        amount = shares * price
        fee = amount * E.FEE
        port["cash"] -= amount + fee
        name = qq["name"] or s["name"]
        port["positions"].append({
            "code": s["code"], "tcode": tc, "name": name,
            "shares": shares, "cost": price, "cost_amount": round(amount, 2),
            "init_date": date, "score_rank": s.get("score_rank"),
            "pe": s.get("pe"), "peg": s.get("peg"), "band_flag": s.get("band_flag"),
        })
        trades.append({"date": date, "type": "建仓", "code": s["code"], "name": name,
                       "shares": shares, "price": price, "amount": round(amount, 2),
                       "fee": round(fee, 2), "reason": f"初始建仓 score_rank={s.get('score_rank')}"})

    mv, nav, _ = E.port_value(port, q)
    nav_list = E.upsert_nav([], {
        "date": date, "nav": round(nav, 2), "mv": round(mv, 2), "cash": round(port["cash"], 2),
        "day_ret": 0.0, "cum_ret": round(nav / E.CAPITAL - 1, 6),
        "bm_close": bm["price"], "bm_idx": 1.0, "bm_cum": 0.0, "ts": bm["ts"],
    })
    E.jdump(port, E.PORT_FILE)
    E.jdump(trades, E.TRADE_FILE)
    E.jdump(nav_list, E.NAV_FILE)
    R.gen_report(quotes=q)
    print(f"建仓完成 {date}: {n} 只 等权 | 现金 {port['cash']:,.2f} | 净值 {nav:,.2f} ({nav / E.CAPITAL - 1:+.2%})")
    print(f"基准 {E.BM_NAME} {bm['price']} @ {bm['ts']} | 下次调仓 {port['config']['next_rebalance']}")


if __name__ == "__main__":
    main()
