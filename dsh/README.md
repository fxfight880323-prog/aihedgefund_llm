# DeepSeek Harness Integration for AI Fund Framework

This directory integrates [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`) as the **agent orchestration layer** for the AI Fund Framework.

## What This Enables

- **Agent-driven fund cycles**: dsh agents orchestrate the full investment pipeline via structured tools
- **Skill-based analysis**: Reusable investment methodologies as dsh skills (Buffett, Growth Loop, F-Score, etc.)
- **Web UI for fund ops**: Run backtests, screen universes, and analyze signals through dsh's web interface
- **Human-in-the-loop**: Pause before execution for approval (built into dsh)
- **Session persistence**: All agent reasoning and tool calls are logged in JSONL for audit

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  DeepSeek Harness (dsh)                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  Agent Loop  │  │  Tool Registry│  │  Skill Catalog  │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘   │
│         │                 │                    │            │
│         └─────────────────┴────────────────────┘            │
│                           │                                 │
│                    ┌──────┴──────┐                          │
│                    │  bash tool  │──► fund_tools.py CLI     │
│                    └─────────────┘    (Python bridge)       │
└─────────────────────────────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ AI Fund Framework │
                    │ (Python/LangGraph) │
                    └─────────────┘
```

## Quick Start

### 1. Install dsh Python SDK

```bash
pip install deepseek-harness-sdk
```

### 2. Set API keys

```bash
# Already in your .env — dsh reads these automatically
export DEEPSEEK_API_KEY=sk-...
# Optional: export DEEPSEEK_BASE_URL=...
```

### 3. Launch dsh with the fund profile

```bash
# From the ai_fund_framework root:
cd deepseek-harness
pnpm install
pnpm run build

# Run dsh web with fund-specific config
DSH_CORDIS_CONFIG=../dsh/cordis-fund.yml pnpm dsh web --no-open
```

Or use the Python SDK directly:

```python
from deepseek_harness import DeepSeekHarness
from pathlib import Path

config = Path("dsh/cordis-fund.yml").resolve()
workspace = Path(".").resolve()

with DeepSeekHarness(
    provider="deepseek-official",
    model="deepseek-chat",
    cordis=str(config),
    cwd=str(workspace),
) as harness:
    result = harness.run(
        "Screen the A-share universe for high-quality growth stocks "
        "and run a backtest on the top 20 selections.",
        session_id="fund-cycle-001",
    )
    print(result.final_response)
```

## Available Tools (via bash → fund_tools.py)

The fund agent has access to these operations through the `fund_tools.py` CLI bridge:

| Tool Command | Description | Example |
|-------------|-------------|---------|
| `fund_tools.py screen` | Run stock screener with filters | `"screen --min-market-cap 50e8 --min-roic 0.15"` |
| `fund_tools.py backtest` | Run backtest on a strategy | `"backtest --strategy growth_loop --start 2020-01-01"` |
| `fund_tools.py signal` | Run a single alpha model | `"signal --model f_score --ticker 600519.SH"` |
| `fund_tools.py report` | Generate HTML/PDF report | `"report --type backtest --input _bt_results.json"` |
| `fund_tools.py portfolio` | Construct portfolio from signals | `"portfolio --signals-file signals.json"` |
| `fund_tools.py risk` | Run risk checks | `"risk --portfolio portfolio.json"` |

## Skills

Skills are reusable agent instructions stored in `dsh/skills/`. The agent can load them via the `skill` tool:

- **`fund-analyst`** — General framework for analyzing stocks using the AI Fund Framework
- **`value-investing`** — Buffett-style moat + quality + value analysis
- **`growth-loop`** — Growth-at-reasonable-price (GARP) methodology

## Customization

### Add a new alpha model as a skill

1. Create `dsh/skills/my-model/SKILL.md` with your investment thesis and analysis steps
2. The agent will automatically load it when relevant

### Add a new fund tool

1. Add a subcommand to `fund_tools.py`
2. Update the system prompt in `cordis-fund.yml` to teach the model about it

## Files

| File | Purpose |
|------|---------|
| `cordis-fund.yml` | dsh composition profile — tools, model, system prompt |
| `fund_tools.py` | Python CLI bridge — wraps framework operations for dsh |
| `skills/fund-analyst/SKILL.md` | Core fund analysis skill |
| `skills/value-investing/SKILL.md` | Value investing methodology skill |
| `skills/growth-loop/SKILL.md` | Growth loop methodology skill |
