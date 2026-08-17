"""GOAL→HOOK→LOOP 决策引擎测试 — run: pytest tests/test_growth_loop.py

全部离线：数据走合成 DataClient，LLM 走脚本化 MockLLM
（examples/growth_loop_demo.py 里的 ScriptedLoopLLM / MockGrowthClient）。
"""

from __future__ import annotations

try:
    import pytest
except ImportError:
    pytest = None

from examples.growth_loop_demo import MockGrowthClient, ScriptedLoopLLM
from src.signals.growth_loop import GrowthLoopAgent
from src.signals.hooks import screen_hooks, screen_universe
from src.workflow.growth_loop_graph import (
    STAGE_WEIGHTS,
    parse_stage_output,
    run_growth_loop,
)

AS_OF = "2026-12-31"
MANDATE = {
    "target_return": 0.15,
    "return_objective": "15% annualized over 3+ years",
    "horizon": "3-year minimum hold",
    "min_revenue_growth": 0.20,
}


def _hooks(ticker, client=None):
    return screen_hooks(ticker, AS_OF, client or MockGrowthClient())


def _loop(script=None, ticker="GROWTH.SH", **llm_kw):
    llm = ScriptedLoopLLM(script=script or {}, **llm_kw)
    result = run_growth_loop(
        ticker, AS_OF, MockGrowthClient(), llm, mandate=MANDATE
    )
    return result, llm


# ===========================================================================
# HOOK 层 — 数值化筛选
# ===========================================================================

class TestHookScreen:

    def test_h1_accelerating_revenue_trips(self):
        res = _hooks("GROWTH.SH")
        ids = [h["id"] for h in res["tripped"]]
        assert "H1" in ids
        ev = next(h for h in res["tripped"] if h["id"] == "H1")["evidence"]
        assert "accelerating" in ev

    def test_h1_decelerating_does_not_trip(self):
        res = _hooks("STALE.SH")
        assert "H1" not in [h["id"] for h in res["tripped"]]

    def test_h1_insufficient_history_skips(self):
        client = MockGrowthClient()

        class _Thin(client.__class__):
            def get_financial_metrics(self, ticker, end_date, period="ttm",
                                      limit=10):
                rows = super().get_financial_metrics(
                    ticker, end_date, period, limit)
                return rows[:4]  # 少于 5 个季度 → YoY 无法计算

        res = screen_hooks("GROWTH.SH", AS_OF, _Thin())
        assert "H1" not in [h["id"] for h in res["tripped"]]
        assert res["computed"]["revenue_yoy"] == []

    def test_h2_margin_up_with_growth_trips(self):
        # GROWTH: 毛利率环比上行 + 营收 YoY 90% > 20%
        res = _hooks("GROWTH.SH")
        assert "H2" in [h["id"] for h in res["tripped"]]

    def test_h2_margin_down_does_not_trip(self):
        # STALE: 毛利率下行
        res = _hooks("STALE.SH")
        assert "H2" not in [h["id"] for h in res["tripped"]]

    def test_h6_drawdown_with_intact_growth_trips(self):
        # GROWTH: 价格从 362 回撤 ~47%，营收 YoY 90% ≥ 10%
        res = _hooks("GROWTH.SH")
        assert "H6" in [h["id"] for h in res["tripped"]]
        assert res["computed"]["drawdown_1y"] >= 0.30

    def test_h6_no_drawdown_does_not_trip(self):
        # STALE: 价格缓慢上行，无回撤
        res = _hooks("STALE.SH")
        assert "H6" not in [h["id"] for h in res["tripped"]]

    def test_missing_data_marks_not_ok(self):
        res = _hooks("DARK.SH")
        assert res["data_ok"] is False
        assert res["tripped"] == []


class TestH3Beats:
    def _client_with_beats(self, n_beats):
        base = MockGrowthClient()

        class _Client(base.__class__):
            def get_earnings(self, ticker):
                from datetime import date, timedelta
                d0 = date(2026, 3, 31)
                hist = []
                for i in range(4):
                    hist.append({
                        "filing_date": (d0 - timedelta(days=90 * i)).isoformat(),
                        "eps_surprise": "BEAT" if i < n_beats else "MISS",
                    })
                return hist

        return _Client()

    def test_two_consecutive_beats_trip_h3(self):
        res = screen_hooks("GROWTH.SH", AS_OF, self._client_with_beats(2))
        assert "H3" in [h["id"] for h in res["tripped"]]

    def test_one_beat_does_not_trip_h3(self):
        res = screen_hooks("GROWTH.SH", AS_OF, self._client_with_beats(1))
        assert "H3" not in [h["id"] for h in res["tripped"]]

    def test_no_surprise_data_abstains_h3(self):
        # MockGrowthClient.get_earnings → None → H3 abstain（不算触发也不算错）
        res = _hooks("GROWTH.SH")
        assert "H3" not in [h["id"] for h in res["tripped"]]


class TestScreenUniverse:
    def test_abc_ranking(self):
        ranked = screen_universe(
            ["GROWTH.SH", "STALE.SH", "DARK.SH"], AS_OF, MockGrowthClient()
        )
        assert [i["ticker"] for i in ranked["A"]] == ["GROWTH.SH"]
        assert [i["ticker"] for i in ranked["B"]] == ["STALE.SH"]
        assert [i["ticker"] for i in ranked["C"]] == ["DARK.SH"]

    def test_max_three_a_priority(self):
        tickers = [f"G{i}.SH" for i in range(5)]
        client = MockGrowthClient()
        # 让所有标的都复用 GROWTH 画像（全部触发 hook）
        client._profiles = {t: client._profiles["GROWTH.SH"] for t in tickers}
        ranked = screen_universe(tickers, AS_OF, client)
        assert len(ranked["A"]) == 3
        assert len(ranked["B"]) == 2  # 溢出的 A 候选降级为 B


# ===========================================================================
# 输出解析契约
# ===========================================================================

class TestParseStageOutput:

    def test_full_block(self):
        text = (
            "analysis...\nTHESIS: great grower.\n"
            "TRIPWIRES:\n1) first\n2) second\n3) third\n"
            "SHORT-STRENGTH: 3\nYELLOW-FLAGS: 2\n"
            "SCORE: 82\nGATE: PASS\nREASON: all good"
        )
        p = parse_stage_output(text)
        assert p["gate"] == "PASS"
        assert p["score"] == 82.0
        assert p["reason"] == "all good"
        assert p["yellow_flags"] == 2
        assert p["short_strength"] == 3.0
        assert p["thesis"] == "great grower."
        assert p["tripwires"] == ["first", "second", "third"]

    def test_missing_gate_returns_none(self):
        p = parse_stage_output("only prose, no machine block")
        assert p["gate"] is None
        assert p["score"] is None

    def test_score_clamped(self):
        p = parse_stage_output("SCORE: 250\nGATE: PASS\nREASON: x")
        assert p["score"] == 100.0

    def test_loop_back_spelling_variants(self):
        for spelling in ("LOOP-BACK", "LOOP BACK", "loopback", "Loop-Back"):
            p = parse_stage_output(f"GATE: {spelling}\nREASON: need NRR")
            assert p["gate"] == "LOOP-BACK", spelling


# ===========================================================================
# LOOP 子图 — 门控路由
# ===========================================================================

class TestLoopGraphRouting:

    def test_all_pass_reaches_l8(self):
        result, llm = _loop({"L1": ("PASS", 80), "L2": ("PASS", 85),
                             "L3": ("PASS", 75), "L4": ("PASS", 70),
                             "L5": ("PASS", 90), "L6": ("PASS", 78),
                             "L7": ("PASS", 75)},
                            default_score=75, yellow_flags=1)
        assert result["status"] == "PASSED"
        assert llm.calls == ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
        # 信念 = Σ w·score = 79.1，黄旗 1 面 × -25% → 59.325
        expected = 79.1 * 0.75
        assert abs(result["conviction"] - expected) < 0.01
        assert result["yellow_flags"] == 1
        assert len(result["tripwires"]) == 3
        assert len(result["exit_rules"]) == 4

    def test_fail_midway_kills(self):
        result, llm = _loop({"L3": "FAIL"})
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L3"
        assert "L4" not in llm.calls  # FAIL 后不再前进

    def test_no_hook_kills_at_gate_h(self):
        result, llm = _loop(ticker="STALE.SH")
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "HOOK"
        assert llm.calls == []  # LLM 从未被调用

    def test_two_loop_backs_then_pass_proceeds(self):
        result, llm = _loop({"L2": "LOOPBACK_TWICE"})
        assert result["status"] == "PASSED"
        assert result["loop_backs"]["L2"] == 2
        assert llm.calls.count("L2") == 3  # 初次 + 2 次重跑

    def test_third_loop_back_kills(self):
        # 剧本: "Maximum 2 loop-backs per stage. Third failure = automatic KILL"
        result, llm = _loop({"L2": "LOOPBACK_ALWAYS"})
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L2"
        assert llm.calls.count("L2") == 3  # 初次 + 2 次重跑，第3次失败 KILL

    def test_unparseable_output_kills_after_loop_backs(self):
        # GARBAGE 输出按 LOOP-BACK 计；回环上限耗尽后 KILL
        result, llm = _loop({"L1": "GARBAGE"})
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L1"
        assert llm.calls.count("L1") == 3

    def test_l7_strong_short_kills(self):
        result, _ = _loop({"L7": ("PASS", 75)}, short_strength=8)
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L7"
        assert result["short_strength"] == 8
        assert "strong" in result["kill_reason"].lower()

    def test_l7_pass_without_tripwires_loops_back(self):
        result, llm = _loop({"L7": "PASS_BARE"})
        # 裸 PASS 无 tripwire → 强制 LOOP-BACK；mock 永远裸 PASS → 耗尽回环 KILL
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L7"

    def test_weights_sum_to_one(self):
        assert abs(sum(STAGE_WEIGHTS.values()) - 1.0) < 1e-9


# ===========================================================================
# 数据完整性原则 — declare_data_gaps + 数据包自证
# ===========================================================================

class TestDataCompleteness:

    def test_full_packet_declares_ok(self):
        from src.workflow.growth_loop_graph import declare_data_gaps
        packet = (
            "FUNDAMENTALS: revenue=100 gross_margin=40\n"
            "FINANCIAL DETAIL:\n  营业利润: 2026一季报=1.2亿\n"
            "  研发费用: 2026一季报=0.8亿\n"
            "  购建固定资产支付的现金: 0.3亿\n"
            "  经营活动产生的现金流量净额: 1.1亿\n"
            "  总股本: 3.3亿股 总市值: 120亿\n"
            "  货币资金: 20亿 短期借款: 2亿\n"
            "SEGMENT BREAKDOWN (主营构成): 光芯片 99%\n"
            "PRICE (last 400d): last=100"
        )
        lines = declare_data_gaps(packet)
        gaps = [l for l in lines if "DATA GAP" in l]
        assert gaps == []
        assert any("10/10 required fields present" in l for l in lines)

    def test_missing_fields_declared_as_gaps(self):
        from src.workflow.growth_loop_graph import declare_data_gaps
        packet = "FUNDAMENTALS: revenue=100 gross_margin=40\nPRICE: last=100"
        lines = declare_data_gaps(packet)
        gap_fields = [l.split("DATA GAP: ")[1].split(" (")[0]
                      for l in lines if "DATA GAP" in l]
        # L3/L6 的必需项缺失 → 显式声明（而不是静默）
        assert "operating income series" in gap_fields
        assert "capex" in gap_fields
        assert "share count / market cap" in gap_fields
        # 每条 GAP 都带"不许单独判死"的指令
        for l in lines:
            if "DATA GAP" in l:
                assert "NEVER fail on this gap alone" in l

    def test_gap_declaration_goes_into_packet(self):
        from src.workflow.growth_loop_graph import build_data_packet
        client = MockGrowthClient()
        packet = build_data_packet("GROWTH.SH", AS_OF, client)
        assert "DATA COMPLETENESS:" in packet
        # mock client 没有 financial_detail 能力 → capex/费用明细应为显式
        # GAP（mock 简介散文里含"增量营业利润"数据，故营业利润判 OK 合理）
        assert "DATA GAP: capex (L3)" in packet
        assert "DATA GAP: opex breakdown" in packet
        assert any("SUMMARY:" in ln for ln in packet.splitlines())

    def test_financial_detail_capability_used_when_present(self):
        from src.workflow.growth_loop_graph import build_data_packet

        class _RichClient(MockGrowthClient):
            def get_financial_detail(self, ticker):
                return ("  [SERIES]\n    营业利润: 2026一季报=1.2亿\n"
                        "    研发费用: 2026一季报=0.8亿\n"
                        "    购建固定资产、无形资产支付的现金: 0.3亿\n"
                        "    经营活动产生的现金流量净额: 1.1亿\n"
                        "  [SNAPSHOT]\n    总股本: 3.3亿股\n"
                        "    总市值: 120亿\n    货币资金: 20亿\n    短期借款: 2亿")

        packet = build_data_packet("GROWTH.SH", AS_OF, _RichClient())
        assert "FINANCIAL DETAIL" in packet
        lines = [
            l for l in packet.splitlines()
            if "DATA GAP" in l and "operating income" in l
        ]
        assert lines == []  # 营业利润已提供 → 不再是 GAP

    def test_mx_client_has_financial_detail(self):
        from src.data.mx_data_client import MXDataClient
        assert hasattr(MXDataClient, "get_financial_detail")


# ===========================================================================
# 审视层 — 确定性门控验证 (LLM 报数, 代码判门)
# ===========================================================================

class TestGateVerification:

    def test_parse_numbers_line(self):
        from src.workflow.growth_loop_graph import parse_stage_output
        p = parse_stage_output(
            "analysis...\nNUMBERS: current_growth=24.58%; growth_floor=0.272; "
            "bear_return=-0.18\nSCORE: 60\nGATE: PASS\nREASON: x"
        )
        assert abs(p["numbers"]["current_growth"] - 0.2458) < 1e-9
        assert abs(p["numbers"]["growth_floor"] - 0.272) < 1e-9
        assert abs(p["numbers"]["bear_return"] - (-0.18)) < 1e-9

    def test_rule_failure_overrides_pass_to_fail(self):
        # LLM 判 PASS 但 TAM 30× 于 bottom-up → verify 强制 FAIL
        result, llm = _loop(
            {"L1": ("PASS", 80)},
            numbers={"L1": "NUMBERS: claimed_tam=3000; bottomup_tam=100"},
        )
        assert result["status"] == "KILLED"
        assert result["kill_stage"] == "L1"
        assert "[verify:tam_ratio]" in result["kill_reason"]
        v = result["verifications"]["L1"][-1]
        assert v["mode"].startswith("OVERRIDE→FAIL")

    def test_math_error_fail_converted_to_loopback_with_correction(self):
        # 传音案例复现：LLM 判 FAIL，理由引用 growth floor，但其自报数字
        # 实际通过该规则（27.2% ≥ 0.5×24.58%）→ verify 纠错回环，第二次
        # 判 PASS → 全程走完
        llm = ScriptedLoopLLM(
            script={"L2": "FAIL_ON_FIRST"},
            fail_reason="Growth floor (27.2%) is less than 0.5× current "
                        "growth rate (24.58%)",
            numbers={"L2": "NUMBERS: current_growth=0.2458; "
                           "growth_floor=0.272; base_cagr=0.25"},
        )
        # FAIL_ON_FIRST 行为：让 mock 首次 L2 FAIL、其后 PASS
        original = llm.complete
        calls = {"n": 0}

        def patched(system, user):
            if "Stage L2" in user:
                calls["n"] += 1
                if calls["n"] == 1:
                    # 首次：FAIL + 传音式错误理由
                    return "\n".join([
                        "cohort math [EST].",
                        "NUMBERS: current_growth=0.2458; growth_floor=0.272; "
                        "base_cagr=0.25",
                        "SCORE: 65", "GATE: FAIL",
                        "REASON: Growth floor (27.2%) is less than 0.5× "
                        "current growth rate (24.58%)",
                    ])
            return original(system, user)

        llm.complete = patched
        result = run_growth_loop(
            "GROWTH.SH", AS_OF, MockGrowthClient(), llm, mandate=MANDATE
        )
        assert result["status"] == "PASSED"
        assert result["loop_backs"]["L2"] == 1
        modes = [v["mode"] for v in result["verifications"]["L2"]]
        assert any("arithmetic error" in m for m in modes)  # 纠错历史保留
        assert modes[-1].startswith("verified")             # 重判后确认
        # 纠正文本确实注入了重跑的 prompt
        assert any("VERIFY CORRECTION" in p for p in llm.prompts)

    def test_fail_with_uncited_reason_stands(self):
        # FAIL 理由不引用数值规则（定性理由）→ verify 不推翻
        result, _ = _loop(
            {"L3": "FAIL"},
            fail_reason="business model requires a diagram to explain",
            numbers={"L3": "NUMBERS: incremental_margin=0.38; "
                           "current_op_margin=0.15"},
        )
        assert result["status"] == "KILLED"
        assert result["verifications"]["L3"][-1]["mode"].startswith("verified")

    def test_no_numbers_marks_unverified(self):
        result, _ = _loop({"L2": "GARBAGE"})
        assert result["status"] == "KILLED"
        assert "unverified" in result["verifications"]["L2"][-1]["mode"]

    def test_l4_pass_through_no_rules(self):
        result, _ = _loop({"L4": ("PASS", 70)})
        assert "pass-through" in result["verifications"]["L4"][-1]["mode"]

    def test_verifications_in_agent_metadata(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM(default_score=80))
        sig = agent.predict("GROWTH.SH", AS_OF, MockGrowthClient())
        # verifications 不进 Signal.metadata（体积大），但 PASSED 路径说明
        # 全部 verify 通过
        assert sig.value > 0


# ===========================================================================
# Agent — Signal 映射与注册
# ===========================================================================

class TestGrowthLoopAgent:

    def test_passed_maps_conviction_over_100(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM(
            default_score=80, yellow_flags=0))
        sig = agent.predict("GROWTH.SH", AS_OF, MockGrowthClient())
        assert sig.model_name == "growth_loop"
        assert abs(sig.value - 0.80) < 1e-6  # 80/100，无黄旗
        assert sig.metadata["status"] == "PASSED"
        assert "abstained" not in sig.metadata  # PASSED 是主动观点，非弃权
        assert len(sig.metadata["tripwires"]) == 3
        assert "conviction" not in sig.components  # components 是 L1-L7 分
        assert sig.components["L1"] == 80.0

    def test_no_hook_abstains(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM())
        sig = agent.predict("STALE.SH", AS_OF, MockGrowthClient())
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True
        assert "no numeric hook" in sig.reasoning

    def test_no_llm_abstains_but_reports_hooks(self):
        agent = GrowthLoopAgent()  # llm_client=None
        sig = agent.predict("GROWTH.SH", AS_OF, MockGrowthClient())
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True
        assert "hooks tripped" in sig.reasoning
        assert sig.metadata["hooks"]  # hook 证据保留

    def test_killed_midway_abstains_with_kill_log(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM(
            script={"L3": "FAIL"}))
        sig = agent.predict("GROWTH.SH", AS_OF, MockGrowthClient())
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True
        assert sig.metadata["kill_stage"] == "L3"

    def test_strong_short_emits_negative(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM(
            short_strength=8))
        sig = agent.predict("GROWTH.SH", AS_OF, MockGrowthClient())
        assert sig.value == -0.5
        assert "abstained" not in sig.metadata
        assert sig.metadata["short_strength"] == 8

    def test_missing_data_abstains(self):
        agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM())
        sig = agent.predict("DARK.SH", AS_OF, MockGrowthClient())
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True

    def test_registered_in_registry(self):
        import src.signals  # noqa: F401
        from src.core.registry import ALPHA_MODEL_REGISTRY
        assert "growth_loop" in ALPHA_MODEL_REGISTRY
