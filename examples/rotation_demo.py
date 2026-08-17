"""有锐度的均衡 · 轮动 Demo — 章宏帆法全流程离线演示。

Mock universe 覆盖三类资产 × 六个环节 + 非主题强基本面名字：
  A 景气成长（光模块/存储/GPU 高增加速）、B 周期成长（成熟+毛利率回升，
  含一只触 PE 上限的 → 负信念=轮出）、C 新兴成长（极端增长无利润）、
  OFF 自下而上备选（非主题强基本面）。

跑完整 fund cycle：分类表 → 方向权重 → 类配比 → 持仓簿。

Run:
    python examples/rotation_demo.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.fund_spec import load_fund
from src.execution.broker import SimBroker
from src.workflow.graph import build_fund_graph
from src.signals.rotation_growth import RotationGrowthModel

AS_OF = "2026-08-17"


class MockRotationClient:
    """合成 DataClient：跨类跨环节的候选池。"""

    _QUARTERS = [
        "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30",
        "2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30",
    ]

    # (ticker, name, 行业, 营收8季(newest-first), 毛利率, PE, ROE, 净利)
    PROFILES = [
        # A 类：光模块 双龙头（高增加速，毛利率高位）
        ("688308.SH", "东之光模块", "光模块/光通信—通信设备",
         [300, 240, 190, 150, 120, 100, 85, 75], [52, 51], 45, 20,
         [40, 30, 22, 16]),
        ("688309.SH", "南之光模块", "光模块/光通信—通信设备",
         [280, 235, 200, 165, 140, 120, 105, 95], [49, 48], 52, 18,
         [35, 27, 21, 15]),
        # A 类：存储（高增加速）
        ("688525.SH", "佰维式存储", "存储模组",
         [160, 120, 95, 78, 68, 62, 58, 55], [53, 21], 30, 12,
         [12, 6, 2, -2]),
        # A 类：GPU/算力
        ("688795.SH", "国产GPU", "GPU/算力芯片",
         [140, 110, 90, 75, 65, 58, 52, 48], [55, 54], 80, 15,
         [18, 12, 8, 5]),
        # B 类：周期成长 — 半导体设备（成熟+毛利率回升，PE 未超限）
        ("688012.SH", "微刻蚀设备", "半导体设备",
         [95, 88, 84, 80, 78, 76, 75, 74], [40, 39], 18, 22,
         [20, 17, 15, 14]),
        # B 类：周期成长 — 触 PE 上限（>20x → 负信念=减仓轮出）
        ("688036.SH", "消费电子组装", "消费电子精密制造",
         [100, 97, 95, 94, 95, 93, 92, 91], [22, 21], 32, 14,
         [8, 7, 7, 6]),
        # C 类：新兴成长（极端增长 + 毛利率弱）
        ("688802.SH", "新兴算力", "国产算力芯片设计",
         [30, 13, 6, 3.5, 2.2, 1.6, 1.3, 1.1], [8, -5], None, 3,
         [0.2, -0.5, -1.2, -1.5]),
        # OFF：非主题强基本面（高ROE高毛利，行业不匹配环节表）
        ("688271.SH", "医疗器械龙头", "医学影像设备",
         [70, 66, 63, 61, 60, 58, 57, 56], [65, 64], 28, 28,
         [18, 16, 15, 14]),
        # 不可投：低增长无周期回升
        ("688009.SH", "传统轨交", "轨道交通控制",
         [50, 50, 49, 49, 50, 49, 49, 48], [28, 29], 15, 8,
         [4, 4, 4, 4]),
    ]

    def __init__(self):
        self._p = {t: dict(zip(
            ("name", "industry", "rev", "gm", "pe", "roe", "ni"), rest))
            for t, *rest in self.PROFILES}

    def get_prices(self, ticker, start_date, end_date):
        p = self._p.get(ticker)
        if not p:
            return []
        d0 = date(2026, 8, 17) - timedelta(days=420)
        return [{"time": (d0 + timedelta(days=i * 3)).isoformat(),
                 "open": 100.0, "high": 101.0, "low": 99.0,
                 "close": 100.0, "volume": 1e6, "amount": 1e8}
                for i in range(140)
                if start_date <= (d0 + timedelta(days=i * 3)).isoformat()
                <= end_date]

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        p = self._p.get(ticker)
        if not p:
            return []
        rows = []
        for i, q in enumerate(self._QUARTERS):
            if q > end_date:
                continue
            rows.append({
                "ticker": ticker, "date": q, "period": period,
                "revenue": p["rev"][i],
                "gross_margin": p["gm"][i] if i < len(p["gm"]) else None,
                "net_income": p["ni"][i] if i < len(p["ni"]) else None,
                "pe_ratio": (p["pe"] + i * 2) if p["pe"] else None,
                "roe": p["roe"],
            })
        return rows

    def get_company_facts(self, ticker):
        p = self._p.get(ticker)
        if not p:
            return None
        return {"ticker": ticker, "name": p["name"],
                "sector": p["industry"], "industry": p["industry"]}

    def get_earnings(self, ticker):
        return None


def main():
    print("=" * 76)
    print("  有锐度的均衡 · 章宏帆轮动 Demo (离线 Mock)")
    print("=" * 76)

    # ---- ① 分类表（模型直跑）----
    print("\n  ① L1 分类 × L2 环节稀缺度")
    print("  " + "-" * 72)
    model = RotationGrowthModel()
    client = MockRotationClient()
    signals = []
    for tk, *_ in MockRotationClient.PROFILES:
        sig = model.predict(tk, AS_OF, client)
        signals.append(sig)
        m = sig.metadata
        if m.get("abstained"):
            print(f"  {tk} {client._p[tk]['name']:8s} → abstain "
                  f"({sig.reasoning[:44]})")
            continue
        s = m.get("s_scores") or {}
        print(f"  {tk} {client._p[tk]['name']:8s} [{m['asset_class']:3s}] "
              f"环节={m['link'] or '-':10s} "
              f"S分={(m.get('link_score') or 0):2d}/10 "
              f"信念={sig.value:+.2f}")
        if m.get("g5", {}).get("pe_dominant"):
            print(f"      └─ G5 泡沫标记：ΔPE 主导 → 信念减半")

    # ---- ② 完整 fund cycle ----
    print("\n  ② 完整 fund cycle (LangGraph: fetch→analysts→blend→risk→orders)")
    spec = load_fund("config/funds/rotation_demo.yaml")
    broker = SimBroker(capital=spec.capital)
    state = {
        "fund_name": spec.name, "as_of": AS_OF,
        "universe": [t for t, *_ in MockRotationClient.PROFILES],
        "capital": spec.capital, "marks": {}, "skipped": [], "signals": [],
        "convictions": {}, "target_weights": {}, "final_weights": {},
        "clamps": [], "orders": [], "fills": [], "positions": {},
        "cash": spec.capital, "nav": spec.capital,
        "equity_before": spec.capital, "errors": [],
        "metadata": {"fund_spec": spec, "data_client": client,
                     "broker": broker, "capital": spec.capital,
                     "llm_client": None},
    }
    result = build_fund_graph().invoke(state)

    # ---- ③ 组合簿 ----
    print("\n  ③ 组合簿（方向 → 名字 → 权重）")
    print("  " + "-" * 72)
    by_link: dict[str, list] = {}
    for sig in result["signals"]:
        if sig.metadata.get("asset_class"):
            link = sig.metadata.get("link") or "自下而上sleeve"
            by_link.setdefault(link, []).append(sig)
    for link, sigs in sorted(by_link.items(),
                             key=lambda kv: -max(s.metadata.get("link_score")
                                                 or 0 for s in kv[1])):
        link_w = sum(result["final_weights"].get(s.ticker, 0) for s in sigs)
        print(f"\n  ▶ {link}  (方向合计 {link_w:.1%})")
        for s in sorted(sigs, key=lambda x: -result["final_weights"]
                        .get(x.ticker, 0)):
            w = result["final_weights"].get(s.ticker, 0)
            if w <= 0 and s.value <= 0:
                print(f"      {s.ticker} {s.metadata['asset_class']:3s} "
                      f"信念={s.value:+.2f} → 轮出（权重 0）")
                continue
            if w <= 0:
                continue
            print(f"      {s.ticker} {s.metadata['asset_class']:3s} "
                  f"权重={w:.1%}  信念={s.value:+.2f}")

    cls_gross = {}
    for sig in result["signals"]:
        c = sig.metadata.get("asset_class")
        if c:
            cls_gross[c] = cls_gross.get(c, 0) + \
                result["final_weights"].get(sig.ticker, 0)
    print("\n  类配比: " + "  ".join(
        f"{c}={w:.1%}" for c, w in sorted(cls_gross.items())))
    print(f"  总仓位: {sum(result['final_weights'].values()):.1%}"
          f"   现金: {1 - sum(result['final_weights'].values()):.1%}")
    print(f"  NAV: ¥{result['nav']:,.0f}   订单数: {len(result['orders'])}")
    print("\n" + "=" * 76)


if __name__ == "__main__":
    main()
