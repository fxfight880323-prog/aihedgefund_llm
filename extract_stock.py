"""Extract full data for 赛力斯 (601127.SH) through the 2024-08 growth loop.

Scans all 2024-08 candidates, evaluates numeric hooks (H1/H2/H3/H6),
computes the conviction proxy for every stock that triggers hooks, and
prints everything (all raw financial fields, price history, YoY, GM,
drawdown) in a clear detailed format.
"""
import json
import os
import sys

BASE = r"D:\workspace\ai_fund_framework"
os.chdir(BASE)
sys.path.insert(0, BASE)

from src.signals.hooks import evaluate_hooks
from src.backtest.strategy import avail_financials

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
print("=" * 80)
print("DATA LOADING")
print("=" * 80)
files = ["_bt_pit_selection.json", "_bt_pit_financials.json",
         "_bt_pit_prices.json", "_bt_pit_warmup.json"]
sel = json.loads(open(files[0], encoding="utf-8").read())
financials = json.loads(open(files[1], encoding="utf-8").read())
prices = json.loads(open(files[2], encoding="utf-8").read())
warmup = json.loads(open(files[3], encoding="utf-8").read())
for f in files:
    print(f"  loaded {f}: {os.path.getsize(f):,} bytes")
print(f"  selection months: {len(sel)}, tickers in financials: {len(financials)}, "
      f"prices: {len(prices)}, warmup: {len(warmup)}")

# Merge warmup (earlier history) + main prices into one series per ticker.
prices_all = {}
for tk in set(prices) | set(warmup):
    prices_all[tk] = {**warmup.get(tk, {}), **prices.get(tk, {})}

MONTH = "2024-08"
as_of = sel[MONTH]["as_of"]
candidates = sel[MONTH]["candidates"]
print(f"\nRebalance month: {MONTH}")
print(f"As-of date: {as_of}")
print(f"Total candidates: {len(candidates)}")

# ---------------------------------------------------------------------------
# 2. Locate 赛力斯
# ---------------------------------------------------------------------------
target = None
for tk, name, sw1 in candidates:
    if "赛力" in name or "601127" in tk:
        target = (tk, name, sw1)
        break
print(f"\nTarget stock: {target[1]} ({target[0]}) | Industry: {target[2]}")

# ---------------------------------------------------------------------------
# 3. Point-in-time financials for every candidate
# ---------------------------------------------------------------------------
fin_at = avail_financials(financials, as_of)


def series_of(periods):
    """Revenue YoY (same-quarter YoY, newest-first) + GM series."""
    rev_by_qp = {}
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
    yoy = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    gm = []
    for pk in sorted(periods.keys(), key=lambda p: (int(p[:4]), int(p[5:])), reverse=True):
        v = periods[pk].get("gross_margin")
        if v is not None:
            gm.append(v)
    return yoy, gm


def drawdown_1y(monthly, dt):
    """Drawdown from the trailing 1-year high of monthly closes (point-in-time)."""
    closes = [(mk, v) for mk, v in sorted(monthly.items())
              if mk <= dt and v and v > 0]
    if len(closes) < 6:
        return None
    window = closes[-13:]
    high = max(v for _, v in window)
    cur = window[-1][1]
    if high <= 0:
        return None
    return max(0.0, 1.0 - cur / high)


def conviction_proxy(n_hooks, hook_ids, latest_yoy):
    base = 0.5 + 0.2 * (n_hooks - 1)
    growth_boost = 0.3 * min(max(latest_yoy, 0.0), 1.5) / 1.5
    h1_boost = 0.05 if "H1" in hook_ids else 0.0
    return min(1.0, base + growth_boost + h1_boost)


# ---------------------------------------------------------------------------
# 4. Full raw financial data for the target (all periods, all fields)
# ---------------------------------------------------------------------------
target_tk, target_name, target_sw1 = target
periods = fin_at.get(target_tk, {})

print("\n" + "=" * 80)
print(f"RAW FINANCIAL DATA for {target_name} ({target_tk}) — point-in-time <= {as_of}")
print("=" * 80)
print(f"Periods available after PIT filter: {len(periods)}")
print(f"Raw (unfiltered) periods in file:   {len(financials.get(target_tk, {}))}")
all_fields = sorted({k for m in financials.get(target_tk, {}).values() for k in m})
print(f"All field keys present: {all_fields}")
print()

# Raw (everything in the file, including future periods)
print("--- ALL RAW PERIODS (file, newest-first) ---")
for pk in sorted(financials.get(target_tk, {}).keys(),
                 key=lambda p: (int(p[:4]), int(p[5:])), reverse=True):
    m = financials[target_tk][pk]
    print(f"  {pk}: " + ", ".join(f"{k}={v}" for k, v in sorted(m.items())))

print("\n--- PERIODS AFTER PIT FILTER (newest-first) ---")
for pk in sorted(periods.keys(), key=lambda p: (int(p[:4]), int(p[5:])), reverse=True):
    m = periods[pk]
    print(f"  {pk}: " + ", ".join(f"{k}={v}" for k, v in sorted(m.items())))

# ---------------------------------------------------------------------------
# 5. YoY / GM / drawdown / hooks / conviction for the target
# ---------------------------------------------------------------------------
yoy, gm_series = series_of(periods)
dd = drawdown_1y(prices_all.get(target_tk, {}), MONTH)

print("\n" + "=" * 80)
print(f"COMPUTED METRICS for {target_name} ({target_tk})")
print("=" * 80)
print(f"Revenue YoY series (same-quarter, newest-first, n={len(yoy)}):")
for i, g in enumerate(yoy):
    print(f"  YoY[{i}] = {g:.4f} ({g:.2%})")
print(f"\nGross Margin series (newest-first, n={len(gm_series)}):")
for i, g in enumerate(gm_series):
    print(f"  GM[{i}] = {g:.2f}%")
print(f"\n1-year drawdown (as of {MONTH}): "
      f"{dd:.2%}" if dd is not None else "\n1-year drawdown: None (insufficient data)")

# Raw prices for 2023-2024 (target)
px = prices_all.get(target_tk, {})
print("\n--- RAW MONTHLY PRICES 2023–2024 (warmup+prices merged) ---")
for mk, v in sorted(px.items()):
    if "2023" in mk or "2024" in mk:
        print(f"  {mk}: {v}")

# ---------------------------------------------------------------------------
# 6. Hooks + conviction for the target
# ---------------------------------------------------------------------------
res = evaluate_hooks(yoy, gm_series, dd, beats=None)
hooks = [h["id"] for h in res["tripped"]]

print("\n" + "=" * 80)
print(f"HOOK EVALUATION for {target_name} ({target_tk})")
print("=" * 80)
print(f"Tripped hooks: {hooks if hooks else 'None'}")
for h in res["tripped"]:
    print(f"  {h['id']} {h['name']}")
    print(f"    Evidence: {h['evidence']}")
print(f"Computed (internal): {res['computed']}")

if hooks and yoy:
    conv = conviction_proxy(len(hooks), hooks, yoy[0])
    print(f"\nCONVICTION PROXY:")
    print(f"  n_hooks     = {len(hooks)}")
    print(f"  hook_ids    = {hooks}")
    print(f"  latest_yoy  = {yoy[0]:.4f}")
    base = 0.5 + 0.2 * (len(hooks) - 1)
    gb = 0.3 * min(max(yoy[0], 0.0), 1.5) / 1.5
    h1b = 0.05 if "H1" in hooks else 0.0
    print(f"  base        = 0.5 + 0.2*({len(hooks)}-1) = {base:.4f}")
    print(f"  growth_boost= 0.3*min({yoy[0]:.4f},1.5)/1.5 = {gb:.4f}")
    print(f"  h1_boost    = {h1b:.4f}")
    print(f"  conviction  = {conv:.4f}")
else:
    conv = None
    print(f"\nCONVICTION PROXY: N/A (no hooks triggered or no YoY data)")

# ---------------------------------------------------------------------------
# 7. Scan ALL 2024-08 candidates for hook triggers
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print(f"HOOK SCAN — ALL {len(candidates)} CANDIDATES in {MONTH}")
print("=" * 80)
print(f"{'ticker':<11} {'name':<10} {'industry':<8} {'hooks':<12} {'latest_yoy':>10}  conviction")
print("-" * 78)

scan = []
for tk, name, sw1 in candidates:
    pf = fin_at.get(tk, {})
    yy, gm = series_of(pf)
    d = drawdown_1y(prices_all.get(tk, {}), MONTH)
    r = evaluate_hooks(yy, gm, d, beats=None)
    hs = [h["id"] for h in r["tripped"]]
    ly = yy[0] if yy else None
    cv = conviction_proxy(len(hs), hs, ly) if hs and ly is not None else None
    scan.append((tk, name, sw1, hs, ly, cv, d))
    if hs:
        tag = "+".join(hs)
        print(f"{tk:<11} {name:<10} {sw1:<8} {tag:<12} {ly:>10.4f}  {cv:.4f}")
    else:
        ly_s = f"{ly:.4f}" if ly is not None else "n/a"
        print(f"{tk:<11} {name:<10} {sw1:<8} {'-':<12} {ly_s:>10}  -")

tripped_rows = [s for s in scan if s[3]]
print(f"\nSUMMARY: {len(tripped_rows)} of {len(candidates)} candidates triggered hooks:")
for tk, name, sw1, hs, ly, cv, d in tripped_rows:
    print(f"  {name} ({tk}) [{sw1}] -> hooks={'+'.join(hs)}, "
          f"latest_yoy={ly:.4f}, drawdown={d if d is None else f'{d:.2%}'}, "
          f"conviction={cv:.4f}")

# ---------------------------------------------------------------------------
# 8. Final summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)
print(f"Stock:     {target_name} ({target_tk})")
print(f"Rebalance: {MONTH} | as-of: {as_of}")
print(f"Industry:  {target_sw1}")
print(f"Hooks:     {'+'.join(hooks) if hooks else 'None'}")
if conv is not None:
    print(f"Conviction:{conv:.4f}")
print(f"\nAll hook-triggering stocks in {MONTH}:")
for tk, name, sw1, hs, ly, cv, d in tripped_rows:
    print(f"  {name} ({tk})  {'+'.join(hs)}  conviction={cv:.4f}")
