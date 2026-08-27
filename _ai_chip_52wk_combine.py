# -*- coding: utf-8 -*-
"""筹码结构 × 52周高点近距 两项信号结合 — AI科技池筛选。

信号:
  1. 筹码结构 (2026-07-31 z-score, 均负向=值越小越好):
     - 机构筹码集中度 (IC -4.4% 最强最稳)
     - 筹码合成       (全A IC -5.7%, 集中度主导)
  2. 52周高点近距 dist52 = 最新月收盘/过去12月最高收盘 (越大越近=越强)

打分 (池内横截面百分位):
  筹码分 = (1-pct(筹码合成) + 1-pct(集中度)) / 2
  高点分 = pct(dist52)
  综合   = 0.5*筹码分 + 0.5*高点分

过滤: 剔除 ST/*ST / 北交所 / 信号缺失; 标注市值与东财行业。
输出: _ai_chip_52wk_top.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RANK = json.load(open(os.path.join(HERE, "_ai_52wk_rank.json"), encoding="utf-8"))
CHIP = json.load(open(os.path.join(HERE, "_chip_industry_data.json"), encoding="utf-8"))
CONC = json.load(open(os.path.join(HERE, "_ai_chip_conc.json"), encoding="utf-8"))


def to_ts(sym: str) -> str:
    mkt, code = sym[:2], sym[2:]
    return code + (".SH" if mkt == "sh" else ".SZ")


def rank_pct(vals: list[float]) -> dict[float, float]:
    """值 -> 池内百分位 [0,1], 越大的值分越高."""
    n = len(vals)
    order = {v: i for i, v in enumerate(sorted(vals))}
    return {v: order[v] / (n - 1) if n > 1 else 0.5 for v in vals}


# 科技行业白名单（东财一级/二级行业口径）
TECH = {"半导体", "软件开发", "IT服务Ⅱ", "计算机设备", "通信设备", "通信服务",
        "消费电子", "元件", "光学光电子", "军工电子Ⅱ", "其他电子Ⅱ", "电子化学品Ⅱ",
        "游戏Ⅱ", "数字媒体", "自动化设备", "航天装备Ⅱ", "光伏设备"}


def main():
    chip_map = {s["ts_code"]: s for s in CHIP["stocks"]}

    rows = []
    for r in RANK:
        sym = r["sym"]
        if sym[:2] == "bj":
            continue
        name = r.get("name", "")
        if "ST" in name.upper():
            continue
        if r.get("dist52") is None:
            continue
        ts = to_ts(sym)
        c = chip_map.get(ts)
        conc = CONC.get(ts)
        if c is None or conc is None:
            continue
        if c.get("industry", "") not in TECH:
            continue
        rows.append({
            "sym": sym, "ts": ts, "name": name,
            "mv": r.get("mv"), "mvc": r.get("mvc"),
            "price": r.get("price"), "pct": r.get("pct"),
            "dist52": r["dist52"],
            "chip": c["chip"],           # 筹码合成 z
            "conc": conc,                # 机构筹码集中度 z
            "industry": c.get("industry", ""),
            "sectors": r.get("sectors", []),
        })
    print(f"合格样本: {len(rows)}")

    # 百分位
    d52 = rank_pct([x["dist52"] for x in rows])
    chipz = rank_pct([x["chip"] for x in rows])
    concz = rank_pct([x["conc"] for x in rows])
    for x in rows:
        x["p_dist52"] = d52[x["dist52"]]
        x["p_chip"] = 1 - chipz[x["chip"]]      # 负向反向
        x["p_conc"] = 1 - concz[x["conc"]]      # 负向反向
        x["chip_score"] = (x["p_chip"] + x["p_conc"]) / 2
        x["score"] = 0.5 * x["chip_score"] + 0.5 * x["p_dist52"]

    rows.sort(key=lambda x: -x["score"])
    for i, x in enumerate(rows, 1):
        x["rank"] = i

    json.dump(rows, open(os.path.join(HERE, "_ai_chip_52wk_top.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n{'#':>3} {'代码':<9} {'名称':<9} {'score':>5} {'筹码分':>6} {'高点分':>6} "
          f"{'dist52':>7} {'筹码z':>6} {'集中z':>6} {'mv亿':>7} {'行业':<8} 板块")
    for x in rows[:20]:
        print(f"{x['rank']:>3} {x['sym']:<9} {x['name']:<9} {x['score']:.3f} {x['chip_score']:.3f} "
              f"{x['p_dist52']:.3f} {x['dist52']:.3f} {x['chip']:>6.2f} {x['conc']:>6.2f} "
              f"{x['mv']:>7.0f} {x['industry']:<8} {'/'.join(x['sectors'][:2])}")


if __name__ == "__main__":
    main()
