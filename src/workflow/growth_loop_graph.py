"""LOOP 层 — GOAL→HOOK→LOOP 九阶段分析引擎的 LangGraph 门控子图。

剧本 (growth_stock_goal_hook_loop_playbook.md) 的 LOOP 是一个带门控的
迭代状态机，与 LangGraph 的条件边一一对应；每个 L 阶段后接**确定性
审视节点**（LLM 报数，代码判门）：

    hook_screen ──(无数值hook)──▶ kill ──▶ END
        │(≥1 hook)
        ▼
        L1 → verify_L1 → L2 → verify_L2 → … → L7 → verify_L7
                                                        │
                                          PASS ▼    l8_conviction → END
        每阶段三向路由（verify 之后）：PASS→下一阶段 /
        LOOP-BACK→回环自身（最多2次，第3次自动 KILL）/ 其余→kill
        verify 可推翻 LLM 门控：规则实败→FAIL；算术比错→带纠正回环

每个 L 阶段 = 一次 LLM 调用（阶段 prompt + mandate + hook 证据 +
数据包 + 前序输出），输出以机器可解析块结尾：

    SCORE: <0-100>
    GATE: PASS | FAIL | LOOP-BACK
    REASON: <一行>
    NUMBERS: key=value; …（L1/L2/L3/L6，供 verify 节点确定性复算）

剧本纪律的落地：
  - 溯源标注：[HARD]/[EST]/[HEUR] 强制写入每个阶段的 system prompt；
  - 回环上限：max_loop_backs=2，第3次 LOOP-BACK 自动 KILL（防
    thesis-rescue）；
  - L7 红队不可跳过：无 tripwire 或空头强度 ≥7/10 → KILL；
  - L8 信念 = 确定性代码（加权门控分 + L5 黄旗减记），LLM 不碰仓位——
    仓位由框架的 blend + risk 决定（"LLM never touches the trade"）；
  - KILL 日志：kill_stage + kill_reason 进 state，是剧本的
    edge-improvement dataset。

数据完整性原则 (Data Completeness Principle) — 框架级纪律：
  1. 取数层尽最大努力：各阶段必需字段（营收/毛利率/营业利润/费用/
     资本开支/现金流/股本/市值/现金负债/主营构成）必须主动获取，
     空响应绕缓存重试；
  2. 缺口显式声明：真取不到的字段在数据包的 DATA COMPLETENESS 块
     中逐项声明为 DATA GAP，禁止静默缺失（declare_data_gaps）；
  3. 缺口不判死：已声明的 DATA GAP 由 LLM 以 [EST]/[HEUR] 构建估值
     继续分析（system prompt 规则 7），DATA GAP 本身永远不是独立的
     FAIL/KILL 理由——只有"估值无法约束结论"时才允许 fail，且理由
     必须指向逻辑而非缺失字段。

独立运行（带 LangGraph 检查点，可用于 L9 季度审计的状态延续）：

    graph = build_growth_loop_graph()
    result = graph.invoke(initial_state, {"recursion_limit": 80})

或用便捷入口：

    from src.workflow.growth_loop_graph import run_growth_loop
    result = run_growth_loop("688012.SH", "2026-08-13", data_client, llm)
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from src.signals.hooks import screen_hooks


# ===========================================================================
# State
# ===========================================================================

class GrowthLoopState(TypedDict, total=False):
    """LOOP 子图的共享状态（LangGraph 约定：节点返回 dict 增量）。"""

    # ---- 输入 ----
    ticker: str
    date: str
    mandate: dict[str, Any]        # GOAL 层参数
    hooks_enabled: list[str]

    # ---- HOOK 层产出 ----
    hook_evidence: dict[str, Any]  # screen_hooks 的结果
    data_packet: str               # 组装好的 point-in-time 数据包

    # ---- SERENITY 审查层（确定性卡点检验，hook 与 L1 之间）----
    serenity_review: dict[str, Any]  # score/factors/verdict/reason

    # ---- LOOP 阶段累积 ----
    stage_outputs: dict[str, str]  # 阶段原始 LLM 输出
    stage_scores: dict[str, float] # 各阶段 SCORE (0-100)
    gates: dict[str, str]          # 各阶段最终 GATE
    loop_backs: dict[str, int]     # 各阶段已发生的 LOOP-BACK 次数
    thesis: str                    # L1 的一句话论点（L9 审计锚）

    # ---- 审视层（确定性验证）----
    verifications: dict[str, list]  # 各阶段 verify 审计记录（按次追加，保留纠错历史）
    corrections: dict[str, str]     # 算术纠错回环时注入下一轮 prompt 的纠正文本

    # ---- 结果 ----
    status: str                    # RUNNING | PASSED | KILLED
    kill_stage: str
    kill_reason: str
    conviction: float              # 0-100，黄旗减记后
    yellow_flags: int
    short_strength: float          # L7: 0-10
    tripwires: list[str]           # L7: 3 条监测绊线
    exit_rules: list[str]          # L8: 4 条预承诺退出规则

    # ---- 基础设施（不序列化） ----
    metadata: dict[str, Any]       # llm_client / data_client / max_loop_backs


_STAGES = ("L1", "L2", "L3", "L4", "L5", "L6", "L7")

# L8 加权（剧本 §5 Quick-Reference Scoring Rubric）
STAGE_WEIGHTS = {
    "L1": 0.15,  # Business/TAM
    "L2": 0.20,  # Growth durability
    "L3": 0.20,  # Unit economics
    "L4": 0.15,  # Moat
    "L5": 0.10,  # Management
    "L6": 0.20,  # Valuation
}

MAX_LOOP_BACKS = 2          # 剧本: "Maximum 2 loop-backs per stage"
YELLOW_FLAG_HAIRCUT = 0.25  # 每面黄旗 -25% 信念，最多计 2 面
DOWNGRADE_MULT_FALLBACK = 0.70  # serenity DOWNGRADE 的回退信念系数


# ===========================================================================
# Prompts — 从剧本忠实浓缩
# ===========================================================================

def _machine_block(extra: str = "") -> str:
    tail = (
        "\nEnd your output with EXACTLY this machine block:\n"
        "SCORE: <0-100>\n"
        "GATE: PASS | FAIL | LOOP-BACK\n"
        "REASON: <one line>\n"
    )
    return extra + tail


STAGE_PROMPTS: dict[str, str] = {
    "L1": _machine_block("""Stage L1: Business decomposition for {ticker}.

1. Describe the business in ≤3 sentences a competitor's CFO would agree with
   (no marketing language).
2. Revenue segmentation: segments, % of revenue, growth rate each. Tag every
   number [HARD from filings] or [EST].
3. TAM audit: state the company's claimed TAM [HARD-claimed], then build a
   bottom-up TAM independently: (# realistic customers) × (realistic ACV).
   Tag [EST] with arithmetic shown. Flag if claimed TAM > 3× bottom-up.
4. S-curve position: <10% / 10-40% / >40% penetration? Evidence required.
5. Customer concentration: top-10 customer revenue %, any single >10%?
   Report as a risk factor ONLY — customer concentration is NOT a kill or
   FAIL criterion in this mandate. Concentrated customer bases are a
   structural feature of this universe (equipment/chip suppliers sell to a
   few large fabs). Flag high concentration so it becomes an L7 tripwire.

GATE L1: PASS if (a) money model clear in 3 sentences, (b) bottom-up TAM
supports ≥5 more years of >{min_growth} growth. Else FAIL or LOOP-BACK
naming the missing data. NEVER fail on customer concentration alone.
KILL on: TAM claim >3× defensible bottom-up; revenue-definition games.

Also include exactly (units consistent, e.g. 亿元):
NUMBERS: claimed_tam=<val>; bottomup_tam=<val>
And one line: THESIS: <your one-sentence long thesis>"""),
    "L2": _machine_block("""Stage L2: Decompose {ticker}'s revenue growth into drivers.
Growth = (new customers × landing ACV) + (existing expansion) + (pricing) + (M&A/FX).

1. Estimate each driver's contribution to the last 4 quarters. Tag every input.
   If disclosure insufficient, name the missing metric (NRR, net adds, ARPU)
   and tag the driver [EST-LOW CONFIDENCE].
2. Which driver is decelerating first? Growth almost never dies evenly.
3. Cohort "growth floor": if new-customer adds go to zero, what does retention
   math imply for growth 8 quarters out?
4. Three 3-year scenarios BEAR / BASE / BULL with CAGRs; state the single
   assumption that most separates BEAR from BULL.

GATE L2: PASS if BASE CAGR ≥ {min_growth} AND growth floor > 0.5× current
growth rate. FAIL if >50% of growth from a single decaying driver.

Also include exactly (decimals 0-1, e.g. 0.25 = 25%):
NUMBERS: current_growth=<dec>; growth_floor=<dec>; base_cagr=<dec>"""),
    "L3": _machine_block("""Stage L3: Unit economics and operating leverage for {ticker}.

1. Gross margin: level, 8-quarter trend, structural driver (mix, scale, input
   costs). [HARD]
2. Incremental margins: (ΔOperating Income / ΔRevenue) over trailing 4 and 8
   quarters — the single most important growth-stock number. [HARD, show math]
3. Rule of 40 (or sector equivalent): revenue growth % + FCF margin %, trend
   over 6 quarters.
4. SBC honesty: SBC as % of revenue; FCF margin AFTER treating SBC as a cash
   cost; dilution rate (share count CAGR, 3yr).
5. Capital intensity: capex + capitalized R&D as % of revenue, trend.
6. Margin bridge: path from current operating margin to the long-term target —
   is the incremental-margin math consistent with that path?

GATE L3: PASS if incremental margins > current operating margin (leverage is
real) AND SBC-adjusted FCF positive or credible ≤8-quarter path. FAIL if
margin targets require never-demonstrated incremental margins.

Also include exactly (decimals, e.g. 0.38 = 38%):
NUMBERS: incremental_margin=<dec>; current_op_margin=<dec>"""),
    "L4": _machine_block("""Stage L4: Competitive position for {ticker}.

1. Classify the moat (network effects / switching costs / scale economies /
   IP-process / brand / regulatory) with EVIDENCE per claim: pricing power
   (raised prices without churn?), win rates, gross margin vs closest comps.
   No evidence = a lead, not a moat.
2. Moat DIRECTION (widening or narrowing) — matters more than level. Cite 2
   observable indicators (NRR trend, competitor gross-margin convergence,
   sales-cycle length).
3. Disruption vectors, force-ranked top 3: technology substitution (what does
   a 10× drop in inference cost / a frontier-model capability jump do to this
   business?), vertical integration by customer/supplier, open-source
   commoditization, regulatory.
4. "Who kills them": name the single most dangerous competitor and write 3
   sentences from THAT company's strategy memo about attacking {ticker}.

GATE L4: PASS if ≥1 evidenced moat AND the top disruption vector has a
quarterly-trackable monitoring indicator. FAIL if the moat rests solely on
"first mover" or "brand" without pricing-power evidence."""),
    "L5": _machine_block("""Stage L5: Management audit for {ticker}.

1. Promise-vs-delivery: guidance given 4, 8, 12 quarters ago vs actuals.
   Compute the average beat/miss. [HARD] Chronic over-promisers fail here.
2. Capital allocation: last 3 years of FCF deployment — % to buybacks (at
   what avg price vs today), M&A (revenue acquired vs price paid), R&D
   intensity vs peers. Grade A-F with one-line justification.
3. Incentives: which metrics drive executive comp — per-share value
   (FCF/share, ROIC) or empire-building (revenue, adjusted EBITDA)?
4. Ownership: founder/insider %, net insider buying/selling 12 months.
5. Disclosure quality: any KPI removed or redefined in the last 2 years?
   (KPI removal is a leading indicator of that KPI deteriorating.)

GATE L5: PASS if promise-vs-delivery neutral-to-positive AND no KPI removals
AND comp not purely revenue-based.

Also include one line: YELLOW-FLAGS: <integer count of yellow flags — heavy
insider selling, aggressive adjusted metrics, etc.>"""),
    "L6": _machine_block("""Stage L6: Expectations-investing valuation for {ticker}.
Ask what is PRICED IN first, not what it is worth.

1. REVERSE DCF: given current EV, solve the implied 10-year revenue CAGR
   assuming terminal FCF margin = the L3 margin-bridge endpoint, discount
   rate 9-11% (state choice), terminal growth 3%. Show the arithmetic.
   Output: "The market is paying for X% CAGR for Y years." [EST]
2. Compare implied CAGR to the L2 BEAR/BASE/BULL scenarios:
   market ≤ BEAR → potentially mispriced cheap (verify you're not missing
   the reason); between BEAR and BASE → interesting; ≥ BASE → you need the
   BULL case just to earn the discount rate; ≥ BULL → uninvestable at this
   price, watchlist with a trigger price.
3. Forward multiple sanity: EV/GP and EV/FCF vs the company's own 3-yr range
   and vs 3 named comps, growth-adjusted.
4. 3-year expected return per scenario: revenue CAGR + margin-change effect +
   multiple change + dilution. State the BASE-case annualized return and the
   BEAR-case drawdown.

GATE L6: PASS if BASE-case expected return ≥ {target_return} AND
market-implied CAGR ≤ your BASE scenario AND BEAR-case 3yr outcome ≥ -30%.
Else FAIL or LOOP-BACK with a computed watchlist trigger price.
Never adjust the terminal margin upward to make the entry price work — that
is thesis-rescue; log it and FAIL.

Also include exactly (decimals, negative returns as negatives):
NUMBERS: implied_cagr=<dec>; base_cagr=<dec>; base_return=<dec>; bear_return=<dec>"""),
    "L7": _machine_block("""Stage L7 (mandatory — cannot be skipped): You are now a short seller
pitching {ticker} to a skeptical PM. Your bonus depends on this pitch.
Using everything above:

1. Write the 5-point short thesis. Attack the weakest [EST] and [HEUR] tags
   from the analysis above — quote them back.
2. Pre-mortem: "It is 3 years from now and this position lost 50%. Write the
   post-mortem." Most-likely failure chain, step by step.
3. Base-rate check: what % of companies with this profile (growth rate,
   multiple, sector) sustained >{min_growth} growth for 5+ years
   historically? [HEUR, state reasoning]
4. Identify the 3 disconfirming datapoints that, if they appeared in the next
   2 earnings reports, would prove the short right. These become the
   monitoring tripwires.
5. Steelman verdict 0-10: how much does the short case rely on valuation
   alone (weak short) vs fundamental deterioration (strong short)?

GATE L7: PASS only if the long thesis survives WITH the tripwires defined
AND short-strength < 7.

Also include EXACTLY this block before the machine block:
TRIPWIRES:
1) <tripwire one>
2) <tripwire two>
3) <tripwire three>
SHORT-STRENGTH: <0-10>"""),
}


def _system_prompt(mandate: dict[str, Any]) -> str:
    """PROMPT G-1 的运行时形态：mandate + 全局纪律。"""
    m = mandate or {}
    return f"""You are my growth-equity investment analyst running the
GOAL → HOOK → LOOP decision engine.

MANDATE:
- Return objective: {m.get('return_objective', '15%+ annualized over 3-5 years')}
- Horizon: {m.get('horizon', 'minimum 2-year hold intent; re-underwrite quarterly')}
- Universe: {m.get('universe', 'provided at runtime')}
- Style: Growth at reasonable expectations — pay for durable growth, not for
  growth already fully priced. Reverse-DCF discipline required.

RULES YOU MUST FOLLOW:
1. Tag every factual claim [HARD], every estimate [EST] with stated method,
   every judgment [HEUR]. Never present [HEUR] as [HARD].
2. When you don't know, say "UNKNOWN — verify via {{source}}". Never
   fabricate financial figures.
3. Every stage output ends with the SCORE/GATE/REASON machine block exactly
   as instructed.
4. You are rewarded for killing bad ideas early, not for completing analyses.
5. The data packet is all you get — no new data arrives on re-runs. If a
   required item is missing, CONSTRUCT it as [EST] or [HEUR] with stated
   assumptions (from the packet metrics and general knowledge) and still
   decide the gate. Reserve LOOP-BACK only for when the gate is genuinely
   undecidable even with tagged estimates.
6. Customer concentration is REPORTED as a monitored risk and may become an
   L7 tripwire — it is NEVER a standalone kill or FAIL reason at any stage
   (concentrated customer bases are structural in this universe).
7. DATA COMPLETENESS CONTRACT: the packet's DATA COMPLETENESS block declares
   every required field that is unavailable after exhaustive fetching. For
   each declared DATA GAP you MUST construct a tagged [EST]/[HEUR] value
   with stated assumptions and continue the analysis. A declared DATA GAP
   is NEVER by itself a valid FAIL or LOOP-BACK reason — aborting on a
   declared gap violates the mandate. Only undecidable gates (where
   estimates cannot bound the answer) may fail, and the reason must then
   name the logic, not the missing field.
"""


# ===========================================================================
# 输出解析 — 机器块契约
# ===========================================================================

_GATE_RE = re.compile(r"GATE:\s*(PASS|FAIL|LOOP[-\s]?BACK)", re.IGNORECASE)
_SCORE_RE = re.compile(r"SCORE:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*([^\n]+)")
_YELLOW_RE = re.compile(r"YELLOW[-\s]?FLAGS:\s*(\d+)", re.IGNORECASE)
_SHORT_RE = re.compile(r"SHORT[-\s]?STRENGTH:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_THESIS_RE = re.compile(r"THESIS:\s*([^\n]+)", re.IGNORECASE)
_NUMBERS_RE = re.compile(r"NUMBERS?\s*:\s*([^\n]+)", re.IGNORECASE)


def parse_stage_output(text: str) -> dict[str, Any]:
    """解析一个阶段的 LLM 输出。

    无法解析 GATE 时返回 gate=None（调用方按 LOOP-BACK 处理一次，
    再失败即 KILL——对应剧本 "untagged claims are discarded"）。
    """
    gate_m = _GATE_RE.search(text)
    gate = gate_m.group(1).upper().replace(" ", "-").replace("--", "-") if gate_m else None
    if gate == "LOOPBACK":
        gate = "LOOP-BACK"

    score_m = _SCORE_RE.search(text)
    score = float(score_m.group(1)) if score_m else None
    if score is not None:
        score = max(0.0, min(100.0, score))

    reason_m = _REASON_RE.search(text)
    yellow_m = _YELLOW_RE.search(text)
    short_m = _SHORT_RE.search(text)
    thesis_m = _THESIS_RE.search(text)

    tripwires: list[str] = []
    tw_m = re.search(
        r"TRIPWIRES?\s*:\s*\n((?:\s*\d\).*\n?){1,5})", text, re.IGNORECASE
    )
    if tw_m:
        tripwires = [
            ln.split(")", 1)[1].strip()
            for ln in tw_m.group(1).strip().splitlines()
            if ")" in ln
        ]

    numbers: dict[str, float] = {}
    nm = _NUMBERS_RE.search(text)
    if nm:
        for part in re.split(r"[;；]", nm.group(1)):
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            v = v.strip()
            try:
                numbers[k.strip().lower()] = (
                    float(v.rstrip("%")) / 100.0 if v.endswith("%")
                    else float(v)
                )
            except ValueError:
                continue

    return {
        "gate": gate,
        "score": score,
        "reason": reason_m.group(1).strip() if reason_m else "",
        "yellow_flags": int(yellow_m.group(1)) if yellow_m else 0,
        "short_strength": float(short_m.group(1)) if short_m else None,
        "thesis": thesis_m.group(1).strip() if thesis_m else "",
        "tripwires": tripwires,
        "numbers": numbers,
    }


# ===========================================================================
# 数据包构建（point-in-time）
# ===========================================================================

def declare_data_gaps(packet: str) -> list[str]:
    """数据完整性自证：按各阶段必需字段检查数据包，产出声明行。

    数据完整性原则（写入框架的三条纪律）：
      1. 取数层尽最大努力（多查询 + 绕缓存重试）获取必需字段；
      2. 真取不到的字段必须在此**显式声明为 DATA GAP**，禁止静默缺失；
      3. 已声明的缺口由 LLM 按规则 7 以 [EST]/[HEUR] 构建估值，
         DATA GAP 本身永远不是独立的 FAIL/KILL 理由。

    Returns: 写入数据包尾部的声明行列表（OK 项 + GAP 项）。
    """
    checks = [
        # (字段, 所属阶段, 检测正则)
        ("revenue series", "L1/L2", ("revenue", "营业收入")),
        ("margins", "L1/L3", ("gross_margin", "毛利率")),
        # 营业利润(绝对额)，排除"营业利润率"的子串误报
        ("operating income series", "L3",
         (r"营业利润(?!率)", r"operating\s*income")),
        ("opex breakdown (R&D etc.)", "L3/L5",
         ("研发费用", "R&D")),
        ("capex", "L3", ("购建固定资产", "capex")),
        ("operating cash flow", "L3",
         ("经营活动产生的现金流量净额", "经营现金流", "operating cash")),
        ("share count / market cap", "L6",
         ("总股本", "market_cap", "市值")),
        ("cash / debt position", "L6",
         ("货币资金", "net_cash", "短期借款")),
        ("segment breakdown", "L1",
         ("SEGMENT BREAKDOWN", "主营构成")),
        ("price history", "L6/H6", ("PRICE", "收盘")),
    ]
    out: list[str] = []
    gaps = 0
    for field, stages, patterns in checks:
        if any(re.search(p, packet) for p in patterns):
            out.append(f"  OK: {field} ({stages})")
        else:
            gaps += 1
            out.append(
                f"  DATA GAP: {field} ({stages}) — fetched but unavailable "
                f"from source; construct [EST]/[HEUR] with stated "
                f"assumptions (rule 7); NEVER fail on this gap alone"
            )
    out.append(f"  SUMMARY: {len(checks) - gaps}/{len(checks)} required "
               f"fields present, {gaps} declared gap(s)")
    return out


def build_data_packet(ticker: str, date: str, data_client: Any) -> str:
    """组装 L1-L7 共用的 point-in-time 数据包文本（含完整性自证块）。"""
    lines = [f"TICKER: {ticker}", f"AS-OF DATE: {date[:10]}", ""]

    try:
        metrics = [
            m for m in (data_client.get_financial_metrics(ticker, date, limit=8) or [])
            if isinstance(m, dict) and str(m.get("date") or "")[:10] <= date[:10]
        ]
    except Exception:
        metrics = []
    if metrics:
        lines.append("FUNDAMENTALS (newest first, quarterly):")
        for m in metrics[:8]:
            fields = ", ".join(
                f"{k}={v}" for k, v in m.items()
                if k not in ("ticker", "period") and v not in (None, "")
            )
            lines.append(f"  {m.get('date', '?')}: {fields}")
        lines.append("")

    try:
        facts = data_client.get_company_facts(ticker) or {}
    except Exception:
        facts = {}
    if facts:
        lines.append(
            f"COMPANY: sector={facts.get('sector')} "
            f"industry={facts.get('industry')}"
        )
        desc = facts.get("description")
        if desc:
            lines.append(f"  description: {str(desc)[:400]}")
        lines.append("")

    # 主营构成 / 客户集中度（可选能力：MXDataClient 实现，其他 client 跳过）
    seg_fn = getattr(data_client, "get_segment_breakdown", None)
    if callable(seg_fn):
        try:
            seg = seg_fn(ticker)
        except Exception:
            seg = None
        if seg:
            lines.append("SEGMENT BREAKDOWN (主营构成, latest period):")
            lines.append(seg[:1500])
            lines.append("")

    # 财务明细（可选能力）：L3 单位经济 / L5 管理 / L6 估值的核心输入
    detail_fn = getattr(data_client, "get_financial_detail", None)
    if callable(detail_fn):
        try:
            detail = detail_fn(ticker)
        except Exception:
            detail = None
        if detail:
            lines.append("FINANCIAL DETAIL (利润表/现金流/资产负债表, "
                         "newest first):")
            lines.append(detail[:2200])
            lines.append("")

    # ---- 数据完整性自证（原则：缺口必须显式声明，禁止静默缺失）----
    lines.append("DATA COMPLETENESS:")
    lines.extend(declare_data_gaps("\n".join(lines)))
    lines.append("")

    try:
        from datetime import datetime as _dt, timedelta as _td
        as_of = _dt.strptime(date[:10], "%Y-%m-%d").date()
        start = (as_of - _td(days=400)).isoformat()
        bars = [
            b for b in (data_client.get_prices(ticker, start, date) or [])
            if (b.get("time") or "")[:10] <= date[:10]
        ]
    except Exception:
        bars = []
    if bars:
        closes = [float(b["close"]) for b in bars if _is_num(b.get("close"))]
        if closes:
            hi, lo, last = max(closes), min(closes), closes[-1]
            first = closes[0]
            lines.append(
                f"PRICE (last 400d): last={last:.2f} high={hi:.2f} "
                f"low={lo:.2f} period_return={last / first - 1:+.1%} "
                f"drawdown_from_high={1 - last / hi:+.1%}"
            )

    return "\n".join(lines)


def _is_num(v: Any) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


# ===========================================================================
# 审视层 — 确定性门控验证 (LLM proposes numbers, code disposes gates)
# ===========================================================================
# 背景：真实运行中 GLM-4 曾把不等式比反（"floor 27.2% < 0.5×24.58%"——
# 实际 27.2% > 12.29%，规则明明通过），一只票死于算术错误。审视层把
# "报数"与"判门"分离：LLM 输出 NUMBERS 行，verify 节点用代码复算
# 剧本的数值规则，三种处置：
#   1. 任一规则实败        → 覆盖为 FAIL（确定性，不可上诉）
#   2. 全部规则通过，但 LLM 的 FAIL 理由引用了实际通过的规则（算术比错）
#                           → 覆盖为 LOOP-BACK，注入纠正文本重判
#   3. 无 NUMBERS / 无规则  → 透传（审计记录标记 unverified）
# 每次验证结果进 state["verifications"]，是 kill log 的算术审计痕迹。

def _rule(rule_id, keys, check, fail_reason, cites):
    return {
        "id": rule_id, "keys": keys, "check": check,
        "fail": fail_reason, "cites": cites,
    }


VERIFY_RULES: dict[str, list[dict]] = {
    "L1": [
        _rule(
            "tam_ratio", ("claimed_tam", "bottomup_tam"),
            lambda n, m: n["bottomup_tam"] > 0
            and n["claimed_tam"] <= 3 * n["bottomup_tam"],
            "claimed TAM > 3× bottom-up TAM",
            ("tam",),
        ),
    ],
    "L2": [
        _rule(
            "growth_floor", ("current_growth", "growth_floor"),
            lambda n, m: n["current_growth"] > 0
            and n["growth_floor"] >= 0.5 * n["current_growth"],
            "growth floor < 0.5× current growth",
            ("growth floor", "0.5", "floor"),
        ),
        _rule(
            "base_cagr", ("base_cagr",),
            lambda n, m: n["base_cagr"] >= m.get("min_revenue_growth", 0.20),
            "BASE CAGR below mandate minimum growth",
            ("cagr",),
        ),
    ],
    "L3": [
        _rule(
            "incr_margin", ("incremental_margin", "current_op_margin"),
            lambda n, m: n["incremental_margin"] > n["current_op_margin"],
            "incremental margin ≤ current operating margin",
            ("incremental",),
        ),
    ],
    "L6": [
        _rule(
            "implied_vs_base", ("implied_cagr", "base_cagr"),
            lambda n, m: n["implied_cagr"] <= n["base_cagr"],
            "market-implied CAGR exceeds your BASE scenario",
            ("implied",),
        ),
        _rule(
            "base_return", ("base_return",),
            lambda n, m: n["base_return"] >= m.get("target_return", 0.15),
            "BASE-case expected return below mandate target",
            ("return", "priced in"),
        ),
        _rule(
            "bear_floor", ("bear_return",),
            lambda n, m: n["bear_return"] >= -0.30,
            "BEAR-case 3yr outcome below -30%",
            ("bear",),
        ),
    ],
}


def _make_verify_node(stage: str):
    """verify 节点工厂：复算该阶段的数值规则，可推翻 LLM 的门控。"""

    def node(state: GrowthLoopState) -> dict[str, Any]:
        rules = VERIFY_RULES.get(stage, [])
        gates = state.get("gates", {})
        gate = gates.get(stage)
        parsed = parse_stage_output(state.get("stage_outputs", {}).get(stage, ""))
        numbers = parsed.get("numbers") or {}
        mandate = state.get("mandate", {})

        verif: dict[str, Any] = {"stage": stage, "checks": []}
        history = list(state.get("verifications", {}).get(stage) or [])
        updates: dict[str, Any] = {
            "verifications": {
                **state.get("verifications", {}), stage: history + [verif]
            }
        }

        if not rules:
            verif["mode"] = "pass-through (no numeric rules at this stage)"
            return updates
        if not numbers:
            verif["mode"] = "unverified (LLM provided no NUMBERS line)"
            return updates

        failed: list[dict] = []
        checked: list[dict] = []   # 实际评估过的规则（键齐全的）
        for r in rules:
            if not all(k in numbers for k in r["keys"]):
                verif["checks"].append(
                    {"rule": r["id"], "status": "skipped (missing keys)"})
                continue
            checked.append(r)
            try:
                ok = bool(r["check"](numbers, mandate))
            except Exception:
                ok = None
            verif["checks"].append({
                "rule": r["id"],
                "status": "PASS" if ok else ("FAIL" if ok is False else "ERROR"),
                "inputs": {k: numbers[k] for k in r["keys"]},
            })
            if ok is False:
                failed.append(r)

        if failed:
            r = failed[0]
            verif["mode"] = f"OVERRIDE→FAIL [{r['id']}]"
            updates["gates"] = {**gates, stage: "FAIL"}
            updates["kill_stage"] = stage
            updates["kill_reason"] = (
                f"[verify:{r['id']}] {r['fail']} — "
                + ", ".join(f"{k}={numbers[k]}" for k in r["keys"])
            )
            return updates

        verif["mode"] = "verified (all numeric rules PASS)"
        # 算术纠错：LLM 判 FAIL 且 REASON 引用了实际通过且评估过的规则
        # → 回环重判（引用未评估规则不纠错——键都没报齐）
        if gate == "FAIL":
            reason_l = parsed.get("reason", "").lower()
            for r in checked:
                if any(c in reason_l for c in r["cites"]):
                    lb = dict(state.get("loop_backs", {}))
                    lb[stage] = lb.get(stage, 0) + 1
                    corrections = dict(state.get("corrections", {}))
                    corrections[stage] = (
                        f"VERIFY CORRECTION: your REASON cited [{r['id']}] "
                        f"but the deterministic check PASSES with your own "
                        f"numbers ("
                        + ", ".join(f"{k}={numbers.get(k)}" for k in r["keys"])
                        + f"). The comparison in your reason was "
                        f"mathematically wrong. Re-evaluate the gate; if you "
                        f"still FAIL, cite a different concrete reason."
                    )
                    updates["gates"] = {**gates, stage: "LOOP-BACK"}
                    updates["loop_backs"] = lb
                    updates["corrections"] = corrections
                    verif["mode"] = (
                        f"OVERRIDE→LOOP-BACK [arithmetic error on {r['id']} "
                        f"corrected]"
                    )
                    break
        return updates

    node.__name__ = f"verify_{stage.lower()}"
    return node


# ===========================================================================
# 节点
# ===========================================================================

def hook_screen_node(state: GrowthLoopState) -> dict[str, Any]:
    """HOOK 门：无数值 hook → 直接 KILL（剧本 GATE H）。

    若 state 已带 hook_evidence（外部批量筛选注入——剧本流程里 HOOK 是
    每周对全 universe 跑一次的，A 名单进入 LOOP 时复用已有证据，不再
    重复取数），则跳过内部筛选只补数据包。
    """
    ticker, date = state["ticker"], state["date"]
    meta = state.get("metadata", {})

    pre = state.get("hook_evidence")
    if pre and pre.get("tripped"):
        hooks = pre
    else:
        enabled = state.get("hooks_enabled") or None
        hooks = screen_hooks(ticker, date, meta["data_client"], enabled=enabled)

    packet = build_data_packet(ticker, date, meta["data_client"])

    updates: dict[str, Any] = {
        "hook_evidence": hooks,
        "data_packet": packet,
        "status": "RUNNING",
        "stage_outputs": {},
        "stage_scores": {},
        "gates": {},
        "loop_backs": {s: 0 for s in _STAGES},
        "tripwires": [],
        "exit_rules": [],
    }
    if not hooks["tripped"]:
        updates["status"] = "KILLED"
        updates["kill_stage"] = "HOOK"
        updates["kill_reason"] = (
            "no numeric hook tripped (GATE H) — "
            f"computed={hooks.get('computed', {})}"
        )
    return updates


def _make_stage_node(stage: str):
    """L1-L7 阶段节点工厂：组 prompt → 调 LLM → 解析门控。"""

    def node(state: GrowthLoopState) -> dict[str, Any]:
        meta = state.get("metadata", {})
        llm = meta.get("llm_client")
        max_lb = meta.get("max_loop_backs", MAX_LOOP_BACKS)
        mandate = state.get("mandate", {})
        min_growth = mandate.get("min_revenue_growth", 0.20)
        target_return = mandate.get("target_return", 0.15)

        # ---- 组装 user prompt：hook 证据 + 数据包 + 前序输出 ----
        hooks = state.get("hook_evidence", {})
        hook_lines = "\n".join(
            f"  {h['id']} {h['name']}: {h['evidence']}"
            for h in hooks.get("tripped", [])
        ) or "  (none)"

        prior = state.get("stage_outputs", {})
        prior_lines = ""
        if prior:
            recent = [s for s in _STAGES if s in prior and s != stage][-3:]
            for s in recent:
                out = prior[s]
                prior_lines += f"\n--- {s} output (abridged) ---\n{out[:2500]}\n"

        loop_note = ""
        loop_backs = state.get("loop_backs", {}).get(stage, 0)
        correction = state.get("corrections", {}).get(stage)
        if loop_backs > 0 or correction:
            prior_gate = state.get("gates", {}).get(stage, "")
            prior_reason = ""
            prev_out = prior.get(stage, "")
            m = _REASON_RE.search(prev_out)
            if m:
                prior_reason = m.group(1).strip()
            loop_note = (
                f"\nNOTE: this is re-run {loop_backs + 1} for stage {stage} "
                f"(prior attempt: {prior_gate} — {prior_reason}). "
                f"You have {max_lb - loop_backs + 1} re-runs left before "
                f"automatic KILL. Provide the missing data or FAIL cleanly.\n"
            )
            if correction:
                loop_note += f"\n{correction}\n"

        instruction = (
            STAGE_PROMPTS[stage]
            .replace("{ticker}", state["ticker"])
            .replace("{min_growth}", f"{min_growth:.0%}")
            .replace("{target_return}", f"{target_return:.0%}")
        )

        user = (
            f"{instruction}\n\n"
            f"HOOK EVIDENCE (why this ticker entered the loop):\n{hook_lines}\n"
            f"\n{state.get('data_packet', '')}\n"
            f"{prior_lines}{loop_note}"
        )

        # ---- 调 LLM ----
        try:
            raw = llm.complete(_system_prompt(mandate), user)
        except Exception as exc:
            return {
                "gates": {**state.get("gates", {}), stage: "FAIL"},
                "stage_outputs": {
                    **state.get("stage_outputs", {}), stage: f"LLM error: {exc}"
                },
                "kill_stage": stage,
                "kill_reason": f"LLM infrastructure error: {exc}",
            }

        parsed = parse_stage_output(raw)
        gate = parsed["gate"]
        reason = parsed["reason"] or "(no reason given)"

        # 无法解析 → 按剧本纪律视为一次 LOOP-BACK（无标签断言被丢弃）
        if gate is None:
            gate = "LOOP-BACK"
            reason = "unparseable stage output (missing GATE block)"

        # ---- L7 专属强制：tripwire 必须有；强空头 → KILL ----
        if stage == "L7":
            if parsed["short_strength"] is not None and parsed["short_strength"] >= 7 \
                    and gate == "PASS":
                gate = "FAIL"
                reason = (
                    f"strong fundamental short "
                    f"(SHORT-STRENGTH={parsed['short_strength']:.0f}/10 ≥ 7)"
                )
            elif gate == "PASS" and not parsed["tripwires"]:
                gate = "LOOP-BACK"
                reason = "L7 PASS requires 3 defined tripwires"

        updates: dict[str, Any] = {
            "stage_outputs": {**state.get("stage_outputs", {}), stage: raw},
            "gates": {**state.get("gates", {}), stage: gate},
        }
        if gate == "FAIL":
            updates["kill_stage"] = stage
            updates["kill_reason"] = reason
        if parsed["score"] is not None:
            updates["stage_scores"] = {
                **state.get("stage_scores", {}), stage: parsed["score"]
            }
        if gate == "LOOP-BACK":
            lb = dict(state.get("loop_backs", {}))
            lb[stage] = lb.get(stage, 0) + 1
            updates["loop_backs"] = lb
        if stage == "L1" and parsed["thesis"]:
            updates["thesis"] = parsed["thesis"]
        if stage == "L5":
            updates["yellow_flags"] = parsed["yellow_flags"]
        if stage == "L7":
            if parsed["tripwires"]:
                updates["tripwires"] = parsed["tripwires"]
            if parsed["short_strength"] is not None:
                updates["short_strength"] = parsed["short_strength"]
        return updates

    node.__name__ = f"stage_{stage.lower()}"
    return node


def l8_conviction_node(state: GrowthLoopState) -> dict[str, Any]:
    """L8：确定性信念计算（LLM 不碰仓位 — 框架的 blend+risk 负责 sizing）。

    conviction = Σ w_s · score_s  (L1 .15 / L2 .20 / L3 .20 / L4 .15 /
                                   L5 .10 / L6 .20)
    黄旗减记：每面 -25%，最多计 2 面（剧本 L8 的 haircut 映射到信念层）。

    无 LLM 回退模式（serenity_gate 路由直达）：stage_scores 为空且带
    serenity_review → conviction = hook 强度 × serenity 分数映射
    （DOWNGRADE ×0.7）——深研层降级运行，确定性审查兜底。
    """
    scores = state.get("stage_scores", {})
    review = state.get("serenity_review")

    if not scores and review and review.get("score") is not None:
        hooks = state.get("hook_evidence", {}).get("tripped") or []
        hook_boost = 1.0 + 0.15 * max(0, len(hooks) - 1)
        ser_mult = (DOWNGRADE_MULT_FALLBACK
                    if review.get("verdict") == "DOWNGRADE" else 1.0)
        conviction = review["score"] * hook_boost * ser_mult
        conviction = min(100.0, conviction)
        exit_rules = [
            "Serenity fallback kill: 毛利率 z-score > 2.0 或季度环比 "
            "转负 → 退出（情景性利润证伪）",
            "Valuation kill: 1 年涨幅超 100% 后再涨 50% → 减半",
            "Time stop: 营收增速连续 2 季回落 → 退出",
            "Re-entry: 仅经完整 loop 或 serenity 复审 PASS",
        ]
        return {
            "status": "PASSED",
            "conviction": round(conviction, 2),
            "exit_rules": exit_rules,
            "thesis": (f"[serenity fallback] score={review['score']} "
                       f"{review.get('reason', '')}"),
            "kill_reason": "", "kill_stage": "",
        }

    missing = [s for s in STAGE_WEIGHTS if s not in scores]
    filled = {s: scores.get(s, 50.0) for s in STAGE_WEIGHTS}

    conviction = sum(w * filled[s] for s, w in STAGE_WEIGHTS.items())
    yellow = int(state.get("yellow_flags", 0) or 0)
    haircut = 1.0 - YELLOW_FLAG_HAIRCUT * min(yellow, 2)
    conviction *= haircut

    tripwires = state.get("tripwires", [])
    thesis = state.get("thesis", "")
    exit_rules = [
        "Thesis kill: any L7 tripwire fires → exit ≥50% within 5 sessions, "
        "re-run loop for remainder"
        + (f" (tripwires: {'; '.join(tripwires)})" if tripwires else ""),
        "Valuation kill: market-implied CAGR rises above BULL scenario → "
        "trim to half",
        "Time stop: BASE-case KPIs miss for 3 consecutive quarters → exit "
        "regardless of price",
        "Re-entry: only via a full loop re-run at the computed trigger price "
        "(market-implied CAGR = BASE); never average down through a tripwire",
    ]

    return {
        "status": "PASSED",
        "conviction": round(conviction, 2),
        "exit_rules": exit_rules,
        "thesis": thesis,
        "kill_reason": "",
        "kill_stage": "",
        "_missing_scores": missing,  # 内部审计用
    }


def kill_node(state: GrowthLoopState) -> dict[str, Any]:
    """终止节点：固化 KILL 日志（edge-improvement dataset）。"""
    updates: dict[str, Any] = {"status": "KILLED"}
    if not state.get("kill_stage"):
        # 从最后一个非 PASS 门控回溯 kill 来源
        gates = state.get("gates", {})
        for s in reversed(_STAGES):
            if gates.get(s) not in (None, "PASS"):
                updates["kill_stage"] = s
                break
        else:
            updates["kill_stage"] = "HOOK"
    if not state.get("kill_reason"):
        stage = updates.get("kill_stage") or state.get("kill_stage") or "?"
        updates["kill_reason"] = (
            f"gate {state.get('gates', {}).get(stage, 'FAIL')} at {stage}"
        )
    return updates


# ===========================================================================
# 路由与建图
# ===========================================================================

def _route_after_hook(state: GrowthLoopState) -> str:
    if state.get("status") == "KILLED":
        return "kill"
    return "serenity_gate"


def serenity_gate_node(state: GrowthLoopState) -> dict[str, Any]:
    """SERENITY 门：确定性卡点审查（serenity-skill 量化层）。

    位置：HOOK（找到高增长）与 L1-L7（LLM 深研）之间。
    - KILL：卡点证据不足 / 情景性毛利率（一次性利润，IVD 型陷阱）
    - DOWNGRADE：证据中等 → 信念 ×0.7（记录在案，L8 参考）
    - PASS：证据充分 → 进入 LOOP

    审查摘要注入 data_packet —— L1-L7 的 LLM 提示词直接看到卡点
    证据链，深研层在确定性审查的地基上工作。
    """
    from src.signals.serenity_gate import serenity_review

    ticker, date = state["ticker"], state["date"]
    meta = state.get("metadata", {})
    mandate = state.get("mandate") or {}
    params = mandate.get("serenity_gate") or None
    if params is not None and "enabled" in params and not params["enabled"]:
        return {"serenity_review": None}   # 显式关闭 → 直通 L1

    try:
        review = serenity_review(
            ticker, date, meta["data_client"],
            hook_evidence=state.get("hook_evidence"),
            params=params)
    except Exception as exc:  # 审查层 fail-open：不因数据缺失挡深研
        return {"serenity_review": {"verdict": "PASS",
                                    "score": None,
                                    "reason": f"review error: {exc}"}}

    updates: dict[str, Any] = {"serenity_review": review}
    if review["verdict"] == "KILL":
        updates["status"] = "KILLED"
        updates["kill_stage"] = "SERENITY"
        updates["kill_reason"] = f"[serenity] {review['reason']}"
        return updates

    # 卡点证据注入数据包（L1-L7 可见）
    summary = (f"\n\n--- SERENITY 卡点审查（确定性层）---\n"
               f"score: {review['score']} | verdict: {review['verdict']}\n"
               f"结构性毛利率 floor: {review.get('gm_floor')}pp | "
               f"情景性 z: {review.get('gm_z')}\n"
               f"1y涨幅 {review.get('runup_1y') and round(review['runup_1y'], 2)}"
               f" | {review['reason']}\n"
               f"LLM 深研应验证：客户为什么绕不开（结构性 vs 情景性）。")
    updates["data_packet"] = (state.get("data_packet") or "") + summary
    return updates


def _route_after_serenity(state: GrowthLoopState) -> str:
    if state.get("status") == "KILLED":
        return "kill"
    meta = state.get("metadata", {})
    # 无 LLM 回退：serenity × hook 直接产出信念（跳过 L1-L7）
    if meta.get("llm_client") is None:
        return "l8_conviction"
    return "L1"


def _make_stage_router(stage: str, next_stage: str):
    """门控路由：PASS→下一阶段 / LOOP-BACK(未超限)→自身 / 其余→KILL。

    回环计数语义：节点在解析到 LOOP-BACK 时递增 loop_backs[stage]，
    路由允许回环当且仅当 loop_backs ≤ max_loop_backs — 即最多 2 次重跑，
    第 3 次 LOOP-BACK 自动 KILL（剧本规则）。
    """

    def router(state: GrowthLoopState) -> str:
        gate = state.get("gates", {}).get(stage)
        if gate == "PASS":
            return next_stage
        max_lb = state.get("metadata", {}).get("max_loop_backs", MAX_LOOP_BACKS)
        if gate == "LOOP-BACK" and state.get("loop_backs", {}).get(stage, 0) <= max_lb:
            return stage  # 回环自身重跑
        return "kill"

    return router


def build_growth_loop_graph() -> Any:
    """构建并编译 LOOP 门控子图。图本身无每运行数据（全部走 state）。

    结构：每个 L 阶段后接一个确定性 verify 节点 —— LLM 报数（NUMBERS
    行），代码复算剧本的数值门控规则并可推翻 LLM 的判决。审视层是图
    的一等节点：无论从 fund 主图（run_analysts → GrowthLoopAgent）还是
    独立 invoke 进入，每次运行都强制经过。
    """
    g = StateGraph(GrowthLoopState)

    g.add_node("hook_screen", hook_screen_node)
    g.add_node("serenity_gate", serenity_gate_node)
    for stage in _STAGES:
        g.add_node(stage, _make_stage_node(stage))
        g.add_node(f"verify_{stage}", _make_verify_node(stage))
    g.add_node("l8_conviction", l8_conviction_node)
    g.add_node("kill", kill_node)

    g.set_entry_point("hook_screen")
    g.add_conditional_edges(
        "hook_screen", _route_after_hook,
        {"kill": "kill", "serenity_gate": "serenity_gate"},
    )
    g.add_conditional_edges(
        "serenity_gate", _route_after_serenity,
        {"kill": "kill", "L1": "L1", "l8_conviction": "l8_conviction"},
    )

    for i, stage in enumerate(_STAGES):
        next_stage = _STAGES[i + 1] if i + 1 < len(_STAGES) else "l8_conviction"
        g.add_edge(stage, f"verify_{stage}")
        g.add_conditional_edges(
            f"verify_{stage}",
            _make_stage_router(stage, next_stage),
            {next_stage: next_stage, stage: stage, "kill": "kill"},
        )

    g.add_edge("l8_conviction", END)
    g.add_edge("kill", END)
    return g.compile()


# 模块级单例：图无可变状态，编译一次反复 invoke。
_GRAPH = None


def run_growth_loop(
    ticker: str,
    date: str,
    data_client: Any,
    llm_client: Any,
    mandate: dict[str, Any] | None = None,
    hooks_enabled: list[str] | tuple[str, ...] | None = None,
    max_loop_backs: int = MAX_LOOP_BACKS,
    hook_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """便捷入口：对一个标的跑完整的 HOOK→L1..L7→L8 门控循环。

    hook_evidence: 外部批量筛选的 screen_hooks/evaluate_hooks 结果。
    提供时 LOOP 复用该证据（剧本流程：HOOK 每周对全 universe 跑一次，
    A 名单直接进 LOOP），不再重复取数。

    Returns: GrowthLoopState 的浅拷贝（含 status / conviction /
    stage_scores / tripwires / kill_reason 等）。
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_growth_loop_graph()

    initial: dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "mandate": mandate or {},
        "hooks_enabled": list(hooks_enabled) if hooks_enabled else None,
        "metadata": {
            "llm_client": llm_client,
            "data_client": data_client,
            "max_loop_backs": max_loop_backs,
        },
    }
    if hook_evidence:
        initial["hook_evidence"] = hook_evidence
    result = _GRAPH.invoke(initial, {"recursion_limit": 80})
    result.pop("metadata", None)  # 不泄漏客户端对象
    return result
