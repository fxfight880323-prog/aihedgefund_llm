"""vnpy 式策略模板 + 章宏帆轮动策略回测封装。

对应 vnpy_portfoliostrategy/template.py：
  StrategyTemplate.on_bars(bars) / set_target / rebalance_portfolio
  —— 策略只给目标仓位，引擎按 vnpy 语义在下一期撮合。

RotationStrategy：调仓月（报告披露截止日后的第一个月末）执行
  ① 点时财务过滤（只看当时已披露的报告期）
  ② 动态行业发现 —— 每期用成分股基本面（增长广度/加速度/毛利率
     趋势/增长水平）重建各行业 S1-S5 稀缺度表，替代静态 2026 快照
     → 方法论通用化：2021 年轮动到新能源，而非锚死 AI 链
  ③ RotationGrowthModel 逐票打分 + BalancedSharpnessBlend 组仓
  ④ 权重 × 当期权益 → 目标股数 → rebalance_portfolio
"""

from __future__ import annotations

import math
from datetime import date

from src.backtest.engine import BarData, BacktestingEngine
from src.core.models import Signal, OrderSide


class StrategyTemplate:
    """目标仓位式策略基类（vnpy portfolio StrategyTemplate）。"""

    def __init__(self, engine: BacktestingEngine, setting: dict):
        self.engine = engine
        self.inited = False
        self.trading = False
        self.pos_data: dict[str, float] = {}
        self.target_data: dict[str, float] = {}
        self.setting = setting

    # ---- 生命周期回调 ----
    def on_init(self):
        pass

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def on_bars(self, bars: dict[str, BarData]):
        raise NotImplementedError

    # ---- 目标仓位 API ----
    def get_pos(self, symbol: str) -> float:
        return self.engine.pos_data.get(symbol, 0.0)

    def get_target(self, symbol: str) -> float:
        return self.target_data.get(symbol, 0.0)

    def set_target(self, symbol: str, target: float) -> None:
        self.target_data[symbol] = target

    def rebalance_portfolio(self, bars: dict[str, BarData]) -> None:
        """目标仓位 → 差额市价化限价单（下一期撮合）。

        委托价 = 参考价 ± buffer：vnpy 的 rebalance 语义。月频 bar 隔月
        跳空常见 10%+，buffer 需覆盖（默认 20%）；成交价仍按 vnpy 取
        min/max(委托, 开盘)，缓冲不抬高实际成交价。跳空超缓冲的委托
        保留至后期或下次调仓 cancel_all 清除。
        """
        self.cancel_all()
        buf = self.setting.get("price_buffer", 0.20)
        for symbol in list(self.target_data.keys()):
            if symbol not in bars:
                # 当期无行情：用引擎缓存价兜底下单
                bar = self.engine.bars.get(symbol)
                if bar is None:
                    continue
                price = bar.close_price
            else:
                price = bars[symbol].close_price
            if price <= 0:
                continue
            target = self.target_data[symbol]
            diff = target - self.get_pos(symbol)
            if diff > 1:            # 整数股（A 股 100 股制近似）
                vol = math.floor(diff / 100) * 100 \
                    if self.setting.get("lot_100", False) else diff
                self.buy(symbol, price * (1 + buf), vol)
            elif diff < -1:
                self.sell(symbol, price * (1 - buf), -diff)

    # ---- 交易 API（转发引擎）----
    def buy(self, symbol: str, price: float, volume: float) -> list[str]:
        if self.trading:
            return self.engine.send_order(self, symbol, OrderSide.BUY,
                                          price, volume)
        return []

    def sell(self, symbol: str, price: float, volume: float) -> list[str]:
        if self.trading:
            return self.engine.send_order(self, symbol, OrderSide.SELL,
                                          price, volume)
        return []

    def cancel_all(self) -> None:
        if self.trading:
            self.engine.cancel_all()


# ===========================================================================
# 动态行业发现：每期重建各行业稀缺度表
# ===========================================================================

def _member_series(periods: dict[str, dict]) -> tuple[list[float],
                                                       list[float]]:
    """成员的最新/上期营收 YoY 与毛利率序列。"""
    rev_by_qp: dict[tuple, float] = {}
    gm: list[tuple] = []      # (最新gm, 上期gm)
    for pk, m in periods.items():
        parts = pk.split("-")
        if len(parts) != 2:
            continue
        try:
            y, q = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if m.get("revenue"):
            rev_by_qp.setdefault((y, q), m["revenue"])
    gm_periods = sorted(periods.keys(), reverse=True)   # 新→旧
    gm_vals = [periods[pk].get("gross_margin")
               for pk in gm_periods if periods[pk].get("gross_margin")
               is not None]
    yoy: list[float] = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    latest_yoy = yoy[:2]
    return latest_yoy, gm_vals[:2]


def build_period_link_map(fin_at: dict[str, dict],
                          universe: list[tuple[str, str, str]],
                          ) -> dict[str, dict]:
    """用点时财务给每个行业打 S1-S5 分 → 生成该期 link_map。

    S 分语义对齐 spec（0-2/项，满分 10）：
      S1 需求强度   = 行业内最新 YoY≥40% 的成员占比
      S2 供给刚性   = 成员增长中位数水平（越高供给越稀缺）
      S3 格局改善   = 毛利率环比回升的成员占比
      S4 增长加速度 = 最新 vs 上期 YoY 中位变化（+10pp 满分）
      S5 主题验证   = 无点时数据 → 0（诚实标注）
    """
    groups: dict[str, list[str]] = {}
    label_of: dict[str, str] = {}
    for tk, _name, label in universe:
        groups.setdefault(label, []).append(tk)
        label_of[tk] = label

    link_map: dict[str, dict] = {}
    for label, members in groups.items():
        yoys: list[float] = []
        accels: list[float] = []
        gm_ups: list[int] = []
        for tk in members:
            periods = fin_at.get(tk)
            if not periods:
                continue
            latest_yoy, gm_pair = _member_series(periods)
            if not latest_yoy:
                continue
            yoys.append(latest_yoy[0])
            if len(latest_yoy) >= 2:
                accels.append(latest_yoy[0] - latest_yoy[1])
            if len(gm_pair) >= 2 and gm_pair[0] > gm_pair[1]:
                gm_ups.append(1)
        if not yoys:
            link_map[label] = {"s_scores": [0, 0, 0, 0, 0], "keywords": []}
            continue
        yoys.sort()
        med_growth = yoys[len(yoys) // 2]
        breadth_hi = sum(1 for y in yoys if y >= 0.40) / len(yoys)
        med_accel = (sorted(accels)[len(accels) // 2] if accels else 0.0)
        frac_gm_up = (sum(gm_ups) / len(gm_ups) if gm_ups else 0.0)
        s1 = min(2, round(2 * breadth_hi))
        s2 = min(2, max(0, round(2 * min(med_growth, 0.8) / 0.8)))
        s3 = min(2, round(2 * frac_gm_up))
        s4 = min(2, max(0, round(2 * med_accel / 0.10)))
        link_map[label] = {"s_scores": [s1, s2, s3, s4, 0],
                           "keywords": [],
                           "n_members": len(yoys),
                           "med_growth": med_growth,
                           "med_accel": med_accel}
    return link_map


# ===========================================================================
# 离线数据适配器（喂 RotationGrowthModel）
# ===========================================================================

class BacktestAdapter:
    """离线 DataClient：点时财务 + 该月价格 → 模型输入。"""

    def __init__(self, fin_at: dict, universe: list[tuple[str, str, str]],
                 month_key: str):
        self._fin_at = fin_at
        self._month = month_key
        self._names = {tk: name for tk, name, _ in universe}
        self._links = {tk: label for tk, _, label in universe}

    def get_prices(self, ticker, start_date, end_date):
        return []  # 模型只用估值行；PE 由 run 层注入 series 缓存

    def get_financial_metrics(self, ticker, end_date, period="ttm",
                              limit=60):
        periods = self._fin_at.get(ticker, {})
        rows = []
        for pk in sorted(periods.keys(), reverse=True)[:limit]:
            y, q = int(pk[:4]), int(pk[5])
            d = f"{y}-{q * 3:02d}-30"
            if d > end_date:
                continue
            m = periods[pk]
            row = {"ticker": ticker, "date": d, "period": period,
                   "revenue": m.get("revenue"),
                   "gross_margin": m.get("gross_margin"),
                   "roe": m.get("roe"),
                   "net_income": m.get("net_income")}
            rows.append(row)
        return rows

    def get_company_facts(self, ticker):
        return {"ticker": ticker, "name": self._names.get(ticker, ""),
                "sector": "", "industry": "",
                "link": self._links.get(ticker)}

    def get_earnings(self, ticker):
        return None


# ===========================================================================
# 轮动策略
# ===========================================================================

class RotationStrategy(StrategyTemplate):
    """章宏帆轮动：调仓月重建行业稀缺度 → 模型打分 → blend 组仓。"""

    def __init__(self, engine: BacktestingEngine, setting: dict):
        super().__init__(engine, setting)
        self.financials = setting["financials"]        # 全历史财务
        self.universe = setting["universe"]            # (tk, name, label)
        self.rebalance_dts = set(setting.get("rebalance_dts", []))
        self.disclosure_of = setting.get("disclosure_of", {})
        self.blend_params = setting.get("blend_params", {})
        self.pe_by_link = setting.get("pe_ceiling_by_link", {})
        self.history: list[dict] = []                  # 调仓日志
        self._model = None
        self._model_dt = None

    def on_bars(self, bars: dict[str, BarData]) -> None:
        dt = self.engine.datetime
        if dt not in self.rebalance_dts:
            return
        as_of = self.disclosure_of.get(dt, f"{dt[:4]}-{dt[5:]}-28")
        self._rebalance(dt, as_of, bars)

    # ------------------------------------------------------------------

    def _rebalance(self, dt: str, as_of: str, bars: dict[str, BarData]):
        from src.signals.rotation_growth import RotationGrowthModel
        from src.portfolio.balanced_sharpness import BalancedSharpnessBlend

        # ① 点时财务（披露截止过滤）
        fin_at = avail_financials(self.financials, as_of)

        # ② 动态行业稀缺度表（该期专用模型实例）
        link_map = build_period_link_map(fin_at, self.universe)
        model = RotationGrowthModel(
            link_map=link_map, boom_growth=0.40,
            pe_ceiling_by_link=self.pe_by_link,
            off_theme_scope=None)
        blender = BalancedSharpnessBlend(
            top_direction_weight=0.22, tail_direction_weight=0.12,
            max_directions=8,
            class_mix={"A": 0.60, "B": 0.35, "C": 0.05},
            per_name_cap=0.05, off_theme_sleeve=0.05,
            max_names_per_direction=6, scale_to_target=True,
            **self.blend_params)

        # ③ 逐票打分（当期有行情的标的）
        adapter = BacktestAdapter(fin_at, self.universe, dt)
        signals: list[Signal] = []
        members = {tk for tk, _, _ in self.universe if tk in bars}
        for tk in sorted(members):
            try:
                sig = model.predict(tk, as_of, adapter)
            except Exception:
                continue
            if sig is not None:
                signals.append(sig)

        # ④ blend 组仓
        result = blender.blend(signals, {"rotation_growth": 1.0},
                               gross_target=1.0)
        weights = {t: w for t, w in result.weights.items() if w > 0}

        # ⑤ 目标股数（权重 × 当期权益）
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * equity / bar.close_price
        # 清掉不在目标里的旧持仓（全卖出指令）
        for s in list(self.engine.pos_data.keys()):
            if self.engine.pos_data.get(s, 0) > 0 and s not in weights:
                self.target_data[s] = 0.0

        self.rebalance_portfolio(bars)

        # 日志
        by_label: dict[str, float] = {}
        label_of = {tk: lab for tk, _, lab in self.universe}
        for tk, w in weights.items():
            lab = label_of.get(tk, "?")
            by_label[lab] = by_label.get(lab, 0.0) + w
        top_links = sorted(link_map.items(),
                           key=lambda kv: -sum(kv[1]["s_scores"]))[:4]
        self.history.append({
            "dt": dt, "as_of": as_of, "n_signals": len(signals),
            "n_hold": len(weights), "equity": equity,
            "weights": weights, "by_label": by_label,
            "top_links": [(name, sum(c["s_scores"]))
                          for name, c in top_links],
        })
        eng = self.engine
        eng.output(
            f"[{dt}] 调仓: {len(signals)} 信号 → {len(weights)} 持仓 | "
            f"权益 ¥{equity:,.0f} | "
            f"top行业 " + ", ".join(
                f"{n}({s}/10)" for n, s in self.history[-1]["top_links"]))


def avail_financials(financials: dict, as_of: str) -> dict:
    """过滤到 as_of 已披露的报告期（截止日近似：Q1/年报 4-30，
    中报 8-31，三季报 10-31）。"""
    out = {}
    d = date.fromisoformat(as_of)
    for tk, periods in financials.items():
        filtered = {}
        for pk, metrics in periods.items():
            parts = pk.split("-")
            if len(parts) != 2:
                continue
            try:
                y, q = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if q == 1:
                deadline = date(y, 4, 30)
            elif q == 2:
                deadline = date(y, 8, 31)
            elif q == 3:
                deadline = date(y, 10, 31)
            else:
                deadline = date(y + 1, 4, 30)
            if deadline <= d:
                filtered[pk] = metrics
        if filtered:
            out[tk] = filtered
    return out
