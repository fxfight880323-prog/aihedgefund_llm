# Engineering · 自动化任务状态

> 截至 2026-09-10

## 日频净值 Automation

| Automation ID | 组合 | 频率 | 状态 | 备注 |
|---|---|---|---|---|
| 1787723540036 | LX-top40 | 日频（盘后） | 正常 | |
| 1787816093790 | Q20·质衡优选 | 日频（盘后） | ⚠️ 间歇失败 | `WinError 10061` ConnectionRefused |

### Q20 净值 automation 排查

- 错误：`urllib.request.urlopen` → `https://qt.gtimg.cn` 在 Python 进程 socket 层 `WinError 10061`
- 诊断：`curl http(s)://qt.gtimg.cn/q=sh000985` 200 正常 → 腾讯端未故障
- 根因：本地进程/代理层到 `qt.gtimg.cn` TCP 被拒
- 兜底：未改代码（保留与 LX-top40 等组合口径一致）
- 当前快照：`_sim_q20_nav.json` / `_sim_q20_report.html` 维持 2026-09-01 净值 1,016,886.05
- 跟踪：详见 automation memory

## Windows 端绕过代理

回测 / 模拟组合跑实盘数据时需绕开 Windows 系统代理：

```bash
NO_PROXY=* HTTPS_PROXY="" HTTP_PROXY="" python _sim_q20_daily.py
```

详见 `known_issues.md` 沙箱 cwd 段。
