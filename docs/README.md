# docs/ · 项目文档体系

> Agent 启动 → `.workbuddy/memory/MEMORY.md` (quick reference)
> → 任务前粘贴 → `prompt_template_fund_framework.md` (11 铁律 + 任务模板)
> → 按需查阅 → `engineering/` / `research_log/` / `workspace_archive/`

---

## 入口

| 文件 | 何时读 |
|---|---|
| `prompt_template_fund_framework.md` | **每次发起 fund_framework 任务前**粘贴给 AI。11 铁律 + 4 任务模板。 |
| `投资认知框架.md` | 新成员 / 季度回顾时读。投资哲学顶层（池子+因子+方法论+卖出）。 |
| `ALPHA_LAYERS.md` | 任何 alpha 改进 → 必读。三层归因（L1 数据 / L2 方法论 / L3 信号）。 |
| `STRATEGIES.md` | 看具体选股模型实现时读。七模型 + 框架分层。 |
| `agent-context-audit-2026-09-10.md` | 当本文件体系需要 review / 修订时读。最近一次 context 审计。 |

## `engineering/` · 工程基础设施

| 文件 | 何时读 |
|---|---|
| `known_issues.md` | **新 session 必读**。Python 路径、调仓日、cwd 坑。 |
| `git_workflow.md` | 准备 git push / 写 commit message 前。SSH 凭据、commit 规范。 |
| `data_coverage.md` | 写回测 / 拉数据前。数据源 + 覆盖限制 + 已知坑。 |
| `automation_status.md` | automation 任务失败排查时。 |

## `research_log/` · 研究历史档案

| 文件 | 何时读 |
|---|---|
| `STRATEGY_HISTORY.md` | 决定用哪个策略 / 看 Pareto 前沿。**Pareto 排序版策略结论表**。 |
| `HISTORICAL_FINDINGS.md` | 11 铁律"为什么"的完整溯源 + 反模式速查。 |
| `2026-09-08_band_validation.md` | band 规避层对照回测（Q20 +11~16pp 增益）。 |
| `2026-09-10_q20_band80_landing.md` | band80 落地到实盘 Q20 的工程实施。 |

## `workspace_archive/` · 已废弃 / 归档

| 子目录 | 内容 |
|---|---|
| `daily_logs/` | 2026-08-19 ~ 2026-09-09 daily log 归档（13 个文件） |

---

## 文档维护规则

1. **Single home**：每条事实只在 1 个文件维护，其他文件用单行指针
2. **changelog 顶部更新**：每个文件改动时顶部 changelog 加 1 行
3. **stale 风险**：MEMORY.md 里的"已同步至 24"等 hardcoded 数字 → 改指向 `obsidian_sync_state.md`（TODO 自动化提取）
4. **新 doc 创建时**：在本文档（README.md）"何时读"列加一行
