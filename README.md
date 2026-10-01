# aihedgefund_llm — A股量化研究主仓

个人量化研究统一仓库：多策略研发、回测、模拟组合跟踪与基金持仓证据系统。
三大系统共用一套数据口径铁律（见文末），全部结论可由代码复现。

## 仓库地图

| 模块 | 内容 | 状态 |
|---|---|---|
| `run.py` + `pipeline/` | ai_fund_framework 统一数据管线（筛选/回测/模拟组合/审计） | ✅ 每日自动运行 |
| `a_share_financing_backtest/` | A股融资市场世界观回测（双Regime，V1→V3） | 🆕 2026-10 |
| `rag/` | 基金持仓×研报 RAG 证据系统（混合检索+rerank） | ✅ v4 |
| `src/` | 核心框架库（backtest/core/data/risk/signals/portfolio...） | ✅ |
| `examples/` | 策略示例（CScore/F-Score/growth_loop/BSADF/rotation...） | ✅ |
| `tests/` | 单元测试（engine/growth_loop/rotation/serenity_gate/signals） | ✅ |
| `docs/` | 架构文档（ALPHA_LAYERS / STRATEGIES / research_log） | ✅ |
| `alpha_ledger/` | alpha账本记录 | ✅ |
| `dsh/` | 仪表盘与工具（cordis-fund） | ✅ |
| 根目录 `_*.py`（231个） | 已验证的策略/筛选/回测脚本（**不移动**——自动化任务引用绝对路径） | ✅ |

---

# 系统一：ai_fund_framework 统一数据管线

把已验证的策略筛选、回测、模拟组合跟踪**固定为可重复运行的代码**。更新数据
只跑 `run.py` 一个入口，不再手工改脚本日期、不再依赖会话里临时拼装。

## 快速上手

```bash
# 使用管理 venv 的解释器（含 pandas 2.3.3）
PY="C:\Users\xfugm\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

$PY run.py status      # ① 数据新鲜度体检（推荐先跑）
$PY run.py daily       # ② 每日：两个模拟组合净值 + 报告（幂等，非交易日自动 SKIP）
$PY run.py screen      # ③ 名单刷新：数据拉取 + 三轨筛选（主轨/KFIN/q20），约 5~15 分钟
$PY run.py backtest    # ④ 权威回测集重跑（garp 审计/gm 证伪/q20 增量/全景总结）
$PY run.py audit       # ⑤ 一致性审计：最新名单 vs 模拟组合账本（差异=数据更新效应提示）
$PY run.py all         # ⑥ 全流程 = screen + backtest（重，慎用）
$PY run.py --list      # 预览所有步骤
```

`--only 子串` 可只跑部分步骤（如 `run.py screen --only q20`、`run.py backtest --only garp`）；
`--continue-on-error` 允许失败后继续（默认 fail-fast 停住，便于定位）。

## 管线结构

```
run.py                  # 统一总控入口（CLI）
pipeline/
  config.py             # 根目录/解释器/资金参数统一配置（AIFF_PYTHON 可覆盖解释器）
  dates.py              # 候选交易日自动推导 + 新鲜度体检
  runner.py             # 步骤定义（Step）与顺序执行器（产物校验 + fail-fast）
```

设计原则：
1. **不移动/不重写已验证脚本**（每日自动化任务引用其绝对路径）——编排层只按序调用；
2. **唯一日期入口**：`_lx_now_fetch.py` 支持 `--candidate-dates`，由 `pipeline/dates.py`
   自动注入最近 6 个工作日，**无需再手工改 CANDIDATE_DATES**；
3. 每个 Step 校验产物存在，失败即停并报错（screen 链中间产物缺失会在第一步暴露）。

## 数据流（screen 步骤明细）

```
①  _lx_now_fetch.py       万得全A PIT成分 / 估值面板 / HF因子 / 一致预期
        ↓（_bt_lx_now_{universe,valuation,factors,consensus}.json）
②  _lx_now_screen.py      主轨筛选（剔金融, LX-core+garp）→ _lx_now_results.json
③  _lx_now_score.py       评分（价值50/质量25/安全25）→ _lx_now_scored.json
④  _lx_now_band.py        估值Band（5年自身分位）→ _lx_now_band.json
⑤  _lx_band_apply.py      Band规避剔除(PB分位>90%)→ _lx_now_final.json + 报告
⑥  _lx_now_screen_kfin.py KFIN轨筛选（含金融, core原始口径）→ _lx_now_results_kfin.json
⑦  _lx_kfin_band.py       KFIN Band → _lx_kfin_final.json + 报告
⑧  _bt_q20_kfin.py        q20混合排序（0.8×PE+0.2×质量）top40 → _bt_q20_kfin.json + 报告
⑨  _pipeline_audit.py     一致性审计（run.py audit 独立触发）
```

## 一致性审计（audit 步骤）

`run.py audit` 校验：q20 最新名单 ↔ Q20 模拟组合账本、行业构成、资金使用率。
**名单与账本出现差异 = 数据更新效应，非 bug**：模拟组合只在调仓日（2027-04-30）重平衡，
期间 screen 每次刷新（一致预期 T+1 落地、估值/HF 更新）都可能让最新名单小幅变动。
典型例子：2026-08-27 建仓（consensus@08-24，池 221 只）后首次重跑
（consensus@08-26，池 210 只），q20 名单 7 进 7 出 —— garp 门控 L4/L5 随预期数据变化所致。
差异提示 exit code = 2（区别于管线错误的 1）。

## 模拟组合（daily 步骤）

| 组合 | 账本 | 引擎 | 下次调仓 |
|---|---|---|---|
| LX-top40（core+garp 剔金融） | `_sim_portfolio.json` / `_sim_nav.json` | `_sim_engine.py` → `_sim_daily.py` | 2027-04-30 |
| Q20·质衡优选（含金融, q20 排序） | `_sim_q20_portfolio.json` / `_sim_q20_nav.json` | `_sim_q20_engine.py` → `_sim_q20_daily.py` | 2027-04-30 |

两个 daily 脚本**幂等**：同日重复跑覆盖当天条目；行情日期≠今天自动 SKIP。
调仓请用 `_sim_rebalance.py` / `_sim_q20_rebalance.py`（--dry 先预览），
或等自动化任务在 2027-04-30 / 2027-08-31 触发。

## 自动化（已配置，无需手工）

- 每日净值：LX automation-1787723540036 / Q20 automation-1787816093790（工作日 15:35）
- 调仓：LX 1787723732694/1787723732711、Q20 1787816093812/1787816093831（2027 年生效）

---

# 系统二：A股融资市场逻辑回测（a_share_financing_backtest/）

基于"A股是融资市场"世界观的双Regime行业轮动策略，2016-01 ~ 2026-03，三轮迭代。
详见 [`a_share_financing_backtest/README.md`](a_share_financing_backtest/README.md)。

**Regime 1 — 产业扶持**（不看盈利不看估值）：产业政策+流动性+国家队三条件共振买成长行业；
卖出=盈利成熟（增速减缓/ROE峰值回落）或国家队卖出清盘。

**Regime 2 — 消费吃药**：居民杠杆率年增量≥2pct → 买白酒/消费/医药；跌破阈值（平台期）→ 清仓。

| 版本 | 标的 | 总收益 | 夏普 | 最大回撤 |
|---|---|---|---|---|
| V1 严格（单Regime） | 申万一级行业 | +26.8% | 0.28 | -27.0% |
| V2 双Regime+大基金 | 申万一级行业 | +116.7% | 0.58 | -33.2% |
| **V3 双Regime+大基金** | **中证主题指数** | **+201.5%** | **0.64** | -39.7% |
| 沪深300基准 | — | +25.6% | — | -45.6% |

关键结论：①消费吃药=居民加杠杆的镜像（白酒2016-04→2022-04 **+402%**）；②条件优先级消融——流动性
条件冗余、政策/国家队价值在锁定底部买点、杠杆双Regime是最强增强；③同信号下主题指数=高beta放大器
（收益+85pct、回撤同步放大）。

---

# 系统三：基金持仓×研报 RAG 证据系统（rag/）

调仓决策的证据支撑：基金持仓数据 + 研报全文库（5879向量）混合检索（BM25+向量）+ bge-reranker
精排，输出 Q20 持仓×研报证据报告。含评估集（39题）与个股相关性门槛过滤。
入口：`rag/query.py` / `rag/report.py`；文档见 `docs/`。

---

# 核心框架（src/ + examples/ + tests/）

```
src/
  backtest/   回测引擎    core/       基础组件    data/       数据层
  execution/  执行模拟    portfolio/  组合构建    research/   研究流程
  risk/       风险管理    signals/    信号系统    workflow/   工作流    utils/     工具集
examples/     策略示例：CScore / F-Score / growth_loop / BSADF泡沫检测 / rotation / serenity
tests/        单元测试覆盖引擎与信号逻辑
docs/         ALPHA_LAYERS.md / STRATEGIES.md / prompt_template_fund_framework.md / research_log/
```

---

# 数据源与口径铁律（勿违背）

- 池子 = 万得全A(881001.WI) PIT 成分，禁止手工精选；结论先对"等权全A"基准
- 回测一律**日频 + 复权**；半年调仓策略基准 = "半年调仓等权全A"
- 质量层只能排序微调（q20 +3.40pp），gm 硬过滤已证伪禁止引入
- garp 权威口径 = 全池 g60（+67.01%），旧 +34.57% 禁止引用
- HF 因子健康判定：gpm top5 头部 >50 才健康（2026-08-20 起污染），fetch 自动回退
- 回测四项铁律：数据对齐 / 无未来数据（披露日对齐+T+1） / 样本外验证 / 逻辑可溯源
- 多源交叉检验后才入库（如：沪深300双源偏差<0.0001%、LPR双源一致、事件表对照官方公告）

# 更新日志

- **2026-10-01** 新增 `a_share_financing_backtest/`：融资市场世界观双Regime回测（V1→V3，82文件）
- **2026-09-10** rag v4：Q20持仓×研报证据报告 + 经理访谈纪要入库 + 个股相关性门槛
- **2026-09-10** rag v2/v3：PDF全文回填+混合检索+评估集；全文库5879向量+bge-reranker
- 历史迭代见 `docs/research_log/`
