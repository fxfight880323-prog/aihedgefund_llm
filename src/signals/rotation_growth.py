"""有锐度的均衡 — 章宏帆轮动策略 alpha model (L1/L2/L3-G5/L5)。

实现 spec (zhang-hongfan-strategy-spec.md) 的可代码化核心：

  L1 资产分类器   每只候选归入 A 景气成长 / B 周期成长 / C 新兴成长
                  ——类决定估值逻辑、跟踪 KPI 与卖出规则
  L2 环节稀缺度   先选环节后选股：S1 供给刚性 / S2 需求锁定 / S3 价值份额
                  通胀 / S4 涨价阶段 / S5 成本传导地位，各 0-2 分
  L3-G5 泡沫检验  涨幅分解 return = ΔEPS + ΔPE，ΔPE 主导 → 信念减半
  L5 领先指标     AI 周期仪表盘（可配置，默认中性），≥2/3 领先指标转熊
                  → A 类信念减半

类与环节信息通过 Signal.metadata 流向组合构造器
（src/portfolio/balanced_sharpness.py，L4），由后者完成方向权重、
类配比与单票上限。

数据代理与扩展点（诚实标注）：
  - 渗透率 5% 临界点 → 营收增速 + 加速度代理（真实渗透率数据源待接）
  - G1 跨市场证伪（美股 analog）→ 扩展点，见 TODO
  - G4 两波状态机（现货 KPI → 利润持续性 KPI）→ 扩展点，见 TODO
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import QuantModel
from src.core.models import Signal

# ---------------------------------------------------------------------------
# 默认环节表 — 2026-05 快照 [param]（YAML link_map 可整体覆盖）
# S = [S1供给刚性, S2需求锁定, S3价值份额, S4涨价阶段, S5成本传导] 各0-2
# ---------------------------------------------------------------------------

DEFAULT_LINK_MAP: dict[str, dict[str, Any]] = {
    "光模块/光通信": {
        "s_scores": [2, 2, 2, 1, 2],   # 9/10 — 稀缺度第一
        "keywords": ["光模块", "光通信", "光器件", "光缆", "硅光",
                    "光学光电子", "光纤"],
    },
    "PCB材料": {
        "s_scores": [2, 1, 1, 2, 2],   # 8/10 — 日系垄断上游，涨价早段
        "keywords": ["覆铜板", "CCL", "PCB", "铜箔", "电子布", "印制电路", "生益"],
    },
    "CPU+光芯片": {
        "s_scores": [2, 2, 1, 1, 2],   # 8/10
        "keywords": ["光芯片", "CPU", "处理器", "模拟芯片设计"],
    },
    "国产算力": {
        "s_scores": [1, 2, 1, 1, 2],   # 7/10
        "keywords": ["算力", "GPU", "AI芯片", "图形处理", "智能芯片", "芯原",
                    "IP授权", "数字芯片设计", "集成电路设计"],
    },
    "半导体设备": {
        "s_scores": [1, 1, 1, 1, 2],   # 6/10 — 长周期可见性
        # 注意：不放裸"设备"关键词（避免误吸"医学影像设备"等非半导体行业）
        "keywords": ["半导体设备", "刻蚀", "薄膜沉积", "清洗设备",
                     "离子注入", "光刻"],
    },
    "半导体材料": {
        "s_scores": [2, 1, 1, 1, 2],   # 6/10 — 硅片/电子材料，上游价格制定者
        "keywords": ["硅片", "半导体材料", "电子化学", "靶材", "光刻胶"],
    },
    "晶圆代工": {
        "s_scores": [2, 2, 1, 1, 2],   # 8/10 — 产能稀缺，价格制定者
        "keywords": ["晶圆代工", "晶圆制造", "代工"],
    },
    "电子制造/封测": {
        "s_scores": [1, 1, 1, 0, 0],   # 3/10 — 下游组装/封测：成本承受方
        # （spec S5: upstream price-setter > downstream cost-taker）
        "keywords": ["消费电子", "精密制造", "电子制造", "封测",
                     "元器件", "被动元件", "电子零部件"],
    },
    "存储": {
        "s_scores": [2, 2, 1, 1, 0],   # 6/10 — 涨价中段；模组是成本承受方
        "keywords": ["存储", "内存", "闪存", "DRAM", "NAND", "存储器"],
    },
}

_LINK_FACTORS = ("S1_supply_rigidity", "S2_demand_lockin",
                 "S3_value_share", "S4_price_stage", "S5_passthrough")

# L5 领先指标（3 领先 + 3 验证）；bearish/neutral/bullish
_DEFAULT_DASHBOARD = {
    "frontier_models": "neutral",   # 1 前沿模型迭代
    "frontier_arr": "neutral",      # 2 前沿实验室 ARR 斜率
    "cloud_roi": "neutral",         # 3 云收入 vs 算力 ROI
    "h100_rental": "neutral",       # V1
    "lta_deposits": "neutral",      # V2
    "token_mom": "neutral",         # V3
}
_LEADING = ("frontier_models", "frontier_arr", "cloud_roi")


def _band(x: float | None, low: float, high: float) -> float:
    """把 x 映射到 [0,1]（low→0, high→1）；None → 0.5（不惩罚未知）。"""
    if x is None:
        return 0.5
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (x - low) / (high - low)))


class RotationGrowthModel(QuantModel):
    """章宏帆法 alpha model：分类 → 环节打分 → 类则估值 → G5/L5 修正。"""

    def __init__(
        self,
        link_map: dict[str, dict] | None = None,
        # L1 分类阈值 [param]
        boom_growth: float = 0.50,        # A 类：高增长（渗透率代理）
        emerging_growth: float = 1.50,    # C 类：极端增长
        emerging_max_gm: float = 15.0,    # C 类：无利润上限（毛利率%）
        b_class_max_gm: float = 50.0,     # B 类：周期性毛利率上限（高于此
                                          # = 结构性优质，归 OFF 而非周期）
        off_theme_roe: float = 15.0,      # 自下而上 sleeve 门槛
        off_theme_gm: float = 30.0,
        # 类则估值 [param]
        b_class_pe_ceiling: float = 20.0, # B 类 PE 上限（消费电子核心口径）
        upside_hurdle: float = 0.30,      # A 类 3 年空间代理门槛
        # 质量 [param] — 章宏帆实际持仓全是各环节高质量龙头（旭创/北方
        # 华创/中芯/圣邦…），重视质量甚于增速尖点：
        #   信念 = 增速×环节 × 质量乘数；高质量龙头豁免"加速"一刀切；
        #   OFF sleeve 限科技域；ST 过滤
        min_roe_for_a: float = 8.0,       # A 类 ROE 硬门槛（大市值豁免至 5）
        good_gm: float = 45.0,            # 毛利率质量带（≥45 = 设计/IP 型优）
        bad_gm: float = 20.0,
        good_roe: float = 20.0,
        leader_mcap_tier2: float = 200.0, # 龙头度市值档（亿元）
        leader_mcap_tier1: float = 500.0,
        require_profit: bool = True,      # A 类要求正利润（PE>0）
        quality_lane: bool = True,        # 高质量龙头允许增速回落仍入 A
        pe_ceiling_by_link: dict[str, float] | None = None,  # B 类 PE 上限
        # 按环节覆盖（spec 的 20x 是消费电子核心口径；设备/材料龙头
        # 估值中枢不同，硬套 20x 会把北方华创们全部轮出）
        st_filter: bool = True,           # ST/*ST 直接 abstain
        off_theme_scope: list[str] | None = None,  # OFF sleeve 行业域关键词
        # G5 / L5 [param]
        g5_pe_dominance: float = 0.30,    # ΔPE 主导判定阈值
        ai_dashboard: dict[str, str] | None = None,
        lookback_years: float = 3.0,
        **kwargs,
    ):
        self._link_map = link_map or DEFAULT_LINK_MAP
        self._boom_growth = boom_growth
        self._emerging_growth = emerging_growth
        self._emerging_max_gm = emerging_max_gm
        self._b_class_max_gm = b_class_max_gm
        self._off_theme_roe = off_theme_roe
        self._off_theme_gm = off_theme_gm
        self._pe_ceiling = b_class_pe_ceiling
        self._min_roe_a = min_roe_for_a
        self._good_gm, self._bad_gm = good_gm, bad_gm
        self._good_roe = good_roe
        self._mc_t2, self._mc_t1 = leader_mcap_tier2, leader_mcap_tier1
        self._require_profit = require_profit
        self._quality_lane = quality_lane
        self._pe_by_link = pe_ceiling_by_link or {}
        self._st_filter = st_filter
        self._off_scope = off_theme_scope if off_theme_scope is not None else [
            "电子", "通信", "计算机", "半导体", "软件", "芯片", "光电",
            "数据中心", "人工智能", "元器件", "光学", "军工"]
        self._upside_hurdle = upside_hurdle
        self._g5_threshold = g5_pe_dominance
        dash = dict(_DEFAULT_DASHBOARD)
        dash.update(ai_dashboard or {})
        self._dashboard = dash
        self._lookback_years = lookback_years
        self._series_cache: dict[str, tuple[str, dict]] = {}

    @property
    def name(self) -> str:
        return "rotation_growth"

    # ------------------------------------------------------------------

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        series = self._load_series(ticker, date, data_client)
        rev_yoy = series["rev_yoy"]
        gm = series["gm"]
        if not rev_yoy:
            return self._abstain(ticker, date, "no revenue history")

        growth = rev_yoy[0]
        accel = len(rev_yoy) >= 2 and rev_yoy[0] > rev_yoy[1]
        gm_now, gm_prev = (gm[0] if len(gm) > 0 else None,
                           gm[1] if len(gm) > 1 else None)
        gm_recovering = (gm_now is not None and gm_prev is not None
                         and gm_now > gm_prev)

        # 环节注入优先（龙头直取：环节由选股器查询给定，非关键词猜测）
        assigned = series.get("assigned_link")
        if assigned and assigned in self._link_map:
            link = assigned
            s_scores = list(self._link_map[assigned].get("s_scores", [0] * 5))
        else:
            link, s_scores = self._match_link(ticker, series)
        link_score = sum(s_scores) if s_scores else None
        link_norm = (link_score / 10.0) if link_score is not None else 0.0

        # 全局科技域门：无环节匹配且行业在域外 → abstain（任何类）。
        # 环节匹配的名字天然在域内（环节表本身是数字经济链）。
        if link is None:
            scope_text = " ".join(filter(None, [
                series.get("sector") or "", series.get("industry") or ""]))
            if scope_text and not any(
                    k in scope_text for k in self._off_scope):
                return self._abstain(
                    ticker, date,
                    f"out of digital-economy scope: {scope_text[:40]}")

        # ---- 质量分（Q）：章宏帆持仓全是环节内高质量龙头 ----
        roe = series["roe"]
        pe = series["pe"]
        mcap = series.get("market_cap")          # 亿元
        name_text = str(series.get("name") or "") + ticker
        if self._st_filter and ("ST" in name_text.upper()):
            return self._abstain(ticker, date, "ST/*ST filtered")

        q_gm = _band(gm_now, self._bad_gm, self._good_gm)
        q_roe = _band(roe, 0.0, self._good_roe)
        is_leader = (mcap is not None and mcap >= self._mc_t2)
        is_big_leader = (mcap is not None and mcap >= self._mc_t1)
        profitable = (pe is None) or (pe > 0)    # PE 未知不惩罚
        quality_mult = 0.55 + 0.25 * q_gm + 0.15 * q_roe \
            + (0.15 if is_big_leader else 0.10 if is_leader else 0.0) \
            + (0.05 if profitable else -0.25)
        quality_mult = max(0.30, min(1.15, quality_mult))

        # ---- L1 分类（C 极端/低质 → A 高增(含质量豁免通道) → B 周期 → OFF）----
        low_quality_growth = (roe is not None and roe < 5) or not profitable
        if (growth >= self._emerging_growth
                and ((gm_now is not None and gm_now < self._emerging_max_gm)
                     or low_quality_growth)):
            asset_class = "C"
        elif growth >= self._boom_growth and accel:
            # A 类质量门槛：ROE≥8（大市值龙头豁免至 5）+ 正利润
            roe_gate = roe is None or roe >= (
                5.0 if is_leader else self._min_roe_a)
            if self._require_profit and not profitable:
                return self._abstain(
                    ticker, date,
                    f"[A] loss-making high-growth downgraded: "
                    f"growth={growth:+.0%} but PE={pe} — fails quality "
                    f"gate (spec: boom leaders are profitable)")
            if not roe_gate:
                # 高增速低 ROE → 降级 C 小仓位（他的书里这类是摩尔线程们）
                asset_class = "C"
            else:
                asset_class = "A"
        elif (self._quality_lane
              and growth >= (self._boom_growth * 0.5 if is_big_leader
                             else self._boom_growth * 0.6)
              and roe is not None and roe >= (5 if is_big_leader else 15)
              and gm_now is not None
              and gm_now >= 30 and is_leader):
            # 质量豁免通道：龙头(市值≥200亿)+ROE≥15+毛利≥30，增速从顶点
            # 自然回落但仍 ≥30% → 仍入 A（打 0.85 折）——旭创/北方华创类
            asset_class = "A"
            quality_mult *= 0.85
        elif ((gm_recovering or accel) and 0 < growth < self._boom_growth
                and (gm_now is not None and gm_now < self._b_class_max_gm)):
            # B 周期成长：毛利率回升或增速拐点（新曲线 inflecting）皆可
            asset_class = "B"
        elif (is_big_leader and 0 < growth < self._boom_growth
                and link is not None):
            # B 成熟龙头通道：≥500亿 + 正增长 + 有环节归属——中芯/华虹/
            # 建滔式产能稀缺龙头，无加速无毛利回升但有方向卡位
            asset_class = "B"
        elif (roe is not None
                and roe >= (8 if is_big_leader else self._off_theme_roe)
                and gm_now is not None and gm_now >= self._off_theme_gm):
            # OFF sleeve 限科技域（数字经济基金语境：补涨的强基本面科技股，
            # 不是地产/矿业/ST）
            scope_text = " ".join(filter(None, [
                series.get("sector") or "", series.get("industry") or ""]))
            if not any(k in scope_text for k in self._off_scope):
                return self._abstain(
                    ticker, date,
                    f"off-theme out of scope: {scope_text[:40]}")
            asset_class = "OFF"
        else:
            return self._abstain(
                ticker, date,
                f"not investable under framework: growth={growth:+.0%}, "
                f"accel={accel}, gm_recovering={gm_recovering}",
            )

        # ---- 类则估值 + 信念（质量乘数统一作用）----
        g5 = self._g5_decomposition(series)
        g5_penalty = 0.5 if g5.get("pe_dominant") else 1.0

        if asset_class == "A":
            # 忽略静态 PE：增长质量 × 环节稀缺度；3 年空间代理 vs 门槛
            upside_proxy = growth * (1 + (gm_now or 0) / 100.0)
            if upside_proxy < self._upside_hurdle:
                value = 0.15  # 空间不足 → 极低参与
            else:
                value = min(1.0, 0.30 + 0.50 * link_norm
                            + 0.20 * min(growth, 1.0))
        elif asset_class == "B":
            pe = series["pe"]
            ceiling = self._pe_by_link.get(link, self._pe_ceiling)
            if is_big_leader:
                ceiling *= 2  # 成熟龙头估值容忍度加倍（产能稀缺溢价）
            if pe is not None and pe > ceiling:
                # 估值上限强制：超限 → 减仓/轮出信号（负信念）
                value = -0.5
            elif pe is not None and pe <= 0:
                # 负 PE = 亏损：周期成熟类不容亏（spec B 类是"成熟大公司
                # +周期+新曲线"），直接 abstain 处理由 OFF/其他类判定
                return self._abstain(
                    ticker, date,
                    f"[B] loss-making (PE={pe:.0f}) — cyclical-mature "
                    f"class requires profitability")
            else:
                value = min(0.8, 0.30 + 0.40 * link_norm
                            + (0.20 if gm_recovering else 0.0))
        elif asset_class == "C":
            value = min(0.30, 0.20 + 0.10 * link_norm)  # 小仓位参与
        else:  # OFF：自下而上 sleeve，小幅参与
            value = min(0.40, 0.20
                        + 0.10 * min((series["roe"] or 0) / 30.0, 1.0))

        value *= quality_mult * g5_penalty

        # ---- L5 regime：≥2/3 领先指标转熊 → A 类减半 ----
        regime = "neutral"
        bearish = sum(1 for k in _LEADING
                      if self._dashboard.get(k) == "bearish")
        if bearish >= 2:
            regime = "de-risk"
            if asset_class == "A":
                value *= 0.5

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=round(max(-1.0, min(1.0, value)), 4),
            reasoning=self._reasoning(asset_class, link, link_score, growth,
                                      accel, gm_recovering, series, g5, regime),
            components={
                "link_score": link_score if link_score is not None else 0.0,
                "growth": round(growth, 4),
                "valuation": round(value / g5_penalty, 4),
                "g5_penalty": g5_penalty,
            },
            metadata={
                "asset_class": asset_class,
                "link": link,
                "s_scores": dict(zip(_LINK_FACTORS, s_scores)) if s_scores else {},
                "link_score": link_score,
                "g5": g5,
                "regime": regime,
                "dashboard": self._dashboard,
                # 扩展点
                "g1_cross_market": None,   # TODO: 美股 analog 证伪
                "g4_two_wave": None,       # TODO: 现货KPI→利润持续性KPI
            },
        )

    # ------------------------------------------------------------------
    # 环节匹配（L2）：优先级 = S 分降序，首个关键词命中即归属
    # ------------------------------------------------------------------

    def _match_link(self, ticker: str, series: dict) -> tuple[str | None, list[int] | None]:
        # 只用 行业+名称 匹配（概念标签 blob 会把 PCB 厂匹配进光模块）
        text = " ".join(filter(None, [
            series.get("name") or "", series.get("industry") or "",
        ]))
        ordered = sorted(
            self._link_map.items(),
            key=lambda kv: -sum(kv[1].get("s_scores", [0])),
        )
        for link_name, cfg in ordered:
            kws = cfg.get("keywords") or []
            if isinstance(kws, str):
                kws = [kws]
            if any(kw.lower() in text.lower() for kw in kws):
                return link_name, list(cfg.get("s_scores", [0] * 5))
        return None, None

    # ------------------------------------------------------------------
    # G5-lite：涨幅分解 return = ΔEPS + ΔPE（数据可得窗口内）
    # ------------------------------------------------------------------

    @staticmethod
    def _g5_decomposition(series: dict) -> dict[str, Any]:
        ni = [v for v in series.get("net_income_series") or [] if v]
        pe = [v for v in series.get("pe_series") or [] if v]
        if len(ni) < 2 or len(pe) < 2 or ni[-1] == 0 or pe[-1] == 0:
            return {"available": False}
        eps_growth = ni[0] / abs(ni[-1]) - 1.0 if ni[-1] else 0.0
        pe_change = pe[0] / pe[-1] - 1.0
        pe_dominant = (pe_change > 0.30 and abs(pe_change) > abs(eps_growth))
        return {
            "available": True,
            "eps_growth": round(eps_growth, 4),
            "pe_change": round(pe_change, 4),
            "pe_dominant": pe_dominant,
        }

    # ------------------------------------------------------------------
    # 数据加载（point-in-time）
    # ------------------------------------------------------------------

    def _load_series(self, ticker: str, date: str, data_client: Any) -> dict:
        cached_date, cached = self._series_cache.get(ticker, ("", {}))
        if cached and cached_date >= date:
            return cached

        from datetime import datetime, timedelta
        as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        start = (as_of - timedelta(days=int(365 * self._lookback_years))).isoformat()

        rows = []
        facts = {}
        try:
            rows = [
                r for r in (data_client.get_financial_metrics(
                    ticker, date, limit=60) or [])
                if isinstance(r, dict)
                and str(r.get("date") or "")[:10] <= date[:10]
            ]
        except Exception:
            rows = []
        try:
            facts = data_client.get_company_facts(ticker) or {}
        except Exception:
            facts = {}

        # 妙想报表是年内累计值（一季报=3个月/中报=6个月/…），YoY 必须
        # 同期对齐（一季报 vs 上年一季报）；日频估值行按月份锚点排除。
        def _qkey(row):
            d = str(row.get("date") or "")[:10]
            if len(d) != 10 or not d[:4].isdigit():
                return None
            return (int(d[:4]),
                    {"03": 1, "06": 2, "09": 3, "12": 4}.get(d[5:7]))

        rev_by_qp: dict[tuple, float] = {}
        ni_by_qp: dict[tuple, float] = {}
        gm = []
        roe = None
        for r in rows:  # rows 已 newest-first
            qk = _qkey(r)
            if qk is None:
                continue
            # 注意：QuantModel._safe_float(None) 返回 0.0（默认值语义），
            # 缺失字段必须先判原始值，否则 ROE 缺失会被当成 0 → 低质量
            for target, field in ((rev_by_qp, "revenue"),
                                  (ni_by_qp, "net_income")):
                raw = r.get(field)
                if raw is not None:
                    v = self._safe_float(raw)
                    if v is not None and v != 0:
                        target.setdefault(qk, v)
            if r.get("gross_margin") is not None:
                gm.append(self._safe_float(r["gross_margin"]))
            if roe is None and r.get("roe") is not None:
                roe = self._safe_float(r["roe"])

        rev_yoy = []
        for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
            prev = rev_by_qp.get((y - 1, q))
            if prev and prev > 0:
                rev_yoy.append(v / prev - 1.0)

        pe_series = [self._safe_float(r["pe_ratio"]) for r in rows
                     if r.get("pe_ratio") is not None]

        # 市值（亿元）：metrics 行或 facts 提供（选股器 adapter 传）
        mcap = None
        for r in rows:
            if r.get("market_cap") is not None:
                mcap = self._safe_float(r["market_cap"])
                break
        if mcap is None and facts.get("market_cap") is not None:
            mcap = self._safe_float(facts["market_cap"])
        if mcap is not None and mcap > 1e6:      # 元 → 亿元
            mcap = mcap / 1e8

        series = {
            "rev_yoy": rev_yoy, "gm": gm,
            "net_income_series": [v for _, v in sorted(ni_by_qp.items(),
                                                       reverse=True)],
            "pe_series": pe_series,
            "pe": pe_series[0] if pe_series and pe_series[0] else None,
            "roe": roe, "market_cap": mcap,
            "name": facts.get("name"), "sector": facts.get("sector"),
            "industry": facts.get("industry"),
            "assigned_link": facts.get("link"),
        }
        self._series_cache[ticker] = (date, series)
        return series

    # ------------------------------------------------------------------

    @staticmethod
    def _reasoning(cls_, link, link_score, growth, accel, gm_rec, series,
                   g5, regime) -> str:
        pe = series.get("pe")
        roe = series.get("roe")
        mcap = series.get("market_cap")
        mcap_s = f"{mcap:.0f}亿" if isinstance(mcap, (int, float)) else "-"
        g5_s = (f"G5: ΔEPS={g5['eps_growth']:+.0%} ΔPE={g5['pe_change']:+.0%}"
                f"{' [PE主导→信念减半]' if g5.get('pe_dominant') else ''}"
                ) if g5.get("available") else "G5: n/a"
        return (
            f"[{cls_}] growth={growth:+.0%}(accel={accel}) "
            f"gm_cycle={'↑' if gm_rec else '→'} PE={pe} ROE={roe} "
            f"mcap={mcap_s} "
            f"link={link}({link_score if link_score is not None else '-'}/10) "
            f"{g5_s} regime={regime}"
        )

    def _abstain(self, ticker: str, date: str, why: str) -> Signal:
        return Signal(
            model_name=self.name, ticker=ticker, date=date, value=0.0,
            reasoning=why, metadata={"abstained": True},
        )
