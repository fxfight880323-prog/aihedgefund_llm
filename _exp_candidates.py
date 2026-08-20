# -*- coding: utf-8 -*-
"""行业聚合层实验 · 阶段2：从 _bt_top100.json 构建三种候选。

mode:
  baseline  复刻原逻辑（top5 行业 + 每行业 8 只）→ 与 _bt_pit_selection.json
            对比校验数据源可复现性（对比公平的前提）
  plan2     给 s1 加"龙头质量分"：池内存在 growth≥0.5 且 roe≥15 的成员
            → s1 +1（s1 上限 3）。这是"行业窄但出现 H1/H2 双钩龙头
            加分"的确定性近似（打分阶段只有 growth/roe 两字段，真实
            H1/H2 需毛利率与历史增速，属后续拉财务才能判，此处诚实标注）
  plan1     top-100 直通 HOOK：去掉行业聚合层，候选 = top-100 中
            growth≥30% 且 上年同期营收≥1亿 的全部成员（无行业限制、
            无每行业 8 只上限）

输出：_bt_sel_{mode}.json（格式与 _bt_pit_selection.json 兼容：
      as_of / candidates=[(tk,name,sw1)] / link_map / top_industries）
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOP100_FILE = "_bt_top100.json"
BASELINE_FILE = "_bt_pit_selection.json"


def build_selection(top100: dict, mode: str) -> dict:
    sel: dict[str, dict] = {}
    for month, v in top100.items():
        rows = v["rows"]
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(r["sw1"], []).append(r)
        link_map = {}
        for ind, members in groups.items():
            growths = sorted(m["growth"] for m in members)
            med_g = growths[len(growths) // 2]
            roe8 = sum(1 for m in members if m["roe"] >= 8) / len(members)
            s1 = min(2, len(members) // 4)
            if mode == "plan2":
                # 龙头质量分：准双钩龙头(growth≥0.5 且 roe≥15) +1，
                # 极强龙头(growth≥1.0 且 roe≥15) 再 +1 → s1 上限 4
                leaders = [m for m in members
                           if m["growth"] >= 0.5 and m["roe"] >= 15]
                bonus = 0
                if leaders:
                    bonus = 1 + (1 if any(m["growth"] >= 1.0
                                          for m in leaders) else 0)
                s1 = min(4, s1 + bonus)
            s2 = min(2, max(0, int(med_g / 0.30)))
            s3 = min(2, round(2 * roe8))
            link_map[ind] = {"s_scores": [s1, s2, s3, 0, 0],
                             "keywords": [], "n_members": len(members),
                             "med_growth": med_g}
        ranked = sorted(link_map.items(),
                        key=lambda kv: -sum(kv[1]["s_scores"]))
        top_inds = {n for n, c in ranked[:5] if sum(c["s_scores"]) >= 3}

        cand = []
        for r in rows:
            if mode != "plan1" and r["sw1"] not in top_inds:
                continue
            if r["growth"] < 0.30:
                continue
            if not r["prior_rev_yi"] or r["prior_rev_yi"] < 1:
                continue
            cand.append(r)
        cand.sort(key=lambda r: -(r["growth"] * min(r["roe"], 25)))
        per_ind: dict[str, int] = {}
        capped = []
        for r in cand:
            if mode != "plan1" and per_ind.get(r["sw1"], 0) >= 8:
                continue
            per_ind[r["sw1"]] = per_ind.get(r["sw1"], 0) + 1
            capped.append(r)

        sel[month] = {
            "as_of": v["as_of"], "n_rows": len(rows),
            "n_industries": len(groups),
            "top_industries": [(n, sum(c["s_scores"]))
                               for n, c in ranked[:6]],
            "link_map": link_map,
            "candidates": [(r["tk"], r["name"], r["sw1"])
                           for r in capped],
        }
    return sel


def main():
    top100 = json.loads(open(TOP100_FILE, encoding="utf-8").read())
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    sel = build_selection(top100, mode)
    out = f"_bt_sel_{mode}.json"
    json.dump(sel, open(out, "w", encoding="utf-8"), ensure_ascii=False)

    # 逐期打印
    for month in sorted(sel.keys()):
        s = sel[month]
        print(f"  [{month}] rows={s['n_rows']} cand={len(s['candidates'])}"
              f" | top: "
              + " ".join(f"{n}({sc})" for n, sc in s["top_industries"][:5]))

    # baseline 校验：与既有 selection 对比
    if mode == "baseline" and os.path.exists(BASELINE_FILE):
        old = json.loads(open(BASELINE_FILE, encoding="utf-8").read())
        diffs = []
        for month in sorted(sel.keys()):
            new_c = {c[0] for c in sel[month]["candidates"]}
            old_c = {c[0] for c in old[month]["candidates"]}
            only_new = new_c - old_c
            only_old = old_c - new_c
            if only_new or only_old:
                diffs.append((month, len(only_new), len(only_old),
                              sorted(only_new)[:5], sorted(only_old)[:5]))
        if not diffs:
            print("\n✅ baseline 与 _bt_pit_selection.json 完全一致 → "
                  "数据源可复现，三方案对比公平")
        else:
            print("\n⚠️ baseline 与既有 selection 不一致：")
            for month, n1, n2, new5, old5 in diffs:
                print(f"  [{month}] 新增 {n1} / 缺失 {n2} | "
                      f"新增样本 {new5} | 缺失样本 {old5}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
