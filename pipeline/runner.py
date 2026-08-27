# -*- coding: utf-8 -*-
"""步骤定义与执行器：把已验证的脚本编排成可重复运行的管线。

原则：
  1. 不移动/不重写已验证脚本（自动化任务引用绝对路径）——只按序调用。
  2. 每个 Step = 脚本 + 产物校验；失败即停（fail-fast），可 --continue-on-error。
  3. 数据流唯一入口 _lx_now_fetch.py，日期由 pipeline/dates.py 自动注入，
     不再手工改 CANDIDATE_DATES。
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from . import config
from .dates import candidate_dates


@dataclass
class Step:
    name: str
    script: str                       # 相对 ROOT 的脚本路径
    outputs: tuple = ()               # 期望产物（相对 ROOT），用于校验
    args: list = field(default_factory=list)
    desc: str = ""

    @property
    def cmd(self) -> list:
        return [config.PY, os.path.join(config.ROOT, self.script), *self.args]


# ---------------------------------------------------------------- 数据刷新
def data_refresh_step() -> Step:
    """万得全A PIT 成分 / 估值面板 / HF 因子 / 一致预期 全量拉取（缓存幂等）。"""
    return Step(
        name="① 数据拉取（万得全A PIT/估值/HF因子/一致预期）",
        script="_lx_now_fetch.py",
        args=["--candidate-dates", ",".join(candidate_dates())],
        outputs=("_bt_lx_now_universe.json", "_bt_lx_now_valuation.json",
                 "_bt_lx_now_factors.json", "_bt_lx_now_consensus.json"),
        desc="候选交易日自动注入；非交易日/HF因子污染日由脚本内部探测自动回退",
    )


# ---------------------------------------------------------------- 名单筛选（三轨）
def screen_steps() -> list[Step]:
    return [
        data_refresh_step(),
        Step("② 主轨筛选（剔金融, LX-core+garp）", "_lx_now_screen.py",
             outputs=("_lx_now_results.json", "刘旭框架_当前推荐A股.csv",
                      "_lx_now_report.html")),
        Step("③ 主轨评分（价值50/质量25/安全25）", "_lx_now_score.py",
             outputs=("_lx_now_scored.json", "刘旭框架_评分排名.csv")),
        Step("④ 估值Band（5年自身分位, 40只×5年）", "_lx_now_band.py",
             outputs=("_lx_now_band.json", "_lx_now_band_report.html")),
        Step("⑤ Band规避剔除(PB分位>90%)→final", "_lx_band_apply.py",
             outputs=("_lx_now_final.json", "刘旭框架_最终推荐.csv",
                      "_lx_now_final_report.html")),
        Step("⑥ KFIN轨筛选（含金融, core原始口径）", "_lx_now_screen_kfin.py",
             outputs=("_lx_now_results_kfin.json", "刘旭框架_当前推荐A股_含金融.csv",
                      "_lx_now_report_kfin.html")),
        Step("⑦ KFIN Band → final", "_lx_kfin_band.py",
             outputs=("_lx_kfin_final.json", "_lx_kfin_final_report.html")),
        Step("⑧ q20 混合排序（0.8×PE+0.2×质量）top40", "_bt_q20_kfin.py",
             outputs=("_bt_q20_kfin.json", "_bt_q20_kfin.html"),
             desc="读 KFIN 池（含金融 core-pass），blend20 降序 top40 + band 规避递补"),
    ]


# ---------------------------------------------------------------- 一致性审计
def audit_step() -> Step:
    """screen 全链产物 vs 模拟组合账本一致性审计（账本-名单差异=数据更新效应提示）。"""
    return Step(
        name="⑨ 一致性审计（名单 vs 模拟组合账本）",
        script="_pipeline_audit.py",
        outputs=("_pipeline_audit_report.html",),
        desc="校验 q20 final ↔ Q20 账本 / 行业构成 / 资金使用率；差异≠bug，提示数据更新效应",
    )


# ---------------------------------------------------------------- 权威回测集
BACKTEST_STEPS = [
    Step("garp 审计（双基座全池，权威报告）", "_bt_garp_audit_report.py",
         outputs=("_bt_garp_audit_report.html",),
         desc="全池 g60 +67.01%/超EW +25.88pp —— 唯一可引用权威口径"),
    Step("质量硬过滤证伪（gm vs core）", "_bt_gm_report.py",
         outputs=("_bt_gm_report.html",),
         desc="gm 硬门槛 -21.94pp 证伪；质量层只能排序微调"),
    Step("质量放松 q20 增量验证", "_bt_qrelax_report.py",
         outputs=("_bt_qrelax_report.html",),
         desc="q20(0.8×PE+0.2×质量) +3.40pp 唯一正贡献用法"),
    Step("全景总结（11节，汇总全部权威结论）", "_ai_fund_framework_summary.py",
         outputs=("_ai_fund_framework_summary.html",)),
]


# ---------------------------------------------------------------- 模拟组合跟踪
def sim_steps(only: str | None = None) -> list[Step]:
    steps = [
        Step("LX-top40 每日净值", "_sim_daily.py", desc="幂等：非交易日/盘前自动 SKIP"),
        Step("Q20·质衡优选 每日净值", "_sim_q20_daily.py", desc="幂等：非交易日/盘前自动 SKIP"),
    ]
    if only:
        steps = [s for s in steps if only in s.name]
    return steps


# ---------------------------------------------------------------- 执行器
def run_steps(steps: list[Step], continue_on_error: bool = False) -> tuple[list, list]:
    """顺序执行步骤，返回 (成功, 失败)。stdout 实时透传。"""
    ok, failed = [], []
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}   # 子脚本中文输出不乱码
    for s in steps:
        print(f"\n{'='*70}\n▶ {s.name}\n  {config.PY} {s.script}"
              + (f" {s.args}" if s.args else "")
              + (f"\n  {s.desc}" if s.desc else ""))
        try:
            r = subprocess.run(s.cmd, cwd=config.ROOT, shell=False, env=env)
            if r.returncode != 0:
                raise RuntimeError(f"exit={r.returncode}")
            missing = [o for o in s.outputs
                       if not os.path.exists(os.path.join(config.ROOT, o))]
            if missing:
                raise RuntimeError(f"产物缺失: {missing}")
            ok.append(s); print(f"  ✔ {s.name} 完成")
        except Exception as e:
            failed.append(s)
            print(f"  ✘ {s.name} 失败: {e}")
            if not continue_on_error:
                break
    return ok, failed
