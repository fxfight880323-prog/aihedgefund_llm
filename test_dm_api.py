import requests
from dm_quant_api_client import DMQuantApiClient

session = requests.Session()
session.trust_env = False  # 禁用系统代理，避免读到 127.0.0.1:7890

client = DMQuantApiClient(
    app_key="AKIDmrdaunpaaEna9CJe8lkRDHJ2",
    app_secret="f9PTGVcL2UEtM6m0",
    pythonic=True,
    session=session,
)

df = client.post_data(
    data={
        "security_id_list": ["2500002.IB"],
        "data_source_list": [2],
        "start_date": "2026-04-24",
        "end_date": "2026-04-24",
    },
    api_path="/dm-quant-func-service/api/v1/bond/market-data/date",
)

print("Columns:", df.columns.tolist())
print("Shape:", df.shape)

# 将首行写入 UTF-8 JSON，避免终端编码导致中文乱码
import json
first_row = df.iloc[0].to_dict()
with open("dm_first_row.json", "w", encoding="utf-8") as f:
    json.dump(first_row, f, ensure_ascii=False, indent=2)
print("\nFirst row written to dm_first_row.json")
