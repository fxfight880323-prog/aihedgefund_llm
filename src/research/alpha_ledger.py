"""AlphaLedger — 三层 Alpha 记账模块.

三层目标结构（见 docs/ALPHA_LAYERS.md）：

    L1 数据层 / 信息源层     Data Edge        —— 数据源/信息源/新 MCP 接入的鉴别
    L2 Alpha 层 / 方法论层   Methodology Edge —— 方法论 + benchmark + 迭代
    L3 数量信号层           Signal Edge       —— 买卖信号 / 过热 / 卖出纪律

铁律：
    1. 每笔 alpha 只能记在一个层（data / methodology / quant_signal）
    2. 任何改进必须对照等权万得全A PIT 池（EW-全A）
    3. 无效实验同样记账（REJECTED），防止重复踩坑

用法：
    ledger = AlphaLedger.load()                      # 读 alpha_ledger/ledger.json
    ledger.add_entry("data", {...})                  # 记一笔
    ledger.attribute(layer="data", delta=0.18, ...)  # 归因一笔增量
    ledger.save()
    report_html = ledger.build_report()              # 生成对比报告
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Optional

Layer = Literal["data", "methodology", "quant_signal"]
LAYER_NAMES = {
    "data": "L1 数据层 / 信息源层",
    "methodology": "L2 Alpha层 / 方法论层",
    "quant_signal": "L3 数量信号层",
}
LAYER_EMOJI = {"data": "🛰️", "methodology": "🧠", "quant_signal": "🔔"}
STATUS = {"VERIFIED", "REJECTED", "CANDIDATE", "DEGRADING"}

# 默认账本位置：项目根 alpha_ledger/ledger.json
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent.parent / "alpha_ledger" / "ledger.json"


class AlphaLedger:
    """三层 alpha 账本：数据结构 + 归因 + 层间对比 + 报告导出."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else DEFAULT_LEDGER_PATH
        self.meta: dict[str, Any] = {
            "schema_version": "1.0",
            "updated": date.today().isoformat(),
            "description": "三层 Alpha 记账：data(数据/信息源) / methodology(方法论) / quant_signal(数量信号)",
        }
        # 全局 benchmark（三层共用）：等权万得全A PIT 池
        self.benchmarks: dict[str, Any] = {
            "ew_all_a": {
                "name": "EW-全A（等权万得全A PIT 成分池）",
                "total": 0.5294,     # 2021-06 ~ 2026-08 五年
                "ann": 0.0843,
                "note": "所有回测必须先与等权池子对比再下结论（用户铁律）",
            }
        }
        self.layers: dict[Layer, list[dict[str, Any]]] = {
            "data": [],
            "methodology": [],
            "quant_signal": [],
        }

    # ------------------------------------------------------------ IO
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AlphaLedger":
        ledger = cls(path)
        p = ledger.path
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            ledger.meta = raw.get("meta", ledger.meta)
            ledger.benchmarks = raw.get("benchmarks", ledger.benchmarks)
            for layer in ledger.layers:
                ledger.layers[layer] = raw.get("layers", {}).get(layer, [])
        return ledger

    def save(self, path: Optional[Path] = None) -> Path:
        p = Path(path) if path else self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        self.meta["updated"] = date.today().isoformat()
        payload = {
            "meta": self.meta,
            "benchmarks": self.benchmarks,
            "layers": {k: v for k, v in self.layers.items()},
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    # ------------------------------------------------------------ 记账
    def add_entry(
        self,
        layer: Layer,
        name: str,
        status: str,
        total: Optional[float] = None,
        excess: Optional[float] = None,
        mdd: Optional[float] = None,
        benchmark: Optional[str] = None,
        source: str = "",
        method: str = "",
        evidence: str = "",
        lesson: str = "",
        period: str = "2021-06 ~ 2026-08",
        ref: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """记一笔 alpha 资产（VERIFIED / REJECTED / CANDIDATE / DEGRADING）.

        layer: data | methodology | quant_signal
        excess: 相对 benchmark 的超额（小数，如 0.081）
        """
        if status not in STATUS:
            raise ValueError(f"status must be one of {STATUS}, got {status}")
        entry = {
            "name": name,
            "status": status,
            "period": period,
            "total": total,
            "excess": excess,
            "mdd": mdd,
            "benchmark": benchmark,
            "source": source,
            "method": method,
            "evidence": evidence,
            "lesson": lesson,
            "ref": ref,
            "recorded": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        entry.update(extra)
        self.layers[layer].append(entry)
        return entry

    def attribute(
        self,
        layer: Layer,
        name: str,
        delta: float,
        control: str,
        changed: str,
        evidence: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """归因一笔增量 alpha（控制变量法）.

        layer:     归因到的层
        delta:     增量超额（小数）
        control:   控制不变的东西（同一方法论/同一数据/同一组合）
        changed:   换掉的东西（数据源/方法论/信号）
        """
        entry = {
            "name": name,
            "status": "VERIFIED" if delta > 0 else "REJECTED",
            "delta_excess": delta,
            "control": control,
            "changed": changed,
            "evidence": evidence,
            "recorded": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        entry.update(extra)
        self.layers[layer].append(entry)
        return entry

    # ------------------------------------------------------------ 统计
    def summary(self) -> dict[str, Any]:
        """每层：有效/无效条数 + 已归因超额合计（delta 或 excess）. """
        out: dict[str, Any] = {}
        for layer, entries in self.layers.items():
            verified = [e for e in entries if e.get("status") == "VERIFIED"]
            rejected = [e for e in entries if e.get("status") == "REJECTED"]
            total_delta = 0.0
            for e in entries:
                v = e.get("delta_excess") or e.get("excess")
                if isinstance(v, (int, float)) and e.get("status") == "VERIFIED":
                    total_delta += v
            out[layer] = {
                "name": LAYER_NAMES[layer],
                "n_entries": len(entries),
                "n_verified": len(verified),
                "n_rejected": len(rejected),
                "sum_verified_excess": round(total_delta, 4),
            }
        return out

    def compare(self) -> list[dict[str, Any]]:
        """层间对比：每层有效资产清单（供报告用）. """
        rows: list[dict[str, Any]] = []
        for layer in ["data", "methodology", "quant_signal"]:
            for e in self.layers[layer]:
                if e.get("status") == "VERIFIED":
                    rows.append(
                        {
                            "layer": layer,
                            "layer_name": LAYER_NAMES[layer],
                            "name": e.get("name", ""),
                            "excess": e.get("delta_excess") or e.get("excess"),
                            "mdd": e.get("mdd"),
                            "evidence": e.get("evidence", ""),
                        }
                    )
        rows.sort(key=lambda r: r["layer"])
        return rows

    # ------------------------------------------------------------ 报告
    def build_report(self) -> str:
        """生成三层 alpha 对比 HTML（自包含，无外部依赖）. """
        s = self.summary()
        comp = self.compare()
        ew = self.benchmarks.get("ew_all_a", {})

        # 每层卡片
        layer_cards = ""
        layer_desc = {
            "data": "接入并鉴别能带来超额收益的数据源/信息源/新 MCP。基准：同一方法论下基线数据源 vs 新数据源。",
            "methodology": "记录方法论并设置 benchmark，持续迭代。基准：F-Score 基线（已证实跑赢全A等权）。",
            "quant_signal": "A股卖出比买入重要：过热/估值/回撤/预期下修等买卖信号。基准：无信号基线 vs 加信号。",
        }
        for layer in ["data", "methodology", "quant_signal"]:
            st = s[layer]
            entries = self.layers[layer]
            rows_html = ""
            for e in sorted(entries, key=lambda x: (x.get("status") != "VERIFIED", x.get("recorded", ""))):
                st_badge = e.get("status", "?")
                color = {"VERIFIED": "#1a7f37", "REJECTED": "#cf222e", "CANDIDATE": "#9a6700", "DEGRADING": "#8250df"}.get(st_badge, "#57606a")
                excess = e.get("delta_excess") or e.get("excess")
                excess_txt = f"{excess:+.1%}" if isinstance(excess, (int, float)) else "—"
                mdd = e.get("mdd")
                mdd_txt = f"{mdd:.1%}" if isinstance(mdd, (int, float)) else "—"
                total = e.get("total")
                total_txt = f"{total:+.1%}" if isinstance(total, (int, float)) else "—"
                rows_html += f"""
                <tr>
                  <td><span style="color:{color};font-weight:600">{st_badge}</span></td>
                  <td style="font-weight:600">{e.get('name','')}</td>
                  <td>{excess_txt}</td>
                  <td>{total_txt}</td>
                  <td>{mdd_txt}</td>
                  <td style="color:#57606a;font-size:12px">{e.get('evidence','')}</td>
                </tr>"""
            layer_cards += f"""
            <div style="background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:18px 20px;margin-bottom:16px">
              <div style="font-size:16px;font-weight:700;color:#1f2328">{LAYER_EMOJI[layer]} {LAYER_NAMES[layer]}
                <span style="float:right;font-size:13px;color:#57606a">{st['n_verified']} 有效 / {st['n_rejected']} 无效 · 已归因超额 {st['sum_verified_excess']:+.1%}</span>
              </div>
              <div style="color:#57606a;font-size:13px;margin:6px 0 10px">{layer_desc[layer]}</div>
              <table style="width:100%;border-collapse:collapse;font-size:13px">
                <thead><tr style="color:#57606a;text-align:left;border-bottom:1px solid #d8dee4">
                  <th style="padding:6px">结论</th><th>资产</th><th>超额/增量</th><th>总收益</th><th>MDD</th><th>证据</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>"""

        comp_rows = ""
        for r in comp:
            exc = r.get("excess")
            exc_txt = f"{exc:+.1%}" if isinstance(exc, (int, float)) else "—"
            comp_rows += f"""
            <tr>
              <td>{r['layer_name']}</td>
              <td style="font-weight:600">{r['name']}</td>
              <td style="color:#1a7f37;font-weight:600">{exc_txt}</td>
              <td style="color:#57606a;font-size:12px">{r.get('evidence','')}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三层 Alpha 账本对比</title></head>
<body style="margin:0;background:#f6f8fa;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#1f2328">
<div style="max-width:1080px;margin:0 auto;padding:28px 20px">
  <h1 style="font-size:22px;margin:0 0 4px">🛰️ 三层 Alpha 账本 — 对比总览</h1>
  <div style="color:#57606a;font-size:13px">更新：{self.meta.get('updated','')} · schema v{self.meta.get('schema_version','')} ·
    全局基准：<b>{ew.get('name','EW-全A')}</b>（5年 {ew.get('total',0):+.1%}）</div>

  <div style="margin:16px 0;padding:12px 16px;background:#fff8e6;border:1px solid #d4a72c;border-radius:8px;font-size:13px;color:#7a5c00">
    <b>铁律</b>：① 每笔 alpha 只记一层 ② 先与 EW-全A 对比再下结论 ③ 无效实验也要记账，防止重复踩坑
  </div>

  <h2 style="font-size:17px;margin:24px 0 12px">📊 各层有效 alpha 对比</h2>
  <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #d0d7de;border-radius:10px;overflow:hidden;font-size:13px">
    <thead><tr style="background:#f0f3f6;color:#57606a;text-align:left">
      <th style="padding:10px 12px">归因层</th><th>Alpha 资产</th><th>超额/增量</th><th>证据</th>
    </tr></thead>
    <tbody>{comp_rows}</tbody>
  </table>

  <h2 style="font-size:17px;margin:24px 0 12px">🗂️ 三层明细账</h2>
  {layer_cards}

  <div style="color:#8c959f;font-size:12px;margin-top:20px;border-top:1px solid #d8dee4;padding-top:10px">
    归因协议：换数据源→L1 数据层；换决策框架→L2 方法论层；换买卖信号→L3 数量信号层。详见 docs/ALPHA_LAYERS.md
  </div>
</div>
</body></html>"""
        return html

    def export_report(self, out_path: Optional[Path] = None) -> Path:
        p = Path(out_path) if out_path else self.path.parent / "alpha_ledger_report.html"
        p.write_text(self.build_report(), encoding="utf-8")
        return p


# ------------------------------------------------------------ 便捷函数
def quick_attribute_example() -> None:
    """控制变量归因示例：C-Score vs F-Score（同一矩阵构造，仅换数据源）. """
    ledger = AlphaLedger()
    ledger.attribute(
        layer="data",
        name="一致预期 PIT 数据（con_forecast_stk）",
        delta=0.181,
        control="同一 C-Score 矩阵构造",
        changed="财报数据 → 一致预期数据",
        evidence="C-Score +30.7% vs F-Score +12.6%，增量 +18.1pp（5年，超额均相对EW-全A）",
    )
    ledger.save(Path(os.devnull))  # dry-run: 不落盘


if __name__ == "__main__":
    quick_attribute_example()
    print("AlphaLedger OK")
