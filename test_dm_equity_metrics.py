"""Probe DM Quant API for A-share fundamental metrics (PB, ROE, etc.).

The SDK manual only documents equity K-line (/equity/market-data/bars).
This script checks whether additional endpoints for valuation/fundamentals
exist and are reachable, with delays to avoid rate-limiting.
"""

from __future__ import annotations

import json
import time
import traceback

import requests
from dm_quant_api_client import DMQuantApiClient

session = requests.Session()
session.trust_env = False

client = DMQuantApiClient(
    app_key="AKIDmrdaunpaaEna9CJe8lkRDHJ2",
    app_secret="f9PTGVcL2UEtM6m0",
    pythonic=True,
    session=session,
)

SAMPLE_STOCK = "000001.SZ"  # 平安银行
TRADE_DATE = "2026-05-18"


def probe(label: str, api_path: str, payload: dict):
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"POST {api_path}")
    print(f"payload = {json.dumps(payload, ensure_ascii=False)}")
    try:
        df = client.post_data(data=payload, api_path=api_path)
        print("OK - shape:", df.shape)
        print("Columns:", df.columns.tolist())
        if not df.empty:
            print("First row:")
            print(df.iloc[0].to_json(indent=2, force_ascii=False))
        return True, df
    except Exception as exc:
        print("FAILED:", exc)
        return False, None
    finally:
        time.sleep(2)


# 1. Confirm equity K-line works.
probe(
    "Equity K-line (known endpoint)",
    "/dm-quant-func-service/api/v1/equity/market-data/bars",
    {
        "security_id_list": [SAMPLE_STOCK],
        "security_category": "1",
        "kline_type": 6,
        "start_datetime": TRADE_DATE,
        "end_datetime": TRADE_DATE,
    },
)

# 2. Company basic info with correct identifiers.
probe(
    "Company basic info (correct params)",
    "/dm-quant-func-service/api/v1/company/basic-info/info",
    {
        "com_full_name_list": "",
        "society_code_list": "91440300192185379H",
    },
)

# 3. Try the most plausible equity valuation/fundamental endpoint slowly.
probe(
    "Equity valuation/date",
    "/dm-quant-func-service/api/v1/equity/valuation/date",
    {
        "security_id_list": [SAMPLE_STOCK],
        "start_date": TRADE_DATE,
        "end_date": TRADE_DATE,
    },
)

probe(
    "Equity indicator/date",
    "/dm-quant-func-service/api/v1/equity/indicator/date",
    {
        "security_id_list": [SAMPLE_STOCK],
        "start_date": TRADE_DATE,
        "end_date": TRADE_DATE,
    },
)

# 4. Sanity-check: clearly fake endpoint to compare error format.
probe(
    "Fake endpoint sanity check",
    "/dm-quant-func-service/api/v1/equity/fake-not-exist/date",
    {
        "security_id_list": [SAMPLE_STOCK],
        "start_date": TRADE_DATE,
        "end_date": TRADE_DATE,
    },
)

print("\n" + "=" * 60)
print("Probe complete.")
