# fund_framework 建设 Prompt Template（v1.1 · 2026-09-10 修订）

> **用途**：发起任何 fund_framework 任务（回测 / 筛选 / 因子评估 / 报告 / 诊断）前，把本模板粘贴给 AI。
> **changelog**：
> - v1.1 (2026-09-10)：Python 路径 → `3.13.12`（旧 `D:/Python/python.exe` 废弃）；MCP 申万金工地址 → `http://159.138.132.129/mcp/`（旧 `43.128.57.218:8000` 失效）；11 铁律"理由"列从一句话精简；附录"历史教训"迁 `docs/research_log/HISTORICAL_FINDINGS.md`；金融剔除规则明确双层含义。
> - v1.0 (2026-08-25)：定稿（11 铁律 + 4 任务模板）。
>
> **配套**：
> - 铁律的完整溯源：`docs/research_log/HISTORICAL_FINDINGS.md`
> - 投资哲学：`docs/投资认知框架.md` + `docs/ALPHA_LAYERS.md`
> - 工程坑：`docs/engineering/{known_issues,git_workflow,data_coverage,automation_status}.md`
> - 策略历史：`docs/research_log/STRATEGY_HISTORY.md`
> - 项目状态：`.workbuddy/memory/MEMORY.md`（仅 quick reference）

---

## ① 项目上下文（每任务必附，让 AI 对焦）

我在建设自研量化框架 **fund_framework**（A股全市场选股 / 回测 / 筛选 / 因子评估一体化），核心产出是"可归因的 alpha"：投资收益 = 基准(池子) + 数据端(因子) + 方法论 + 卖出时点。

**数据基础设施**（详细覆盖与坑见 `docs/engineering/data_coverage.md`）：
- SQLite `data/a_share_market.db`：宽表 `pit_universe` / `monthly_close` / `index_monthly` / `consensus` / `factor_panel` / `valuation` / `gbm_factor`，主键 (month, ticker)。回测/筛选一律从 SQLite 读，JSON 仅为原始快照。
- juzi-mcp：万得全A(881001.WI) PIT 成分、一致预期(朝阳永续)、日频估值、HF因子、日频收益面板(parquet download_url，TTL 3600s 需立即落地)。
- 申万金工 MCP：**新地址 `http://159.138.132.129/mcp/`**（尾斜杠必须，Bearer JKAW7A，v1.12.4，48 工具）
- 腾讯行情：qt.gtimg.cn 月K（线程池 16 workers，~5500 只 ≈ 5-8 分钟）、web.ifzq.gtimg.cn 日K。

**Python 双环境**（详细见 `docs/engineering/known_issues.md`）：
- 回测引擎 → **`C:/Users/xfugm/.workbuddy/binaries/python/versions/3.13.12/python.exe`**（3.13.12，已装 pydantic + pyyaml）
- parquet/pyarrow 处理 → 托管 venv `C:/Users/xfugm/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（有 pyarrow 25 + pandas 2.3）
- 旧路径 `D:/Python/python.exe` 仅 fallback，**不要再用**

---

## ② 铁律（关键条违反 = 返工；AI 若发现潜在冲突，先指出冲突点由人裁决）

| # | 铁律 | 一句话理由 |
|---|---|---|
| 1 | **真实数据**：禁止编造/模拟/合成市场数据做分析；拿不到就明说 | 假数据结论全废 |
| 2 | **池子 = 万得全A PIT 成分**，禁止手工精选股票池 | 防幸存者偏差 |
| 3 | **统计颗粒度 = 日频+复权**；月频数字引用须标注"旧口径" | 月频系统性高估 |
| 4 | **同口径基准**：基准必须与策略同调仓频率/持有方式 | 不可直接对比 |
| 5 | **零未来函数**：PIT as_of / HF 因子滞后 / 非交易日映射 / T+1 撮合 | 用户四项验证原则 |
| 6 | **IC ≠ alpha**：高 IC 因子必须做 Q5−Q1 分位回测 | 极端值污染 |
| 7 | **先对比再下结论**：任何收益必须先与"等权池子"对比 | 高收益可能是池子 beta |
| 8 | **MDD 口径** = (peak − trough)/peak，按日频全序列计算 | 月频采样丢回撤 |
| 9 | **金融剔除仅用于"当前推荐名单"展示层**（任务 B），**不进回测/排序管线**（任务 A、C）| PE 升序天然聚集银行股 |
| 10 | **PB band 规避层**：PB 5年自身分位 > 90% 剔除（可选 > 80%）| 捕获"假便宜" |
| 11 | **排序信念 = PE 升序**：质量只能排序微调，不替代主排序 | 质量优先 -12.2pp vs 便宜优先 |

> 完整溯源（含"为什么"和反模式案例）：`docs/research_log/HISTORICAL_FINDINGS.md`

---

## ③ 任务类型模板（选一段替换"任务描述"，可组合）

### A. 回测任务
```
请对 [策略/变体] 在万得全A PIT 成分池上做【日频+复权】回测：
- PIT 区间见 pipeline/dates.py（当前 ~2021-08 ~ 最新）
- 半年调仓，调仓日 T+1 撮合（vnpy 语义）
- 基准 = 同口径半年调仓等权全A + 中证全指(000985.SH)
- 输出：总收益 / 年化 / MDD / 超额 / 每期持仓清单 / nav 序列
- 先跑"等权池子"对照组，再下结论（铁律 #7）
```

### B. 筛选任务（当前推荐名单）
```
池子：万得全A PIT 成分 + mv≥100亿 + 金融剔除(123只名单) + PB band 分位>90% 剔除
排序：LX-core 口径 = 价值50% + 质量25% + 安全25% 百分位打分
      Q20 口径 = 0.8×PE便宜度 + 0.2×质量分（q_score = (gpm+con_roe+cetop)/3 截面分位，详见 MEMORY.md）
因子注意：HF 因子面板滞后 1 个交易日探测（须用前一交易日）；非交易日 as_of 估值面板返回 count=0
```

### C. 因子评估任务
```
- 月频 Spearman IC + Q5−Q1 分位收益（多空验证），区间 2019-02~最新
- 个股层 vs 行业层区分：筹码合成【行业层】已证伪（Q1−Q5 平均 -3.97pp/月），只做行业内个股筛选/负面清单
- 检查极端值污染（单期 IC 被极端行情扭曲）
- MCP 坑：get_factor_ic 的 start/end 必须完整 YYYY-MM-DD
```

### D. 诊断任务
```
校验：数据对齐 / 未来函数 / 持仓数量(目标=实际) / MDD 口径 / 复权一致性 / 撮合时点
输出：结构化检查点表格，每项 pass/fail + 证据
```

---

## ④ 交付格式（默认要求，除非任务另有指定）

- **结论先行**：一行结论 → 支持表格 → 分层拆解（表格 + 结构化分层）
- **报告**：自包含 HTML（含图表 + 详细数据表 + 口径标注），命名 `_bt_*.html` 放工作区
- **进度**：表格回报；长任务分阶段 checkpoint（"继续"触发下一阶段）
- **留痕**：完整代码、过程逻辑、计算中间结果写入 Obsidian（`D:\Fortune\量化研究\`），便于未来复用与追溯
- **回测必加审计**：`docs/prompt_template_fund_framework.md` 11 铁律的合规检查表附在报告末尾

---

## ⑤ AI 自查清单（交付前逐项过）

- [ ] 池子用了 PIT 成分而非手工选股？
- [ ] 收益统计是日频？复权？MDD 是日频全序列标准口径？
- [ ] 与同口径等权全A 对比过？（无对比不结论）
- [ ] 无未来数据？（as_of / 滞后 / T+1 撮合）
- [ ] 金融剔除未误入回测管线？
- [ ] IC 结论做过 Q5−Q1 分位回测验证？
- [ ] 所有数字来自真实数据、可溯源？（数据源、拉取日期、URL 记录）

---

## ⑥ 用户追问模式速查（AI 如何回应）

| 用户说 | 含义 | AI 应做 |
|---|---|---|
| "跑一遍" / "继续" | 启动/推进完整流程 | 自主驱动长任务到完成；遇错继续推进，不中断 |
| "结果为什么与预期不符" | 深层归因 | 量化验证 + 逻辑溯源，直面困难不绕过 |
| "是不是 bug" | 先查口径再下结论 | 依次自查：颗粒度 → 复权 → 撮合时点 → 基准同口径 |
| "以表格回报" | 结构化进度 | 分阶段 checkpoint 表格 |
| "估值 band 更合理？" | 方法选择咨询 | 给出对比口径结论（横截面 vs 自身历史分位），再落地 |
| 对数据来源有疑问 | 真实性核验 | 给出数据源 / 拉取脚本 / 时间戳证据链 |
