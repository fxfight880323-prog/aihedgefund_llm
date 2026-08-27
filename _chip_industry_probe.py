# -*- coding: utf-8 -*-
"""探测申万金工 MCP 服务器：screener 输出截断行为 + 全量行业标签获取."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples"))
from fetch_consensus import JuziHTTP, load_creds  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_chip_industry_probe.json")
results = {}

url, token = load_creds()
# mcp.json 里 juzi-mcp 条目现指向申万金工服务器；/mcp 会 307 到 /mcp/
if not url.rstrip("/").endswith("/mcp"):
    url = url.rstrip("/") + "/mcp"
url = url.rstrip("/") + "/"
cli = JuziHTTP(url, token)
print("connected:", url)

# 1) tools/list 看 screener / decomposition 是否有隐藏参数
resp = cli._post({
    "jsonrpc": "2.0", "id": 900, "method": "tools/list", "params": {},
})
tools = resp.get("result", {}).get("tools", [])
for t in tools:
    if t["name"] in ("run_strategy_screener", "get_factor_industry_decomposition",
                     "run_composite_screener"):
        results[f"schema::{t['name']}"] = t.get("inputSchema", {})
        print("schema:", t["name"], json.dumps(t.get("inputSchema", {}), ensure_ascii=False))

# 2) keep_pct=0.2 直连调用，看原始 picks 数量
r = cli.call_tool("run_strategy_screener", {
    "steps": [{"factor": "筹码合成", "keep_pct": 0.2}],
    "universe": "all_a", "as_of_date": "latest", "name": "chip_full_test",
})
n_picks = len(r.get("picks", []))
meta = r.get("metadata", {})
print(f"keep_pct=0.2 raw picks = {n_picks}, meta = {json.dumps(meta, ensure_ascii=False)}")
results["screener_q5"] = {"n_picks_raw": n_picks, "meta": meta}
if n_picks > 100:
    json.dump(r, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("saved full picks ->", OUT)

# 3) 全市场 pass-through（总市值>=0 应保留全部），拿每只股票的行业标签
r2 = cli.call_tool("run_strategy_screener", {
    "steps": [{"metric": "总市值", "op": ">=", "value": 0}],
    "universe": "all_a", "as_of_date": "latest", "name": "all_pass",
})
n2 = len(r2.get("picks", []))
meta2 = r2.get("metadata", {})
print(f"pass-all raw picks = {n2}, meta = {json.dumps(meta2, ensure_ascii=False)}")
results["pass_all"] = {"n_picks_raw": n2, "meta": meta2}
if n2 > 100:
    json.dump(r2, open(OUT.replace("probe", "allpass"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("saved all-pass ->", OUT.replace("probe", "allpass"))

json.dump(results, open(OUT + ".summary.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")
