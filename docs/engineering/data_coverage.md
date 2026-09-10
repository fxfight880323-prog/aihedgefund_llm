# Engineering · 数据覆盖与口径

## 实时数据源 vs 回测数据源

| 用途 | 数据源 | 频率 | 覆盖 |
|---|---|---|---|
| 实盘 K 线（模拟组合） | 腾讯 `qt.gtimg.cn` | 日频 | 全 A 5500+ |
| 实盘 K 线（拉数据用） | `web.ifzq.gtimg.cn` | 日频 | 全 A 5500+ |
| 回测 PIT 成分 | juzi-mcp `factor_get_universe_members` | 月频 | 万得全A 881001.WI |
| 回测估值 | juzi-mcp `factor_get_valuation_panel` | 月频 | 万得全A 8821 只 |
| 回测因子 | juzi-mcp `factor_get_factor_panel` | 月频 | 万得全A 8821 只 |
| 回测 HF 因子 | juzi-mcp `factor_get_hf_factor_series` | 日频 | 核心 530 只（**不全 A**）|
| 回测日 K | `_bt_daily_px_full.json` 快照 | 日频 | 核心 530 只（**不全 A**）|
| 实盘推荐名单 | juzi-mcp（最新拉取） | 月频 | 核心 70-220 只 |
| 申万因子 IC | 申万金工 MCP | 月频 | 48 工具，新地址 `http://159.138.132.129/mcp/` |

## 关键覆盖限制

| 限制 | 影响 | 兜底 |
|---|---|---|
| `_bt_daily_px_full.json` 只覆盖 **530 只核心票** | 用 daily K 算 mom60 只能覆盖 ~9% 票 | 改用 `monthly_close` 算月 K 动量（覆盖全 PIT 池）|
| `factor_panel.roes` 2026-08 月入库异常（仅 8 条）| q_score = (gpm+con_roe+cetop)/3 的 ROE 用 `consensus.con_roe` 代替 | 已修（见 MEMORY.md q20 口径铁律）|
| **q20 候选有 202 只无日频 PB 历史** | band 规避层数据缺失 | 当前按"不规避"保守处理（占最终持仓 ~5%）；要 100% 覆盖需 juzi 补拉这 202 只 |
| **parquet 只覆盖 LX-core 898 只** | band 快照 (898×10) ≠ 实盘 Q20 候选（~250）| 同上，缺失票按"不规避" |

## juzi-mcp 已知坑

- 参数名 `as_of_date` 不能写成 `as_of`（同名错误）
- 周末返回空 → 回退到最近前一交易日
- `pe_ttm` 含 NaN → 用 `pe != pe` 过滤
- HF 因子滞后 1 交易日；非交易日 as_of 面板 count=0
- 2026-08-20 起 HF 因子落库异常，需探测健康日（见 `pipeline/dates.freshness_status()`）

## 申万金工 MCP 坑

- **新地址**：`http://159.138.132.129/mcp/`（Bearer JKAW7A，v1.12.4，48 工具）
- **旧地址 `43.128.57.218:8000` 已失效**（不要用）
- **尾斜杠必须**（`/mcp/` 不是 `/mcp`）
- `get_factor_ic` 的 start/end 必须完整 YYYY-MM-DD
- csc-mcp：`mcp.csc108.com`，已加入 `~/.workbuddy/mcp.json`，需重新 Trust 才加载
