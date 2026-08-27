"""修复 factors.json 全列同值 bug — 从健康日 2026-08-19 逐因子拉全市场横截面重建。

背景: juzi 服务端 HF 因子数据自 2026-08-20 起被污染(所有因子返回同一值,
      茅台 gpm=4.25 明显荒谬)。series 接口确认 08-17~08-19 正常
      (茅台 gpm=91.18, 与本地 SQLite factor_panel 交叉验证一致)。
方案: factor_get_hf_factor_cross_section @ 2026-08-19, 8 因子逐个 parquet 全市场,
      按 sec_id merge 成宽表, 覆盖 _bt_lx_now_factors.json。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

FACTORS = ["gpm", "cetop", "npyoy", "roeyoy", "roes", "dtop5", "oryoy", "lncap"]
TRADE_DT = "2026-08-19"   # 最后健康因子日（08-20 起 juzi 服务端污染）
OUT_FILE = "_bt_lx_now_factors.json"


def download_parquet(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    import pandas as pd
    return pd.read_parquet(io.BytesIO(raw))


def main():
    cli = JuziHTTP(*load_creds())
    print(f"connected to juzi-mcp | trade_dt={TRADE_DT} | factors={len(FACTORS)}")

    frames = {}
    for i, fc in enumerate(FACTORS):
        out = None
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_hf_factor_cross_section", {
                    "factor_code": fc, "trade_dt": TRADE_DT,
                    "format": "parquet", "limit": 50000})
                # cross_section parquet 的 download_url 在顶层（不是 artifact 包装）
                url = (out.get("download_url")
                       or ((out.get("artifact") or {}).get("download_url")))
                if not url:
                    print(f"  [{fc}] 无 download_url, 重试 {attempt+1}")
                    time.sleep(5)
                    continue
                df = download_parquet(url)
                df.columns = [c.strip().lower() for c in df.columns]
                # 统一股票代码列名（cross_section 返回 sec_id；load_map 消费 stock_code）
                if "sec_id" in df.columns:
                    df = df.rename(columns={"sec_id": "stock_code"})
                elif "stock_code" not in df.columns:
                    print(f"  [{fc}] 列缺失: {list(df.columns)}, 重试 {attempt+1}")
                    time.sleep(5)
                    continue
                val_col = "value" if "value" in df.columns else fc
                df = df[["stock_code", val_col]].rename(columns={val_col: fc})
                frames[fc] = df
                print(f"  [{i+1}/8] {fc}: {len(df)} 行 | 值域 "
                      f"[{df[fc].min():.3f}, {df[fc].max():.3f}] | "
                      f"非空 {df[fc].notna().sum()}")
                break
            except Exception as e:
                print(f"  [{fc}] 尝试 {attempt+1} 失败: {str(e)[:150]}")
                time.sleep(8)
        if fc not in frames:
            print(f"!! [{fc}] 拉取失败, 中止")
            sys.exit(1)
        time.sleep(2)

    # ---- merge 成宽表 ----
    base = frames["gpm"][["stock_code"]]
    for fc in FACTORS:
        base = base.merge(frames[fc], on="stock_code", how="outer")
    records = base.where(base.notna(), None).to_dict(orient="records")

    # ---- 抽样 sanity check ----
    by_code = {r["stock_code"]: r for r in records}
    for probe in ["600519.SH", "000651.SZ", "000858.SZ", "601398.SH"]:
        if probe in by_code:
            r = by_code[probe]
            print(f"\n抽查 {probe}: gpm={r.get('gpm')} cetop={r.get('cetop')} "
                  f"dtop5={r.get('dtop5')} roes={r.get('roes')} "
                  f"npyoy={r.get('npyoy')} lncap={r.get('lncap')}")

    # ---- 保存 ----
    payload = {
        "as_of": TRADE_DT,
        "source": "juzi factor_get_hf_factor_cross_section (逐因子全市场)",
        "note": "juzi 服务端 HF 因子自 2026-08-20 起污染(全因子同值), "
                "本文件回退至最后健康交易日 2026-08-19; "
                "与本地 SQLite factor_panel 08-19 值交叉验证一致",
        "records": records,
    }
    json.dump(payload, open(OUT_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = len(records)
    print(f"\n✅ 保存 {n} 条 → {OUT_FILE} "
          f"({os.path.getsize(OUT_FILE)/1e6:.1f}MB)")

    # ---- 非空率总表 ----
    print("\n因子非空率:")
    for fc in FACTORS:
        cnt = sum(1 for r in records if r.get(fc) is not None)
        print(f"  {fc}: {cnt}/{n} ({cnt/n*100:.1f}%)")


if __name__ == "__main__":
    main()
