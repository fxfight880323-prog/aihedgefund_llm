"""有锐度的均衡 — L4 组合构造器 / 轮动引擎 (BalancedSharpnessBlend)。

实现 spec §4：
  - 持仓 30-40 只、~6 个方向（环节）、top-10 单票 ≈5%
  - 方向权重按稀缺度分**单调**分配（top≈16% 线性过渡到 tail≈7%）
  - 类配比约束：A≤55% / B≤30% / C≤5%（溢出留现金，现金 sleeve 隐式）
  - 自下而上 off-theme sleeve：非主题强基本面名字，上限 10%
  - 轮动语义：B 类触 PE 上限 → 负信念 → 权重归零（涨后减仓），资金
    自然流向未重估的同类滞涨者与下一排名方向（"rotate profit into
    same-class laggards"）；锐度只随证据（S 分/信念）上升，不随价格动量

输入是 rotation_growth 模型的 Signals（metadata 带 asset_class /
link / link_score）；无这些字段的信号按普通 conviction 处理并受
单票上限约束。
"""

from __future__ import annotations

from src.core.models import BlendResult, Signal
from src.core.interfaces import BlendPolicy
from src.core.registry import register_blend_policy


@register_blend_policy("balanced_sharpness")
class BalancedSharpnessBlend(BlendPolicy):
    """方向单调权重 + 类配比 + 单票上限的组合构造器。"""

    def __init__(
        self,
        top_direction_weight: float = 0.16,   # 第一名方向权重 [stated≈16%]
        tail_direction_weight: float = 0.07,  # 末名方向权重 [stated≈7%]
        max_directions: int = 6,              # 持有方向数 [stated≈6]
        class_mix: dict[str, float] | None = None,  # A/B/C 配比上限
        per_name_cap: float = 0.05,           # 单票上限 [stated≈5%]
        off_theme_sleeve: float = 0.10,       # 自下而上非主题 sleeve
        max_names_per_direction: int | None = None,  # 每方向只保留信念最高的
        # N 只（spec："买赢的环节里的龙头"，30-40只/6方向 ≈ 5-6只/方向）
        scale_to_target: bool = False,        # 满仓模式：不足 gross_target
        # 时按比例放大（仍受单票/类配比上限约束）
        **kwargs,
    ):
        self._top_w = top_direction_weight
        self._tail_w = tail_direction_weight
        self._max_dirs = max_directions
        self._class_mix = class_mix or {"A": 0.55, "B": 0.30, "C": 0.05}
        self._cap = per_name_cap
        self._off_theme = off_theme_sleeve
        self._max_names = max_names_per_direction
        self._scale_to_target = scale_to_target

    def blend(
        self,
        signals: list[Signal],
        model_weights: dict[str, float],
        gross_target: float = 1.0,
        market_neutral: bool = False,
    ) -> BlendResult:
        # ---- 收集观点（弃权跳过；负信念=轮出，记录但权重为 0）----
        convictions: dict[str, float] = {}
        views: dict[str, dict] = {}
        for s in signals:
            if s.metadata.get("abstained"):
                continue
            w = model_weights.get(s.model_name, 1.0)
            convictions[s.ticker] = convictions.get(s.ticker, 0.0) + w * s.value
            if s.ticker not in views or w >= 1.0:
                views[s.ticker] = {
                    "value": s.value,
                    "asset_class": s.metadata.get("asset_class", "A"),
                    "link": s.metadata.get("link"),
                    "link_score": s.metadata.get("link_score"),
                }

        longs = {t: v for t, v in views.items() if v["value"] > 0}
        weights: dict[str, float] = {t: 0.0 for t in views}

        # ---- 方向池 vs off-theme 池 ----
        by_link: dict[str, list[str]] = {}
        off_theme: list[str] = []
        for t, v in longs.items():
            if v["link"]:
                by_link.setdefault(v["link"], []).append(t)
            else:
                off_theme.append(t)

        # ---- 方向稀缺度排名 → 单调权重；每方向只留信念最高的 N 只 ----
        dirs = []
        for link, members in by_link.items():
            scores = [views[t]["link_score"] for t in members
                      if views[t]["link_score"] is not None]
            score = sum(scores) / len(scores) if scores else 0.0
            if self._max_names:
                members = sorted(
                    members, key=lambda t: -views[t]["value"]
                )[: self._max_names]
            dirs.append({"link": link, "members": members, "score": score})
        dirs.sort(key=lambda d: -d["score"])
        dirs = dirs[: self._max_dirs]

        k = len(dirs)
        dir_weights: list[float] = []
        for rank in range(k):
            if k == 1:
                w = self._top_w
            else:
                w = self._tail_w + (self._top_w - self._tail_w) * \
                    (k - 1 - rank) / (k - 1)
            dir_weights.append(w)

        # ---- 方向内按信念分配，先内后外施加类配比 ----
        for d, dir_w in zip(dirs, dir_weights):
            total = sum(views[t]["value"] for t in d["members"])
            if total <= 0:
                continue
            for t in d["members"]:
                weights[t] = dir_w * views[t]["value"] / total

        # ---- off-theme sleeve ----
        if off_theme:
            total = sum(views[t]["value"] for t in off_theme)
            if total > 0:
                for t in off_theme:
                    weights[t] = self._off_theme * views[t]["value"] / total

        # ---- 缩放到 gross_target（现金 sleeve 隐式留存）----
        gross = sum(w for w in weights.values() if w > 0)
        budget = max(0.0, min(gross_target, self._top_w * k
                              + self._off_theme if k else self._off_theme))
        if gross > budget > 0:
            scale = budget / gross
            weights = {t: w * scale if w > 0 else 0.0
                       for t, w in weights.items()}

        # ---- 满仓模式：不足 gross_target 时按比例放大到目标（先放大，
        # 再受类配比/单票上限约束——顺序错了会把类配比顶破）----
        if self._scale_to_target:
            gross = sum(w for w in weights.values() if w > 0)
            if 0 < gross < gross_target:
                scale = gross_target / gross
                weights = {t: w * scale if w > 0 else 0.0
                           for t, w in weights.items()}

        # ---- 类配比上限（溢出即现金，不再分配）----
        for cls, cap in self._class_mix.items():
            cls_names = [t for t, v in views.items()
                         if v["asset_class"] == cls and weights.get(t, 0) > 0]
            cls_gross = sum(weights[t] for t in cls_names)
            if cls_gross > cap and cls_gross > 0:
                scale = cap / cls_gross
                for t in cls_names:
                    weights[t] *= scale

        # ---- 单票上限（超出部分留在现金，不重分配——与风控哲学一致）----
        weights = {t: min(w, self._cap) for t, w in weights.items()}

        return BlendResult(convictions=convictions, weights=weights)
