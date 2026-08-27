# -*- coding: utf-8 -*-
"""拉取 AI 产业链池的『机构筹码集中度』因子 (2026-07-31, z-score)。

池子: _ai_52wk_rank.json 的 sym (剔除北交所 bj)
输出: _ai_chip_conc.json {ts_code: value}
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples"))
from fetch_consensus import JuziHTTP, load_creds  # noqa: E402

DATE = "2026-07-31"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ai_chip_conc.json")


def to_ts(sym: str) -> str:
    mkt, code = sym[:2], sym[2:]
    return code + (".SH" if mkt == "sh" else ".SZ")


def main():
    rank = json.load(open(os.path.join(os.path.dirname(OUT), "_ai_52wk_rank.json"), encoding="utf-8"))
    syms = sorted(r["sym"] for r in rank if r["sym"][:2] != "bj")
    ts_codes = [to_ts(s) for s in syms]
    print(f"AI池(非北交所): {len(ts_codes)} 只")

    url, token = load_creds()
    url2 = url.rstrip("/") + "/" if url.rstrip("/").endswith("/mcp") else url
    cli = JuziHTTP(url2, token)

    out: dict[str, float] = {}
    if os.path.exists(OUT):
        out = json.load(open(OUT, encoding="utf-8"))
        print(f"已有缓存 {len(out)} 只")
        todo = [t for t in ts_codes if t not in out]
    else:
        todo = ts_codes

    B = 100
    t0 = time.time()
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        got = 0
        for attempt in range(3):
            try:
                r = cli.call_tool("get_factor_value", {
                    "factors": ["机构筹码集中度"], "ts_codes": batch, "date": DATE})
                recs = r.get("records") or []
                for rec in recs:
                    v = rec.get("机构筹码集中度")
                    if v is not None:
                        out[rec["ts_code"]] = v
                        got += 1
                break
            except Exception as e:
                print(f"  batch {i//B} attempt{attempt+1}: {str(e)[:80]}")
                time.sleep(3)
        if (i // B) % 5 == 0:
            print(f"  batch {i//B+1}/{(len(todo)+B-1)//B}: +{got} total {len(out)} 耗时{time.time()-t0:.0f}s", flush=True)
        time.sleep(0.4)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"完成: {len(out)}/{len(ts_codes)} -> {OUT}, 耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
