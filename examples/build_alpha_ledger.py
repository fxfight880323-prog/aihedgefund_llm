# -*- coding: utf-8 -*-
"""构建三层 Alpha 账本（alpha_ledger/ledger.json）并生成对比报告.

数据来源：全部为项目内真实回测结果（_bt_*.json + docs/ALPHA_LAYERS.md 已记结论）：
  - _bt_cscore_results.json      (C-Score/F×C/F-Score 三臂)
  - _bt_zhf_veto_results.json    (ZHF-veto 四臂 + EW-全A)
  - _bt_gl_valsell_*.json        (Growth Loop 估值卖出系列)
  - docs/ALPHA_LAYERS.md         (已沉淀结论：否决制+4.7pp, ROA加权-3.7pp, Growth Trap 等)

用法：python examples/build_alpha_ledger.py
输出：alpha_ledger/ledger.json + alpha_ledger/alpha_ledger_report.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.research.alpha_ledger import AlphaLedger  # noqa: E402


def load_json(name: str):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> None:
    ledger = AlphaLedger(ROOT / "alpha_ledger" / "ledger.json")

    # 全局 benchmark：EW-全A（以 _bt_zhf_veto_results.json 实测为准）
    veto = load_json("_bt_zhf_veto_results.json") or {}
    ew = veto.get("ew", {}) or {}
    ledger.benchmarks["ew_all_a"] = {
        "name": "EW-全A（等权万得全A PIT 成分池）",
        "total": ew.get("total", 0.5294),
        "ann": ew.get("ann"),
        "note": "所有回测必须先与等权池子对比再下结论（用户铁律）",
    }

    # ============================================================ L1 数据层
    ledger.add_entry(
        layer="data",
        name="juzi 一致预期 PIT 数据（con_forecast_stk）",
        status="VERIFIED",
        excess=0.181,  # C-Score 超额 26.2pp − F-Score 超额 8.1pp = 数据增量 18.1pp
        total=0.307,
        mdd=-0.229,
        benchmark="F-Score 财报数据基线",
        source="juzi-mcp factor_get_consensus_forecast（PIT 快照，parquet 全市场）",
        method="同一 C-Score 矩阵构造，仅换数据源（财报→一致预期）",
        evidence="C-Score +30.7%/超额+26.2pp vs F-Score +12.6%/超额+8.1pp；数据增量 +18.1pp，10期8期跑赢",
        ref="_bt_cscore_results.json / _bt_cscore_nav.json",
    )
    ledger.add_entry(
        layer="data",
        name="万得全A 881001.WI PIT 成分（基准池）",
        status="VERIFIED",
        excess=0.0,
        benchmark="无（基础设施）",
        source="juzi-mcp factor_get_universe_members('881001.WI', as_of_date)",
        method="每期 PIT 成分作为全市场池子，剔除手工精选股池偏差",
        evidence="消除幸存者偏差约 53pp：龙头池等权 5年+455% vs 全A等权 +52.9%",
        ref="_bt_zhf_pool_nav.json / _bt_winda_universe.json",
    )
    ledger.add_entry(
        layer="data",
        name="腾讯月K 行情（线程池全市场）",
        status="VERIFIED",
        excess=0.0,
        benchmark="无（基础设施）",
        source="qt.gtimg.cn 月K，16 workers，~5500 只 5-8 分钟",
        method="回测价格数据，N月末下单 N+1月成交",
        evidence="支撑全市场 5.2 年回测的基础数据管线",
        ref="_bt_fscore_prices.json / _bt_winda_prices.json",
    )
    ledger.add_entry(
        layer="data",
        name="券商/新 MCP（westock / wind / gildata 等）",
        status="CANDIDATE",
        benchmark="待接入后 A/B 鉴别",
        source="待接入",
        method="新数据源 → 标准方法论 A/B → 增量>0 才入账",
        evidence="待鉴别：一致预期数据已被证实是数据层核心（+18.1pp），券商 MCP 需证明增量",
    )

    # ============================================================ L2 方法论层
    ledger.add_entry(
        layer="methodology",
        name="F-Score 预期差（Piotroski-So + 刘旭纪律）",
        status="VERIFIED",
        excess=0.081,
        total=0.126,
        mdd=-0.144,
        benchmark="EW-全A +52.9%（5年）",
        method="9因子 F-Score × BM 矩阵（Piotroski-So）＋ 刘旭持仓纪律",
        evidence="5年 +12.6% / MDD -14.4% / 超额 +8.1pp；低估值=熊市防御（方法论基线，本层 benchmark）",
        ref="_bt_fscore_nav.json / examples/backtest_f_score.py",
    )
    ledger.add_entry(
        layer="methodology",
        name="ZHF 否决制（consensus_veto 只否决不打分）",
        status="VERIFIED",
        excess=0.047,
        total=-0.026,
        mdd=-0.384,
        benchmark="ZHF 打分制（ZHF-cons）",
        method="预期数据只做否决闸门（con_np_yoy>0 | np_revision_4w>0 | PEG∈(0,2)），通过后走 ZHF 决策树",
        evidence="否决 -2.6% vs 打分 -7.3%，+4.7pp；印证「预期信息量在方向变动，非水平排序」",
        ref="_bt_zhf_veto_results.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="methodology",
        name="章宏帆框架（rotation_growth 有锐度的均衡）",
        status="CANDIDATE",
        total=3.291,
        mdd=-0.270,
        benchmark="龙头池等权 +455%",
        method="A/B/C 分类 + S1-S5 环节稀缺度 + 龙头直取 + G5 泡沫分解 + L5 仪表盘",
        evidence="ZHF-cons 5年 +329.1%/MDD -27.0%，但跑输池子 126pp → 框架价值=纪律(MDD砍半)非选股；纪律贡献待独立归因",
        ref="_bt_zhf_cons_nav.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="methodology",
        name="Growth Loop 剧本（GOAL→HOOK→LOOP 深研）",
        status="REJECTED",
        total=-0.140,
        mdd=-0.566,
        benchmark="EW-全A +52.9%",
        method="H1 营收加速/H2 毛利率拐点/H3 连续BEAT + L1-L7 LLM 深研",
        evidence="纯增速 5年 -14.0%/MDD -56.6%：Growth Trap（买入点=YoY峰值，追高接盘循环）",
        lesson="纯增速方法论在 A股 是陷阱；须叠加估值/预期维度",
        ref="_bt_gl_nav.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="methodology",
        name="ROA 加权（F-Score 变体）",
        status="REJECTED",
        excess=-0.037,
        benchmark="F-Score 基线",
        method="F1/F2 已含 ROA 信息，叠加 ROA 绝对值加权",
        evidence="-3.7pp：周期股盈利峰值偏误（钢铁/化工/煤炭超配→周期下行暴亏）",
        lesson="因子信息重叠时叠加绝对值=重复暴露周期风险",
        ref="_bt_fscore_roaw_nav.json",
    )
    ledger.add_entry(
        layer="methodology",
        name="IRR 门控 / BSADF 叠加 / 减速清仓（GL 系列变体）",
        status="REJECTED",
        benchmark="Growth Loop 基线",
        method="IRR 门槛、BSADF 相位叠加、营收减速清仓",
        evidence="均无效：在 Growth Trap 基线上加任何门控都无法扭转 -14%",
        lesson="方法论层先修根（买入点），门控只能修枝叶",
        ref="_bt_gl_irr_*.json / _bt_gl_valsell_*.json",
    )

    # ============================================================ L3 数量信号层
    ledger.add_entry(
        layer="quant_signal",
        name="估值卖出（PE 上限/高估降权）",
        status="VERIFIED",
        excess=0.11,
        benchmark="F-Score 基线（无卖出信号）",
        method="估值高位卖出信号（PE 上限/高估降权）",
        evidence="+11pp：A股卖出比买入重要——最有效的单一改进",
        ref="_bt_gl_valsell_val*.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="BSADF 泡沫检验（调仓月叠加）",
        status="VERIFIED",
        excess=0.009,
        mdd=-0.320,
        benchmark="Growth Loop 基线（无 BSADF）",
        method="Phillips-Shi-Yu 泡沫检验，仅在调仓月叠加减仓",
        evidence="略优于基线（泡沫破裂期正确减仓），但幅度有限",
        ref="_bt_pit_nav.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="BSADF 逐月出场",
        status="REJECTED",
        excess=-0.029,
        benchmark="Growth Loop 基线",
        method="BSADF 相位机逐月出场（CALM/IGNITION/RIDING/FADING/BURST/FEAR）",
        evidence="-2.9pp：主升段卖飞赢家；月频相位机无法区分抛物线回撤与真破裂",
        lesson="过热信号灵敏度要可控，超灵敏=卖飞",
        ref="_bt_pit_nav_nobsadf.json / docs/ALPHA_LAYERS.md",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="yoy_drop 下修清仓（每半年）",
        status="REJECTED",
        mdd=-0.663,
        benchmark="ZHF-veto 基线（无清仓纪律）",
        method="预期下修（con_np_yoy 走弱）触发清仓",
        evidence="MDD -66.3%：持续下修期每半年砍光全部持仓→满仓接刀→割肉换血循环",
        lesson="卖出纪律=收益换回撤，非免费午餐；超灵敏砍太狠",
        ref="_bt_zhf_veto_ZHF-veto-sell_nav.json",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="回撤止损 strict（dd50%/yoy50pp）",
        status="REJECTED",
        mdd=-0.730,
        benchmark="ZHF-veto 基线",
        method="严格回撤止损（713 笔）",
        evidence="MDD -73.0%：止损太晚，无甜蜜点",
        lesson="回撤止损阈值需在灵敏度与时机间找平衡，当前参数无甜区",
        ref="_bt_zhf_veto_ZHF-veto-sell-strict_nav.json",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="涨幅分解 G5（ΔPE 主导→信念×0.5）",
        status="VERIFIED",
        benchmark="rotation_growth 无 G5 版本",
        method="涨幅分解 ΔEPS vs ΔPE，ΔPE 主导时信念×0.5",
        evidence="框架内置过热降温，已随 rotation_growth 使用",
        ref="src/signals/rotation_growth.py",
    )
    ledger.add_entry(
        layer="quant_signal",
        name="过热监控清单（候选信号，待鉴别）",
        status="CANDIDATE",
        benchmark="无信号基线",
        method="1年涨幅热度罚 / 换手率过热 / 龙虎榜北向异动 / 一致预期上修终止 / 技术顶背离",
        evidence="A股卖出>买入：候选信号逐一 A/B 鉴别后入账",
    )

    # 落盘
    ledger.save()
    report = ledger.export_report()
    print("ledger:", ledger.path)
    print("report:", report)
    for k, v in ledger.summary().items():
        print(f"  {k:16s} {v['name']}: {v['n_entries']}条 (有效{v['n_verified']}/无效{v['n_rejected']}) 已归因超额 {v['sum_verified_excess']:+.1%}")


if __name__ == "__main__":
    main()
