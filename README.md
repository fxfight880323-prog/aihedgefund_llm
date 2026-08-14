# AI Investment Fund Framework

A **LangGraph-powered AI investment fund** framework built on the architecture of [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund), with blank templates for your own investment theories.

> **Educational use only.** Not investment advice. Not intended for real trading.

---

## What This Is

A framework for building your own AI-powered investment fund. You staff it with **alpha models** (analysts), bundle them into **strategies** (pods), and the engine runs a complete cycle: data → analysts → portfolio → risk → execution → ledger.

The entire workflow is orchestrated by **LangGraph**, giving you:
- Checkpointing (resume any cycle from any point)
- Human-in-the-loop (pause before execution for approval)
- Parallelism (run analysts simultaneously)
- Streaming (watch signal generation in real-time)
- Conditional logic (skip execution when all signals are neutral)

### Architecture

```
FUND      =  capital slices over STRATEGIES   (master risk on the netted book)
STRATEGY  =  a blend policy over MODELS       (a "pod")
MODEL     =  an alpha model → Signal          (conviction in [-1,+1] + thesis)
```

```
 point-in-time data        only what was actually filed by this date
        │
        ▼
 analysts emit Signals     Buffett +0.7 "durable moat, fair price"
        │                   PEAD    -1.0 "missed earnings"
        ▼
 portfolio construction    blend views → target weights
        ▼
 risk model                hard caps clamp or veto
        ▼
 execution                 target vs. broker reality → orders
        ▼
 ledger                    persist the decision, thesis, fills, NAV
```

### Key Principles (from ai-hedge-fund)

1. **Point-in-time by construction** — no lookahead in backtests
2. **The LLM never touches the trade** — agents form views, deterministic code sizes positions
3. **One interface for every analyst** — implement `AlphaModel.predict()` and it plugs in
4. **Fail loud** — infrastructure failures raise; only genuine "no data" returns empty
5. **Conviction requests, risk disposes** — analysts propose, risk disposes

---

## Quick Start

### 1. Install

```bash
cd ai_fund_framework
pip install -e .
```

### 2. Set up API keys

```bash
cp .env.example .env
# Edit .env and add your FINANCIAL_DATASETS_API_KEY
# Add an LLM API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
```

### 3. Run a fund cycle

```python
from src.workflow.runner import run_fund_cycle

record = run_fund_cycle(
    mandate_path="config/funds/example_fund.yaml",
    tickers=["AAPL", "MSFT", "NVDA"],
    as_of="2024-01-15",
)

print(f"NAV: ${record.nav:,.2f}")
print(f"Positions: {record.positions}")
for signal in record.signals:
    print(f"  {signal.model_name} → {signal.ticker}: {signal.value:+.2f}")
    print(f"    {signal.reasoning}")
```

### 4. Backtest

```python
from src.research.backtest import backtest_fund

result = backtest_fund(
    mandate_path="config/funds/example_fund.yaml",
    tickers=["AAPL", "MSFT", "NVDA"],
    start_date="2023-01-01",
    end_date="2024-01-01",
    capital=100_000,
)

print(f"Total Return: {result['stats']['total_return']:.2%}")
print(f"Sharpe: {result['stats']['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {result['stats']['max_drawdown']:.2%}")
```

### 5. Run with human approval (paper trading)

```python
from src.workflow.graph import build_fund_graph_with_approval

graph = build_fund_graph_with_approval()
config = {"configurable": {"thread_id": "cycle-1"}}

# Runs up to build_orders, then pauses
result = graph.invoke(initial_state, config)

# Review proposed orders
for order in result["orders"]:
    print(f"  {order.side} {order.shares:.0f} {order.ticker} @ {order.limit_price}")

# Approve and continue to execution
result = graph.invoke(None, config)
```

---

## Project Structure

```
ai_fund_framework/
├── config/
│   ├── funds/                       # Fund mandate YAML files
│   │   └── example_fund.yaml        # Example two-strategy fund
│   └── strategies/                  # Strategy YAML files
│       ├── fundamental_ls.yaml      # Value L/S strategy
│       ├── earnings_drift.yaml      # Quant PEAD strategy
│       └── _template.yaml           # ⬅ BLANK TEMPLATE for your strategy
│
├── src/
│   ├── core/                        # Core framework (don't modify)
│   │   ├── models.py                # Data contracts (Signal, Order, Fill, etc.)
│   │   ├── interfaces.py            # All abstract interfaces
│   │   ├── fund_spec.py             # Fund/Strategy spec (YAML → objects)
│   │   └── registry.py              # Plugin system for alpha models
│   │
│   ├── data/                        # Data layer
│   │   ├── fin_datasets_client.py   # Financial Datasets API client
│   │   ├── cache.py                 # Disk cache for API responses
│   │   └── _template_client.py      # ⬅ BLANK TEMPLATE for custom data source
│   │
│   ├── signals/                     # Alpha models (your analysts)
│   │   ├── base.py                  # AlphaModel / QuantModel / LLMAgent
│   │   ├── pead.py                  # Example quant model
│   │   ├── buffett.py               # Example LLM agent
│   │   ├── _template_quant.py       # ⬅ BLANK TEMPLATE for quant model
│   │   ├── _template_llm.py         # ⬅ BLANK TEMPLATE for LLM agent
│   │   └── __init__.py              # ⬅ REGISTER YOUR MODELS HERE
│   │
│   ├── portfolio/                   # Portfolio construction
│   │   ├── construction.py          # Conviction-weighted blend (default)
│   │   └── _template_allocator.py   # ⬅ BLANK TEMPLATE for custom allocator
│   │
│   ├── risk/                        # Risk management
│   │   ├── limits.py                # Hard limits (per-position + gross)
│   │   └── _template_risk.py        # ⬅ BLANK TEMPLATE for custom risk model
│   │
│   ├── execution/                   # Order execution
│   │   ├── broker.py                # SimBroker (backtesting)
│   │   └── _template_broker.py      # ⬅ BLANK TEMPLATE for live broker
│   │
│   ├── workflow/                    # LangGraph workflow (the engine)
│   │   ├── graph.py                 # Graph definition (nodes + edges)
│   │   ├── nodes.py                 # Graph nodes (fetch, analyze, blend, risk, execute)
│   │   ├── state.py                 # Workflow state (FundState TypedDict)
│   │   └── runner.py                # Entry point (run_fund_cycle, run_fund_backtest)
│   │
│   ├── research/                    # Research lab
│   │   ├── backtest.py              # Backtesting + performance stats
│   │   └── _template_research.py    # ⬅ BLANK TEMPLATE for custom research
│   │
│   └── utils/                       # Utilities
│
├── pyproject.toml
├── .env.example
└── README.md                        # You are here
```

**⬅ = blank templates for you to fill in**

---

## How to Add Your Own Investment Theory

### Step 1: Create an Alpha Model

Copy a template and implement your logic:

**For a quant model** (momentum, RSI, factor screens, etc.):
```bash
cp src/signals/_template_quant.py src/signals/my_model.py
```

**For an LLM agent** (your own investment persona):
```bash
cp src/signals/_template_llm.py src/signals/my_agent.py
```

### Step 2: Register It

In `src/signals/__init__.py`:
```python
from src.signals.my_model import MyModel
ALPHA_MODEL_REGISTRY["my_model"] = MyModel
```

### Step 3: Use It in a Strategy

Create `config/strategies/my_strategy.yaml` (copy `_template.yaml`):
```yaml
name: my_strategy
models:
  - name: my_model
    weight: 1.0
blend:
  method: conviction_weighted
  gross_target: 1.0
  market_neutral: false
```

### Step 4: Add to a Fund

In your fund mandate YAML:
```yaml
strategies:
  - name: my_pod
    weight: 1.0
    models:
      - name: my_model
        weight: 1.0
    blend:
      method: conviction_weighted
      gross_target: 1.0
```

**That's it.** The engine runs your model without any other changes.

---

## The Signal Contract

Every alpha model produces a `Signal`:

```python
Signal(
    model_name="my_model",      # your model's name
    ticker="AAPL",
    date="2024-01-15",
    value=0.7,                  # conviction in [-1, +1]
    reasoning="Strong momentum",# human-readable thesis
    components={"momentum": 0.8, "rsi": 0.6},  # optional sub-scores
    metadata={"lookback": 252}, # optional extra data
)
```

**The value is the only thing the engine uses.** Everything else is for you, for logging, and for the audit trail.

- `+1.0` = maximally bullish
- `0.0` = no view (abstain)
- `-1.0` = maximally bearish

---

## LangGraph Workflow

The fund cycle is a LangGraph `StateGraph` with 7 nodes:

```python
from src.workflow.graph import build_fund_graph

graph = build_fund_graph()
result = graph.invoke({
    "fund_name": "My Fund",
    "as_of": "2024-01-15",
    "universe": ["AAPL", "MSFT"],
    "capital": 100_000,
    "metadata": {
        "fund_spec": spec,
        "data_client": client,
        "broker": broker,
    },
})
```

### Available graph variants:

| Function | Description |
|----------|-------------|
| `build_fund_graph()` | Standard pipeline (no pauses) |
| `build_fund_graph_with_approval()` | Pauses before execution for human review |
| `build_fund_graph_parallel()` | Parallel analyst execution (advanced) |

### Custom graph nodes:

You can add your own nodes to the graph. For example, a news sentiment node:

```python
from langgraph.graph import StateGraph
from src.workflow.graph import build_fund_graph

# Get the compiled graph's builder... or build your own:
graph = StateGraph(FundState)
graph.add_node("fetch_data", fetch_data)
graph.add_node("news_sentiment", my_news_sentiment_node)  # YOUR NODE
graph.add_node("run_analysts", run_analysts)
# ... rest of pipeline
```

---

## Three Modes — One Code Path

```
BACKTEST  =  historical clock  +  simulated broker   (the past, fake money)
PAPER     =  live clock         +  simulated broker   (right now, fake money)
LIVE      =  live clock         +  real broker         (right now, real money)
```

The only thing that changes is the clock and the broker. The pipeline never changes.

---

## Pluggable Components

| Component | Interface | Template | Built-in |
|-----------|-----------|----------|----------|
| Alpha Model (quant) | `QuantModel` | `_template_quant.py` | `pead.py` |
| Alpha Model (LLM) | `LLMAgent` | `_template_llm.py` | `buffett.py` |
| Data Client | `DataClient` | `_template_client.py` | `fin_datasets_client.py` |
| Blend Policy | `BlendPolicy` | `_template_allocator.py` | `construction.py` |
| Risk Model | `RiskModel` | `_template_risk.py` | `limits.py` |
| Broker | `Broker` | `_template_broker.py` | `broker.py` (SimBroker) |
| Research | — | `_template_research.py` | `backtest.py` |

---

## Disclaimer

This project is for **educational and research purposes only**.
- Not intended for real trading or investment
- No investment advice or guarantees provided
- Past performance does not indicate future results
