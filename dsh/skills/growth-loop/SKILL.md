# Growth Loop Skill

## Purpose

Guide the agent in applying the Growth Loop methodology — a GARP (Growth at Reasonable Price) strategy that combines earnings momentum with valuation discipline.

## When to Use

- User asks about growth investing
- User references earnings momentum, growth at reasonable price, or GARP
- User wants to find companies with accelerating earnings + reasonable valuation
- User asks about the "Growth Loop" strategy specifically

## Core Concept

The Growth Loop identifies companies where:
1. **Earnings are accelerating** (revenue and profit growth trending up)
2. **Valuation is reasonable** (PEG < 1.5, not bubble territory)
3. **Quality is high** (ROIC > WACC, strong balance sheet)
4. **Technical confirmation** (price action supports fundamentals)

### The Loop Logic

```
Earnings Acceleration
       ↓
   Quality Check (ROIC, FCF)
       ↓
   Valuation Filter (PEG, EV/EBIT)
       ↓
   Technical Confirmation
       ↓
   Position Sizing (conviction-weighted)
       ↓
   Sell Rules (deceleration, overvaluation)
```

## Key Metrics

| Metric | Target | Red Flag |
|--------|--------|----------|
| Revenue Growth YoY | > 15% and accelerating | Decelerating for 2+ quarters |
| EPS Growth YoY | > 20% and accelerating | Decelerating for 2+ quarters |
| PEG Ratio | < 1.5 | > 2.5 |
| ROIC | > 12% | < 8% |
| FCF/Net Income | > 70% | < 50% (low earnings quality) |
| Debt/EBITDA | < 2x | > 4x |

## Sell Rules

1. **Growth deceleration**: Revenue or EPS growth slows for 2 consecutive quarters
2. **Valuation expansion**: PEG rises above 2.0
3. **Quality degradation**: ROIC falls below 10%
4. **Technical breakdown**: Falls below 200-day MA with volume
5. **Position cap**: No single position > 10% of portfolio

## Framework Integration

```bash
# Run Growth Loop signal on a ticker
python dsh/fund_tools.py signal --model growth_loop --ticker 300750.SZ

# Backtest the Growth Loop strategy
python dsh/fund_tools.py backtest --strategy growth_loop --start 2019-01-01

# Screen for growth candidates
python dsh/fund_tools.py screen --min-roe 0.12 --sector 电力设备

# Check existing Growth Loop reports
python dsh/fund_tools.py report --type backtest
ls -lt growth_loop*.html
```

## Backtest Variants

The framework has tested multiple Growth Loop variants:

| Variant | Key Difference | File |
|---------|---------------|------|
| Baseline | Standard GARP | `_bt_gl_v2_baseline_*` |
| v2a | Added ROIC filter | `_bt_gl_v2_v2a_*` |
| v2rec | Recommender blend | `_bt_gl_v2_v2rec_*` |
| v3 | Consensus overlay | `_bt_gl_v2_v3a_*`, `_bt_gl_v2_v3b_*` |
| v4 | PEG-based sell rules | `_bt_gl_v4_*` |

To compare variants:
```bash
python _gl_v4_report.py   # Generates v4 comparison report
```

## Analysis Workflow

1. **Universe**: Start with all A-shares (or user's watchlist)
2. **Screen**: Filter for minimum growth + quality thresholds
3. **Score**: Rank by growth acceleration, quality, and valuation
4. **Select**: Top N stocks with highest composite score
5. **Size**: Conviction-weighted allocation (higher score = larger position)
6. **Monitor**: Track quarterly earnings for deceleration signals
7. **Rebalance**: Monthly or quarterly based on signal refresh

## Risk Considerations

- Growth stocks are more volatile than value stocks
- Earnings acceleration can reverse quickly (mean reversion)
- High valuation leaves little margin of safety
- Concentration risk in popular growth sectors
- Liquidity risk in smaller growth names

Always run risk checks:
```bash
python dsh/fund_tools.py risk --portfolio-file _bt_gl_v2_baseline_detail.json
```
