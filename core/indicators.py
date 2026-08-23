# -*- coding: utf-8 -*-
"""技术指标库：MACD / KDJ / RSI / BOLL / 均线"""
import pandas as pd


def ma(close, n=20):
    """简单移动平均线"""
    return close.rolling(n).mean()


def ema(close, n=12):
    """指数移动平均线"""
    return close.ewm(span=n, adjust=False).mean()


def macd(close, fast=12, slow=26, signal=9):
    """
    MACD 指标。
    返回 DataFrame: dif(快慢线差), dea(信号线), macd(柱, 2*diff)
    """
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"dif": dif, "dea": dea, "macd": 2 * (dif - dea)})


def kdj(high, low, close, n=9, m1=3, m2=3):
    """
    随机指标 KDJ（国内常用 9,3,3）。
    返回 DataFrame: k, d, j
    """
    low_n = low.rolling(n, min_periods=1).min()
    high_n = high.rolling(n, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, 1e-9) * 100
    # K/D 是 RSV 的 SMÁ 平滑（alpha=1/m1），初始用 50
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"k": k, "d": d, "j": j})


def rsi(close, n=14):
    """相对强弱指标 RSI（Wilder 平滑）"""
    diff = close.diff()
    up = diff.clip(lower=0)
    down = (-diff).clip(lower=0)
    avg_up = up.ewm(alpha=1 / n, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_up / avg_down.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def boll(close, n=20, k=2):
    """
    布林带。
    返回 DataFrame: mid(中轨), upper(上轨), lower(下轨)
    """
    mid = ma(close, n)
    std = close.rolling(n).std()
    return pd.DataFrame({"mid": mid, "upper": mid + k * std, "lower": mid - k * std})