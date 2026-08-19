"""Serenity 卡点审查门 — growth_loop 的 LOOP 层替代/补充。

来源：serenity-skill（供应链卡点猎手，~/.agents/skill/serenity-skill）。
接入点：growth_loop 子图 hook_screen 与 L1 之间。

  HOOK（找到高增长）→ SERENITY GATE（审查卡点真伪）→ L1-L7（LLM 深研）

设计吸取 backtest_serenity.py 的教训（-26.4%，全部点时版本最差）：
量化代理最大的坑是把"毛利率高"当"卡点"——2022 年新冠 IVD
（万孚/万泰/九安，GM 70%+）拿了最高分然后均值回归崩塌。本 gate 的
核心修正：

  1. 结构性定价权 = 毛利率水平 × 持续性（近 4 期最低值也高，或趋势
     上行）——只有"一直高"或"越走越高"才算卡点证据
  2. 情景性利润罚项 = 毛利率 z-score（当前 GM 远超自身历史均值 +
     波动大 = 疫情/周期一次性利润 → kill）
  3. hype 罚项 = 1 年涨幅（低点至今 >100% 罚分——买在热度上是
     growth_loop 2022-08 锂矿满仓扛崩的直接原因）

门控语义（对齐剧本 GATE 风格）：
  score ≥ pass_threshold（默认 55）→ PASS（进入 LOOP）
  35 ≤ score < 55              → PASS w/ DOWNGRADE（信念 ×0.7）
  score < kill_threshold（35） → KILL（kill_reason = 卡点证据不足）

无 LLM 回退模式：metadata 无 llm_client 时，serenity 分数 × hook
强度直接产出 L8 信念（跳过 L1-L7）——深研层的降级运行。
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import QuantModel
from src.core.models import Signal
from src.core.registry import register_alpha_model

# scorecard 权重（同 serenity-skill/scripts/serenity_scorecard.py）
WEIGHTS = {
    "demand_inflection": 15,
    "architecture_coupling": 10,
    "chokepoint_severity": 15,
    "supplier_concentration": 12,
    "expansion_difficulty": 12,
    "evidence_quality": 15,
    "valuation_disconnect": 11,
    "catalyst_timing": 10,
}
PENALTY_MULT = 2.0

KILL_THRESHOLD = 35.0
PASS_THRESHOLD = 55.0
DOWNGRADE_MULT = 0.70


def _rate(v: float, stops: list[float]) -> int:
    for i, s in enumerate(stops):
        if v >= s:
            return 5 - i
    return max(0, 5 - len(stops))


def _series(periods: dict[str, dict]) -> tuple[list[float], list[float]]:
    """period-matched YoY（newest-first）与毛利率序列（newest-first）。"""
    rev_by_qp: dict[tuple, float] = {}
    gm: list[float] = []
    for pk in sorted(periods.keys(),
                     key=lambda p: (int(p.split("-")[0]),
                                    int(p.split("-")[1])), reverse=True):
        m = periods[pk]
        try:
            y, q = int(pk[:4]), int(pk[5])
        except (ValueError, IndexError):
            continue
        if m.get("revenue"):
            rev_by_qp.setdefault((y, q), m["revenue"])
        gmv = m.get("gross_margin")
        if gmv is not None:
            gm.append(gmv)
    yoy = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    return yoy, gm


def _price_stats(data_client: Any, ticker: str, date: str
                 ) -> tuple[float | None, float | None]:
    """(距 1 年高点回撤, 距 1 年低点涨幅)。"""
    try:
        bars = data_client.get_prices(ticker, "2019-01-01", date)
    except Exception:
        return None, None
    closes = [b.get("close") for b in (bars or [])
              if isinstance(b, dict) and b.get("close")]
    if len(closes) < 6:
        return None, None
    window = closes[-13:]
    high, low, cur = max(window), min(window), window[-1]
    dd = max(0.0, 1 - cur / high) if high > 0 else 0.0
    runup = (cur / low - 1) if low > 0 else 0.0
    return dd, runup


def serenity_review(ticker: str, date: str, data_client: Any,
                    hook_evidence: dict | None = None,
                    params: dict | None = None) -> dict[str, Any]:
    """确定性卡点审查（scorecard 量化 + 情景性利润修正）。"""
    cfg = {
        "kill_threshold": KILL_THRESHOLD,
        "pass_threshold": PASS_THRESHOLD,
        **(params or {}),
    }
    metrics: list[dict] = []
    try:
        metrics = data_client.get_financial_metrics(ticker, date,
                                                    limit=60)
    except Exception:
        pass
    periods: dict[str, dict] = {}
    for r in metrics or []:
        d = str(r.get("date") or "")[:10]
        if len(d) == 10 and d[:4].isdigit():
            pk = f"{int(d[:4])}-{'1234'[int(d[5:7]) // 3 - 1]}"
            m = periods.setdefault(pk, {})
            for src, dst in (("revenue", "revenue"),
                             ("gross_margin", "gross_margin")):
                if r.get(src) is not None:
                    m.setdefault(dst, float(r[src]))
    yoy, gm = _series(periods)
    dd, runup = _price_stats(data_client, ticker, date)

    g0 = yoy[0] if yoy else 0.0
    accel = len(yoy) >= 2 and yoy[0] > yoy[1]
    accel2 = len(yoy) >= 3 and yoy[0] > yoy[1] > yoy[2]
    gm_now = gm[0] if gm else 0.0
    gm_prev = gm[1] if len(gm) > 1 else gm_now
    # 全历史最低毛利率：结构性 = "一直高"。只看近 4 期会被 IVD 型
    # （低基数冲顶后近 4 期全高）伪装成结构性卡点
    gm_floor = min(gm) if gm else 0.0
    gm_chg = gm_now - gm_prev
    n = len(periods)

    # 情景性尖峰：当前毛利率 − 自身较早历史（后半段索引=较旧）中位数。
    # IVD 型：25 → 70 冲顶 = +40pp 尖峰；结构性：45-52 平稳抬升 = +5pp。
    # （不用 z-score：平稳上行趋势天然偏离自身均值，会把结构性误标情景）
    half = gm[len(gm) // 2:] if gm else []      # 较旧的一半（newest-first）
    base_med = sorted(half)[len(half) // 2] if half else gm_now
    gm_spike = gm_now - base_med
    if len(gm) >= 4:
        mean = sum(gm) / len(gm)
        std = (sum((x - mean) ** 2 for x in gm) / len(gm)) ** 0.5
    else:
        std = 0.0

    factors = {
        "demand_inflection": min(5, _rate(g0, [0.9, 0.6, 0.4, 0.2, 0.1])
                                 + (1 if accel2 else 0)),
        # 结构性定价权修正：水平 × 持续性（floor 高 = 一直高）
        "architecture_coupling": min(
            5, _rate(gm_now, [50, 35, 25, 15, 8]) * 0.6
            + _rate(gm_floor, [45, 32, 22, 14, 8]) * 0.4),
        "chokepoint_severity": _rate(gm_chg, [12, 8, 4, 1.5, 0.3]),
        # gate 层无同业数据 → 中性
        "supplier_concentration": 2.5,
        "expansion_difficulty": _rate(gm_floor, [45, 32, 22, 14, 8]),
        "evidence_quality": _rate(n, [7, 5, 4, 3, 2]),
        "valuation_disconnect": (
            _rate(dd, [0.45, 0.35, 0.25, 0.15, 0.08])
            if (dd or 0) >= 0.15 and g0 >= 0.15 else 1),
        "catalyst_timing": 5 if accel2 else (3 if accel else 1),
    }
    # 情景性尖峰折价：毛利率相对基线尖峰 >25pp 时，毛利率驱动的三个
    # 结构性因子打 4 折——一次性利润不能记作架构卡点的功劳（IVD 教训：
    # 罚分抵不过 demand+evidence 的 36 分底仓，必须折价因子本身）
    if gm_spike > 25:
        for k in ("architecture_coupling", "chokepoint_severity",
                  "expansion_difficulty"):
            factors[k] = factors[k] * 0.4
    penalties = {
        # 情景性利润（IVD 教训）：毛利率相对自身历史基线尖峰 >25pp =
        # 一次性利润（疫情/周期），非结构性定价权
        "episodic_margin": (4 if gm_spike > 25 else
                            2 if gm_spike > 15 else
                            1 if std > 10 else 0),
        "hype_risk": _rate(runup or 0, [2.0, 1.5, 1.0, 0.6, 0.3]),
        "cyclicality": _rate(std, [12, 8, 5, 3, 1.5]),
    }
    raw = sum(min(factors[k], 5) / 5 * w for k, w in WEIGHTS.items())
    pen = sum(penalties.values()) * PENALTY_MULT
    score = max(0.0, min(100.0, raw - pen))

    if score < cfg["kill_threshold"]:
        verdict, reason = "KILL", (
            f"卡点证据不足（score {score:.0f}）"
            + (f"；情景性毛利率（尖峰 +{gm_spike:.0f}pp）——一次性利润"
               f"非结构性定价权" if gm_spike > 15 else "")
            + ("；热度罚（1年涨幅 {:.0%}）".format(runup)
               if (runup or 0) > 1.0 else ""))
    elif score < cfg["pass_threshold"]:
        verdict, reason = "DOWNGRADE", (
            f"卡点证据中等（score {score:.0f}），信念 ×{DOWNGRADE_MULT}")
    else:
        verdict, reason = "PASS", f"卡点证据充分（score {score:.0f}）"

    return {
        "score": round(score, 1), "raw": round(raw, 1),
        "penalties_points": round(pen, 1),
        "factors": factors, "penalties": penalties,
        "gm_spike": round(gm_spike, 1), "gm_floor": round(gm_floor, 1),
        "runup_1y": runup, "drawdown_1y": dd,
        "verdict": verdict, "reason": reason,
    }


@register_alpha_model("serenity_gate")
class SerenityGateModel(QuantModel):
    """standalone alpha model：serenity 分数 → 信念（供 fund 主图直接挂载）。

    value = score/100 × hook 联动（若 metadata 带 hook_evidence，高增长
    加成），KILL → abstain。
    """

    def __init__(self, kill_threshold: float = KILL_THRESHOLD,
                 pass_threshold: float = PASS_THRESHOLD, **kwargs):
        self._kill = kill_threshold
        self._pass = pass_threshold

    @property
    def name(self) -> str:
        return "serenity_gate"

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        review = serenity_review(ticker, date, data_client,
                                 params={"kill_threshold": self._kill,
                                         "pass_threshold": self._pass})
        if review["verdict"] == "KILL":
            return Signal(
                model_name=self.name, ticker=ticker, date=date,
                value=0.0, reasoning=f"[serenity KILL] {review['reason']}",
                metadata={"serenity": review, "status": "KILLED"})
        value = review["score"] / 100.0
        if review["verdict"] == "DOWNGRADE":
            value *= DOWNGRADE_MULT
        return Signal(
            model_name=self.name, ticker=ticker, date=date,
            value=round(value, 3),
            reasoning=(f"[serenity {review['verdict']}] "
                       f"score={review['score']:.0f} "
                       f"gm_floor={review['gm_floor']} "
                       f"spike={review['gm_spike']}pp | {review['reason']}"),
            metadata={"serenity": review, "status": "RUNNING"})
