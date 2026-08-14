"""Data client implementations.

The DataClient protocol (defined in src/core/interfaces.py) is the contract.
Any class implementing those methods works — no inheritance needed.

Built-in clients:
  - FinancialDatasetsClient: uses financialdatasets.ai API (like ai-hedge-fund)
  - MXDataClient: uses 东方财富 妙想(MX) MCP — A股/港股/美股/基金/债券/宏观.
                 Set EM_API_KEY. Low-level access via MXMCPClient.query().

TO ADD YOUR OWN DATA SOURCE:
  Copy _template_client.py and implement the methods.
  See src/data/_template_client.py for a blank template.
"""

from __future__ import annotations

from src.data.fin_datasets_client import FinancialDatasetsClient
from src.data.mx_mcp_client import MXMCPClient
from src.data.mx_data_client import MXDataClient
from src.data.cache import DiskCache

__all__ = [
    "FinancialDatasetsClient",
    "MXMCPClient",
    "MXDataClient",
    "DiskCache",
]
