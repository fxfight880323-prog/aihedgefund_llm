# agent-context-audit · 投资策略框架 审计报告

> **方法论**：Anthropic Claude 5 context-engineering rubric（6 shifts + 跨切面失败模式）
> **审计对象**：本仓库的 agent context surface（doc / memory / run.py / daily log）
> **审计时间**：2026-09-10
> **审计结果摘要**：13 high / 9 medium / 5 low；always-loaded 上下文预估从 ~12k token → 4k token（-67%）

---

## 1. Scorecard

| Artifact | 现状 | finding 数（H/M/L） | 建议处置 |
|---|---|---|---|
| `docs/prompt_template_fund_framework.md` | 120 行 / ~9k 字符 / 6 个主要段落（11 铁律 + 4 任务模板 + 交付格式 + 自查 + 用户模式 + 附录） | 4 / 3 / 2 | **restructure**（按 shift 3 拆为"任务前必读"+"按需深读"） |
| `.workbuddy/memory/MEMORY.md` | 72 行 / 7.3k 字符 / auto-loaded | 3 / 2 / 1 | **trim + 拆分**（迁出研究历史归档，仅保留 quick reference） |
| 6 个 daily log（09-01/02/04/07/08/09/10） | ~35k 字符 / 全部 auto-loaded | 2 / 1 / 0 | **trim**（只保留最近 1-2 个；其余进 `docs/workspace_archive/`） |
| `docs/ALPHA_LAYERS.md` | 222 行 / 详细规范 | 0 / 2 / 1 | **keep**（但补 ledger.json 路径指向，去除重复叙述） |
| `docs/STRATEGIES.md` | 111 行 / 七模型表格 | 0 / 1 / 1 | **keep**（补 `src/signals/*.py` 路径指向） |
| `docs/投资认知框架.md` | 150 行 / 哲学+证伪清单+案例 | 1 / 2 / 1 | **restructure**（按 shift 3 拆 3 文件） |
| `run.py` | 123 行 / 命令行入口 | 0 / 0 / 1 | **keep**（补 pipeline module doc 引用） |
| **always-loaded 总量** | **~48k 字符 / ~12k token** | — | **目标：~16k 字符 / ~4k token（-67%）** |

---

## 2. 6 Shifts 跨切面 Finding 汇总

### Shift 1 · Rules → Judgment

| ID | 文件:行 | 原文 | 严重度 | 建议 |
|---|---|---|---|---|
| S1-1 | `prompt_template:25` | "违反任何一条 = 返工。AI 若发现冲突，直接说'违反铁律 X'并停下说明" | medium | 改为"违反关键条 = 返工。AI 若发现潜在冲突，先指出冲突点由人裁决"（去绝对化） |
| S1-2 | `MEMORY.md:16-21` | "回测方法论铁律" 4 条简版铁律（与 prompt_template 11 铁律重复） | high | **删**：单 home 在 prompt_template，MEMORY 只保留"已生效策略"事实 |

### Shift 2 · Examples → Interface

| ID | 文件:行 | 原文 | 严重度 | 建议 |
|---|---|---|---|---|
| S2-1 | `prompt_template:44-72` | 4 段"任务模板"长字符串（A/B/C/D） | medium | 重构为 `TASK_TYPES = {'backtest': {...params}, 'screen': {...}, 'factor_eval': {...}, 'diagnose': {...}}`（enum-style） |

### Shift 3 · Upfront Context → Progressive Disclosure

| ID | 文件:行 | 原文 | 严重度 | 建议 |
|---|---|---|---|---|
| S3-1 | `MEMORY.md:23-36` | 12 行"已验证策略结论"表 | high | **迁出**到 `docs/research_log/STRATEGY_HISTORY.md`（按 Pareto 排序，AD_top15 置顶） |
| S3-2 | `MEMORY.md:44-52` | 3 段"路径 A/B/D + Pareto 完整结论" | high | **迁出**到 `docs/research_log/2026-09-07_pareto.md`（daily log 已记录，MEMORY 留 1 行指针） |
| S3-3 | `MEMORY.md:65-72` | "数据与工程坑"8 条 | medium | 精简到 4 条最常踩的；其余迁 `docs/engineering/known_issues.md` |
| S3-4 | `prompt_template:110-120` | 附录"历史教训速览"9 条 | medium | **迁出**到 `docs/research_log/HISTORICAL_FINDINGS.md`（已存在部分内容于 投资认知框架.md） |
| S3-5 | 6 个 daily log auto-load | ~35k 字符 | high | 只 auto-load 最近 1-2 个；旧文件迁 `docs/workspace_archive/daily_logs/` |

### Shift 4 · Repetition → Single-Home

| ID | 文件:行 | 重复点 | 严重度 | 建议 |
|---|---|---|---|---|
| S4-1 | prompt_template:27-39 vs MEMORY.md:16-21 | 11 铁律 / 4 简版 | high | prompt_template 是 single home；MEMORY.md 删"回测方法论铁律"小节 |
| S4-2 | prompt_template:117 vs MEMORY.md:38 | "金融剔除 = 负贡献" 数字 | high | 数字源 = 投资认知框架.md（VERIFIED），MEMORY.md 留单行指针 |
| S4-3 | prompt_template:119 vs MEMORY.md:40 | "PB band = 正贡献" 5.03pp 数字 | high | 同 S4-2，单 home |
| S4-4 | MEMORY.md:55, 56 vs daily log 09-08:88-89 | "调仓日 2027-04-30" | high | 单一指针：MEMORY.md:55 即可；daily log 是"事件发生时的快照" |
| S4-5 | MEMORY.md:34 vs MEMORY.md:32 | "AD_top15 (+117.5%) Pareto 唯一" vs "D_top20_mom60 (+99.1%)" | high | 顺序问题——AD_top15 是 Pareto 最优应该置顶/标 ⭐，D_top20 是 D 路径代表 |
| S4-6 | MEMORY.md:36 vs prompt_template:115 | "q20+band80 +135.0% MDD14.5%" 数字 | medium | 数字存 `docs/research_log/2026-09-08_band_validation.md`；MEMORY 单行指针 |
| S4-7 | MEMORY.md 第 5 行 "已同步至 24" 同步状态 | hardcoded | medium | 改为"vault 同步状态见 docs/obsidian_sync_state.md"（auto-update） |

### Shift 5 · Manual Memory → Auto Memory

| ID | 文件:行 | 内容 | 严重度 | 建议 |
|---|---|---|---|---|
| S5-1 | MEMORY.md 整体 | 7.3k 字符手维护笔记 | medium | daily log 已经自动按日写；MEMORY.md 应该从最近 1-2 个 daily log 自动摘要（cron 任务），避免手维护 |
| S5-2 | MEMORY.md:23-36 策略结论表 | 12 行研究历史 | high | 迁 `docs/research_log/STRATEGY_HISTORY.md`（项目事实，不是 agent 启动必备） |
| S5-3 | daily logs 6 个文件 | 手写 daily notes | low | 接受现状（按日 append-only 已经是 WorkBuddy 设计意图） |

### Shift 6 · Simple Specs → Rich References

| ID | 文件:行 | 原文 | 严重度 | 建议 |
|---|---|---|---|---|
| S6-1 | prompt_template:46 | 任务 A "区间 2021-05 ~ 最新" | medium | 改为 "区间 2021-05 ~ 最新（具体 PIT_DATES 见 `pipeline/dates.py`）" |
| S6-2 | prompt_template:57 | 任务 B "排序：价值50% + 质量25% + 安全25% 百分位打分" | medium | 改为指向 `pipeline/` 模块；避免和 MEMORY.md q20 0.8/0.2 权重混淆 |
| S6-3 | STRATEGIES.md 模型表 | 七模型无文件路径 | low | 补 `src/signals/<model>.py` 路径列 |
| S6-4 | ALPHA_LAYERS.md 章节"记录载体" | 提到 `alpha_ledger/ledger.json` 但没给 schema | low | 补 ledger.json 字段示例或 `alpha_ledger/README.md` |

### 跨切面 · Conflicts

| ID | 冲突点 | 严重度 | 建议 |
|---|---|---|---|
| C-1 | **Python 路径冲突**：prompt_template:21 "回测 → `D:/Python/python.exe`" vs MEMORY.md:70 "回测用 `C:/Users/xfugm/.workbuddy/binaries/python/versions/3.13.12/python.exe`" | high | **以 MEMORY.md 为准**（更新版）。prompt_template 改写并加 "(已废弃旧路径)" 提示 |
| C-2 | **MCP 地址冲突**：prompt_template:16 "申万金工 MCP http://43.128.57.218:8000" vs MEMORY.md:13 "http://159.138.132.129" | high | **以 MEMORY.md 为准**（新地址）。prompt_template 改写 |
| C-3 | **调仓日 stale 风险**：MEMORY.md:55 "2027-04-30" 正确，但 9-08 daily log:43 写 "2026-10-31"（已修） | high | MEMORY.md 单一指针；daily log 9-08:43 行加 "（已修正为 2027-04-30）" 旁注 |
| C-4 | **金融剔除的双重含义**：prompt_template 铁律 #10 说"金融剔除只用于展示层"，但任务 B 模板要"金融剔除(123只名单)" | medium | 铁律 #10 措辞改："金融剔除**仅用于"当前推荐名单"展示层**（任务 B），**不进回测/排序管线**（任务 A、C）" |
| C-5 | **评分权重混淆**：prompt_template 任务 B "价值50%/质量25%/安全25%" vs MEMORY.md q20 "0.8×PE+0.2×质量" | medium | prompt_template 任务 B 注明 "LX-core 口径；q20 口径见 MEMORY.md" |

### 跨切面 · Staleness

| ID | stale 点 | 严重度 | 修复 |
|---|---|---|---|
| T-1 | prompt_template:114 "金融剔除证伪：PE 升序天然聚集低估值银行股，收益 ~85% 来自金融" 数字过时（q20 改权重后该比例不适用） | high | 改为 "见 `docs/research_log/` 历史记录" 指针 |
| T-2 | prompt_template 顶部 "v1.0 · 2026-08-25 定稿"——3 周没更新 | medium | 加 "v1.1 · 2026-09-10：MCP 地址 + Python 路径 + 11 铁律拆分（见 S4-1）" changelog 行 |
| T-3 | MEMORY.md:5 "已同步至 **24**（2026-09-02）"——同步次数 stale | medium | 同 S4-7 |
| T-4 | 投资认知框架.md:5 "2026-08-26 修订"——2 周没更新（q20+band 验证未并入） | medium | 加 "v1.2 · 2026-09-10：q20+band 验证结论" 修订行 |

### 跨切面 · Missing Unknown-Knowns（探查发现）

| ID | "团队知道但没写进 doc" 的事实 | 建议位置 |
|---|---|---|
| U-1 | **Python 3.13.12 venv 缺 pydantic + pyyaml**（2026-09-07 已装） | 新增 `docs/engineering/known_issues.md` |
| U-2 | **HTTPS git push 在 Windows 必失败**（系统代理拦），**必须用 SSH** | 新增 `docs/engineering/git_workflow.md` |
| U-3 | **q20 候选有 202 只无日频 PB 历史**，parquet 只覆盖 LX-core 898 只 | 新增 `docs/engineering/data_coverage.md` |
| U-4 | **Bash 沙箱 cwd 可能损坏**（长任务用 Agent 子进程） | 补进 `docs/engineering/known_issues.md` |
| U-5 | **q20_cap8 vs LX-core 唯一区别**：LX 有 band_veto，Q20 已内置 band90（之前误判为缺，2026-09-10 更正） | 补进 `docs/research_log/STRATEGY_HISTORY.md` 顶部注记 |
| U-6 | **automation 1787816093790 (Q20 净值) WinError 10061 失败** | 补进 `docs/engineering/automation_status.md` |
| U-7 | **实盘数据源 = 腾讯 qt.gtimg.cn（线程池 16 workers），回测数据源 = JSON 快照** | 补进 `docs/engineering/data_coverage.md` |
| U-8 | **每月调仓日固定 = 4 月末/8 月末**（不是任意半年） | 补进 `docs/engineering/known_issues.md` 顶部 |

---

## 3. Top 5 最高 ROI 修改（建议优先执行）

1. **S4-1 + S4-2 + S4-3 + S4-5（消除四处重复铁律）**：删 MEMORY.md:16-21 与 prompt_template 重复的 4 条铁律；同时把策略结论表按 Pareto 重排（AD_top15 置顶）。
2. **C-1 + C-2（Python 路径 + MCP 地址冲突）**：在 prompt_template 顶部 changelog 加一行修正，避免每次 session agent 拿到旧地址。
3. **S3-1 + S3-2（迁出研究历史）**：把 12 行策略结论 + 3 段路径结论迁到 `docs/research_log/`，MEMORY.md 只留指针。
4. **S3-5（daily log 不全 auto-load）**：旧 daily log 迁 `docs/workspace_archive/daily_logs/`，只留最近 2 个。
5. **U-1 + U-2 + U-3 + U-4（建立 engineering 文档）**：把"团队都知道但没写"的事实落地为 3 个 `docs/engineering/*.md`，让新 agent / 新会话能快速 onboard。

---

## 4. Projected Result

| 指标 | 现状 | 目标（应用所有 high + medium 修复） | Δ |
|---|---|---|---|
| always-loaded 字符 | ~48k | ~16k | **-67%** |
| always-loaded token | ~12k | ~4k | **-67%** |
| high severity finding | 13 | 0 | -13 |
| 重复维护的铁律/事实 | 8 处 | 1 处（single home） | -7 处 |
| Stale 数字 | 6 处 | 0 处（指针化） | -6 处 |
| unknown-knowns 文档化 | 0 个文件 | 3 个文件（known_issues / git_workflow / data_coverage） | +3 |

---

## 5. 建议应用顺序（Step 4）

1. **新建** `docs/engineering/{known_issues.md, git_workflow.md, data_coverage.md, automation_status.md}`（U-1~U-8）
2. **新建** `docs/research_log/{STRATEGY_HISTORY.md, HISTORICAL_FINDINGS.md}`（S3-1, S3-2, S3-4）
3. **重建** `docs/prompt_template_fund_framework.md`（修复 C-1/C-2/C-4/C-5，去重复，删附录，指向真代码）
4. **重建** `MEMORY.md`（删 4 简版铁律 / 12 行策略表 / 3 段路径结论 / 8 条工程坑 → 保留 quick reference + 指针）
5. **搬迁** 旧 daily log 到 `docs/workspace_archive/daily_logs/`（S3-5）
6. **不动**：`run.py`（OK），`ALPHA_LAYERS.md`（keep + 补路径），`STRATEGIES.md`（keep + 补路径），`投资认知框架.md`（restructure 后续单独做）

预计总工作量：~8-10 个文件，30-40 分钟。完成后做一次 git commit 收尾。
