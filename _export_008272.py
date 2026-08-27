# -*- coding: utf-8 -*-
"""生成 008272 大成优势企业C (刘旭) 持仓导出 Excel"""
import json, os
import pandas as pd

BASE = r"C:\Users\xfugm\.workbuddy\workspace\files\91232\6078897d-8e67-4781-8f33-7be6ca03bd08"

def load(fn):
    with open(os.path.join(BASE, fn), "r", encoding="utf-8") as f:
        return json.load(f)

q2 = load("_fund_008272_holdings_2026Q2.json")
ar = load("_fund_008272_holdings_2025AR.json")

def to_df(d):
    df = pd.DataFrame(d["holdings"])
    # 市场归属
    def mkt(c):
        if c.endswith(".HK"): return "港股"
        if c.endswith(".BJ"): return "北交所"
        return "A股"
    df["market"] = df["code"].apply(mkt)
    df["pct_nav"] = pd.to_numeric(df["pct_nav"], errors="coerce")
    df["market_value"] = pd.to_numeric(df["market_value"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df = df.sort_values("pct_nav", ascending=False, na_position="last")
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    return df

df_q2 = to_df(q2)
df_ar = to_df(ar)

# 输出列
cols = ["code", "name", "market", "market_value", "quantity", "pct_nav", "pct_stock", "citics_l1", "shenwan_l1"]
col_names = ["代码", "名称", "市场", "市值(元)", "持股数量", "占净值比%", "占股票市值比%", "中信一级", "申万一级"]

def fmt(df):
    out = df[cols].copy()
    out.columns = col_names
    out["市值(万元)"] = (out["市值(元)"] / 1e4).round(2)
    out = out.drop(columns=["市值(元)"])
    out["占净值比%"] = out["占净值比%"].round(2)
    out["占股票市值比%"] = out["占股票市值比%"].round(2)
    return out

sheet_q2 = fmt(df_q2)
sheet_ar = fmt(df_ar)

# 行业汇总（2025年报，中信一级，按占净值比）
ind = df_ar.dropna(subset=["citics_l1"]).groupby("citics_l1").agg(
    stock_count=("name", "count"),
    mkt_value=("market_value", "sum"),
    pct_nav=("pct_nav", "sum")
).sort_values("pct_nav", ascending=False).reset_index()
ind.columns = ["中信一级行业", "股票数", "市值合计(元)", "占净值比%"]
ind["市值合计(万元)"] = (ind["市值合计(元)"] / 1e4).round(2)
ind["占净值比%"] = ind["占净值比%"].round(2)
ind = ind.drop(columns=["市值合计(元)"])

# 市场分布
mkt_dist = df_ar.groupby("market").agg(
    stock_count=("name", "count"),
    mkt_value=("market_value", "sum"),
    pct_nav=("pct_nav", "sum")
).reset_index()
mkt_dist.columns = ["市场", "股票数", "市值合计(元)", "占净值比%"]
mkt_dist["市值合计(万元)"] = (mkt_dist["市值合计(元)"] / 1e4).round(2)
mkt_dist["占净值比%"] = mkt_dist["占净值比%"].round(2)
mkt_dist = mkt_dist.drop(columns=["市值合计(元)"])

# 集中度
tot_nav_pct_ar = df_ar["pct_nav"].sum()
tot_nav_pct_q2 = df_q2["pct_nav"].sum()
summary = pd.DataFrame({
    "指标": ["报告期(2025年报)持仓股票数", "2025年报披露占净值比合计%", "2025年报股票市值合计(元)",
             "报告期(2026Q2)披露前十大占净值比合计%", "基金净资产(2026Q2, 亿元)", "股票仓位(2026Q2)", "港股仓位(2026Q2)"],
    "数值": [len(df_ar), round(tot_nav_pct_ar, 2), round(df_ar["market_value"].sum(), 0),
             round(tot_nav_pct_q2, 2), 21.58, "87%", "21.37%"]
})

# 与2026Q2前十大重合对比
q2_codes = set(df_q2["code"])
ar_top = set(df_ar.head(10)["code"])
overlap = q2_codes & ar_top
summary2 = pd.DataFrame({
    "对比项": ["2025年报前十大与2026Q2前十大重合数量", "2026Q2新进前十大(相对2025年报前十大)"],
    "说明": [f"{len(overlap)} 只",
            "、".join(df_q2[~df_q2['code'].isin(ar_top)]['name'].tolist()) or "无"]
})

out_path = os.path.join(BASE, "大成优势企业C_008272_刘旭持仓.xlsx")
with pd.ExcelWriter(out_path, engine="openpyxl") as w:
    summary.to_excel(w, sheet_name="概览", index=False)
    sheet_ar.to_excel(w, sheet_name="2025年报全量持仓", index=False)
    sheet_q2.to_excel(w, sheet_name="2026Q2前十大", index=False)
    ind.to_excel(w, sheet_name="行业分布(年报)", index=False)
    mkt_dist.to_excel(w, sheet_name="市场分布(年报)", index=False)
    summary2.to_excel(w, sheet_name="持仓变化对比", index=False)

print("OK ->", out_path)
print("2025年报股票数:", len(df_ar), "| 占净值比合计:", round(tot_nav_pct_ar, 2), "%")
print("2026Q2前十大占净值比合计:", round(tot_nav_pct_q2, 2), "%")
print("\n=== 行业分布(中信一级, 2025年报) ===")
print(ind.to_string(index=False))
print("\n=== 市场分布 ===")
print(mkt_dist.to_string(index=False))
