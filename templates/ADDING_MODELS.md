# Guide: Adding Your Own Investment Theory

This guide walks through every way to customize the framework with your own
investment ideas. Every file marked ⬅ BLANK TEMPLATE is a starting point.

---

## Table of Contents

1. [Add a Quant Alpha Model](#1-add-a-quant-alpha-model)
2. [Add an LLM Investor Agent](#2-add-an-llm-investor-agent)
3. [Add a Custom Data Source](#3-add-a-custom-data-source)
4. [Add a Custom Portfolio Allocator](#4-add-a-custom-portfolio-allocator)
5. [Add a Custom Risk Model](#5-add-a-custom-risk-model)
6. [Add a Custom Broker](#6-add-a-custom-broker)
7. [Add a Custom Research Module](#7-add-a-custom-research-module)
8. [Add a Custom Graph Node](#8-add-a-custom-graph-node)
9. [Build a Complete Fund](#9-build-a-complete-fund)

---

## 1. Add a Quant Alpha Model

**File:** `src/signals/_template_quant.py` → copy to `src/signals/my_model.py`

A quant model is pure math. It fetches data, computes a signal, and returns
a conviction in [-1, +1].

### Example: 12-1 Month Momentum

```python
from src.signals.base import QuantModel
from src.core.models import Signal
from datetime import datetime, timedelta

class MomentumModel(QuantModel):
    def __init__(self, lookback_days: int = 252, skip_days: int = 21, **kwargs):
        self.lookback = lookback_days
        self.skip = skip_days

    @property
    def name(self) -> str:
        return "momentum"

    def predict(self, ticker: str, date: str, data_client) -> Signal:
        as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        start = (as_of - timedelta(days=self.lookback + self.skip + 30)).isoformat()

        prices = data_client.get_prices(ticker, start, date)
        closes = [p["close"] for p in prices if p.get("time", "")[:10] <= date]

        if len(closes) < self.lookback:
            return Signal(model_name=self.name, ticker=ticker, date=date, value=0.0,
                         reasoning="Insufficient price history")

        # 12-1 momentum: return over last 252 days excluding most recent 21
        momentum = (closes[-self.skip - 1] / closes[-self.lookback - self.skip]) - 1
        value = self._sigmoid(momentum, scale=3.0)

        return Signal(
            model_name=self.name, ticker=ticker, date=date,
            value=value,
            reasoning=f"12-1 momentum: {momentum:.2%}",
            components={"momentum": momentum},
        )
```

### Register it:

```python
# src/signals/__init__.py
from src.signals.momentum import MomentumModel
ALPHA_MODEL_REGISTRY["momentum"] = MomentumModel
```

### Use it in YAML:

```yaml
models:
  - name: momentum
    weight: 1.0
    params:
      lookback_days: 252
      skip_days: 21
```

---

## 2. Add an LLM Investor Agent

**File:** `src/signals/_template_llm.py` → copy to `src/signals/my_agent.py`

An LLM agent is a system prompt + data. The prompt IS the investment philosophy.

### Example: Your Own Investment Theory

```python
from src.signals.base import LLMAgent

class MyTheoryAgent(LLMAgent):
    @property
    def name(self) -> str:
        return "my_theory"

    def get_system_prompt(self) -> str:
        return """You are an investor who follows these principles:

1. Buy companies with accelerating revenue growth (>20% YoY)
2. Require gross margin > 40% (software-like economics)
3. Must have net cash (cash > total debt)
4. Avoid companies with declining R&D as % of revenue
5. Valuation: willing to pay up to 15x revenue for >30% growth

Signal:
- bullish: meets all 5 criteria
- bearish: fails criteria 1 or 2
- neutral: mixed

Confidence: 90+ if exceptional, 70-89 if solid, 40-69 if mixed.

Respond with JSON:
{"signal": "bullish"|"bearish"|"neutral", "confidence": <0-100>,
 "reasoning": "<thesis>"}"""
```

---

## 3. Add a Custom Data Source

**File:** `src/data/_template_client.py` → copy to `src/data/my_client.py`

Implement the DataClient protocol to bring your own data:

### Example: yfinance Client (free)

```python
import yfinance as yf

class YFinanceClient:
    def get_prices(self, ticker, start_date, end_date):
        df = yf.download(ticker, start=start_date, end=end_date)
        return [
            {"time": idx.isoformat(), "open": r.Open, "high": r.High,
             "low": r.Low, "close": r.Close, "volume": r.Volume}
            for idx, r in df.iterrows()
        ]

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return [{
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "roe": info.get("returnOnEquity"),
            # ... add what you need
        }]

    def get_company_facts(self, ticker):
        info = yf.Ticker(ticker).info
        return {"sector": info.get("sector"), "industry": info.get("industry")}

    def get_earnings(self, ticker):
        return yf.Ticker(ticker).earnings
```

### Use it:

```python
from src.data.my_client import YFinanceClient
from src.workflow.runner import run_fund_cycle

record = run_fund_cycle(
    mandate_path="config/funds/example_fund.yaml",
    tickers=["AAPL"],
    data_client=YFinanceClient(),  # ← your custom client
)
```

---

## 4. Add a Custom Portfolio Allocator

**File:** `src/portfolio/_template_allocator.py`

### Example: Risk-Parity Allocator

```python
from src.core.models import Signal, BlendResult
from src.core.interfaces import BlendPolicy

class RiskParityBlend(BlendPolicy):
    def blend(self, signals, model_weights, gross_target=1.0, market_neutral=False):
        # Get per-ticker conviction
        convictions = {}
        for s in signals:
            if s.metadata.get("abstained"):
                continue
            w = model_weights.get(s.model_name, 1.0)
            convictions[s.ticker] = convictions.get(s.ticker, 0) + w * s.value

        # Weight by inverse volatility (simplified)
        # In practice, you'd fetch price history and compute vol
        vols = {t: 0.20 for t in convictions}  # placeholder
        raw = {t: convictions[t] / vols[t] for t in convictions}

        gross = sum(abs(v) for v in raw.values())
        if gross < 1e-9:
            weights = {t: 0.0 for t in convictions}
        else:
            weights = {t: v / gross * gross_target for t, v in raw.items()}

        return BlendResult(convictions=convictions, weights=weights)
```

---

## 5. Add a Custom Risk Model

**File:** `src/risk/_template_risk.py`

### Example: Drawdown Deleveraging

```python
from src.core.models import RiskResult, ClampEvent
from src.core.interfaces import RiskModel

class DrawdownRiskModel(RiskModel):
    def __init__(self, max_drawdown=0.15, **kwargs):
        self.max_dd = max_drawdown
        self.peak_nav = None

    def apply(self, weights):
        # Track peak NAV and deleverage when in drawdown
        # (In practice, you'd pass current NAV through the state)
        clamps = []
        clamped = dict(weights)

        # If drawdown > threshold, scale down
        # scale = max(0, 1 - (current_dd - self.max_dd) / self.max_dd)
        # clamped = {t: w * scale for t, w in clamped.items()}

        return RiskResult(weights=clamped, clamps=clamps)
```

---

## 6. Add a Custom Broker

**File:** `src/execution/_template_broker.py`

### Example: Alpaca Paper Trading

```python
from alpaca.trading.client import TradingClient

class AlpacaBroker:
    def __init__(self, api_key, api_secret, paper=True):
        self.client = TradingClient(api_key, api_secret, paper=paper)

    def positions(self):
        positions = self.client.get_all_positions()
        return {p.symbol: Position(ticker=p.symbol, shares=float(p.qty),
                                   avg_cost=float(p.avg_entry_price))
                for p in positions}

    def cash(self):
        return float(self.client.get_account().cash)

    def place_order(self, order):
        req = MarketOrderRequest(
            symbol=order.ticker, qty=order.shares,
            side=order.side.value, time_in_force="day"
        )
        result = self.client.submit_order(req)
        return Fill(ticker=order.ticker, side=order.side,
                    shares=float(result.filled_qty),
                    price=float(result.filled_avg_price))
```

---

## 7. Add a Custom Research Module

**File:** `src/research/_template_research.py`

Ideas:
- **Walk-forward optimization**: optimize parameters on rolling windows
- **CPCV**: Combinatorial Purged Cross-Validation for overfitting detection
- **Factor IC**: Information Coefficient for new alpha factors
- **Attribution**: decompose returns by model, sector, factor
- **Monte Carlo**: simulate path dependencies and worst-case scenarios

---

## 8. Add a Custom Graph Node

Insert your own step into the LangGraph workflow:

```python
from langgraph.graph import StateGraph
from src.workflow.state import FundState
from src.workflow.nodes import fetch_data, run_analysts, blend_signals

def my_news_sentiment_node(state: FundState) -> dict:
    """Fetch news sentiment and add it as a signal."""
    tickers = state.get("marks", {}).keys()
    signals = state.get("signals", [])

    for ticker in tickers:
        sentiment = fetch_sentiment(ticker, state["as_of"])
        signals.append(Signal(
            model_name="news_sentiment",
            ticker=ticker,
            date=state["as_of"],
            value=sentiment,
            reasoning=f"News sentiment: {sentiment:.2f}",
        ))

    return {"signals": signals}

# Build custom graph
graph = StateGraph(FundState)
graph.add_node("fetch_data", fetch_data)
graph.add_node("news_sentiment", my_news_sentiment_node)  # YOUR NODE
graph.add_node("run_analysts", run_analysts)
graph.add_node("blend_signals", blend_signals)

graph.set_entry_point("fetch_data")
graph.add_edge("fetch_data", "news_sentiment")     # data → your node
graph.add_edge("news_sentiment", "run_analysts")    # → then analysts
graph.add_edge("run_analysts", "blend_signals")
# ... rest of pipeline
```

---

## 9. Build a Complete Fund

### A. Define your alpha models
Create models in `src/signals/` using the templates.

### B. Define your strategies
Create YAML files in `config/strategies/` bundling models with blend policies.

### C. Define your fund mandate
Create a YAML in `config/funds/` specifying:
- Which strategies to use and their capital allocation
- Risk limits (max position size, max gross exposure)
- Rebalance cadence (daily/weekly/monthly)
- Benchmark to measure against

### D. Run it
```python
from src.workflow.runner import run_fund_cycle

record = run_fund_cycle(
    mandate_path="config/funds/my_fund.yaml",
    tickers=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
    as_of="2024-06-01",
)
```

### E. Backtest it
```python
from src.research.backtest import backtest_fund

result = backtest_fund(
    mandate_path="config/funds/my_fund.yaml",
    tickers=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
    start_date="2022-01-01",
    end_date="2024-01-01",
)
```

### F. Iterate
- Add more alpha models
- Tune blend policies
- Adjust risk limits
- Try different rebalance cadences
- Promote what works, cut what doesn't

The framework is the scaffolding. Your investment theory is what makes it yours.
