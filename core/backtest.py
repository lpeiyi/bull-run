# -*- coding: utf-8 -*-
"""
回测引擎：用技术指标的信号，历史回测个股/ETF 的收益表现
支持 MACD / KDJ / RSI / BOLL / MA，可调参数，全仓买卖（默认含万分之2.5双向手续费）
"""
import numpy as np
import pandas as pd
from core import indicators

# 各指标的默认参数（网页上可改）
DEFAULT_PARAMS = {
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "kdj": {"n": 9, "m1": 3, "m2": 3},
    "rsi": {"n": 14, "oversold": 30, "overbought": 70},
    "boll": {"n": 20, "k": 2},
    "ma": {"n": 20},
}

INDICATOR_NAMES = {
    "macd": "MACD 金叉死叉",
    "kdj": "KDJ 金叉死叉",
    "rsi": "RSI 超买超卖",
    "boll": "布林带 均值回归",
    "ma": "均线 趋势跟踪",
}


def _cross_up(a, b):
    """a 上穿 b（当前 a>b 且上一根 a<=b）"""
    return (a > b) & (a.shift(1) <= b.shift(1))


def _cross_down(a, b):
    """a 下穿 b（当前 a<b 且上一根 a>=b）"""
    return (a < b) & (a.shift(1) >= b.shift(1))


def build_signal(df, indicator, params=None):
    """
    根据指标生成买卖信号序列。
    返回 Series：1=买入信号，-1=卖出信号，0=无信号（只在信号当天非零）
    """
    p = dict(DEFAULT_PARAMS.get(indicator, {}))
    p.update(params or {})
    close = df["close"]
    high, low = df["high"], df["low"]
    buy = pd.Series(False, index=df.index)
    sell = pd.Series(False, index=df.index)

    if indicator == "macd":
        m = indicators.macd(close, p["fast"], p["slow"], p["signal"])
        buy = _cross_up(m["dif"], m["dea"])
        sell = _cross_down(m["dif"], m["dea"])
    elif indicator == "kdj":
        kdj = indicators.kdj(high, low, close, p["n"], p["m1"], p["m2"])
        buy = _cross_up(kdj["k"], kdj["d"])
        sell = _cross_down(kdj["k"], kdj["d"])
    elif indicator == "rsi":
        r = indicators.rsi(close, p["n"])
        buy = _cross_up(r, pd.Series(p["oversold"], index=r.index))
        sell = _cross_down(r, pd.Series(p["overbought"], index=r.index))
    elif indicator == "boll":
        b = indicators.boll(close, p["n"], p["k"])
        buy = close < b["lower"]
        sell = close > b["upper"]
    elif indicator == "ma":
        m = indicators.ma(close, p["n"])
        buy = _cross_up(close, m)
        sell = _cross_down(close, m)

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[buy] = 1
    sig[sell & ~buy] = -1   # 同一根K线同时触发时，买入优先
    return sig, p


def backtest(df, indicator, params=None, init_cash=100000.0, fee_rate=0.00025):
    """
    执行回测。返回结果字典（含净值曲线、统计指标、交易明细）。
    """
    signal, used_params = build_signal(df, indicator, params)
    cash, shares = init_cash, 0.0
    equity, trades = [], []
    buy_date = buy_price = None

    for i in range(len(df)):
        price = float(df["close"].iloc[i])
        date = df["date"].iloc[i]
        s = int(signal.iloc[i])
        if s > 0 and shares == 0:
            shares = cash * (1 - fee_rate) / price
            cash = 0.0
            buy_date, buy_price = date, price
        elif s < 0 and shares > 0:
            cash = shares * price * (1 - fee_rate)
            trades.append({
                "buy_date": buy_date, "sell_date": date,
                "buy_price": round(buy_price, 4), "sell_price": round(price, 4),
                "ret": round(price / buy_price - 1, 4),
                "days": (date - buy_date).days,
            })
            shares = 0.0
            buy_date = buy_price = None
        equity.append(cash + shares * price)

    df = df.copy()
    df["equity"] = equity
    df["signal"] = signal

    eq = pd.Series(equity)

    n = len(eq)
    total_ret = float(eq.iloc[-1] / init_cash - 1)
    years = n / 252 if n else 1
    annual_ret = float((eq.iloc[-1] / init_cash) ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    # 最大回撤
    cummax = eq.cummax()
    mdd = float(((eq - cummax) / cummax).min())
    # 胜率（按已平仓交易）
    wins = sum(1 for t in trades if t["ret"] > 0)
    win_rate = round(wins / len(trades) * 100, 2) if trades else 0.0
    # 基准（买入持有）
    bh = pd.Series(df["close"] / df["close"].iloc[0] * init_cash)
    bh_ret = float(bh.iloc[-1] / init_cash - 1)

    return {
        "indicator": indicator,
        "indicator_name": INDICATOR_NAMES.get(indicator, indicator),
        "params": used_params,
        "total_ret": round(total_ret * 100, 2),
        "annual_ret": round(annual_ret * 100, 2),
        "max_drawdown": round(mdd * 100, 2),
        "win_rate": win_rate,
        "trade_count": len(trades),
        "win_count": wins,
        "benchmark_ret": round(bh_ret * 100, 2),
        "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
        "equity": [round(x, 2) for x in eq],
        "benchmark": [round(x, 2) for x in bh],
        "signal": [int(x) for x in signal],
        "close": [round(x, 4) for x in df["close"]],
        "trades": trades,
    }