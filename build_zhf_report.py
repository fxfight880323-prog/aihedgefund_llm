# -*- coding: utf-8 -*-
"""生成《章宏帆轮动策略 · 全A满仓选股报告》PDF。

结构（A4 纵向，8 页）：
  P1 封面（标题 + KPI 卡片 + 日期/数据源）
  P2 整体框架图（docs/framework_architecture.png 嵌入）
  P3 执行流程与方法（策略管线 + universe 说明）
  P4 选股结果概览（方向汇总 / 类配比 / 统计）
  P5-7 完整持仓名单（47 只，分 3 页表格）
  P8 附录与免责声明

Run:
    D:\\Python\\python.exe build_zhf_report.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

# ---------------------------------------------------------------- 字体
_FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
fm.fontManager.addfont(_FONT_PATH)
_FONT = fm.FontProperties(fname=_FONT_PATH)
plt.rcParams["font.family"] = _FONT.get_name()
plt.rcParams["axes.unicode_minus"] = False

A4_W, A4_H = 8.27, 11.69

# 配色（浅色专业风）
C_NAVY = "#1F3A5F"
C_BLUE = "#1565C0"
C_LIGHT = "#E3F2FD"
C_ACCENT = "#C2185B"
C_GRAY = "#607D8B"
C_LINE = "#B0BEC5"
C_ROW = "#F5F7FA"
C_ROW2 = "#FFFFFF"
C_GREEN = "#2E7D32"
C_RED = "#C62828"
C_GOLD = "#F9A825"
C_ORANGE = "#EF6C00"
C_PURPLE = "#5E35B1"

RESULT = json.load(open("zhf_allA_selection_result.json", encoding="utf-8"))
ARCH_PNG = "docs/framework_architecture.png"
OUT_PDF = "zhf_allA_selection_report.pdf"

CLASS_CN = {"A": "A 景气成长", "B": "B 周期成长", "C": "C 新兴成长", "OFF": "OFF 自下而上"}
CLASS_COLOR = {"A": "#E8F5E9", "B": "#FFF8E1", "C": "#FCE4EC", "OFF": "#EEEEEE"}


def new_page() -> tuple:
    fig, ax = plt.subplots(figsize=(A4_W, A4_H))
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 141)
    ax.axis("off")
    return fig, ax


def rbox(ax, x, y, w, h, fc, ec, lw=1.2, r=1.5):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, zorder=2)
    ax.add_patch(p)


def page_footer(ax, page_no, total):
    ax.text(50, 1.6, f"— {page_no} / {total} —", ha="center", va="center",
            fontsize=7.5, color=C_GRAY)
    ax.text(98.5, 1.2, "zhf_allA_selection · 2026-08-17", ha="right", va="center",
            fontsize=6.5, color="#90A4AE")


def draw_table(ax, x0, y_top, x1, headers, rows, col_aligns=None,
               header_h=3.2, row_h=2.9, fs=7.2, header_fs=7.6,
               row_colors=None, header_fc="#ECEFF1"):
    """手绘表格（向下生长）。y_top 是表格顶部 y 坐标；表头在顶部，
    数据行向下排列。返回表格底部 y 坐标。
    """
    n_cols = len(headers)
    n_rows = len(rows)
    total_h = header_h + n_rows * row_h

    # 表头（顶部）
    head_top = y_top
    head_bot = y_top - header_h
    rbox(ax, x0, head_bot, x1 - x0, header_h, header_fc, C_LINE, lw=0.8, r=0.6)
    ax.text(x0 + 0.6, head_bot + header_h / 2, headers[0], ha="left", va="center",
            fontsize=header_fs, fontweight="bold", color=C_NAVY)
    for c in range(1, n_cols):
        ax.text(x0 + 0.6 + (x1 - x0) * c / n_cols, head_bot + header_h / 2,
                headers[c], ha="left", va="center", fontsize=header_fs,
                fontweight="bold", color=C_NAVY)

    # 数据行（向下）
    yy = head_bot
    for i, row in enumerate(rows):
        row_bot = yy - row_h
        fc = (row_colors[i] if row_colors and row_colors[i] else
              (C_ROW if i % 2 == 0 else C_ROW2))
        rbox(ax, x0, row_bot, x1 - x0, row_h, fc, C_LINE, lw=0.4, r=0.3)
        for c in range(n_cols):
            txt = str(row[c])
            ha = "left"
            x_txt = x0 + 0.6 + (x1 - x0) * c / n_cols
            if col_aligns and col_aligns[c] == "center":
                x_txt = x0 + (x1 - x0) * (c + 0.5) / n_cols
            ax.text(x_txt, row_bot + row_h / 2, txt, ha=ha, va="center",
                    fontsize=fs, color="#212121")
        yy = row_bot
    return yy  # bottom y


def kpi_card(ax, x, y, w, h, value, label, fc, ec):
    rbox(ax, x, y, w, h, fc, ec, lw=1.4, r=1.8)
    ax.text(x + w / 2, y + h * 0.60, value, ha="center", va="center",
            fontsize=15, fontweight="bold", color=C_NAVY)
    ax.text(x + w / 2, y + h * 0.24, label, ha="center", va="center",
            fontsize=7.6, color=C_GRAY)


# ================================================================ P1 封面
def page_cover(pdf):
    fig, ax = new_page()
    # 顶部装饰条
    rbox(ax, 0, 138, 100, 3, C_NAVY, C_NAVY, r=0)
    rbox(ax, 0, 0, 100, 3, C_NAVY, C_NAVY, r=0)

    ax.text(50, 118, "章宏帆轮动策略", ha="center", va="center",
            fontsize=26, fontweight="bold", color=C_NAVY)
    ax.text(50, 111, "全A满仓选股报告", ha="center", va="center",
            fontsize=20, fontweight="bold", color=C_NAVY)
    ax.text(50, 105.5, "有锐度的均衡 · rotation_growth  |  L1 分类 → L2 环节稀缺度 → G5 泡沫检验 → L4 组合构造",
            ha="center", va="center", fontsize=8.5, color=C_GRAY)
    ax.text(50, 101.5, "基于 ai_fund_framework 框架 · wind 全A universe · 单策略全仓执行",
            ha="center", va="center", fontsize=8.5, color=C_BLUE)

    # KPI 卡片 3x2
    cards = [
        ("98", "全A候选 (H1营收YoY>30% 且 Q1>20%)", C_LIGHT, C_BLUE),
        ("60", "营收加速中 (H1 YoY > Q1 YoY)", "#E8F5E9", C_GREEN),
        ("98", "生成信号 (46 正信念 + 28 弃权 + 24 负/零)", "#FFF8E1", C_GOLD),
        ("47", "入选持仓 (满仓组合)", "#FCE4EC", C_ACCENT),
        ("90.6%", "总仓位 (单票≤5% 上限约束下)", "#E3F2FD", C_BLUE),
        ("6+1", "主题方向 (光模块/PCB/算力/存储/半导体…)", "#F3E5F5", C_PURPLE),
    ]
    cw, ch, gap = 30.5, 10.5, 1.6
    for i, (v, lbl, fc, ec) in enumerate(cards):
        x = 3.2 + (i % 3) * (cw + gap)
        y = 90 - (i // 3) * (ch + gap)
        kpi_card(ax, x, y, cw, ch, v, lbl, fc, ec)

    # 执行信息块
    rbox(ax, 3.2, 62, 93.6, 16, "#F5F7FA", C_LINE, lw=1.0, r=1.5)
    info_lines = [
        ("执行日期", "2026-08-17（交易日收盘后截面）"),
        ("数据源", "东方财富·妙想选股器 — 全部A股（沪深京），最新报告期 2026 半年报"),
        ("基金授权书", "config/funds/rotation_full.yaml — 满仓版（gross_target=1.0）"),
        ("策略/模型", "rotation_growth（章宏帆）· 权重 1.0 · 唯一 alpha 模型"),
        ("基准", "中证全指 000985.SH · 组合构造器 balanced_sharpness"),
    ]
    yy = 75.8
    for k, v in info_lines:
        ax.text(5.0, yy, k, ha="left", va="center", fontsize=8.2,
                fontweight="bold", color=C_NAVY)
        ax.text(24, yy, v, ha="left", va="center", fontsize=8.2, color="#333333")
        yy -= 2.6

    ax.text(50, 52, "关键约束", ha="center", va="center", fontsize=10,
            fontweight="bold", color=C_NAVY)
    constr = [
        "A≤60% / B≤35% / C≤5% 类配比上限（scale_to_target 后按比例放大）",
        "单票权重上限 5%（47 只持仓中 27 只触及上限）",
        "方向阶梯权重：top 22% → tail 12%，最多 6 个方向 + 自下而上 sleeve 5%",
        "B 类 PE>20 强制轮出（负信念）；G5 ΔPE 主导 → 信念减半",
    ]
    yy = 48.5
    for c_line in constr:
        ax.text(6, yy, "•  " + c_line, ha="left", va="center", fontsize=8, color="#333")
        yy -= 2.6

    ax.text(50, 8, "仅供研究参考，不构成投资建议 · 数据来自第三方行情/财务接口，可能存在滞后或误差",
            ha="center", va="center", fontsize=7, color=C_GRAY)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ P2 框架图
def page_architecture(pdf, page_no, total):
    fig, ax = new_page()
    ax.text(50, 137.5, "一、ai_fund_framework 整体框架", ha="center", va="center",
            fontsize=14, fontweight="bold", color=C_NAVY)
    ax.text(50, 133.5, "LangGraph 编排 · 数据 → 分析师 → 组合 → 风控 → 执行 → 账本 · 五接口可插拔",
            ha="center", va="center", fontsize=8, color=C_GRAY)

    # 用 PIL 读取 PNG 以保持透明通道，按原图比例居中嵌入
    from PIL import Image
    import numpy as np

    img = Image.open(ARCH_PNG)
    arr = np.array(img)
    H, W = arr.shape[:2]
    ar = W / H

    # 可用区域：宽 96，高 ~100（标题与页脚之间）
    max_w, max_h = 96.0, 100.0
    if max_w / ar <= max_h:
        disp_w = max_w
        disp_h = max_w / ar
    else:
        disp_h = max_h
        disp_w = max_h * ar
    x0 = (100 - disp_w) / 2
    y0 = 30 + (95 - disp_h) / 2  # 在 y=30~125 之间居中

    ax.imshow(arr, extent=[x0, x0 + disp_w, y0, y0 + disp_h], zorder=1)
    # 细边框，无填充，避免遮挡图片
    p = FancyBboxPatch((x0 - 0.5, y0 - 0.5), disp_w + 1, disp_h + 1,
                       boxstyle="round,pad=0,rounding_size=1.0",
                       fc="none", ec=C_LINE, lw=1.0, zorder=2)
    ax.add_patch(p)
    page_footer(ax, page_no, total)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ P3 执行流程
def page_method(pdf, page_no, total):
    fig, ax = new_page()
    ax.text(50, 137.5, "二、执行流程与方法", ha="center", va="center",
            fontsize=14, fontweight="bold", color=C_NAVY)
    ax.text(50, 133.5, "严格复用框架既有路径：选股器截面 → DataClient 协议适配 → LangGraph fund cycle（仅 rotation_growth 一个模型）",
            ha="center", va="center", fontsize=8, color=C_GRAY)

    steps = [
        ("① 全A Universe 定义", "wind 全A 等价：全部 A 股（沪深京）为原始空间；"
         "以妙想选股器截面提取「2026 半年报营收 YoY>30% 且 2026 一季报营收 YoY>20%」的成长候选 98 只。"
         "（注：选股器为该条件的真实筛选结果，宽松条件 >20% 时返回 176 只，未见截断）", C_BLUE),
        ("② 截面数据本地化", "每只候选携带：四期营收（26H1/25H1/26Q1/25Q1）、两期毛利率、PE-TTM、ROE、"
         "东财行业、所属概念、最新价。包装为 ScreenerAdapter（DataClient 协议），"
         "后续零额外查询，全程本地计算。", C_GREEN),
        ("③ L1 资产分类", "营收增速 + 加速度 + 毛利率拐点 + ROE 分四类："
         "A 景气成长（≥50% 且加速）/ B 周期成长（毛利回升、增速<50%）/ C 新兴成长（≥150% 且毛利<15%）/ "
         "OFF 自下而上（ROE≥15% 且毛利≥30% 非主题）。不满足 → abstain。", C_ACCENT),
        ("④ L2 环节稀缺度", "主题关键词命中 7 个环节表（光模块/PCB/CPU+光芯片/国产算力/半导体设备/半导体材料/存储），"
         "按 S1 供给刚性…S5 成本传导五维 0-2 分加总（最高 10 分），决定方向权重与参与度。", C_ORANGE),
        ("⑤ G5 泡沫检验 + 类则估值", "涨幅分解 ΔEPS vs ΔPE：ΔPE 主导 → 信念减半。"
         "A 类用增长×毛利 3 年空间代理；B 类 PE>20 强制负信念轮出；C 类小仓位（≤0.30）；OFF 类 ≤0.40。", C_PURPLE),
        ("⑥ L4 组合构造（满仓）", "balanced_sharpness：方向按稀缺度单调权重（top 22%→tail 12%，≤6 方向）、"
         "每方向保留信念最高 6 只、类配比上限、单票≤5%、scale_to_target 放大至满仓目标 100%。", C_NAVY),
    ]
    yy = 126
    for title, desc, color in steps:
        rbox(ax, 3.2, yy - 3.6, 93.6, 13.2, "#FFFFFF", C_LINE, lw=0.9, r=1.2)
        rbox(ax, 3.2, yy - 3.6, 1.2, 13.2, color, color, r=0.6)
        ax.text(5.8, yy + 3.0, title, ha="left", va="center", fontsize=9.5,
                fontweight="bold", color=color)
        ax.text(5.8, yy - 0.6, desc, ha="left", va="center", fontsize=7.8,
                color="#333333", wrap=True)
        yy -= 14.6

    page_footer(ax, page_no, total)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ P4 结果概览
def page_overview(pdf, page_no, total):
    fig, ax = new_page()
    ax.text(50, 137.5, "三、选股结果概览（2026-08-17）", ha="center", va="center",
            fontsize=14, fontweight="bold", color=C_NAVY)

    # ---- 左：方向汇总 ----
    ax.text(25, 130, "主题方向仓位（按稀缺度排名）", ha="center", va="center",
            fontsize=9.5, fontweight="bold", color=C_NAVY)
    link_rows = []
    for link, v in sorted(RESULT["link_summary"].items(), key=lambda kv: -kv[1]["gross"]):
        link_rows.append([link, f"{v['names']} 只", f"{v['gross']:.1%}",
                          f"{v['avg_value']:+.2f}"])
    draw_table(ax, 3.2, 128, 50, ["方向", "只数", "仓位", "均信念"],
               link_rows, col_aligns=["left", "center", "center", "center"],
               header_h=3.0, row_h=3.0, fs=7.4)
    ax.text(26.6, 102.5, "合计 6 个主题方向 + 自下而上 sleeve", ha="center", va="center",
            fontsize=7.2, color=C_GRAY)

    # ---- 右：类配比 ----
    ax.text(75, 130, "资产类别配比", ha="center", va="center",
            fontsize=9.5, fontweight="bold", color=C_NAVY)
    cls_rows = []
    cls_map = RESULT["class_mix"]
    total_w = sum(cls_map.values())
    for cls in ["A", "B", "C", "OFF"]:
        w = cls_map.get(cls, 0.0)
        cls_rows.append([CLASS_CN.get(cls, cls), f"{w:.1%}",
                         f"{w / total_w:.0%}"])
    draw_table(ax, 53, 128, 96.8, ["类别", "组合权重", "占组合比"],
               cls_rows, col_aligns=["left", "center", "center"],
               header_h=3.0, row_h=3.0, fs=7.4)
    ax.text(74.9, 111.5, "注：scale_to_target 放大后 A 类权重超过 60% 名义上限", ha="center",
            va="center", fontsize=6.8, color=C_RED)

    # ---- 统计条 ----
    ax.text(50, 105, "组合统计", ha="center", va="center", fontsize=10,
            fontweight="bold", color=C_NAVY)
    stats = [
        ("Universe", f"{RESULT['universe_size']} 只", C_BLUE),
        ("信号", f"{RESULT['signal_count']} 条（弃权 {RESULT['abstain_count']}）", C_GOLD),
        ("持仓", f"{RESULT['position_count']} 只", C_ACCENT),
        ("总仓位", f"{RESULT['gross']:.1%}", C_GREEN),
        ("订单", f"{RESULT['orders']} 笔", C_ORANGE),
        ("异常", "0 条", C_GRAY),
    ]
    cw, ch, gap = 14.7, 5.2, 1.2
    for i, (k, v, c) in enumerate(stats):
        x = 3.2 + i * (cw + gap)
        y = 97.5
        rbox(ax, x, y, cw, ch, "#F5F7FA", C_LINE, lw=0.8, r=0.8)
        ax.text(x + cw / 2, y + ch * 0.62, v, ha="center", va="center", fontsize=8.0,
                fontweight="bold", color=c)
        ax.text(x + cw / 2, y + ch * 0.24, k, ha="center", va="center", fontsize=6.2,
                color=C_GRAY)

    # ---- 权重前 15 ----
    ax.text(50, 91.5, "权重 Top 15 持仓", ha="center", va="center", fontsize=10,
            fontweight="bold", color=C_NAVY)
    top_rows = []
    for p in RESULT["positions"][:15]:
        top_rows.append([
            p["ticker"], p["name"],
            CLASS_CN.get(p["asset_class"], p["asset_class"]),
            p["link"] or "—",
            f"{p['weight']:.1%}", f"{p['value']:+.2f}",
            f"{p['h1_yoy']:.0%}", f"{p['pe']:.0f}" if p.get("pe") else "—",
        ])
    draw_table(ax, 3.2, 88, 96.8,
               ["代码", "名称", "类别", "方向", "权重", "信念", "H1增速", "PE"],
               top_rows, col_aligns=["left", "left", "center", "left",
                                     "center", "center", "center", "center"],
               header_h=3.0, row_h=2.55, fs=6.9)

    ax.text(50, 5.5, "完整 47 只名单见下页（按权重降序）", ha="center", va="center",
            fontsize=8, color=C_GRAY)
    page_footer(ax, page_no, total)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ P5-7 持仓名单
def page_holdings(pdf, start, end, page_no, total):
    fig, ax = new_page()
    ax.text(50, 137.5, f"四、完整持仓名单（{start + 1}–{end} / {len(RESULT['positions'])}）",
            ha="center", va="center", fontsize=13, fontweight="bold", color=C_NAVY)
    ax.text(50, 133.5, "按权重降序 · 类别：A 景气成长 / B 周期成长 / C 新兴成长 / OFF 自下而上",
            ha="center", va="center", fontsize=8, color=C_GRAY)

    rows = []
    row_colors = []
    for p in RESULT["positions"][start:end]:
        rows.append([
            p["ticker"], p["name"],
            CLASS_CN.get(p["asset_class"], p["asset_class"]),
            p["link"] or "—",
            f"{p['weight']:.2%}",
            f"{p['value']:+.2f}",
            f"{p['h1_yoy']:.0%}",
            f"{p['q1_yoy']:.0%}",
            f"{p['gm_h1']:.0f}%" if p.get("gm_h1") else "—",
            f"{p['pe']:.1f}" if p.get("pe") else "—",
            f"{p['roe']:.1f}%" if p.get("roe") else "—",
            (p.get("industry") or "")[:8],
        ])
        row_colors.append(CLASS_COLOR.get(p["asset_class"]))

    draw_table(ax, 3.2, 128, 96.8,
               ["代码", "名称", "类别", "方向", "权重", "信念",
                "H1增速", "Q1增速", "毛利率", "PE", "ROE", "行业"],
               rows, col_aligns=["left", "left", "center", "left",
                                 "center", "center", "center", "center",
                                 "center", "center", "center", "left"],
               header_h=3.4, row_h=3.7, fs=7.0, header_fs=7.2,
               row_colors=row_colors)

    page_footer(ax, page_no, total)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ P8 附录
def page_appendix(pdf, page_no, total):
    fig, ax = new_page()
    ax.text(50, 137.5, "附录 · 方法与数据说明", ha="center", va="center",
            fontsize=13, fontweight="bold", color=C_NAVY)

    sections = [
        ("数据来源", [
            "全A 截面：东方财富·妙想选股器（mx_stocks_screener），2026-08-17 收盘后查询，"
            "查询条件见封面「数据源」。",
            "行情：最新价 / 市值等为 2026-08-17 收盘截面；财务：2026 半年报 / 一季报已披露数据。",
            "股价信息经 ScreenerAdapter 注入 fund cycle，全程 point-in-time（≤2026-08-17）。",
        ]),
        ("策略语义（忠实于 spec）", [
            "「只执行 zhanghongfan 策略」= rotation_full.yaml 中唯一 alpha 模型 rotation_growth（权重 1.0），"
            "未混入其他模型；组合构造器为配套的 balanced_sharpness（满仓参数）。",
            "L5 AI 周期仪表盘全部为 neutral（默认值，无外部数据源接入）——未触发 A 类减半。",
            "G1 跨市场证伪 / G4 两波状态机为 spec 声明的扩展点，当前实现中为 None（诚实标注）。",
        ]),
        ("已知行为与局限", [
            "scale_to_target 在类配比钳制之后执行，放大后 A 类实际权重 85.4% > 名义上限 60%——"
            "框架当前行为，报告中如实呈现。",
            "单票 5% 上限在放大后生效，导致总仓位 90.6%（<100%），差额留存现金。",
            "渗透率 5% 临界点以营收增速代理；universe 仅为选股器命中条件的高增长子集，"
            "非逐票全市场扫描。",
        ]),
        ("运行信息", [
            f"执行时间：{RESULT.get('run_at', '—')}",
            f"基金授权书：{RESULT.get('mandate', '—')}",
            f"模型：{', '.join(RESULT.get('models', []))}",
            f"异常（errors）：{len(RESULT.get('errors', []))} 条",
        ]),
    ]
    yy = 128
    for title, lines in sections:
        ax.text(4, yy, title, ha="left", va="center", fontsize=10.5,
                fontweight="bold", color=C_NAVY)
        yy -= 3.4
        for ln in lines:
            ax.text(5, yy, "•  " + ln, ha="left", va="center", fontsize=8,
                    color="#333333")
            yy -= 2.9
        yy -= 1.6

    rbox(ax, 3.2, 4.5, 93.6, 8.5, "#F5F7FA", C_LINE, lw=1.0, r=1.0)
    ax.text(50, 8.8, "免责声明", ha="center", va="center", fontsize=9,
            fontweight="bold", color=C_RED)
    ax.text(50, 6.3, "本报告由 ai_fund_framework 自动生成，仅供研究学习使用，不构成任何投资建议。"
            "数据来自第三方接口，可能存在滞后或误差；据此操作风险自负。",
            ha="center", va="center", fontsize=7.4, color="#333333")
    page_footer(ax, page_no, total)
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)


# ================================================================ 主流程
def main():
    n_pos = len(RESULT["positions"])
    per_page = 17
    n_hold_pages = (n_pos + per_page - 1) // per_page
    total_pages = 5 + n_hold_pages  # 封面 + 架构 + 方法 + 概览 + 持仓页 + 附录

    with PdfPages(OUT_PDF) as pdf:
        page_cover(pdf)
        page_architecture(pdf, 2, total_pages)
        page_method(pdf, 3, total_pages)
        page_overview(pdf, 4, total_pages)
        for p_idx in range(n_hold_pages):
            s = p_idx * per_page
            e = min(s + per_page, n_pos)
            page_holdings(pdf, s, e, 5 + p_idx, total_pages)
        page_appendix(pdf, total_pages, total_pages)

    print(f"PDF 已生成: {OUT_PDF}  ({total_pages} 页, {n_pos} 只持仓)")


if __name__ == "__main__":
    main()
