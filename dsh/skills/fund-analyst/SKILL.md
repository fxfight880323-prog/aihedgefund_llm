# Fund Analyst Skill

## Purpose

Guide the agent in using the AI Fund Framework to analyze stocks, run backtests, construct portfolios, and generate investment reports.

## When to Use

- User asks to analyze a stock, screen a universe, or run a strategy
- User wants backtest results or performance attribution
- User needs portfolio construction or risk checks
- User asks for investment research using the framework's alpha models

## Framework Overview

The AI Fund Framework is a LangGraph-powered quantitative investment system:

```
FUND      = capital slices over STRATEGIES (master risk on netted book)
STRATEGY  = blend policy over MODELS (a "pod")
MODEL     = alpha model → Signal (conviction in [-1,+1] + thesis)
```

### Key Alpha Models (in src/signals/)

| Model | Type | Description |
|-------|------|-------------|
| f_score | Quant | Piotroski F-Score (9-factor financial health) |
| c_score | Quant | Custom C-Score variant |
| growth_loop | Hybrid | Growth-at-reasonable-price with earnings momentum |
| buffett | LLM | Buffett-style moat + quality + value analysis |
| pead | Quant | Post-earnings announcement drift |
| serenity_gate | Quant | Quality + low volatility filter |
| tech_confluence | Quant | Technical indicator confluence |
| rotation_growth | Quant | Sector rotation + growth timing |
| bsadf | Quant | Bubble detection (BSADF test) |
| ashare_value | Quant | A-share specific value metrics |

### Workflow

1. **Screen** → Identify candidate universe
2. **Analyze** → Run alpha models on candidates
3. **Blend** → Combine signals into target weights
4. **Risk** → Apply hard limits and vetos
5. **Execute** → Generate orders
6. **Report** → Persist decision trail

## Tool Usage

Always use the `fund_tools.py` bridge for framework operations:

```bash
# Screen universe
python dsh/fund_tools.py screen --min-roic 0.15 --top-n 50

# Run backtest on a strategy
python dsh/fund_tools.py backtest --strategy growth_loop --start 2020-01-01

# Analyze single stock
python dsh/fund_tools.py signal --model f_score --ticker 600519.SH

# View portfolio
python dsh/fund_tools.py portfolio --signals-file _bt_sel_baseline.json

# Risk check
python dsh/fund_tools.py risk --portfolio-file _bt_zhf_weights.json

# Find reports
python dsh/fund_tools.py report --type backtest
```

## Principles

1. **Point-in-time by construction** — never use future information
2. **The LLM never touches the trade** — agents form views, deterministic code sizes positions
3. **Fail loud** — report data gaps explicitly; never silently skip
4. **Conviction requests, risk disposes** — your signals are proposals; risk can veto
5. **Generate reports** — always produce audit trails after backtests

## Data Sources

The framework integrates multiple data providers:
- Wind (万得) — A-share/HK data, screener, consensus
- Financial Datasets API — US/global fundamentals
- MCP data clients — Structured financial data

## Report Generation

After running any analysis, check for existing HTML reports:
```bash
ls -lt *report*.html
```

Or generate new ones using the framework's report scripts:
```bash
python _fs_report.py        # F-Score report
python _gl_build_report.py  # Growth Loop report
python _zhf_cons_report.py  # ZHF Consensus report
```
