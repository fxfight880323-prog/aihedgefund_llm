# -*- coding: utf-8 -*-
"""统一总控入口 —— 以后更新数据只跑这一个文件。

用法:
    python run.py daily            # 模拟组合每日净值（LX-top40 + Q20）
    python run.py screen           # 数据刷新 + 三轨名单（主轨/KFIN/q20）
    python run.py backtest         # 权威回测集重跑（--only garp 可指定）
    python run.py all              # screen + backtest 全流程
    python run.py status           # 数据新鲜度体检
    python run.py --list           # 预览所有步骤（不执行）

可选参数:
    --continue-on-error   单个步骤失败后继续（默认 fail-fast）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import config
from pipeline import dates
from pipeline import runner


def cmd_status():
    rows = dates.freshness_status()
    print(f"\n📋 数据新鲜度体检（今天 {json.dumps(dates.candidate_dates(1)[0])} 为最近工作日候选）")
    print(f"{'组件':<14}{'文件':<34}{'as_of':<12}{'状态':<8}备注")
    print("-" * 90)
    for r in rows:
        st = "✅ 最新" if r["fresh"] else "⚠️ 滞后"
        print(f"{r['key']:<14}{r['file']:<34}{str(r['as_of']):<12}{st:<8}{r['note']}")
    stale = [r for r in rows if not r["fresh"] and r["key"] not in ("universe PIT成分",)]
    # 模拟组合净值在非交易日自然滞后，不作为"过期"信号
    nav_stale = [r for r in rows if not r["fresh"] and ("净值" in r["key"] or "账本" in r["key"])]
    data_stale = [r for r in rows if not r["fresh"] and r["key"] not in
                  ("universe PIT成分",) and "净值" not in r["key"] and "账本" not in r["key"]]
    if data_stale:
        print(f"\n⚠️ {len(data_stale)} 项数据缓存滞后 → 跑 `python run.py screen` 刷新名单")
    if nav_stale and dates.candidate_dates(1)[0] == __import__("datetime").date.today().isoformat():
        pass  # 净值滞后说明今天自动化已跑或非交易日，不额外提示
    print("\n✅ 体检完成。日常命令：python run.py daily | screen | backtest | all")


def main():
    if hasattr(sys.stdout, "reconfigure"):   # Windows GBK 控制台 → UTF-8 + 行缓冲（保证子进程输出顺序）
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = argparse.ArgumentParser(description="ai_fund_framework 统一数据管线")
    ap.add_argument("cmd", nargs="?", choices=["daily", "screen", "backtest", "all",
                                               "status", "audit"],
                    default=None, help="daily=净值跟踪 | screen=名单刷新 | "
                    "backtest=权威回测 | all=全流程 | status=体检 | audit=一致性审计")
    ap.add_argument("--list", action="store_true", help="预览所有步骤（不执行）")
    ap.add_argument("--only", default=None, help="只跑指定步骤（子串匹配步骤名）")
    ap.add_argument("--continue-on-error", action="store_true")
    args = ap.parse_args()

    print(f"解释器: {config.PY}\n工作目录: {config.ROOT}")

    if args.list:
        print("\n=== 可执行步骤预览（不运行）===")
        for s in runner.screen_steps():
            print(f"  [screen] {s.name}")
        for s in runner.BACKTEST_STEPS:
            print(f"  [backtest] {s.name}")
        for s in runner.sim_steps():
            print(f"  [daily] {s.name}")
        print(f"  [audit] {runner.audit_step().name}")
        print("\n运行方式：python run.py <daily|screen|backtest|all|audit> [--only 子串] "
              "[--continue-on-error]")
        return

    if args.cmd is None:
        ap.print_help()
        return

    if args.cmd == "status":
        cmd_status()
        return

    steps: list = []
    if args.cmd in ("screen", "all"):
        steps += runner.screen_steps()
    if args.cmd == "backtest":
        steps += runner.BACKTEST_STEPS
    if args.cmd == "all":
        steps += runner.BACKTEST_STEPS
    if args.cmd == "daily":
        steps += runner.sim_steps()
    if args.cmd == "audit":
        steps = [runner.audit_step()]

    if args.only:
        steps = [s for s in steps if args.only in s.name]
        if not steps:
            print(f"!! --only {args.only!r} 无匹配步骤")
            sys.exit(1)

    print(f"\n共 {len(steps)} 个步骤，开始执行（{datetime_now()}）")
    ok, failed = runner.run_steps(steps, continue_on_error=args.continue_on_error)
    print(f"\n{'='*70}\n结果: 成功 {len(ok)} / 失败 {len(failed)}")
    for s in failed:
        print(f"  ✘ {s.name}")
    if failed:
        if args.cmd == "audit":
            # 审计差异 = 提示性（数据更新效应），非管线错误
            print("\n⚠️ 审计发现差异（非管线错误）→ 详见 _pipeline_audit_report.html")
            sys.exit(2)
        sys.exit(1)
    print("✅ 全部完成")


def datetime_now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
