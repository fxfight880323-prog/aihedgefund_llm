"""科创50 GOAL→HOOK→LOOP 选股 — 按剧本流程跑完整一轮。

流程（严格按 growth_stock_goal_hook_loop_playbook.md）：

  ① HOOK 全 universe 筛选（PROMPT H-1）
     科创50 成分股（妙想 TOOL_INDEX 实时获取）→ 每票一次合并查询
     （3期营收YoY + 毛利率 + 近一年最高价 + 最新价）→ evaluate_hooks
     规则求值 → A/B/C 优先级排名，A 上限 3 只（强制排名）
  ② LOOP 深研（A 优先级，LangGraph 门控子图）
     L1 业务/TAM → L2 增长分解 → L3 单位经济 → L4 护城河 →
     L5 管理层 → L6 Reverse-DCF → L7 红队 → L8 确定性信念
     全部走真实智谱 GLM-4 + 妙想全量个股数据
  ③ 选股报告：hook 证据、各阶段门控与评分、信念值、tripwires、
     kill 日志（KILLED 也是信息——剧本的 edge-improvement dataset）

积分效率：HOOK 层每票仅 1 次妙想查询（50 票 ≈ 50 次，线程并发）；
LOOP 层每票 ~4 次查询（≤3 只 A 优先级）。

Run:
    python examples/kechuang50_selection.py [--max-a 3] [--skip-loop]
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.data.mx_data_client import sheet_to_indexed, parse_cn_number
from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE, TOOL_INDEX
from src.signals.growth_loop import GrowthLoopAgent
from src.signals.hooks import evaluate_hooks
from src.utils.llm_client import get_default_llm_client

AS_OF = date.today().isoformat()
MAX_A = 3
HOOK_WORKERS = 3          # 妙想查询并发数（过高触发限流 → 大量空响应）
PERIOD_RANK = {"一季报": 1, "中报": 2, "半年报": 2, "二季报": 2,
               "三季报": 3, "年报": 4}


# ===========================================================================
# ① 成分股
# ===========================================================================

def fetch_constituents(cli: MXMCPClient) -> list[tuple[str, str, float | None]]:
    """[(ticker, name, close), ...] — 科创50 最新成分（close 为当日收盘）。"""
    sheets = cli.query(
        TOOL_INDEX, "科创50指数最新的50只成分股名单，输出股票代码和简称"
    )
    out: list[tuple[str, str, float | None]] = []
    for sheet in sheets:
        cols = sheet.get("columns", [])
        if "证券代码" not in cols:
            continue
        i_code, i_name = cols.index("证券代码"), cols.index("证券简称")
        i_close = cols.index("收盘价") if "收盘价" in cols else None
        for row in sheet.get("items", []):
            code = str(row[i_code]).strip()
            name = str(row[i_name]).strip() if i_name < len(row) else ""
            close = (parse_cn_number(str(row[i_close]))
                     if i_close is not None and i_close < len(row) else None)
            if code and code != "证券代码":
                out.append((code, name, close))
    return out


# ===========================================================================
# ② 单票合并查询 → hook 输入
# ===========================================================================

def fetch_hook_inputs(
    cli: MXMCPClient, ticker: str, name: str, fallback_close: float | None = None
) -> dict:
    """一次妙想查询拿全 hook 需要的指标（省积分路径）。"""
    q = (
        f"{name}({ticker}) 最近3个报告期的营业收入同比增速、"
        f"最近2个报告期的销售毛利率、近一年最高价、最新收盘价"
    )
    yoy_by_period: dict[str, float] = {}
    gm_by_period: dict[str, float] = {}
    high_1y: float | None = None
    last_close: float | None = fallback_close  # 成分股 sheet 的当日收盘

    def _parse_sheets(sheet_list):
        nonlocal high_1y, last_close
        for sheet in sheet_list:
            indexed = sheet_to_indexed(sheet)
            for metric, by_col in indexed.items():
                for col, val in by_col.items():
                    col_s, val_s = str(col), str(val)
                    if "营业收入同比增长" in metric and _is_period(col_s):
                        v = _yoy_fraction(val_s)      # '34.13%' → 0.3413
                        if v is not None:
                            yoy_by_period[_period_key(col_s)] = v
                    elif "毛利率" in metric and _is_period(col_s):
                        v = parse_cn_number(val_s)    # 保持百分比刻度 (39.89)
                        if v is not None:
                            gm_by_period[_period_key(col_s)] = v
                    elif ("最高价" in metric and "日" not in metric
                          and col_s != "区间最高价日"):
                        v = parse_cn_number(val_s)
                        if v is not None and (high_1y is None or v > high_1y):
                            high_1y = v
                    elif metric.strip() in ("最新价", "最新收盘价"):
                        # 不匹配"收盘价"——那是多日时序行，列序不可靠
                        v = parse_cn_number(val_s)
                        if v is not None:
                            last_close = v

    try:
        sheets = cli.query(TOOL_ASHARE, q)
        _parse_sheets(sheets)
        # 妙想并发下偶发空响应（且空结果会被缓存）——解析不到 YoY 时
        # 绕过缓存重试一次
        if not yoy_by_period:
            _parse_sheets(cli.query(TOOL_ASHARE, q, use_cache=False))
    except Exception as exc:
        return {"ticker": ticker, "name": name, "error": str(exc)}

    # 兜底：同比增速问不出来时，改问营收绝对额 + 毛利率，同期自算 YoY
    # （不同问题形状，妙想响应稳定性不同）
    if not yoy_by_period:
        try:
            fb = cli.query(
                TOOL_ASHARE,
                f"{name}({ticker}) 最近9个报告期的营业收入、销售毛利率",
                use_cache=False,
            )
            rev_by_period: dict[str, float] = {}
            for sheet in fb:
                for metric, by_col in sheet_to_indexed(sheet).items():
                    for col, val in by_col.items():
                        col_s, val_s = str(col), str(val)
                        if not _is_period(col_s):
                            continue
                        v = parse_cn_number(val_s)
                        if v is None:
                            continue
                        if "营业收入" in metric and "同比" not in metric:
                            rev_by_period[_period_key(col_s)] = v
                        elif "毛利率" in metric:
                            gm_by_period.setdefault(_period_key(col_s), v)
            for k, v in rev_by_period.items():
                prev = _prev_period_key(k)
                if prev in rev_by_period and rev_by_period[prev] > 0:
                    yoy_by_period[k] = v / rev_by_period[prev] - 1.0
        except Exception:
            pass

    # 合并查询的响应形状不稳定（有时只回"年最高价日"日期行，最高价数值
    # 被丢）——缺失时补一次专查，专查稳定返回数值。
    if high_1y is None:
        try:
            extra = cli.query(TOOL_ASHARE, f"{name}({ticker}) 近一年最高价")
            _parse_sheets(extra)
        except Exception:
            pass

    # newest-first 排序（period_key 字符串序 = 时间序）
    yoy = [yoy_by_period[k] for k in sorted(yoy_by_period, reverse=True)]
    gm = [gm_by_period[k] for k in sorted(gm_by_period, reverse=True)]

    drawdown = None
    if last_close and high_1y:
        drawdown = 1.0 - last_close / high_1y

    return {
        "ticker": ticker, "name": name,
        "revenue_yoy": yoy, "gm_series": gm,
        "high_1y": high_1y, "last_close": last_close, "drawdown": drawdown,
    }


def _is_period(col: str) -> bool:
    return any(p in col for p in PERIOD_RANK)


def _period_key(col: str) -> str:
    """'2026一季报' → '2026-1'，使字符串排序 = 时间排序。"""
    import re
    m = re.search(r"(\d{4})", col)
    year = m.group(1) if m else "0000"
    for cn, rank in PERIOD_RANK.items():
        if cn in col:
            return f"{year}-{rank}"
    return f"{year}-0"


def _prev_period_key(k: str) -> str:
    """'2026-1' → '2025-1'（同期匹配 YoY 用）。"""
    year, _, rest = k.partition("-")
    try:
        return f"{int(year) - 1}-{rest}"
    except ValueError:
        return k


def _yoy_fraction(v: str) -> float | None:
    """'34.13%' → 0.3413（妙想同比给的是百分数）；'-' → None。"""
    n = parse_cn_number(v)
    return None if n is None else n / 100.0


# ===========================================================================
# ③ HOOK 筛选 + A/B/C 排名
# ===========================================================================

def run_hook_screen(
    cli: MXMCPClient, universe: list[tuple[str, str, float | None]]
) -> dict:
    from src.data.cache import DiskCache

    inputs: dict[str, dict] = {}
    # 跨轮持久化并集：妙想同题响应不稳定，某轮拿到的数据落盘后永久复用
    # （否则像摩尔线程/沐曦那样"上轮有、本轮无"就凭空丢失）。
    store = DiskCache()

    def _pass(items, label):
        """一轮并发取数；成功结果并入 inputs 并落盘（并集语义）。"""
        with ThreadPoolExecutor(max_workers=HOOK_WORKERS) as pool:
            futs = {pool.submit(fetch_hook_inputs, cli, tk, nm, close): tk
                    for tk, nm, close in items}
            done = 0
            for fut in as_completed(futs):
                tk = futs[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"ticker": tk, "error": str(exc)}
                if res.get("revenue_yoy"):  # 有数据才覆盖（并集）
                    inputs[tk] = res
                    try:
                        store.put(res, "kc50_hook_inputs", tk)
                    except Exception:
                        pass
                done += 1
                if done % 10 == 0:
                    print(f"    … {label} {done}/{len(items)}", flush=True)

    # 先读历史轮次的持久化结果作为种子
    seeded = 0
    for tk, _nm, _close in universe:
        prev = store.get("kc50_hook_inputs", tk)
        if prev and isinstance(prev, dict) and prev.get("revenue_yoy"):
            inputs[tk] = prev
            seeded += 1
    if seeded:
        print(f"    … 载入历史轮次持久化数据: {seeded} 只", flush=True)

    _pass(universe, "pass1")

    # 妙想自然语言查询响应不稳定（同题时有时无）——对缺数据的票补查到
    # 覆盖完整为止（上限 4 轮），任一轮拿到数据即入池。覆盖率（而不是
    # 市值）才是 universe 筛选的真正瓶颈。
    for round_no in (2, 3, 4):
        misses = [(tk, nm, close) for tk, nm, close in universe
                  if not inputs.get(tk, {}).get("revenue_yoy")]
        if not misses:
            break
        print(f"    … retry pass{round_no}: {len(misses)} 只补查", flush=True)
        _pass(misses, f"pass{round_no}")

    a_cands, b_list, c_list = [], [], []
    for tk, nm, _close in universe:
        inp = inputs.get(tk) or {"ticker": tk, "name": nm,
                                 "error": "no data after 3 passes"}
        if inp.get("error") or not inp.get("revenue_yoy"):
            c_list.append({**inp, "hooks": [], "tripped": []})
            continue
        res = evaluate_hooks(
            inp["revenue_yoy"], inp["gm_series"], inp["drawdown"], beats=None,
        )
        item = {**inp, "tripped": res["tripped"],
                "hooks": [h["id"] for h in res["tripped"]]}
        if item["hooks"]:
            a_cands.append(item)
        else:
            b_list.append(item)

    a_cands.sort(key=lambda x: (-len(x["hooks"]), -(x["revenue_yoy"][0])))
    return {"A": a_cands[:MAX_A], "A_overflow": a_cands[MAX_A:],
            "B": b_list, "C": c_list}


# ===========================================================================
# ④ LOOP 深研（LangGraph + 真实 GLM-4）
# ===========================================================================

def run_loops(a_list: list[dict]) -> list:
    from src.data.mx_data_client import MXDataClient

    llm = get_default_llm_client()
    if llm is None:
        print("\n  ⚠️  ZHIPU_API_KEY 未配置，LOOP 阶段跳过\n")
        return []
    agent = GrowthLoopAgent(
        target_return=0.15, horizon_years=3, min_revenue_growth=0.20,
        universe_note="科创50指数全部成分股（50只）— 无市值限制，"
                      "从小市值到大市值一视同仁，仅按基本面与钩子证据评估",
        llm_client=llm,
    )
    signals = []
    for item in a_list:
        tk = item["ticker"]
        print(f"\n  ── LOOP: {tk} {item['name']} ──", flush=True)
        # LOOP 数据包用全新缓存：上一轮跑挂时可能把空响应缓存住了
        import tempfile
        from src.data.cache import DiskCache
        mx_data = MXDataClient(cache=DiskCache(tempfile.mkdtemp()))
        try:
            sig = agent.predict(
                tk, AS_OF, mx_data,
                hook_result={  # 注入批量筛选证据，LOOP 不重复取数（剧本:
                    # HOOK 周度全 universe 一次，A 名单直接进 LOOP）
                    "tripped": item["tripped"],
                    "computed": {
                        "revenue_yoy": item.get("revenue_yoy"),
                        "gross_margin": item.get("gm_series"),
                        "drawdown_1y": item.get("drawdown"),
                        "recent_beats": None,
                    },
                    "data_ok": True,
                },
            )
        except Exception as exc:
            print(f"    LOOP error: {exc}")
            continue
        signals.append((item, sig))
        m = sig.metadata
        status = m.get("status")
        if status == "PASSED":
            print(f"    ✅ PASSED  conviction={sig.value:+.2f} "
                  f"(kill_stage=-)")
        else:
            print(f"    ❌ {status} @ {m.get('kill_stage')}: "
                  f"{(m.get('kill_reason') or '')[:90]}")
    return signals


# ===========================================================================
# 报告
# ===========================================================================

def print_report(ranked: dict, signals: list) -> None:
    print("\n" + "=" * 78)
    print(f"  科创50 GOAL→HOOK→LOOP 选股报告   as_of={AS_OF}")
    print("=" * 78)

    print(f"\n  [A 优先级 — 进入 LOOP]  (剧本规则: 上限 {MAX_A} 只)")
    for it in ranked["A"]:
        yoy = it["revenue_yoy"][0] if it.get("revenue_yoy") else 0
        print(f"    {it['ticker']} {it['name']:6s} hooks={'+'.join(it['hooks']):8s}"
              f" 最新YoY={yoy:+.1%} 回撤={it.get('drawdown', 0) or 0:.0%}")
        for h in it["tripped"]:
            print(f"        └─ {h['id']}: {h['evidence']}")
    if ranked["A_overflow"]:
        names = ", ".join(f"{i['ticker']}({'/'.join(i['hooks'])})"
                          for i in ranked["A_overflow"])
        print(f"\n  [A 溢出 → 观察名单]  {names}")

    print(f"\n  [B 观察] {len(ranked['B'])} 只   "
          f"[C 数据缺失丢弃] {len(ranked['C'])} 只")

    if signals:
        print("\n  " + "─" * 74)
        print("  LOOP 深研结果 (LangGraph L1→L7 门控 + L8 信念)")
        print("  " + "─" * 74)
        for item, sig in signals:
            m = sig.metadata
            print(f"\n  ◆ {item['ticker']} {item['name']}"
                  f"   hooks={'+'.join(item['hooks'])}")
            print(f"    Signal value = {sig.value:+.3f}   "
                  f"status={m.get('status')}   "
                  f"kill=@{m.get('kill_stage') or '-'}")
            comps = sig.components
            if comps:
                stages = " ".join(
                    f"{k}={v:.0f}" for k, v in sorted(comps.items())
                    if k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7")
                )
                print(f"    阶段分: {stages}")
            print(f"    {sig.reasoning[:110]}")
            for tw in (m.get("tripwires") or [])[:3]:
                print(f"    ⚡ {tw[:90]}")
            lb = m.get("loop_backs")
            if lb:
                print(f"    回环合计: {lb}   黄旗: {m.get('yellow_flags')}"
                      f"   空头强度: {m.get('short_strength')}")

        print("\n  " + "─" * 74)
        passed = [(i, s) for i, s in signals if s.value > 0]
        print("  ★ 选股结论:")
        if passed:
            for item, sig in sorted(passed, key=lambda x: -x[1].value):
                print(f"    入选 {item['ticker']} {item['name']}: "
                      f"conviction {sig.value:+.2f} → 按策略 blend+risk 定仓"
                      f"（剧本 GOAL: 单票上限 8%）")
        else:
            print("    本周无标的通过全部门控 — 空仓等待也是决策"
                  f"（kill 日志见上，剧本: kill log 即 edge 数据集）")
    print("\n" + "=" * 78)


# =========================================================================##

def main():
    from src.data.mx_data_client import MXDataClient

    print("=" * 78)
    print("  科创50 GOAL→HOOK→LOOP 选股")
    print(f"  as_of: {AS_OF}   HOOK并发: {HOOK_WORKERS}   A上限: {MAX_A}")
    print("=" * 78)

    cli = MXMCPClient()
    print("\n  ① 获取科创50成分股…", flush=True)
    universe = fetch_constituents(cli)
    print(f"    {len(universe)} 只成分股: "
          f"{universe[0][1]}、{universe[1][1]}、{universe[2][1]} …")

    print("\n  ② HOOK 全 universe 筛选（每票1次合并查询）…", flush=True)
    ranked = run_hook_screen(cli, universe)
    n_hooked = len(ranked["A"]) + len(ranked["A_overflow"])
    print(f"    触发 hook: {n_hooked} 只 → A={len(ranked['A'])} "
          f"B={len(ranked['B'])} C={len(ranked['C'])}")

    print("\n  ③ LOOP 深研（LangGraph 门控子图 × 真实 GLM-4）…")
    signals = run_loops(ranked["A"])

    print_report(ranked, signals)


if __name__ == "__main__":
    main()
