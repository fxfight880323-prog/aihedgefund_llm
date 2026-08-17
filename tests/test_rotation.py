"""有锐度的均衡 · 轮动策略测试 — run: pytest tests/test_rotation.py

覆盖：L1 分类器、L2 环节匹配与 S 分、G5 泡沫惩罚、L5 regime 缩放、
L4 构造器（方向单调权重/类配比/单票上限/off-theme sleeve/轮出）、
blend registry 接线、端到端 mini cycle。全部离线（MockRotationClient）。
"""

from __future__ import annotations

from datetime import date, timedelta

from examples.rotation_demo import MockRotationClient, AS_OF
from src.core.models import Signal
from src.portfolio.balanced_sharpness import BalancedSharpnessBlend
from src.signals.rotation_growth import RotationGrowthModel

CLIENT = MockRotationClient()


def _predict(ticker):
    return RotationGrowthModel().predict(ticker, AS_OF, CLIENT)


# ===========================================================================
# L1 分类器
# ===========================================================================

class TestClassifier:

    def test_boom_class_a(self):
        sig = _predict("688308.SH")
        assert sig.metadata["asset_class"] == "A"   # 高增加速
        assert sig.value > 0.5

    def test_emerging_class_c(self):
        sig = _predict("688802.SH")
        assert sig.metadata["asset_class"] == "C"   # 极端增长 + 毛利率弱
        assert 0 < sig.value <= 0.30                # C 类小仓位

    def test_cyclical_class_b(self):
        sig = _predict("688012.SH")
        assert sig.metadata["asset_class"] == "B"   # 毛利率低位回升
        assert sig.value > 0

    def test_structural_quality_goes_off_theme_not_b(self):
        # 65% 稳定毛利 = 结构性优质（OFF），不该按周期 B 类处理
        sig = _predict("688271.SH")
        assert sig.metadata["asset_class"] == "OFF"
        assert sig.metadata["link"] is None

    def test_not_investable_abstains(self):
        sig = _predict("688009.SH")
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True


# ===========================================================================
# L2 环节稀缺度
# ===========================================================================

class TestLinkScoring:

    def test_optical_module_top_link(self):
        sig = _predict("688308.SH")
        assert sig.metadata["link"] == "光模块/光通信"
        assert sig.metadata["link_score"] == 9
        assert set(sig.metadata["s_scores"]) == {
            "S1_supply_rigidity", "S2_demand_lockin", "S3_value_share",
            "S4_price_stage", "S5_passthrough"}

    def test_scoring_ranks_optical_above_storage(self):
        # spec 2026 快照: network > storage
        opt = _predict("688308.SH").metadata["link_score"]
        sto = _predict("688525.SH").metadata["link_score"]
        assert opt > sto

    def test_generic_equipment_keyword_not_matched(self):
        # "医学影像设备" 不应命中半导体设备环节（无裸"设备"关键词）
        sig = _predict("688271.SH")
        assert sig.metadata["link"] != "半导体设备"

    def test_custom_link_map_override(self):
        model = RotationGrowthModel(link_map={
            "自定义环节": {"s_scores": [2, 2, 2, 2, 2],
                          "keywords": ["医学影像"]}})
        sig = model.predict("688271.SH", AS_OF, CLIENT)
        assert sig.metadata["link"] == "自定义环节"
        assert sig.metadata["link_score"] == 10


# ===========================================================================
# L3-G5 泡沫检验 与 L5 regime
# ===========================================================================

class TestG5AndRegime:

    def test_pe_dominant_rally_halves_conviction(self):
        # PE 序列年涨幅大（pe+i*2 → 两年翻倍 = ΔPE≈+100%）且净利增速
        # 慢 → G5 触发，信念减半
        base = _predict("688308.SH").value
        model = RotationGrowthModel(g5_pe_dominance=0.10)  # 更低门槛
        sig = model.predict("688308.SH", AS_OF, CLIENT)
        g5 = sig.metadata["g5"]
        if g5.get("pe_dominant"):
            assert sig.components["g5_penalty"] == 0.5
            assert sig.value < base + 0.35  # 相对全值有折让
        else:
            assert sig.components["g5_penalty"] == 1.0

    def test_bearish_dashboard_halves_class_a(self):
        neutral = _predict("688308.SH").value
        bearish = RotationGrowthModel(ai_dashboard={
            "frontier_models": "bearish", "frontier_arr": "bearish",
        }).predict("688308.SH", AS_OF, CLIENT)
        assert bearish.metadata["regime"] == "de-risk"
        assert abs(bearish.value - neutral * 0.5) < 0.01

    def test_single_bearish_indicator_not_enough(self):
        sig = RotationGrowthModel(ai_dashboard={
            "frontier_models": "bearish"}).predict("688308.SH", AS_OF, CLIENT)
        assert sig.metadata["regime"] == "neutral"


# ===========================================================================
# L4 构造器
# ===========================================================================

def _sig(ticker, value, cls="A", link=None, link_score=None):
    return Signal(model_name="rotation_growth", ticker=ticker,
                  date=AS_OF, value=value,
                  metadata={"asset_class": cls, "link": link,
                            "link_score": link_score})


class TestBalancedSharpnessBlend:

    def _blend(self, signals, **kw):
        return BalancedSharpnessBlend(**kw).blend(
            signals, {"rotation_growth": 1.0}, gross_target=0.90)

    def test_direction_weights_monotonic_in_score(self):
        # 单成员方向 + 放开单票上限 → 方向权重本身的单调性可见
        res = self._blend([
            _sig("HI", 0.9, link="高分环节", link_score=9),
            _sig("MID", 0.9, link="中分环节", link_score=6),
            _sig("LO", 0.9, link="低分环节", link_score=3),
        ], per_name_cap=0.20)
        assert res.weights["HI"] > res.weights["MID"] > res.weights["LO"]

    def test_top_direction_weight_cap(self):
        res = self._blend([_sig("HI", 0.9, link="高分环节", link_score=9)])
        assert res.weights["HI"] <= 0.16 + 1e-9

    def test_per_name_cap(self):
        # 单一方向单一名字：方向权重 16% → 单票上限 5% 接管
        res = self._blend([_sig("SOLO", 0.9, link="环节", link_score=9)])
        assert res.weights["SOLO"] <= 0.05 + 1e-9

    def test_class_mix_caps(self):
        res = self._blend(
            [_sig(f"A{i}", 0.9, link="环节X", link_score=9) for i in range(3)]
            + [_sig(f"B{i}", 0.9, cls="B", link="环节X", link_score=8)
               for i in range(3)],
            top_direction_weight=0.40, per_name_cap=0.30,
        )
        a_gross = sum(w for t, w in res.weights.items() if t.startswith("A"))
        b_gross = sum(w for t, w in res.weights.items() if t.startswith("B"))
        assert a_gross <= 0.55 + 1e-9
        assert b_gross <= 0.30 + 1e-9

    def test_c_class_hard_capped(self):
        res = self._blend(
            [_sig(f"C{i}", 0.3, cls="C", link="环节", link_score=8)
             for i in range(4)],
            per_name_cap=0.05,
        )
        c_gross = sum(res.weights.values())
        assert c_gross <= 0.05 + 1e-9   # C 类配比 5%

    def test_negative_conviction_rotates_out(self):
        res = self._blend([
            _sig("KEEP", 0.8, link="环节", link_score=8),
            _sig("TRIM", -0.5, cls="B", link="环节", link_score=8),
        ])
        assert res.weights["TRIM"] == 0.0
        assert res.convictions["TRIM"] == -0.5   # 审计痕迹保留

    def test_off_theme_sleeve(self):
        res = self._blend([
            _sig("THEME", 0.9, link="环节", link_score=9),
            _sig("OFF1", 0.5, cls="OFF", link=None),
            _sig("OFF2", 0.3, cls="OFF", link=None),
        ], per_name_cap=0.05, off_theme_sleeve=0.10)
        off = res.weights["OFF1"] + res.weights["OFF2"]
        assert 0 < off <= 0.10 + 1e-9

    def test_abstained_excluded(self):
        s = _sig("ABS", 0.9)
        s.metadata["abstained"] = True
        res = self._blend([s])
        assert res.weights.get("ABS", 0.0) == 0.0


# ===========================================================================
# Registry 接线 + 端到端
# ===========================================================================

class TestWiring:

    def test_blend_registry_contains(self):
        import src.signals  # noqa: F401
        import src.portfolio  # noqa: F401
        from src.core.registry import BLEND_POLICY_REGISTRY, ALPHA_MODEL_REGISTRY
        assert "balanced_sharpness" in BLEND_POLICY_REGISTRY
        assert "conviction_weighted" in BLEND_POLICY_REGISTRY
        assert "rotation_growth" in ALPHA_MODEL_REGISTRY

    def test_yaml_loads_new_blend(self):
        from src.core.fund_spec import load_fund, load_strategy
        spec = load_fund("config/funds/rotation_demo.yaml")
        assert spec.strategies[0].blend.method == "balanced_sharpness"
        strat = load_strategy("config/strategies/rotation_growth.yaml")
        assert strat.blend.params["per_name_cap"] == 0.05

    def test_unknown_blend_method_rejected(self):
        from src.core.fund_spec import BlendPolicySpec
        try:
            BlendPolicySpec(method="nonexistent_policy")
            raise SystemError("should have raised")
        except ValueError as e:
            assert "Unknown blend policy" in str(e)
