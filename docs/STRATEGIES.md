# AI Fund Framework — 选股策略总览

> 更新：2026-08 · 全部模型经 `ALPHA_MODEL_REGISTRY` / `BLEND_POLICY_REGISTRY` 注册，
> LangGraph 主图驱动，YAML 可选组合。

## 一、框架分层

```
LangGraph 主图（src/workflow/graph.py）
fetch_data → run_analysts → blend_signals → apply_risk → build_orders → execute_orders → record_cycle

GOAL→HOOK→LOOP 子图（src/workflow/growth_loop_graph.py）
hook_screen → L1→verify→L2→verify…L7→l8_conviction（门控回环，带 kill 终端）

vnpy 式回测引擎（src/backtest/）
union-of-dates 月频循环 → cross→on_bars→mark；N 月末下单 N+1 月成交（无前视）
```

组件角色：
- **AlphaModel**（signals）：逐票产出 Signal(value∈[-1,1], metadata)
- **BlendPolicy**（portfolio）：多信号 → 目标权重（读 metadata 做类配比/方向权重）
- **RiskModel**（risk）：硬限制钳制
- **Broker**（execution）：SimBroker / 实盘接 口

## 二、七大选股/择时模型

| # | 模型 | 类型 | 核心逻辑 | 适用场景 |
|---|------|------|----------|----------|
| 1 | `buffett` | LLM | 护城河/ROE 一贯性/估值合理性（GLM-4 推理） | 长线价值 |
| 2 | `growth_loop` | LLM+图 | GOAL→HOOK→LOOP 剧本：H1-H6 钩子筛 → L1-L7 门控深研 → L8 信念；确定性验证层校验 LLM 算术 | 高成长深研（科创板/AI 链） |
| 3 | `rotation_growth` | 量化 | 章宏帆"有锐度的均衡"：A/B/C 分类 + 环节稀缺度 S1-S5 + 龙头直取 + G5 泡沫分解 + L5 仪表盘缩放 | 行业轮动满仓 |
| 4 | `bsadf` | 量化 | Phillips-Shi-Yu 泡沫检验（ADF t 矩阵 + MC 临界值）→ v3 相位机 CALM/IGNITION/RIDING/FADING/BURST/FEAR，骑泡沫策略 | 泡沫择时/热度卖出 |
| 5 | `tech_confluence` | 量化 | MACD 面积背离 / RSI 超买 / 量价背离 / Chandelier exit / MACD 死叉 | 技术面共振确认 |
| 6 | `ashare_value` | 量化 | A 股量化价值多因子 | 价值底仓 |
| 7 | `pead` | 量化 | 盈余公告后漂移 | 事件驱动 |

### 模型详解

**② growth_loop（剧本门控）**
- 钩子层（hooks.py，规则解耦）：H1 营收加速（连续 2 季）、H2 毛利率拐点（环比上行+增速>20%）、H3 连续 BEAT、H6 深回撤高增长（-30% 回撤+YoY≥10%）
- 门控层：L1 商业模式/数据完整性 → L2 竞争壁垒 → L3 单位经济 → L4 客户集中度（不单独 kill）→ L5 TAM/渗透率 → L6 估值 → L7 反证
- 原则：数据完整性契约（缺数据必须显式声明 DATA GAP，声明后不 kill）；LLM 报 NUMBERS、代码验证门算术
- A/B/C 优先级排序 + LOOP 深研上限

**③ rotation_growth（章宏帆方法论）**
- L1 分类：A 景气成长（营收加速+高增长，ROE≥8+正利润）、B 周期成长（成熟+毛利率回升，PE 上限环节化）、C 新兴成长（YoY>150% 小仓位）
- L2 环节：10 个行业环节稀缺度表（S1 供给刚性/S2 需求锁定/S3 格局/S4 加速度/S5 验证）；龙头直取（assigned_link）；B 类成熟龙头通道（≥500 亿）；OFF 自下而上 sleeve
- G5-lite 涨幅分解（ΔEPS vs ΔPE，ΔPE 主导→信念×0.5）；L5 AI 仪表盘（≥2/3 转熊→A 减半）
- 质量分道：市值分层质量宽限道（tier1 500 亿/tier2 200 亿）

## 三、两大组仓策略（BlendPolicy）

| 策略 | 逻辑 |
|------|------|
| `conviction_weighted` | 信念加权（通用基线，支持 market_neutral） |
| `balanced_sharpness` | 方向权重按 S 分单调（top≈16%→tail≈7%）＋类配比 A≤60/B≤35/C≤5＋单票 5% 上限＋OFF sleeve＋满仓缩放 |

## 四、七个策略配置（config/strategies/，可 YAML 组合）

| 配置 | 组合 | 说明 |
|------|------|------|
| `buffett/fundamental_ls` | buffett × conviction | 基本面 L/S（对冲） |
| `growth_loop` | growth_loop × conviction | 科创板成长深研 |
| `rotation_growth` | rotation_growth × balanced_sharpness | 轮动满仓（demo：gross 0.9） |
| `bsadf_bubble` | bsadf | 纯泡沫择时 |
| `bsadf_confluence` | bsadf + tech_confluence | 泡沫+技术共振双确认 |
| `ashare_value` | ashare_value | A 股价值 |
| `earnings_drift` | pead | 盈余漂移 |

基金层（config/funds/）：rotation_full（满仓 A60/B35/C5、单票 5%、环节化 PE 上限）等 7 个。

## 五、选股/回测执行脚本（examples/）

| 脚本 | 用途 | 数据 |
|------|------|------|
| `kechuang50_selection.py` | 科创50 周度选股（HOOK 筛→LOOP 深研真实 GLM-4） | MX MCP |
| `alla_rotation.py` | 万得全A 满仓轮动（LEADER_SEEDS 10 环节龙头直取+选股器三队列） | MX MCP |
| `backtest_universal.py` | 76 只跨行业龙头池 5 年回测（vnpy 式引擎） | MX 缓存 |
| `backtest_pit.py` | **点时选择回测**（全市场 top-100→行业聚合→个股，无幸存者偏差）+ BSADF 热度卖出 | MX 选股器点时字段 |
| `analyze_backtest.py` | 深度归因（绩效/回撤/分期/个股贡献/持仓特征） | 回测缓存 |
| `compare_backtests.py` | 点时 vs 龙头池对比 | 回测缓存 |

## 六、回测实证结论（2021-06 → 2026-08，5.2 年）

| 版本 | 总收益 | 超额 | 回撤 |
|------|--------|------|------|
| 龙头池（幸存者偏差） | +33.2% | +28.7% | -24.2% |
| 点时无 BSADF | -19.5% | -24.0% | -32.7% |
| 点时 + BSADF 调仓月叠加 | -18.7% | -23.2% | -32.0% |
| 点时 + BSADF 逐月出场 | -21.6% | -26.1% | -32.8% |

1. **幸存者偏差 ≈ 53pp**——龙头池回测的 +33% 主要是"已知赢家"的 artifact
2. BSADF 调仓月叠加略优（泡沫破裂期正确减仓）；**逐月出场在主升段卖飞赢家**（月频相位机无法区分抛物线回撤与真破裂，参数不敏感）
3. 点时执行暴露的方法论缺口（= 下一步）：行业龙头识别（非增速排名）、供给格局 S 分（供应链审计）、估值上限数据源、渗透率临界点（区分真成长与基数效应复苏）

## 七、测试覆盖

118 项测试：signals(23) + growth_loop(~40) + rotation(34) + backtest_engine(21)
