# -*- coding: utf-8 -*-
"""记分卡 + 组合回测 + 信号级验证 -> _bt_style_rotation_report.html

执行规则: 周五 T 收盘后打分 -> 下周五 T+5 收盘调仓 (weight = f(signal).shift(2) 于周收益)
组合: 50% Growth/Value sleeve (159915 vs 512890) + 50% Small/Large sleeve (512100 vs 510050)
ETF 上市前用对应指数替代 (日收益拼接)。基准: 中证800。
"""
import os
import numpy as np
import pandas as pd

CACHE = r"D:\workspace\ai_fund_framework\_sr_cache"
SIG = os.path.join(CACHE, "_sr_signals.csv")
OUT_HTML = r"D:\workspace\ai_fund_framework\_bt_style_rotation_report.html"

# ---------------- price / return construction ----------------
def load_daily(path):
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df["close"]

def load_idx(slug):
    return load_daily(os.path.join(CACHE, f"{slug}.csv"))

ETF_INFO = {
    # slug -> (etf_csv, index_csv, etf_inception)
    "growth": ("etf_chinext", "idx_chinext", "2011-12-09"),   # 159915 vs 399006
    "value": ("etf_divlowvol", "idx_divlowvol", "2019-01-18"), # 512890 vs H30269
    "small": ("etf_csi1000", "idx_csi1000", "2016-11-04"),     # 512100 vs 000852
    "large": ("etf_sse50", None, None),                        # 510050 全期
}

def daily_returns():
    out = {}
    for k, (etf, idx, inc) in ETF_INFO.items():
        r_etf = load_daily(os.path.join(CACHE, f"{etf}.csv")).pct_change()
        if idx is not None:
            r_idx = load_idx(idx).pct_change()
            inc = pd.Timestamp(inc)
            r = pd.concat([r_idx[r_idx.index < inc], r_etf[r_etf.index >= inc]])
        else:
            r = r_etf
        out[k] = r
    out["bench"] = load_idx("idx_csi800").pct_change()
    return out

def weekly_returns(r, fri_index):
    """日收益 -> 周收益(按每周最后交易日分组复利), 对齐 fri_index"""
    df = pd.DataFrame({"r": r})
    iso = df.index.isocalendar()
    key = pd.MultiIndex.from_arrays([iso.year.astype(int), iso.week.astype(int)])
    df["key"] = key
    wk = df.groupby("key")["r"].apply(lambda x: (1 + x).prod() - 1)
    # 组最后日期
    last_day = df.groupby("key").apply(lambda x: x.index.max(), include_groups=False)
    wk.index = last_day.values
    wk = wk[wk.index.isin(fri_index)]
    return wk.reindex(fri_index)

# ---------------- scorecard ----------------
def vote(z, pos_thr, neg_thr):
    return np.where(z > pos_thr, 1.0, np.where(z < neg_thr, -1.0, 0.0))

def scores(sig):
    """返回 value sleeve / size sleeve 的离散与连续得分 (Value/Small 方向)"""
    # 离散投票版
    v_odds = vote(sig["odds_val"].values, 1.0, -1.0)
    v_trend = vote(sig["trend_val"].values, 0.5, -0.5)
    v_crowd = vote(sig["crowd_val"].values, -1.0, 1.0)   # 拥挤极端高->-1, 极端低->+1
    v_wr = sig["winrate_val"].values
    s_val_disc = v_odds + v_trend + v_crowd + v_wr

    s_odds = vote(sig["odds_size"].values, 1.0, -1.0)
    s_trend = vote(sig["trend_size"].values, 0.5, -0.5)
    s_crowd = vote(sig["crowd_size"].values, -1.0, 1.0)
    s_size_disc = s_odds + s_trend + s_crowd

    # 连续版
    s_val_cont = (sig["odds_val"].clip(-2, 2) + sig["trend_val"].clip(-2, 2)
                  - sig["crowd_val"].clip(-2, 2) + sig["winrate_val"])
    s_size_cont = (sig["odds_size"].clip(-2, 2) + sig["trend_size"].clip(-2, 2)
                   - sig["crowd_size"].clip(-2, 2))
    return s_val_disc, s_size_disc, s_val_cont.values, s_size_cont.values

def weight_from_score(s):
    """s>0 -> 全仓 style A(Value/Small)=1; s<0 -> 0; s=0 -> 0.5"""
    return np.where(s > 0, 1.0, np.where(s < 0, 0.0, 0.5))

# ---------------- backtest engine ----------------
def run_portfolio(sig, wr, scores_pair, fee=0.0):
    """wr: dict of weekly return series aligned to sig dates.
    scores_pair: (s_val, s_size) already lagged appropriately"""
    s_val, s_size = scores_pair
    w_val = pd.Series(weight_from_score(s_val), index=sig["date"])   # value sleeve: 1=value
    w_size = pd.Series(weight_from_score(s_size), index=sig["date"]) # size sleeve: 1=small
    # T 打分 -> T+5 执行 -> 承载下一段周收益: shift(2)
    w_val = w_val.shift(2)
    w_size = w_size.shift(2)

    rG, rV = wr["growth"], wr["value"]
    rS, rL = wr["small"], wr["large"]
    rB = wr["bench"]

    sleeve_val = w_val * rV + (1 - w_val) * rG
    sleeve_size = w_size * rS + (1 - w_size) * rL
    port = 0.5 * sleeve_val + 0.5 * sleeve_size

    # 换手: 资产层面单边换手 = sum|dw|/2, 两 sleeve 各 50% 资金
    dw_val = w_val.diff().abs() * 0.5
    dw_size = w_size.diff().abs() * 0.5
    turn = dw_val + dw_size  # 单边(以组合 NAV 计)
    cost = (dw_val + dw_size) * 2 * fee  # 双边费用
    port = port - cost.fillna(0)
    port = port.dropna()
    rB_al = rB.reindex(port.index)
    excess = port - rB_al
    return port, rB_al, excess, w_val, w_size, turn

def metrics(port, bench, excess, turn):
    n = len(port)
    ann = (1 + port).prod() ** (52 / n) - 1
    ann_b = (1 + bench).prod() ** (52 / n) - 1
    ex_ann = (1 + excess).prod() ** (52 / n) - 1
    te = excess.std() * np.sqrt(52)
    ir = ex_ann / te if te > 0 else np.nan
    nav_e = (1 + excess).cumprod()
    mdd_e = (nav_e / nav_e.cummax() - 1).min()
    nav = (1 + port).cumprod()
    mdd = (nav / nav.cummax() - 1).min()
    turn_ann = turn.mean() * 52
    hit = (excess > 0).mean()
    return dict(ann=ann, ann_b=ann_b, ex_ann=ex_ann, te=te, ir=ir,
                mdd=mdd, mdd_e=mdd_e, turn=turn_ann, hit=hit, n=n)

def yearly_table(port, bench, excess):
    df = pd.DataFrame({"port": port, "bench": bench, "ex": excess})
    out = []
    for y, g in df.groupby(df.index.year):
        p = (1 + g["port"]).prod() - 1
        b = (1 + g["bench"]).prod() - 1
        e = (1 + g["ex"]).prod() - 1
        out.append({"year": y, "port": p, "bench": b, "excess": e, "hit": (g["ex"] > 0).mean()})
    return pd.DataFrame(out)

# ---------------- main ----------------
def main():
    sig = pd.read_csv(SIG, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    # 回测起点 = 全部信号齐备（trend 的 ICIR 52周 + 6y z warm-up 最晚, 2017-09）
    need = ["odds_val", "odds_size", "trend_val", "trend_size", "crowd_val", "crowd_size", "winrate_val"]
    first_ok = sig.dropna(subset=need)["date"].min()
    sig = sig[sig["date"] >= first_ok].reset_index(drop=True)
    print(f"backtest window: {first_ok.date()} -> {sig['date'].max().date()}  ({len(sig)} weeks)")
    fri_index = pd.DatetimeIndex(sig["date"])
    dr = daily_returns()
    wr = {k: weekly_returns(v, fri_index) for k, v in dr.items()}

    s_val_d, s_size_d, s_val_c, s_size_c = scores(sig)

    results = {}
    for name, sv, ss, fee in [
        ("disc_0bp", s_val_d, s_size_d, 0.0),
        ("disc_5bp", s_val_d, s_size_d, 0.0005),
        ("disc_10bp", s_val_d, s_size_d, 0.001),
        ("cont_0bp", s_val_c, s_size_c, 0.0),
        ("cont_5bp", s_val_c, s_size_c, 0.0005),
        ("cont_10bp", s_val_c, s_size_c, 0.001),
    ]:
        port, bench, excess, wv, ws, turn = run_portfolio(sig, wr, (sv, ss), fee=fee)
        m = metrics(port, bench, excess, turn)
        yt = yearly_table(port, bench, excess)
        results[name] = dict(m=m, yt=yt, port=port, bench=bench, excess=excess,
                             w_val=wv, w_size=ws, turn=turn)
        print(f"{name}: ann={m['ann']:.2%} bench={m['ann_b']:.2%} ex={m['ex_ann']:.2%} "
              f"TE={m['te']:.2%} IR={m['ir']:.2f} turn={m['turn']:.0%} hit_w={m['hit']:.0%}")

    # save intermediate for report
    import pickle
    with open(os.path.join(CACHE, "_sr_bt_results.pkl"), "wb") as f:
        pickle.dump(results, f)
    print("saved results pickle")

if __name__ == "__main__":
    main()
