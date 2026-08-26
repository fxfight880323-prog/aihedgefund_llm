"""刘旭式框架当前时点筛选 — 数据拉取（2026-08 最新一期）。

拉取:
  A. 万得全A(881001.WI) PIT 成分 @ 最新交易日
  B. 估值面板   pe_ttm / pb / total_mv(万元) / float_mv
  C. HF 因子    gpm / cetop / npyoy / roeyoy / roes / dtop5 / oryoy / lncap
  D. 一致预期   全市场 con_roe / con_np_yoy / con_peg / con_pe

陷阱处理: 先 inline test 确认 as_of 是交易日(count>0)，非交易日自动回退到前一交易日。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

UNIV_FILE = "_bt_lx_now_universe.json"
VAL_FILE = "_bt_lx_now_valuation.json"
FAC_FILE = "_bt_lx_now_factors.json"
CONS_FILE = "_bt_lx_now_consensus.json"

FACTORS = ["gpm", "cetop", "npyoy", "roeyoy", "roes", "dtop5", "oryoy", "lncap"]

# 候选 as_of（最新交易日优先，逐个测试）
CANDIDATE_DATES = ["2026-08-25", "2026-08-24", "2026-08-21", "2026-08-20"]


def load_cache(path):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}


def download_json(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    import pandas as pd
    return pd.read_parquet(io.BytesIO(raw)).to_dict(orient="records")


def save(cache, path, n):
    json.dump(cache, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  → {n} 条 → {path} ({os.path.getsize(path)/1e6:.1f}MB)")


def main():
    cli = JuziHTTP(*load_creds())
    print("connected to juzi-mcp")

    # ---- 0. 找到最新交易日 ----
    as_of = None
    for d in CANDIDATE_DATES:
        try:
            out = cli.call_tool("factor_get_valuation_panel", {
                "stock_codes": ["000001.SZ", "600519.SH"],
                "start_date": d, "end_date": d, "format": "inline"})
            n = len(out.get("records", []))
            print(f"test {d}: {n} 条")
            if n > 0:
                as_of = d
                break
        except Exception as e:
            print(f"test {d} 失败: {str(e)[:100]}")
        time.sleep(2)
    if not as_of:
        print("!! 所有候选日期均非交易日，中止")
        sys.exit(1)
    print(f"\n>>> 最新交易日 = {as_of}")

    # ---- A. 万得全A PIT 成分 ----
    univ = load_cache(UNIV_FILE)
    if univ.get("as_of") == as_of and univ.get("members"):
        members = univ["members"]
        print(f"universe 已缓存: {len(members)} 只")
    else:
        members = None
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_universe_members", {
                    "index_code": "881001.WI", "as_of_date": as_of,
                    "format": "inline"})
                members = [r.get("stock_code", "") if isinstance(r, dict)
                           else str(r) for r in out.get("members", [])]
                members = [m for m in members if m]
                if members:
                    break
                print(f"  尝试 {attempt+1}: 空, 重试")
                time.sleep(5)
            except Exception as e:
                print(f"  尝试 {attempt+1} 失败: {str(e)[:120]}")
                time.sleep(8)
        if not members:
            print("!! universe 拉取失败")
            sys.exit(1)
        json.dump({"as_of": as_of, "members": members},
                  open(UNIV_FILE, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"universe → {len(members)} 只 @ {as_of}")

    # ---- B. 估值面板 ----
    val = load_cache(VAL_FILE)
    if val.get("as_of") == as_of and val.get("records"):
        print(f"valuation 已缓存: {len(val['records'])} 条")
    else:
        ok = False
        for attempt in range(4):
            try:
                out = cli.call_tool("factor_get_valuation_panel", {
                    "stock_codes": members, "start_date": as_of,
                    "end_date": as_of, "format": "parquet"})
                url = ((out.get("artifact") or {}).get("download_url"))
                if url:
                    recs = download_json(url)
                    if recs:
                        val = {"as_of": as_of, "records": recs}
                        save(val, VAL_FILE, len(recs))
                        ok = True
                        break
                print(f"  尝试 {attempt+1}: 无 url, 重试")
                time.sleep(6)
            except Exception as e:
                print(f"  尝试 {attempt+1} 失败: {str(e)[:120]}")
                time.sleep(8)
        if not ok:
            print("!! valuation 拉取失败")
            sys.exit(1)

    # ---- C. HF 因子横截面（逐因子全市场, 健康日探测）----
    # 2026-08-20 起 juzi 服务端 HF 因子被污染(全因子返回同一值, 如茅台 gpm=4.25)。
    # 健康判定: 用 cross_section 拉市场 top5 gpm, 正常市场头部毛利率应 > 50;
    #           污染日 top5 值会 < 20 (如 4.x)。count>0 不可靠, 必须做值域校验。
    fac_asof = None
    for d in CANDIDATE_DATES:
        try:
            out = cli.call_tool("factor_get_hf_factor_cross_section", {
                "factor_code": "gpm", "trade_dt": d,
                "format": "inline", "limit": 5})
            vals = [r.get("value") for r in out.get("cross_section", [])
                    if isinstance(r, dict) and r.get("value") is not None]
            if vals and max(vals) > 50:
                fac_asof = d
                print(f"  gpm top5 @ {d}: {[round(v,1) for v in vals]} → 健康")
                break
            else:
                print(f"  gpm @ {d}: {vals} → 污染/异常, 跳过")
        except Exception as e:
            print(f"  test {d} 失败: {str(e)[:100]}")
        time.sleep(2)
    if not fac_asof:
        print("!! 无健康因子日期（服务端因子数据可能持续污染）")
        sys.exit(1)
    print(f">>> 健康因子日 = {fac_asof}")

    fac = load_cache(FAC_FILE)
    if fac.get("as_of") == fac_asof and fac.get("records"):
        print(f"factors 已缓存: {len(fac['records'])} 条 @ {fac_asof}")
    else:
        # 逐因子 parquet 全市场, merge 成宽表
        import pandas as pd
        frames = {}
        for i, fc in enumerate(FACTORS):
            got = False
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_hf_factor_cross_section", {
                        "factor_code": fc, "trade_dt": fac_asof,
                        "format": "parquet", "limit": 50000})
                    # cross_section parquet 的 download_url 在顶层（非 artifact 包装）
                    url = (out.get("download_url")
                           or ((out.get("artifact") or {}).get("download_url")))
                    if not url:
                        print(f"  [{fc}] 无 url, 重试 {attempt+1}")
                        time.sleep(5)
                        continue
                    raw = urllib.request.urlopen(
                        urllib.request.Request(
                            url, headers={"User-Agent": "Mozilla/5.0"}),
                        timeout=300).read()
                    df = pd.read_parquet(io.BytesIO(raw))
                    df.columns = [c.strip().lower() for c in df.columns]
                    if "sec_id" in df.columns:
                        df = df.rename(columns={"sec_id": "stock_code"})
                    val_col = "value" if "value" in df.columns else fc
                    frames[fc] = df[["stock_code", val_col]].rename(
                        columns={val_col: fc})
                    print(f"  [{i+1}/{len(FACTORS)}] {fc}: {len(df)} 行")
                    got = True
                    break
                except Exception as e:
                    print(f"  [{fc}] 尝试 {attempt+1} 失败: {str(e)[:120]}")
                    time.sleep(8)
            if not got:
                print(f"!! [{fc}] 拉取失败")
                sys.exit(1)
            time.sleep(2)
        base = frames[FACTORS[0]][["stock_code"]]
        for fc in FACTORS[1:]:
            base = base.merge(frames[fc], on="stock_code", how="outer")
        recs = base.where(base.notna(), None).to_dict(orient="records")
        fac = {"as_of": fac_asof, "records": recs}
        save(fac, FAC_FILE, len(recs))

    # ---- D. 一致预期（全市场，先试 val 日期再试因子日期）----
    cons = load_cache(CONS_FILE)
    if cons.get("as_of") == as_of and cons.get("records"):
        print(f"consensus 已缓存: {len(cons['records'])} 条")
    else:
        ok = False
        for d in [as_of, fac_asof]:
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_consensus_forecast", {
                        "universe": "881001.WI", "as_of_date": d,
                        "format": "parquet"})
                    url = ((out.get("artifact") or {}).get("download_url"))
                    if url:
                        recs = download_json(url)
                        if recs:
                            cons = {"as_of": d, "records": recs}
                            save(cons, CONS_FILE, len(recs))
                            print(f"  consensus @ {d}")
                            ok = True
                            break
                    print(f"  尝试 {attempt+1} ({d}): 无 url, 重试")
                    time.sleep(5)
                except Exception as e:
                    print(f"  尝试 {attempt+1} ({d}) 失败: {str(e)[:120]}")
                    time.sleep(6)
            if ok:
                break
        if not ok:
            print("!! consensus 拉取失败")
            sys.exit(1)

    print(f"\n完成: val_asof={as_of} | fac_asof={fac_asof} | "
          f"cons_asof={cons['as_of']} | univ={len(members)} | "
          f"val={len(val['records'])} | fac={len(fac['records'])} | "
          f"cons={len(cons['records'])}")


if __name__ == "__main__":
    main()
