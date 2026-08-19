"""Serenity 卡点审查门测试：情景性利润 kill / 结构性卡点 pass /
growth_loop 子图接线 / 无 LLM 回退模式。"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.signals.serenity_gate import (
    serenity_review, SerenityGateModel, KILL_THRESHOLD, PASS_THRESHOLD,
)


class GateMockClient:
    """构造可控的财报/价格数据。"""

    def __init__(self, gm_path, yoy_level=0.5, price_path="flat"):
        # gm_path: 旧→新的毛利率序列（newest-first 转换在 gate 内）
        self.gm_old_first = gm_path
        self.yoy_level = yoy_level
        self.price_path = price_path

    def get_financial_metrics(self, ticker, end_date, period="ttm",
                              limit=60):
        rows = []
        # 8 个季度（2023Q4 → 2025Q3），YoY 恒定 → 无加速干扰
        quarters = [(2023, 4), (2024, 1), (2024, 2), (2024, 3),
                    (2024, 4), (2025, 1), (2025, 2), (2025, 3)]
        base = 100.0
        for (y, q), gm in zip(quarters, self.gm_old_first):
            prev_year = base / (1 + self.yoy_level)
            rows.append({
                "ticker": ticker,
                "date": f"{y}-{q * 3:02d}-28",
                "revenue": base if q == 1 else base * q / 3,
                "gross_margin": gm,
                "roe": 15.0,
            })
            base *= 1 + self.yoy_level * 0.25
        return rows

    def get_prices(self, ticker, start, end):
        # 简单月频：flat=无涨幅；hot=低点至今 +150%
        n = 24
        if self.price_path == "hot":
            px = [100 * (1 + 1.5 * i / (n - 1)) for i in range(n)]
        elif self.price_path == "dip":
            px = [100 - 60 * i / (n - 1) for i in range(n)]
        else:
            px = [100.0] * n
        return [{"time": f"2024-{m:02d}-15" if m >= 1 else "",
                 "close": px[i]}
                for i, m in enumerate(
                    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] * 2) if px[i]]


class TestSerenityReview:
    def test_structural_chokepoint_passes(self):
        """毛利率持续高企（45-52 区间抬升）+ 高增长 → PASS。"""
        gm = [45.0, 46.5, 48.0, 49.0, 50.0, 51.0, 51.5, 52.0]  # 旧→新
        r = serenity_review("X.SH", "2025-09-30",
                            GateMockClient(gm, yoy_level=0.5,
                                           price_path="flat"))
        assert r["verdict"] == "PASS", r
        assert r["score"] >= PASS_THRESHOLD
        assert r["gm_floor"] >= 45.0          # 持续性 = 一直高

    def test_episodic_margin_kills(self):
        """IVD 型陷阱：毛利率 25 → 70 冲顶（一次性利润）→ KILL。"""
        gm = [25.0, 26.0, 27.0, 45.0, 62.0, 68.0, 70.0, 71.0]
        r = serenity_review("X.SH", "2025-09-30",
                            GateMockClient(gm, yoy_level=1.2,
                                           price_path="hot"))
        assert r["verdict"] == "KILL", r
        assert "情景性" in r["reason"] or r["score"] < KILL_THRESHOLD

    def test_hype_penalty_lowers_score(self):
        """同样结构良好的公司，1 年 +150% 涨幅要被罚。"""
        gm = [45.0, 46.5, 48.0, 49.0, 50.0, 51.0, 51.5, 52.0]
        calm = serenity_review("X.SH", "2025-09-30",
                               GateMockClient(gm, price_path="flat"))
        hot = serenity_review("X.SH", "2025-09-30",
                              GateMockClient(gm, price_path="hot"))
        assert hot["score"] < calm["score"]
        assert hot["penalties"]["hype_risk"] > calm["penalties"]["hype_risk"]

    def test_deep_drawdown_intact_fundamentals_rewards(self):
        """深回撤 + 基本面未坏 → 估值断层加分。"""
        gm = [40.0, 41.0, 42.0, 42.0, 43.0, 43.0, 44.0, 44.0]
        dip = serenity_review("X.SH", "2025-09-30",
                              GateMockClient(gm, price_path="dip"))
        assert dip["factors"]["valuation_disconnect"] >= 3

    def test_review_fail_open_on_bad_client(self):
        class Bad:
            def get_financial_metrics(self, *a, **k):
                raise RuntimeError("boom")

            def get_prices(self, *a, **k):
                raise RuntimeError("boom")

        r = serenity_review("X.SH", "2025-09-30", Bad())
        assert r["verdict"] in ("KILL", "DOWNGRADE", "PASS")  # 不抛异常


class TestSerenityGateModel:
    def test_kill_abstains(self):
        gm = [25.0, 26.0, 27.0, 45.0, 62.0, 68.0, 70.0, 71.0]
        m = SerenityGateModel()
        sig = m.predict("X.SH", "2025-09-30",
                        GateMockClient(gm, yoy_level=1.2,
                                       price_path="hot"))
        assert sig.value == 0.0
        assert sig.metadata["status"] == "KILLED"

    def test_pass_signal_value(self):
        gm = [45.0, 46.5, 48.0, 49.0, 50.0, 51.0, 51.5, 52.0]
        m = SerenityGateModel()
        sig = m.predict("X.SH", "2025-09-30",
                        GateMockClient(gm, yoy_level=0.5))
        assert sig.value > 0
        assert 0 < sig.value <= 1.0


class TestGraphWiring:
    """growth_loop 子图：hook → serenity_gate → L1/l8/kill。"""

    def _client_with_hook(self):
        """触发 H2（毛利率环比上行 + 增速>20%）的 mock 数据。"""
        return GateMockClient(
            [40.0, 41.0, 42.0, 42.5, 43.0, 44.0, 45.0, 46.0],
            yoy_level=0.5, price_path="flat")

    def test_serenity_kill_path(self):
        """hook 触发但卡点证据不足 → KILLED @ SERENITY。"""
        from src.workflow.growth_loop_graph import build_growth_loop_graph
        g = build_growth_loop_graph()
        state = {
            "ticker": "X.SH", "date": "2025-09-30",
            "mandate": {"target_return": 0.15},
            "hook_evidence": {"tripped": [
                {"id": "H2", "name": "Margin Inflection",
                 "evidence": "gm up while yoy 120%"}]},
            "metadata": {
                "data_client": GateMockClient(
                    # IVD 型：低基数毛利率冲顶（25→71）+ 热度涨幅
                    [25.0, 26.0, 27.0, 45.0, 62.0, 68.0, 70.0, 71.0],
                    yoy_level=1.2, price_path="hot"),
                "llm_client": object(),
                "max_loop_backs": 2,
            },
        }
        out = g.invoke(state)
        assert out.get("status") == "KILLED"
        assert out["kill_stage"] == "SERENITY"
        assert "情景性" in out["kill_reason"]

    def test_no_llm_fallback_conviction(self):
        """无 llm_client → serenity 直达 L8，产出回退信念。"""
        from src.workflow.growth_loop_graph import (
            build_growth_loop_graph, l8_conviction_node,
        )
        g = build_growth_loop_graph()
        state = {
            "ticker": "X.SH", "date": "2025-09-30",
            "mandate": {},
            "hook_evidence": {"tripped": [
                {"id": "H2", "name": "m", "evidence": "e"}]},
            "metadata": {
                "data_client": self._client_with_hook(),
                "llm_client": None,          # 回退模式
                "max_loop_backs": 2,
            },
        }
        out = g.invoke(state)
        assert out.get("status") == "PASSED"
        assert 0 < out["conviction"] <= 100
        assert "serenity fallback" in out["thesis"]
        assert any("z-score" in r or "serenity" in r.lower()
                   for r in out["exit_rules"])

    def test_l8_fallback_downgrade_multiplier(self):
        from src.workflow.growth_loop_graph import l8_conviction_node
        base = {
            "stage_scores": {},
            "hook_evidence": {"tripped": [{"id": "H1"}]},
        }
        passed = dict(base, serenity_review={"score": 70.0,
                                             "verdict": "PASS"})
        down = dict(base, serenity_review={"score": 70.0,
                                           "verdict": "DOWNGRADE"})
        c1 = l8_conviction_node(passed)["conviction"]
        c2 = l8_conviction_node(down)["conviction"]
        assert abs(c2 - c1 * 0.7) < 0.01
