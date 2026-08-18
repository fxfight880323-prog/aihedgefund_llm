# -*- coding: utf-8 -*-
"""ai_fund_framework 整体架构图绘制脚本.

输出: docs/framework_architecture.png (高分辨率, 用于 PDF 报告)
"""
import os
import matplotlib
matplotlib.use("Agg")
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(__file__), ".mplcache"))
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ---------------------------------------------------------------- 字体
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",      # Microsoft YaHei
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]
_font_path = None
for fp in _FONT_CANDIDATES:
    if os.path.exists(fp):
        _font_path = fp
        break
if _font_path:
    fm.fontManager.addfont(_font_path)
    _FONT = fm.FontProperties(fname=_font_path)
    plt.rcParams["font.family"] = _FONT.get_name()
else:
    plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------- 画布
W, H = 19.2, 10.8
fig = plt.figure(figsize=(W, H), dpi=200)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 192)
ax.set_ylim(0, 108)
ax.axis("off")

# ---------------------------------------------------------------- 配色
C = {
    "title_bg": "#F5F7FA",
    "title_fg": "#1F3A5F",
    "config_bg": "#EDE7F6", "config_ed": "#5E35B1",
    "mode_bg": "#FFF3E0", "mode_ed": "#EF6C00",
    "core_bg": "#EEEEEE", "core_ed": "#424242",
    "data_bg": "#E3F2FD", "data_ed": "#1565C0",
    "signal_bg": "#E8F5E9", "signal_ed": "#2E7D32",
    "workflow_bg": "#FFF8E1", "workflow_ed": "#F9A825",
    "portfolio_bg": "#FCE4EC", "portfolio_ed": "#C2185B",
    "risk_bg": "#FFEBEE", "risk_ed": "#C62828",
    "exec_bg": "#E0F7FA", "exec_ed": "#00838F",
    "research_bg": "#F1F8E9", "research_ed": "#558B2F",
    "output_bg": "#ECEFF1", "output_ed": "#37474F",
    "loop_bg": "#FBE9E7", "loop_ed": "#D84315",
}


def box(x, y, w, h, bg, ec, text, fs=9.5, tc="#111111", lw=1.6, weight="normal",
        sub=None, sub_fs=7.6, sub_tc="#555555", rounded=0.06):
    """画一个圆角矩形盒子(带可选副标题)。x,y 为左下角。"""
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounded*h}",
                       fc=bg, ec=ec, lw=lw, zorder=3)
    ax.add_patch(p)
    cy = y + h / 2
    if sub:
        ax.text(x + w / 2, cy + h * 0.16, text, ha="center", va="center",
                fontsize=fs, color=tc, fontweight=weight, zorder=4)
        ax.text(x + w / 2, cy - h * 0.20, sub, ha="center", va="center",
                fontsize=sub_fs, color=sub_tc, zorder=4)
    else:
        ax.text(x + w / 2, cy, text, ha="center", va="center",
                fontsize=fs, color=tc, fontweight=weight, zorder=4)


def chip(x, y, w, h, bg, ec, text, fs=8, tc="#111111", weight="normal"):
    """小胶囊/小盒。"""
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.5",
                       fc=bg, ec=ec, lw=1.2, zorder=3)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, fontweight=weight, zorder=4)


def arrow(x1, y1, x2, y2, color="#666666", lw=2.0, style="-|>", ls="-", ms=16):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=ms,
                        color=color, lw=lw, linestyle=ls, zorder=2)
    ax.add_patch(a)


# ---------------------------------------------------------------- 标题
box(1, 101.5, 190, 6, C["title_bg"], "#B0BEC5", "", sub="", fs=1)
ax.text(96, 104.5, "ai_fund_framework — AI 投资基金框架整体架构",
        ha="center", va="center", fontsize=20, color=C["title_fg"], fontweight="bold")
ax.text(96, 102.4, "LangGraph 编排 · 数据 → 分析师 → 组合 → 风控 → 执行 → 账本 · 五接口可插拔",
        ha="center", va="center", fontsize=9.5, color="#607D8B")

# ---------------------------------------------------------------- 配置层
box(1, 90.5, 190, 8.5, C["config_bg"], C["config_ed"], "配置层  config/  (YAML 声明式)", fs=11, weight="bold",
    sub="基金授权书 funds/*.yaml（策略切片+风控+资金）  ·  策略 strategies/*.yaml（模型组合+混合策略）  ·  mandate 不含标的，标的运行时传入")
chip(4, 92.0, 58, 5, "#D1C4E9", C["config_ed"], "funds/example_fund.yaml  Alpha One", fs=7.5)
chip(66, 92.0, 58, 5, "#D1C4E9", C["config_ed"], "funds/buffett_test.yaml  单模型测试", fs=7.5)
chip(128, 92.0, 58, 5, "#D1C4E9", C["config_ed"], "strategies/*.yaml   fundamental-ls / earnings-drift", fs=7.5)

# ---------------------------------------------------------------- 运行模式
box(1, 79.5, 190, 8, C["mode_bg"], C["mode_ed"], "三种运行模式 — 同一代码路径（只换时钟与券商）", fs=11, weight="bold",
    sub="BACKTEST = 历史时钟 + SimBroker（模拟成交）   PAPER = 实时时钟 + SimBroker   LIVE = 实时时钟 + 真实券商（可插拔）")
chip(8, 81.0, 54, 5.2, "#FFE0B2", C["mode_ed"], "BACKTEST  回测", fs=8.5, weight="bold")
chip(69, 81.0, 54, 5.2, "#FFE0B2", C["mode_ed"], "PAPER  纸面交易", fs=8.5, weight="bold")
chip(130, 81.0, 54, 5.2, "#FFE0B2", C["mode_ed"], "LIVE  实盘（模板）", fs=8.5, weight="bold")

# 配置 → 模式 的箭头
arrow(96, 90.2, 96, 87.9, color=C["config_ed"], lw=2.2)
ax.text(98, 89.0, "load_fund(mandate)", fontsize=8, color=C["config_ed"], va="center")

# 模式 → 引擎
arrow(96, 79.2, 96, 73.4, color=C["mode_ed"], lw=2.2)
ax.text(98, 76.2, "run_fund_cycle(tickers, as_of, capital)", fontsize=8, color=C["mode_ed"], va="center")

# ---------------------------------------------------------------- 核心层 & 数据层（左右并排）
# 核心层
box(1, 53.5, 74, 19, C["core_bg"], C["core_ed"], "核心层  src/core/  （框架契约，勿改）", fs=10.5, weight="bold",
    sub="五个接口 · 数据契约 · 注册表")
chip(3.5, 67.5, 68, 3.6, "#E0E0E0", C["core_ed"], "interfaces.py — AlphaModel / DataClient / BlendPolicy / RiskModel / Broker", fs=7.5)
chip(3.5, 63.2, 68, 3.6, "#E0E0E0", C["core_ed"], "models.py — Signal / Order / Fill / Position / CycleRecord（pydantic 契约）", fs=7.5)
chip(3.5, 58.9, 68, 3.6, "#E0E0E0", C["core_ed"], "fund_spec.py — FundSpec / StrategySpec（YAML → 对象，FUND⊃STRATEGY⊃MODEL）", fs=7.5)
chip(3.5, 54.6, 68, 3.6, "#E0E0E0", C["core_ed"], "registry.py — ALPHA_MODEL / BLEND_POLICY / RISK_MODEL / DATA_CLIENT 注册表", fs=7.5)

# 数据层
box(79, 53.5, 112, 19, C["data_bg"], C["data_ed"], "数据层  src/data/  （DataClient 协议 · point-in-time）", fs=10.5, weight="bold",
    sub="取数多查询+绕缓存重试；真缺的字段显式声明 DATA GAP，禁止静默缺失")
chip(81.5, 67.5, 34, 3.6, "#BBDEFB", C["data_ed"], "fin_datasets_client.py\nfinancialdatasets.ai（美股）", fs=7)
chip(118, 67.5, 34, 3.6, "#BBDEFB", C["data_ed"], "mx_data_client.py\n妙想 MX MCP（A股/港/宏观）", fs=7)
chip(155, 67.5, 33, 3.6, "#BBDEFB", C["data_ed"], "mx_mcp_client.py\nMX 底层 NL 查询", fs=7)
chip(81.5, 63.2, 34, 3.6, "#BBDEFB", C["data_ed"], "cache.py\nDiskCache 磁盘缓存", fs=7)
chip(118, 63.2, 34, 3.6, "#BBDEFB", C["data_ed"], "_template_client.py\n自定义数据源模板", fs=7)
chip(155, 63.2, 33, 3.6, "#BBDEFB", C["data_ed"], "protocol.py\nDataClient 协议", fs=7)
ax.text(96, 56.8, "接口契约：get_prices / get_financial_metrics / get_company_facts / get_earnings",
        ha="center", va="center", fontsize=7.8, color="#1565C0")
ax.text(145, 56.8, "扩展：get_segment_breakdown / get_financial_detail（LOOP 深研用）",
        ha="center", va="center", fontsize=7.8, color="#1565C0")

# 数据层 ↔ 核心层
arrow(78, 64, 75.5, 64, color="#90A4AE", lw=1.6, style="<|-|>", ms=12)

# ---------------------------------------------------------------- 信号层
box(1, 40.5, 190, 10.5, C["signal_bg"], C["signal_ed"], "信号层  src/signals/  — Alpha Models（分析师 · 统一 predict() 接口 → Signal ∈ [-1,+1]）",
    fs=11, weight="bold",
    sub="量化模型 QuantModel（纯代码） 与  LLM Agent（LLMAgent · 智谱 GLM · 只形成观点，不碰仓位）")
# 量化
chip(3, 44.4, 29, 5, "#C8E6C9", C["signal_ed"], "pead\n盈余漂移（美股）", fs=7.4)
chip(34, 44.4, 29, 5, "#C8E6C9", C["signal_ed"], "bsadf\n泡沫择时（PSY2015）", fs=7.4)
chip(65, 44.4, 29, 5, "#C8E6C9", C["signal_ed"], "ashare_value\nA股价值", fs=7.4)
chip(96, 44.4, 29, 5, "#C8E6C9", C["signal_ed"], "rotation_growth\n轮动成长（章宏帆）", fs=7.4)
chip(127, 44.4, 29, 5, "#C8E6C9", C["signal_ed"], "tech_confluence\n科技共振", fs=7.4)
# LLM
chip(158, 44.4, 30, 5, "#A5D6A7", C["signal_ed"], "buffett\n巴菲特 LLM 分析师", fs=7.4)
chip(158, 42.0, 30, 2.0, "#81C784", C["signal_ed"], "", fs=1)
chip(127, 42.0, 29, 5, "#81C784", C["signal_ed"], "growth_loop\nGOAL→HOOK→LOOP 引擎", fs=7.4)

# hooks 说明
ax.text(96, 41.6, "数值化筛选（HOOK 层 hooks.py：H1 营收加速 / H2 毛利拐点 / H3 指引上调链 / H6 回撤后质量）——无数值 hook 无资格深研",
        ha="center", va="center", fontsize=7.4, color="#33691E")

# 核心层 → 信号层（注册表实例化）
arrow(96, 53.2, 96, 51.4, color=C["signal_ed"], lw=2.0)
ax.text(98, 52.2, "registry 按策略 YAML 实例化模型，LLM agent 注入共享 llm_client", fontsize=7.4, color=C["signal_ed"], va="center")

# ---------------------------------------------------------------- 工作流引擎（主图）
box(1, 25.0, 190, 12.5, C["workflow_bg"], C["workflow_ed"], "工作流引擎  src/workflow/  — LangGraph StateGraph（主图 7 节点 · 可检查点/并行/人机协同）",
    fs=11, weight="bold", sub="FundState TypedDict 贯穿全程 · 每节点纯函数 (state)→dict 增量")

# 主图 7 节点横排
steps = [
    ("fetch_data", "取行情", 3.5, 78, 3.4),
    ("run_analysts", "跑分析师", 3.5, 78, 3.4),
    ("blend_signals", "混合信号", 3.5, 78, 3.4),
    ("apply_risk", "风控钳制", 3.5, 78, 3.4),
    ("build_orders", "生成订单", 3.5, 78, 3.4),
    ("execute_orders", "执行成交", 3.5, 78, 3.4),
    ("record_cycle", "记账结 NAV", 3.5, 78, 3.4),
]
x = 3.0
for i, (name, cn, wd, ht, _) in enumerate(steps):
    chip(x, 31.5, 24.5, 4.6, "#FFF9C4", C["workflow_ed"], f"{cn}", fs=8.6, weight="bold")
    ax.text(x + 12.25, 29.2, name, ha="center", va="center", fontsize=7.2, color="#8D6E63")
    if i < len(steps) - 1:
        arrow(x + 27.5, 33.8, x + 29.0, 33.8, color=C["workflow_ed"], lw=1.8)
    x += 27.5

# 主图下方：数据流标注
ax.text(96, 27.2, "数据流：marks(价格) → signals(信念) → convictions/target_weights → final_weights(风控后) → orders → fills → positions/cash/NAV",
        ha="center", va="center", fontsize=7.6, color="#8D6E63")

# 模式 → 引擎
arrow(96, 79.2, 96, 73.4, color=C["mode_ed"], lw=0)  # placeholder no-op

# 信号层 → 引擎 run_analysts
arrow(96, 40.2, 96, 38.0, color=C["workflow_ed"], lw=2.2)
ax.text(98, 39.0, "signals", fontsize=8, color=C["workflow_ed"], va="center")

# ---------------------------------------------------------------- 组合 / 风控 / 执行 / 研究（引擎下方并排）
# 组合层
box(3, 8.5, 45.5, 13.5, C["portfolio_bg"], C["portfolio_ed"], "组合层 src/portfolio/\nBlendPolicy（混合策略）", fs=9.3, weight="bold",
    sub="", rounded=0.05)
chip(5, 14.5, 41, 3.4, "#F8BBD0", C["portfolio_ed"], "conviction_weighted — 信念加权（默认）", fs=7.4)
chip(5, 10.8, 41, 3.4, "#F8BBD0", C["portfolio_ed"], "balanced_sharpness — 有锐度的均衡轮动", fs=7.4)
ax.text(25.75, 9.6, "_template_allocator.py 自定义模板", ha="center", va="center", fontsize=7, color="#AD1457")

# 风控层
box(51.5, 8.5, 44, 13.5, C["risk_bg"], C["risk_ed"], "风控层 src/risk/\nRiskModel（硬上限）", fs=9.3, weight="bold",
    sub="", rounded=0.05)
chip(53.5, 14.5, 39.5, 3.4, "#FFCDD2", C["risk_ed"], "HardLimits：单票 |w|≤max_position_pct", fs=7.4)
chip(53.5, 10.8, 39.5, 3.4, "#FFCDD2", C["risk_ed"], "总毛敞口 Σ|w|≤max_gross_exposure", fs=7.4)
ax.text(73.5, 9.6, "“conviction requests, risk disposes”", ha="center", va="center", fontsize=7, color="#B71C1C")

# 执行层
box(98.5, 8.5, 43.5, 13.5, C["exec_bg"], C["exec_ed"], "执行层 src/execution/\nBroker（订单→成交）", fs=9.3, weight="bold",
    sub="", rounded=0.05)
chip(100.5, 14.5, 39, 3.4, "#B2EBF2", C["exec_ed"], "SimBroker — 模拟成交（回测/纸面）", fs=7.4)
chip(100.5, 10.8, 39, 3.4, "#B2EBF2", C["exec_ed"], "_template_broker.py — 实盘券商模板", fs=7.4)
ax.text(120.25, 9.6, "持有现金+仓位，成交记录进账本", ha="center", va="center", fontsize=7, color="#006064")

# 研究层
box(145, 8.5, 44, 13.5, C["research_bg"], C["research_ed"], "研究层 src/research/\n回测与绩效评估", fs=9.3, weight="bold",
    sub="", rounded=0.05)
chip(147, 14.5, 39.5, 3.4, "#DCEDC8", C["research_ed"], "backtest.py — 全周期回测引擎", fs=7.4)
chip(147, 10.8, 39.5, 3.4, "#DCEDC8", C["research_ed"], "收益/Sharpe/最大回撤等统计", fs=7.4)
ax.text(167, 9.6, "回测即生产，同一代码路径", ha="center", va="center", fontsize=7, color="#33691E")

# 引擎 → 各层
arrow(30, 30.8, 30, 22.4, color=C["portfolio_ed"], lw=1.8)
ax.text(31.5, 26.5, "blend_signals", fontsize=6.6, color=C["portfolio_ed"], rotation=90, va="center")
arrow(73.5, 30.8, 73.5, 22.4, color=C["risk_ed"], lw=1.8)
ax.text(75, 26.5, "apply_risk", fontsize=6.6, color=C["risk_ed"], rotation=90, va="center")
arrow(120.25, 30.8, 120.25, 22.4, color=C["exec_ed"], lw=1.8)
ax.text(121.75, 26.5, "execute_orders", fontsize=6.6, color=C["exec_ed"], rotation=90, va="center")
arrow(167, 30.8, 167, 22.4, color=C["research_ed"], lw=1.8)
ax.text(168.5, 26.5, "backtest", fontsize=6.6, color=C["research_ed"], rotation=90, va="center")

# 各层回流到引擎（组合/风控输出回主图）
arrow(30, 8.3, 30, 3.6, color=C["portfolio_ed"], lw=0)  # no-op

# ---------------------------------------------------------------- 输出层
box(1, 0.5, 190, 6.5, C["output_bg"], C["output_ed"], "输出  CycleRecord — 单周期完整审计轨迹（持久化到账本 ledger）",
    fs=10, weight="bold",
    sub="signals(每分析师信念+论点) · clamps(风控触发事件) · orders / fills(成交) · positions / cash / NAV · metadata(错误与跳过清单) · L8 信念/退出规则/绊线")

# 各层 → 输出
arrow(96, 22.2, 96, 7.4, color=C["output_ed"], lw=2.2)
ax.text(98, 15.0, "record_cycle 汇总", fontsize=7.4, color=C["output_ed"], va="center")

# ---------------------------------------------------------------- LOOP 子图（右侧浮动注释）
# 放在右上角空白区域? 空间有限, 改放底部右侧? 重新规划: 在模式层右侧画 LOOP 子图
box(1, 65.5, 190, 12.5, C["loop_bg"], C["loop_ed"], "成长股决策子图  src/workflow/growth_loop_graph.py  — GOAL→HOOK→LOOP 九阶段门控引擎（GrowthLoopAgent 内部）",
    fs=10.5, weight="bold", sub="LLM 报数（SCORE/GATE/REASON/NUMBERS 机器块）· 确定性 verify 节点复算判门，可推翻 LLM · 回环上限 2 次，第 3 次自动 KILL")

loop_stages = [
    ("hook_screen", "HOOK 数值筛选", "#FFCCBC"),
    ("L1", "商业/TAM", "#FFE0B2"),
    ("L2", "增长持久性", "#FFE0B2"),
    ("L3", "单位经济", "#FFE0B2"),
    ("L4", "护城河", "#FFE0B2"),
    ("L5", "管理层", "#FFE0B2"),
    ("L6", "估值(反向DCF)", "#FFE0B2"),
    ("L7", "空头红队", "#FFE0B2"),
    ("l8", "信念计算", "#C8E6C9"),
    ("kill", "KILL 日志", "#FFCDD2"),
]
x = 3.0
for i, (name, cn, bg) in enumerate(loop_stages):
    wd = 18.2
    chip(x, 70.6, wd, 4.4, bg, C["loop_ed"], cn, fs=7.4, weight="bold")
    ax.text(x + wd / 2, 68.4, name, ha="center", va="center", fontsize=6.4, color="#8D6E63")
    if i < len(loop_stages) - 1:
        arrow(x + wd + 0.4, 72.8, x + wd + 1.0, 72.8, color=C["loop_ed"], lw=1.4)
    x += wd + 1.4
ax.text(96, 66.6, "三向路由：PASS→下一阶段 / LOOP-BACK→回环自身（最多2次）/ 其余→KILL · verify 可因算术错误带纠正回环 · L7 强空头≥7/10 必杀 · 信念=确定性代码（黄旗 -25%/面，LLM 不碰仓位）",
        ha="center", va="center", fontsize=7.2, color="#BF360C")

# LOOP 与信号层连接
arrow(127+14.5+1, 45.2, 127+14.5+1, 42.2, color="#BF360C", lw=0)

fig.savefig(os.path.join(os.path.dirname(__file__), "framework_architecture.png"),
            dpi=200, facecolor="white", bbox_inches="tight")
print("saved OK")
