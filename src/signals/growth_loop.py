"""GrowthLoopAgent — GOAL→HOOK→LOOP 决策引擎的注册表适配器。

把剧本的三层结构接到框架的 AlphaModel 契约上：

    GOAL  → 构造参数（YAML `params:` 传入：目标收益、期限、最低增速…）
    HOOK  → src/signals/hooks.py 的数值化筛选（无 hook → 无资格深研）
    LOOP  → src/workflow/growth_loop_graph.py 的 LangGraph 门控子图
            （L1-L7 LLM 阶段 + L8 确定性信念）

Signal 映射（conviction → [-1,+1]）：

    status=KILLED @HOOK     → 0.0 abstain（无 hook，未进入深研）
    status=KILLED @L1-L7    → 0.0 abstain（kill 日志进 metadata；
                              剧本语义是"不买"，不是做空）
    L7 强空头 ≥7/10 被 KILL → strong_short_value（默认 -0.5）——强基本面
                              空头可喂 market-neutral 策略的做空端
    status=PASSED           → conviction / 100 ∈ [0, 1]（多头信念）

L8 的分批建仓/仓位不在 agent 内实现——框架的 blend + risk 负责 sizing
（"conviction requests, risk disposes"）。4 条预承诺退出规则与 L7
tripwires 进 metadata 留审计痕迹；rebalance 周期重跑 predict() 即
剧本 L9 的季度审计形态。

用法（strategy YAML）：

    models:
      - name: growth_loop
        weight: 1.0
        params:
          target_return: 0.15
          horizon_years: 3
          min_revenue_growth: 0.20
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import LLMAgent
from src.core.models import Signal
from src.signals.hooks import DEFAULT_HOOKS, screen_hooks
from src.workflow.growth_loop_graph import run_growth_loop


class GrowthLoopAgent(LLMAgent):
    """GOAL→HOOK→LOOP 成长股决策引擎的 alpha model 适配器。"""

    def __init__(
        self,
        target_return: float = 0.15,
        horizon_years: int = 3,
        min_revenue_growth: float = 0.20,
        max_loop_backs: int = 2,
        strong_short_value: float = -0.5,
        universe_note: str = "",
        hooks: list[str] | tuple[str, ...] | None = None,
        llm_client: Any = None,
        **kwargs,
    ):
        super().__init__(llm_client=llm_client, **kwargs)
        self._mandate = {
            "target_return": target_return,
            "return_objective": f"{target_return:.0%} annualized over "
                                f"{horizon_years}+ years, absolute return",
            "horizon": f"{horizon_years}-year minimum hold intent; "
                       f"re-underwrite quarterly",
            "min_revenue_growth": min_revenue_growth,
            # 显式无市值限制：防止 LLM 代入剧本示例 mandate 里的
            # "market cap $2B-$200B" 偏好；universe 以运行时输入为准，
            # 大小市值一视同仁
            "universe": universe_note or (
                "the full user-provided universe at runtime — ALL market "
                "caps eligible (small to large), NO market-cap restriction; "
                "evaluate each name on its own fundamentals"
            ),
            "style": "Growth at reasonable expectations; reverse-DCF "
                     "discipline required",
        }
        self._max_loop_backs = max_loop_backs
        self._strong_short_value = strong_short_value
        self._hooks_enabled = tuple(hooks) if hooks else DEFAULT_HOOKS

    @property
    def name(self) -> str:
        return "growth_loop"

    # ------------------------------------------------------------------

    def predict(
        self,
        ticker: str,
        date: str,
        data_client: Any,
        hook_result: dict | None = None,
    ) -> Signal:
        # ---- HOOK 门（GATE H）：无数值 hook → 不进 LOOP ----
        # hook_result: 外部批量筛选结果注入（剧本流程：HOOK 周度全
        # universe 跑一次，A 名单直接进 LOOP，避免重复取数）。未提供
        # 时内部自行筛选。
        if hook_result is None:
            hook_result = screen_hooks(
                ticker, date, data_client, enabled=self._hooks_enabled
            )
        tripped = hook_result.get("tripped", [])
        if not tripped:
            return self._signal(
                ticker, date, value=0.0, abstained=True,
                reasoning=(
                    f"GATE H: no numeric hook tripped — "
                    f"{hook_result.get('computed', {})}"
                ),
                hooks=hook_result,
            )

        # ---- 无 LLM → 只报 hook，深研 abstain ----
        if self._llm is None:
            return self._signal(
                ticker, date, value=0.0, abstained=True,
                reasoning=(
                    f"hooks tripped ({', '.join(h['id'] for h in tripped)}) "
                    f"but no LLM client configured"
                ),
                hooks=hook_result,
            )

        # ---- LOOP：完整门控子图 ----
        try:
            result = run_growth_loop(
                ticker, date, data_client, self._llm,
                mandate=self._mandate,
                hooks_enabled=list(self._hooks_enabled),
                max_loop_backs=self._max_loop_backs,
                hook_evidence=hook_result if tripped else None,
            )
        except Exception as exc:
            return self._signal(
                ticker, date, value=0.0, abstained=True,
                reasoning=f"growth loop error: {exc}",
                hooks=hook_result,
            )

        return self._map_result(ticker, date, hook_result, result)

    # ------------------------------------------------------------------

    def _map_result(
        self,
        ticker: str,
        date: str,
        hook_result: dict,
        result: dict,
    ) -> Signal:
        status = result.get("status", "KILLED")
        kill_stage = result.get("kill_stage", "")
        kill_reason = result.get("kill_reason", "")
        scores = result.get("stage_scores", {})
        tripwires = result.get("tripwires", [])
        short_strength = result.get("short_strength")

        common_meta = {
            "status": status,
            "hooks": hook_result.get("tripped", []),
            "kill_stage": kill_stage,
            "kill_reason": kill_reason,
            "tripwires": tripwires,
            "exit_rules": result.get("exit_rules", []),
            "thesis": result.get("thesis", ""),
            "loop_backs": sum(result.get("loop_backs", {}).values()),
            "yellow_flags": result.get("yellow_flags", 0),
            "short_strength": short_strength,
        }

        if status == "PASSED":
            conviction = float(result.get("conviction", 0.0))
            value = max(0.0, min(1.0, conviction / 100.0))
            thesis = result.get("thesis") or "growth thesis passed all gates"
            return self._signal(
                ticker, date, value=value, abstained=False,
                reasoning=(
                    f"LOOP PASSED: conviction={conviction:.1f}/100 "
                    f"(L1-L6 weighted, yellow-flags="
                    f"{result.get('yellow_flags', 0)}) — {thesis}"
                ),
                hooks=hook_result, scores=scores, meta=common_meta,
            )

        # ---- KILLED ----
        # L7 强空头（≥7/10）：剧本 KILL 掉多头论点，但作为做空候选
        # 信号输出 strong_short_value。
        if (kill_stage == "L7" and short_strength is not None
                and short_strength >= 7):
            return self._signal(
                ticker, date, value=self._strong_short_value, abstained=False,
                reasoning=(
                    f"KILLED at L7: strong fundamental short "
                    f"({short_strength:.0f}/10) — {kill_reason}"
                ),
                hooks=hook_result, scores=scores, meta=common_meta,
            )

        return self._signal(
            ticker, date, value=0.0, abstained=True,
            reasoning=f"KILLED at {kill_stage}: {kill_reason}",
            hooks=hook_result, scores=scores, meta=common_meta,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _signal(
        ticker: str,
        date: str,
        value: float,
        abstained: bool,
        reasoning: str,
        hooks: dict | None = None,
        scores: dict | None = None,
        meta: dict | None = None,
    ) -> Signal:
        metadata: dict[str, Any] = dict(meta or {})
        if abstained:
            metadata["abstained"] = True
        if hooks:
            metadata.setdefault("hooks", hooks.get("tripped", []))
            metadata.setdefault("hook_computed", hooks.get("computed", {}))
        components = {k: round(v, 1) for k, v in (scores or {}).items()}
        return Signal(
            model_name="growth_loop",
            ticker=ticker,
            date=date,
            value=round(value, 4),
            reasoning=reasoning,
            components=components,
            metadata=metadata,
        )
