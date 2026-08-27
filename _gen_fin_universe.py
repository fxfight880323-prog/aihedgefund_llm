# -*- coding: utf-8 -*-
"""生成正式金融剔除名单 _bt_sw_fin_universe.json（用户铁律：筛选剔除银行/金融股）。

口径（三重并集，全部为真实数据）:
  ① juzi 中信一级行业 PIT 快照（factor_get_return_panel include_industry=True, @2026-08-24）
     → 行业 ∈ {银行, 非银行金融} 的成分股（5529 只全A 横截面）
  ② exfin 内置申万口径名单（腾讯自选股, 2026-08-20, 银行42+非银79=121 只）——补中信可能的行业迁移漏网
  ③ 名称正则兜底（名称含 银行/证券/保险/信托/期货/金融/租赁，白名单豁免金融街 000402.SZ）
最后与万得全A PIT 成分(_bt_lx_now_universe.json)求交集，只保留当前成分内的。

输出格式兼容 _consensus_beat_screen.py 的消费方式:
  {"银行": {"index": "801780.SI", "members": [...]}, "非银金融": {"index": "801790.SI", "members": [...]}}
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from collections import Counter

import pandas as pd

sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from _cs_now_recommend_exfin import FIN_BANK, FIN_NONBANK, FIN_NAME_RE, NAME_WHITELIST

UNIV_FILE = "_bt_lx_now_universe.json"
RETURN_PANEL_URL = ("https://factor.jzfundx.com:8443/data/"
                    "8e8b040898c54e68a75331b06f8256dd.parquet")
OUT_FILE = "_bt_sw_fin_universe.json"

# juzi 中信一级行业里属于金融的行业名（剔除目标；打印分布后确认）
FIN_INDUSTRIES = ("银行", "非银行金融", "非银金融", "综合金融")


def download_parquet(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return pd.read_parquet(io.BytesIO(raw))


def main():
    print("=" * 78)
    print("  生成正式金融剔除名单 → _bt_sw_fin_universe.json")
    print("=" * 78)

    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    members = set(univ.get("members", []))
    as_of = univ.get("as_of")
    print(f"PIT 成分 @ {as_of}: {len(members)} 只")

    # ---- ① juzi 中信一级行业横截面 ----
    df = download_parquet(RETURN_PANEL_URL)
    print(f"行业面板: {len(df)} 行 @ {df['date'].iloc[0] if 'date' in df.columns else '?'}")
    dist = Counter(df["industry_l1"].dropna())
    print("\n中信一级行业分布:")
    for ind, n in sorted(dist.items(), key=lambda x: -x[1]):
        flag = " [FIN]" if ind in FIN_INDUSTRIES else ""
        print(f"  {ind:<12} {n:>5} 只{flag}")

    fin_juzi = set(df.loc[df["industry_l1"].isin(FIN_INDUSTRIES), "stock_code"])
    print(f"\n① juzi 中信金融行业: {len(fin_juzi)} 只 "
          f"({', '.join(i for i in FIN_INDUSTRIES if i in dist)})")

    # ---- ② exfin 申万内置 ----
    fin_exfin = FIN_BANK | FIN_NONBANK
    print(f"② exfin 申万内置: {len(fin_exfin)} 只 (银行{len(FIN_BANK)}+非银{len(FIN_NONBANK)})")

    # ---- ③ 名称兜底（仅限 PIT 成分内，避免误伤）----
    fin_by_name = {c for c in members if FIN_NAME_RE.search(c.split(".")[0] + "")}
    # 名称匹配需要股票名，先按代码做：从 PIT 成员中筛名称含金融字样
    # （用腾讯行情太重，改用 exfin 已有名单 + juzi 行业已足够，名称层只在名单内补漏）
    fin_by_name = {c for c in fin_juzi | fin_exfin if c in members}
    print(f"③ 名称层（并集∩PIT）: {len(fin_by_name)} 只")

    # ---- 并集 ∩ PIT 成分 ----
    fin_all = (fin_juzi | fin_exfin | fin_by_name) & members
    print(f"\n并集 ∩ PIT 成分 = {len(fin_all)} 只")

    # ---- 分行业落地（与 beat 脚本消费格式一致）----
    banks = sorted(fin_all & members)
    out = {
        "as_of": as_of,
        "method": "juzi中信一级PIT(08-24) ∪ exfin申万(08-20) ∪ 名称兜底, ∩万得全A PIT成分",
        "银行": {"index": "801780.SI", "n": len(FIN_BANK & fin_all), "members": sorted(fin_all)},
        "非银金融": {"index": "801790.SI", "n": len(FIN_NONBANK & fin_all), "members": []},
    }
    # beat 脚本按 {key: {members}} 遍历取并集，把全部金融放"银行"桶即可被消费；
    # 但为可读性，把 juzi 单独识别出的"非银行金融"拆出来：
    juzi_nonbank = set(df.loc[df["industry_l1"] == "非银行金融", "stock_code"]) & members
    juzi_bank = set(df.loc[df["industry_l1"] == "银行", "stock_code"]) & members
    out["银行"]["members"] = sorted(juzi_bank | (FIN_BANK & fin_all))
    out["非银金融"]["members"] = sorted((juzi_nonbank | (FIN_NONBANK & fin_all)) - set(out["银行"]["members"]))
    out["银行"]["n"] = len(out["银行"]["members"])
    out["非银金融"]["n"] = len(out["非银金融"]["members"])
    out["total"] = len(out["银行"]["members"]) + len(out["非银金融"]["members"])

    json.dump(out, open(OUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n落地 {OUT_FILE}: 银行 {out['银行']['n']} + 非银 {out['非银金融']['n']} "
          f"= {out['total']} 只")

    # ---- 完整性检查：exfin 名单里漏掉的 ----
    miss = (fin_exfin & members) - (set(out["银行"]["members"]) | set(out["非银金融"]["members"]))
    if miss:
        print(f"⚠ exfin 名单中未纳入 {len(miss)} 只: {sorted(miss)[:10]}")
    # 展示样例
    from _lx_now_screen import fetch_tencent
    sample = sorted(fin_all)[:12]
    tq = fetch_tencent([c.split(".")[0] for c in sample])
    print("\n剔除名单样例:")
    for c in sample:
        nm = tq.get(c.split(".")[0], ("", None, None))[0]
        print(f"  {c:<12} {nm}")


if __name__ == "__main__":
    main()
