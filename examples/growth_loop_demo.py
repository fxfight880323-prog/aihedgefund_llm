"""GOAL→HOOK→LOOP 成长股决策引擎 Demo。

三段演示（默认全部离线可跑，无需 API key）：

  ① HOOK 全 universe 筛选 — 数值化 hook（H1/H2/H3/H6）+ A/B/C 优先级
  ② LOOP 全流程 — A 优先级标的过 L1-L7 门控子图（MockLLM 脚本化输出）
     + L8 确定性信念 → Signal
  ③ 说明实盘模式（ZHIPU_API_KEY + MXDataClient）

Run:
    python examples/growth_loop_demo.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.signals.growth_loop import GrowthLoopAgent
from src.signals.hooks import screen_universe
from src.workflow.growth_loop_graph import run_growth_loop, STAGE_WEIGHTS


# ===========================================================================
# Mock 数据：三个不同画像的标的
# ===========================================================================

class MockGrowthClient:
    """合成 DataClient：GROWTH（加速成长）/ STALE（减速）/ DARK（无数据）。"""

    # newest-first，与 revenue/gm 列表的顺序严格对齐（GLM-4 红队曾抓到
    # 日期升序 + 数值降序的错位 bug——日期标签必须与数值时序一致）
    _QUARTERS = [
        "2026-12-31", "2026-09-30", "2026-06-30", "2026-03-31",
        "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31",
    ]

    def __init__(self):
        # GROWTH：营收 YoY 连续加速（→ H1），毛利率环比上行（→ H2）
        # newest-first：最新季度在前。
        grow_rev = list(reversed([100, 108, 118, 132, 148, 175, 211, 251]))
        gm = [43.0, 42.6, 42.1, 41.5, 41.0, 40.6, 40.2, 40.0]  # 最新 43.0
        # 价格（收尾对齐 AS_OF=2026-12-31）：慢涨 → 冲顶 362 → 回落 ~47%（→ H6）
        price = [
            100 + i * 1.2 for i in range(120)   # 慢涨
        ] + [
            244 + i * 2.0 for i in range(60)    # 冲顶 362
        ] + [
            362 * (0.992 ** i) for i in range(80)  # 回落至 ~191 (-47%)
        ]
        self._profiles = {
            "GROWTH.SH": {"revenue": grow_rev, "gm": gm, "price": price},
            # STALE：营收减速（→ 无 H1），毛利率下行（→ 无 H2），无回撤
            "STALE.SH": {
                "revenue": list(reversed([100, 140, 190, 240, 275, 295, 305, 308])),
                "gm": [38, 39, 40, 41, 42, 43, 44, 45],  # 最新 38（下行）
                "price": [100 * (1 + 0.002 * i) for i in range(260)],
            },
        }

    def _profile(self, ticker):
        return self._profiles.get(ticker)

    # ---- DataClient 协议 ----
    def get_prices(self, ticker, start_date, end_date):
        p = self._profile(ticker)
        if not p:
            return []
        from datetime import date, timedelta
        # 价格序列收尾对齐 AS_OF，保证 1 年回看窗口内有数据
        d0 = date(2026, 12, 31) - timedelta(days=len(p["price"]) - 1)
        bars = []
        for i, c in enumerate(p["price"]):
            d = (d0 + timedelta(days=i)).isoformat()
            if start_date <= d <= end_date:
                bars.append({"time": d, "open": c * 0.99, "high": c * 1.01,
                             "low": c * 0.98, "close": c, "volume": 1e6,
                             "amount": c * 1e6})
        return bars

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        p = self._profile(ticker)
        if not p:
            return []
        rows = []
        for i, q in enumerate(self._QUARTERS):  # lists already newest-first
            if q > end_date:
                continue
            rows.append({
                "ticker": ticker, "date": q, "period": period,
                "revenue": p["revenue"][i],
                "gross_margin": p["gm"][i],
                "net_margin": p["gm"][i] - 20,
                "roe": 18.0,
                "pe_ratio": 45.0 - i,
            })
        return rows

    def get_company_facts(self, ticker):
        if not self._profile(ticker):
            return None
        return {
            "ticker": ticker, "sector": "半导体", "industry": "AI 芯片",
            "description": (
                "AI 推理芯片设计商（季度营收单位：百万元，最新季度 2.51 亿"
                "元，年化约 10 亿元）。主营构成：云端推理加速卡 68%（毛利"
                "率 47%，YoY +110%）、边缘端 SoC 24%（毛利率 35%，YoY "
                "+45%）、IP 授权 8%。客户分散：前五大合计 18%，最大单一"
                "客户 9%。可服务市场：约 150 家客户 × 平均年采购 1.5-2 亿"
                "元 ≈ TAM 300 亿元（公司口径 320 亿，一致）；市占率 3%，"
                "S 曲线早期。运营指标：NRR 118%（近四季 115/117/119/118），"
                "客户留存率 96%，季度净增客户 25→32→40→48 家；定价年均提"
                "升约 3%；无并购。营业利润率 12%→15%→19%→23%（近四季），"
                "增量营业利润/增量营收约 38%；SBC 占营收 8%，股本稀释 "
                "1.5%/年；净现金 30 亿元，市值 280 亿元（股本 10 亿股 × "
                "28 元）。过去 8 个季度业绩指引 7 次超越、1 次符合，无"
                " KPI 下架记录；高管薪酬与 FCF/每股指标挂钩。护城河证据："
                "连续两年提价 3-5% 且客户零流失（NRR 118%），投标胜率从 "
                "35% 升至 42%，毛利率 43% 高出行业均值 23% 约 20 个百分"
                "点；CUDA 生态迁移成本构成转换壁垒。颠覆监测（季度跟踪）："
                "单 token 推理成本下降曲线、海外大厂中国特供芯片动向、"
                "开源推理框架（vLLM 类）对自研软件栈的替代进度。可比公司："
                "寒武纪（PS 42x）、海光信息（PS 25x）、澜起科技（PS 20x）。"
            ),
        }

    def get_earnings(self, ticker):
        return None  # 无 eps_surprise 数据 → H3 abstain（正确降级）


# ===========================================================================
# MockLLM：脚本化的 LOOP 阶段输出（离线演示 + 测试复用同款模式）
# ===========================================================================

class ScriptedLoopLLM:
    """按阶段脚本输出。script: {"L1": ("PASS", 80), "L3": ("FAIL", 30), ...}

    行为关键字：PASS / FAIL / LOOPBACK_ONCE / LOOPBACK_TWICE /
    LOOPBACK_ALWAYS（永远回环直到被回环上限 KILL）/ GARBAGE（无机器块）/
    PASS_BARE（PASS 但 L7 不带 TRIPWIRES — 用于测试 L7 强制规则）
    L7 额外输出 TRIPWIRES + SHORT-STRENGTH。
    """

    def __init__(self, script=None, default_score=75, short_strength=4,
                 yellow_flags=1, numbers=None, fail_reason="scripted demo output"):
        self.script = script or {}
        self.default_score = default_score
        self.short_strength = short_strength
        self.yellow_flags = yellow_flags
        # numbers: {stage: "k=v; k=v"} 覆盖默认 NUMBERS（测试算术审视用）
        self.numbers = numbers or {}
        self.fail_reason = fail_reason
        self.calls: list[str] = []
        self.prompts: list[str] = []   # 记录 user_prompt，供审视注入断言

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        stage = "?"
        for s in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"):
            if f"Stage {s}" in user_prompt:  # L7 的标题带括号后缀，不能带冒号匹配
                stage = s
                break
        self.calls.append(stage)
        self.prompts.append(user_prompt)
        entry = self.script.get(stage, "PASS")
        if isinstance(entry, tuple):
            behavior, score = entry[0], float(entry[1])
        else:
            behavior, score = entry, self.default_score
        loopbacks = sum(1 for c in self.calls if c == stage) - 1

        if behavior == "GARBAGE":
            return "I think this company is quite interesting overall."
        if behavior == "LOOPBACK_ONCE" and loopbacks < 1:
            gate = "LOOP-BACK"
        elif behavior in ("LOOPBACK_TWICE", "LOOPBACK_ALWAYS") and (
            loopbacks < 2 or behavior == "LOOPBACK_ALWAYS"
        ):
            gate = "LOOP-BACK"
        else:
            gate = "FAIL" if behavior == "FAIL" else "PASS"

        out = [f"[HARD] revenue data from filings. [EST] scenario math shown.",
               f"[HEUR] moat direction judgment."]
        if stage == "L1":
            out.append("THESIS: durable 30%+ grower with widening moat at a "
                       "reasonable expectations price.")
            out.append(self.numbers.get(
                "L1", "NUMBERS: claimed_tam=300; bottomup_tam=280"))
        if stage == "L2":
            out.append(self.numbers.get(
                "L2", "NUMBERS: current_growth=0.30; growth_floor=0.20; "
                      "base_cagr=0.25"))
        if stage == "L3":
            out.append(self.numbers.get(
                "L3", "NUMBERS: incremental_margin=0.38; "
                      "current_op_margin=0.15"))
        if stage == "L5":
            out.append(f"YELLOW-FLAGS: {self.yellow_flags}")
        if stage == "L6":
            out.append(self.numbers.get(
                "L6", "NUMBERS: implied_cagr=0.20; base_cagr=0.25; "
                      "base_return=0.18; bear_return=-0.20"))
        if stage == "L7" and behavior != "PASS_BARE":
            out += [
                "TRIPWIRES:", "1) NRR falls below 110% for 2 quarters",
                "2) gross margin misses guidance by >200bps",
                "3) top customer >15% of revenue and vertically integrates",
                f"SHORT-STRENGTH: {self.short_strength}",
            ]
        out.append(f"SCORE: {score}")
        out.append(f"GATE: {gate}")
        out.append(f"REASON: {self.fail_reason}")
        return "\n".join(out)


# ===========================================================================
# 演示
# ===========================================================================

AS_OF = "2026-12-31"
UNIVERSE = ["GROWTH.SH", "STALE.SH", "DARK.SH"]


def section(title):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def demo_hooks(data):
    section("① HOOK 筛选 — 数值化触发 (PROMPT H-1 等价物)")
    ranked = screen_universe(UNIVERSE, AS_OF, data)
    for tier, label in (("A", "A — 本周进入 LOOP"), ("B", "B — 观察"), ("C", "C — 丢弃")):
        print(f"\n  [{label}]")
        for item in ranked[tier]:
            hooks = ", ".join(item["hooks"]) or "无"
            yoy = item["latest_yoy"]
            print(f"    {item['ticker']:10s} hooks={hooks:8s} "
                  f"最新营收YoY={yoy:+.1%}")
            for d in item["detail"]:
                print(f"      └─ {d['id']}: {d['evidence']}")
    return ranked


def demo_loop(data, a_list):
    section("② LOOP 门控子图 — L1→L7 红队 → L8 确定性信念 (MockLLM)")
    ticker = a_list[0]["ticker"] if a_list else "GROWTH.SH"

    llm = ScriptedLoopLLM(script={
        "L1": ("PASS", 80), "L2": ("PASS", 85), "L3": ("PASS", 75),
        "L4": ("PASS", 70), "L5": ("PASS", 90), "L6": ("PASS", 78),
        "L7": ("PASS", 75),
    }, default_score=75, short_strength=4)

    result = run_growth_loop(ticker, AS_OF, data, llm, mandate={
        "target_return": 0.15,
        "return_objective": "15% annualized over 3+ years",
        "horizon": "3-year minimum hold",
        "min_revenue_growth": 0.20,
    })

    print(f"  标的: {ticker}    LLM 调用序列: {' → '.join(llm.calls)}")
    print(f"\n  状态: {result['status']}")
    print(f"  一句话论点: {result.get('thesis', '')}")
    print(f"\n  各阶段门控:")
    for s in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        gate = result.get("gates", {}).get(s, "-")
        score = result.get("stage_scores", {}).get(s, "-")
        weight = STAGE_WEIGHTS.get(s, "-")
        lb = result.get("loop_backs", {}).get(s, 0)
        lb_s = f" (回环×{lb})" if lb else ""
        print(f"    {s}  GATE={gate:9s} SCORE={score:>5} 权重={weight}{lb_s}")
    if result["status"] != "PASSED":
        print(f"\n  KILLED @ {result.get('kill_stage')}: {result.get('kill_reason')}")
        print("  （kill 日志 = 剧本的 edge-improvement dataset）")
    else:
        print(f"\n  L8 确定性信念:")
        yf = result.get("yellow_flags", 0)
        print(f"    加权分 = Σ w·score = "
              f"{sum(STAGE_WEIGHTS[s] * result['stage_scores'][s] for s in STAGE_WEIGHTS):.1f}")
        print(f"    黄旗减记: {yf} 面 × -25% → conviction = {result['conviction']:.1f}/100")
    print(f"\n  L7 Tripwires (L9 监测绊线):")
    for tw in result.get("tripwires", []):
        print(f"    ⚡ {tw}")
    print(f"\n  L8 预承诺退出规则 (不可在入场后修改):")
    for i, rule in enumerate(result.get("exit_rules", []), 1):
        print(f"    {i}. {rule}")

    section("③ Signal 映射 — GrowthLoopAgent 注册表适配器")
    agent = GrowthLoopAgent(llm_client=ScriptedLoopLLM(default_score=75))
    sig = agent.predict(ticker, AS_OF, data)
    print(f"  model={sig.model_name}  ticker={sig.ticker}")
    print(f"  value={sig.value:+.3f}  (= conviction/100，多头信念)")
    print(f"  reasoning: {sig.reasoning}")
    print(f"  components (各阶段分): {sig.components}")
    print(f"  metadata.status={sig.metadata.get('status')}  "
          f"tripwires={len(sig.metadata.get('tripwires', []))}  "
          f"yellow_flags={sig.metadata.get('yellow_flags')}")

    print("\n  --- 对比：无 hook 的标的 (STALE) — GATE H 直接拦截 ---")
    sig_stale = agent.predict("STALE.SH", AS_OF, data)
    print(f"  STALE.SH  value={sig_stale.value:+.3f}  abstained="
          f"{sig_stale.metadata.get('abstained')}")
    print(f"  reasoning: {sig_stale.reasoning[:80]}...")

    section("实盘模式")
    print("  export ZHIPU_API_KEY=...  # 或 .env；LLM 阶段走智谱 GLM-4")
    print("  from src.data.mx_data_client import MXDataClient")
    print("  agent = GrowthLoopAgent()  # runner 会自动注入 llm_client")
    print("  record = run_fund_cycle('config/funds/growth_demo.yaml',")
    print("              tickers=['688012.SH', ...], data_client=MXDataClient())")


def main():
    print("=" * 72)
    print("  GOAL→HOOK→LOOP 成长股决策引擎 Demo (全离线 · MockLLM)")
    print("=" * 72)
    data = MockGrowthClient()
    ranked = demo_hooks(data)
    demo_loop(data, ranked["A"])
    print("\n" + "=" * 72)
    print("  Demo 完成")
    print("=" * 72)


if __name__ == "__main__":
    main()
