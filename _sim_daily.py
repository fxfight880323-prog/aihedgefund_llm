# -*- coding: utf-8 -*-
"""每日净值跟踪：拉腾讯行情 → 更新净值序列 → 重新生成报告。

幂等：同一天重复运行会覆盖当天条目；非交易日/盘前（行情日期≠今天）自动跳过。
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E
import _sim_report as R


def main():
    port = E.jload(E.PORT_FILE)
    if not port or not port.get("positions"):
        print("无持仓，请先运行 _sim_init.py")
        return
    tcodes = [p["tcode"] for p in port["positions"]] + [E.BM_CODE]
    q = E.fetch_quotes(tcodes)
    bm = q.get(E.BM_CODE)
    date = bm["ts_date"] if bm else ""
    today = datetime.date.today().strftime("%Y%m%d")
    if date != today:
        print(f"SKIP: 行情日期 {date} ≠ 今日 {today}（非交易日或盘前），未更新")
        return

    nav_list = E.jload(E.NAV_FILE, []) or []
    base_bm = nav_list[0]["bm_close"] if nav_list else bm["price"]
    prevs = [e for e in nav_list if e["date"] < date]
    prev = prevs[-1] if prevs else None

    mv, nav, missing = E.port_value(port, q)
    if missing:
        print(f"WARN: {len(missing)} 只缺行情按成本价估值: {missing}")
    cum = nav / E.CAPITAL - 1
    day_ret = (nav / prev["nav"] - 1) if prev else None
    entry = {
        "date": date, "nav": round(nav, 2), "mv": round(mv, 2), "cash": round(port["cash"], 2),
        "day_ret": round(day_ret, 6) if day_ret is not None else 0.0,
        "cum_ret": round(cum, 6),
        "bm_close": bm["price"], "bm_idx": round(bm["price"] / base_bm, 6),
        "bm_cum": round(bm["price"] / base_bm - 1, 6), "ts": bm["ts"],
    }
    nav_list = E.upsert_nav(nav_list, entry)
    E.jdump(nav_list, E.NAV_FILE)
    R.gen_report(quotes=q)

    dd = f"{day_ret:+.2%}" if day_ret is not None else "—"
    exc = cum - entry["bm_cum"]
    print(f"{date} 净值 {nav:,.2f} | 当日 {dd} | 累计 {cum:+.2%} | "
          f"{E.BM_NAME} {entry['bm_cum']:+.2%} | 超额 {exc:+.2%}")


if __name__ == "__main__":
    main()
