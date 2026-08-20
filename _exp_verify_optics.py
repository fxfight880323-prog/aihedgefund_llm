# -*- coding: utf-8 -*-
"""反事实验证：光模块标的在关键调仓期的 HOOK 触发状态。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.strategy import avail_financials
from src.signals.hooks import evaluate_hooks
import _gl_backtest_variant as gl

fin = {}
if os.path.exists("_bt_exp_financials.json"):
    fin = json.loads(open("_bt_exp_financials.json", encoding="utf-8").read())
if not fin:
    fin = json.loads(open("_bt_pit_financials.json", encoding="utf-8").read())

names = {"300308.SZ": "中际旭创", "300502.SZ": "新易盛",
         "300394.SZ": "天孚通信", "688313.SH": "仕佳光子",
         "688668.SH": "鼎通科技"}

for as_of_label, month in [("2024-08-31", "2024-08"),
                           ("2025-04-30", "2025-04"),
                           ("2025-08-31", "2025-08")]:
    fin_at = avail_financials(fin, as_of_label)
    gl.CUR_DT[0] = month
    print(f"===== {month} (as_of {as_of_label}) =====")
    for tk, nm in names.items():
        if tk not in fin_at:
            print(f"  {nm:6s} 无财务数据")
            continue
        yoy, gm = gl.series_of(fin_at[tk])
        if not yoy:
            print(f"  {nm:6s} 无营收YoY")
            continue
        res = evaluate_hooks(yoy, gm, None, beats=None)
        hooks = [h["id"] for h in res["tripped"]]
        gm_s = "/".join(f"{g:.1f}" for g in gm[:4])
        print(f"  {nm:6s} yoy={yoy[0]*100:.0f}% "
              f"(共{len(yoy)}期) gm={gm_s} hooks={hooks or '无'}")
