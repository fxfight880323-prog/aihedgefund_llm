# -*- coding: utf-8 -*-
"""汇总 dist52 + 6 策略对比 涉及的所有股票，去重输出 _band_need.json（供估值 band 拉取）"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

def load(name):
    p = BASE + name
    if not os.path.exists(p):
        return None
    return json.loads(open(p, encoding="utf-8").read())

need = {}  # code_with_suffix -> name

def add_rows(rows, code_key, name_key="name"):
    for r in rows or []:
        c = (r.get(code_key) or "").strip()
        if c and "." not in c:  # 补后缀（仅内部统一）
            if c.startswith(("6", "9")):
                c += ".SH"
            elif c.startswith(("8", "4")):
                c += ".BJ"
            else:
                c += ".SZ"
        if c:
            need.setdefault(c, r.get(name_key) or c)

# dist52 全量 77 只
d52 = load("_lx_now_dist52.json")
if d52:
    add_rows(d52["rows"], "code")

# 6 策略对比源
lx = load("_lx_now_results.json")
lx_scored = load("_lx_now_scored.json")
cs = load("_cs_now_results.json")
chip = load("_ai_chip_52wk_top.json") or []
beat = load("_bt_consensus_beat_results.json")

if lx:
    add_rows(lx["core"], "code")
if lx_scored:
    add_rows(lx_scored.get("top40", [])[:20], "code")
if cs:
    add_rows(cs["recommend"], "code")
add_rows(chip, "ts")
if beat:
    add_rows(beat["top"], "code")

out = {"codes": sorted(need.keys()), "n": len(need), "names": need}
json.dump(out, open(BASE + "_band_need.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"去重后需拉估值股票: {len(need)} 只")
print(" ".join(sorted(need.keys())[:20]) + " ...")
