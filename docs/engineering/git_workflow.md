# Engineering · Git 工作流

## 凭据与远程

- **远程仓库**：`https://github.com/fxfight880323-prog/aihedgefund_llm.git`
- **本地 origin**：`git@github.com:fxfight880323-prog/aihedgefund_llm.git`（已切到 SSH）
- **SSH key**：`~/.ssh/id_ed25519`（GitHub 已认证 `fxfight880323-prog`）

## 推送到 GitHub

| 步骤 | 命令 |
|---|---|
| 暂存所有变更 | `git add -A` |
| 提交 | `git commit -m "..."` |
| 推送 | `git push origin main`（用 SSH origin，**不要 HTTPS**）|

## 已知坑

### HTTPS push 100% 失败（Windows 系统代理拦）
- 错误信息：`fatal: unable to access ... Recv failure: Connection was reset`
- **修复**：用 SSH origin（已切到 `git@github.com:...`），不要回退到 HTTPS
- **不要尝试**：`NO_PROXY=* git push`（已测，Windows 仍拦截）

### Stale ref 缓存
- 现象：push 成功后 `git branch -vv` 仍报 "ahead 24"
- **不修复**——这是 git in-memory cache bug，不影响远程实际状态
- **权威验证**：`curl -s "https://api.github.com/repos/<user>/<repo>/commits?sha=main&per_page=5" | grep sha`（看真实 commit 链）

### CRLF 警告
- 现象：`warning: LF will be replaced by CRLF the next time Git touches it`
- 无害（Windows 行尾），无需修

## 提交规范

- **类型前缀**：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`
- **主标题**：≤80 字，说明"做了什么"
- **正文**：列出变更点（每点一行 `- xxx`），含数据/数字/链接证据
- **回测/审计类 commit**：附 "依据: docs/prompt_template_fund_framework.md 铁律 X" 引用
