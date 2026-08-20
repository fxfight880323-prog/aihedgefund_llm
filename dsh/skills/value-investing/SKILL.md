# Value Investing Skill

## Purpose

Guide the agent in applying Buffett-style value investing principles using the AI Fund Framework.

## When to Use

- User asks for value investing analysis
- User wants to find "wonderful companies at fair prices"
- User references moat, ROIC, owner earnings, or margin of safety
- User asks about durable competitive advantage

## Core Principles

### 1. Business Quality (Moat)

Look for businesses with durable competitive advantages:

- **Intangible assets**: Brands, patents, regulatory licenses
- **Customer switching costs**: Hard to switch to competitor
- **Network effects**: Value increases with more users
- **Cost advantages**: Scale, location, unique assets
- **Efficient scale**: Natural monopoly in niche markets

### 2. Financial Health

Key metrics to check (via the framework's F-Score and custom screens):

| Metric | Threshold | Why |
|--------|-----------|-----|
| ROIC | > 15% | Returns above cost of capital |
| ROE | > 15% | Shareholder returns |
| Gross Margin | Stable or improving | Pricing power |
| FCF/Net Income | > 80% | Earnings are real cash |
| Debt/Equity | < 0.5 | Conservative leverage |
| Interest Coverage | > 5x | Safety margin |

### 3. Management Quality

- Capital allocation discipline (buybacks, dividends, M&A)
- Insider ownership alignment
- Transparent communication
- Consistent strategy over time

### 4. Valuation

| Method | When to Use |
|--------|-------------|
| DCF | Stable, predictable cash flows |
| Earnings Power Value | Current earnings are sustainable |
| Liquidation Value | Asset-heavy, distressed |
| Relative (P/E, P/B) | Quick sanity check vs peers |

Margin of safety: Require 30-50% discount to intrinsic value.

## Framework Integration

Use these framework tools for value investing:

```bash
# Screen for high-quality value candidates
python dsh/fund_tools.py screen --min-roic 0.15 --min-roe 0.15

# Run F-Score (9-factor financial health check)
python dsh/fund_tools.py signal --model f_score --ticker <TICKER>

# Run Buffett-style LLM analysis
python dsh/fund_tools.py signal --model buffett --ticker <TICKER>

# Backtest the value strategy
python dsh/fund_tools.py backtest --strategy f_score --start 2018-01-01
```

## Analysis Checklist

For each candidate:

- [ ] Understand the business in one paragraph
- [ ] Identify the moat source and durability
- [ ] Check 5-10 year financial trends
- [ ] Verify earnings quality (FCF vs net income)
- [ ] Assess management capital allocation
- [ ] Estimate intrinsic value with multiple methods
- [ ] Calculate margin of safety
- [ ] Check insider ownership and recent transactions
- [ ] Review competitive landscape
- [ ] Identify key risks and kill criteria

## Kill Criteria (Sell/Veto)

- Moat erosion detected (competitor gaining share, technology shift)
- ROIC falls below 10% for 2+ consecutive years
- Management makes value-destructive acquisitions
- Valuation exceeds intrinsic value by >20%
- Accounting red flags (aggressive revenue recognition, inventory buildup)
