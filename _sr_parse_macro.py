import json, csv, os

SRC = r"C:/Users/xfugm/.workbuddy/projects/c-Users-xfugm-.workbuddy-workspace-files-3860-cc679a20-34eb-45ec-bd4b-f6a4e6d8a52f/cc679a20-34eb-45ec-bd4b-f6a4e6d8a52f/tool-results/mcp-connector-proxy-wind-finance_natural_language_get_edb_data-1787728997357-a46636.txt"
OUT = r"D:/workspace/ai_fund_framework/_sr_cache"
os.makedirs(OUT, exist_ok=True)

name_map = {
    "M0041653": "r007",
    "M5525763": "tsf_yoy",   # 社融存量同比
    "M0017126": "pmi",
    "M0001383": "m1_yoy",
    "M0001385": "m2_yoy",
}

with open(SRC, "r", encoding="utf-8") as f:
    payload = json.load(f)

for item in payload["data"]["data"]:
    code = item["meta"]["code"]
    dates = item.get("date", [])
    vals = item.get("value", item.get("values", []))
    slug = name_map.get(code, code)
    if len(dates) != len(vals):
        print(f"[WARN] {code} {slug}: len mismatch {len(dates)} vs {len(vals)}")
    n = min(len(dates), len(vals))
    path = os.path.join(OUT, f"macro_{slug}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for i in range(n):
            w.writerow([dates[i], vals[i]])
    print(f"{slug} ({code}) {item['meta']['name']} freq={item['meta']['freq']}: {n} rows, {dates[0]} -> {dates[-1]}")
