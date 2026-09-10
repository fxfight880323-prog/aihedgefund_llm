# Engineering · 已知坑与解决

> 团队都知道但分散在 daily log / Slack 里的"反常识"操作约束。
> 新 session agent / 新成员 必读。

## Python 环境

| 任务 | 解释器路径 | 备注 |
|---|---|---|
| 回测 / 数据管线 | `C:/Users/xfugm/.workbuddy/binaries/python/versions/3.13.12/python.exe` | 3.13.12，已装 pydantic + pyyaml（2026-09-07） |
| parquet / pyarrow | `C:/Users/xfugm/.workbuddy/binaries/python/envs/default/Scripts/python.exe` | 3.x 托管 venv，含 pyarrow 25 + pandas 2.3 |
| 旧路径（已废弃）| `D:/Python/python.exe` | 3.11.7，仅 fallback |

**坑**：
- 3.13.12 venv **不预装 pydantic / pyyaml**，第一次跑回测若 import 失败需先 `pip install pydantic pyyaml`
- 用 `3.13.12` 跑含 parquet 读取的脚本会 `ModuleNotFoundError: pyarrow`——必须切到 `envs/default`

## 调仓日

- **调仓日固定 = 4 月末 / 8 月末**（不是任意"半年"）
- 实盘 2 个组合（LX-top40 / Q20·质衡优选）当前 2026-08-26/27 建仓
- **下次调仓 = 2027-04-30**（半年后，不是 2026-10-31——多处历史 daily log 写错过，2026-09-08 更正）

## Bash / PowerShell 沙箱

- 沙箱 cwd 可能损坏（尤其长任务），**长任务用 Agent 子进程**
- 涉及"Command blocked for security"（PowerShell from Bash 拦截）时，改用 `PowerShell` 工具而非绕过
- 跨工具转义：`$VAR` (bash) vs `$env:VAR` (PowerShell) vs `os.environ` (Python)，别混

## 沙箱 cwd 重置

如果 git / python 报"fatal: cannot determine current directory"或"FileNotFoundError: cwd"——在子进程里加 `os.chdir("D:/workspace/ai_fund_framework")` 强制重置。
