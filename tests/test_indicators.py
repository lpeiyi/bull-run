# -*- coding: utf-8 -*-
"""core/indicators.py 回归测试：MA / MACD / KDJ / RSI / BOLL。

对应 AC-4.1 ~ AC-4.6。

注意：本模块的 kdj 与 core.tdx.KDJ 是两套独立实现——前者分母用
`.replace(0, 1e-9)`，后者用 `.replace(0, np.nan)` + `fillna(50)`。
两者在「高低价相等」时的结果不同，期望值不可互相套用。
"""
import numpy as np
import pandas as pd
import pytest

from core import indicators


@pytest.fixture
def rising_close():
    """1..60 的等差递增收盘价序列。"""
    return pd.Series([float(i) for i in range(1, 61)])


def test_ma_rolling_window(rising_close):
    """AC-4.1: 第 n 位起等于前 n 个值的算术平均，前 n-1 位为 NaN。"""
    n = 5
    out = indicators.ma(rising_close, n)
    assert out.iloc[:n - 1].isna().all()
    assert out.iloc[:n - 1].isna().sum() == n - 1
    assert out.iloc[n - 1] == pytest.approx(rising_close.iloc[:n].mean())
    assert out.iloc[-1] == pytest.approx(rising_close.iloc[-n:].mean())


def test_ema_initialized_from_first_value(rising_close):
    """AC-4.1 补充：EMA 无前导 NaN，首值等于序列首值（adjust=False 递推）。"""
    out = indicators.ema(rising_close, 12)
    assert not out.isna().any()
    assert out.iloc[0] == pytest.approx(rising_close.iloc[0])


def test_macd_histogram_identity(rising_close):
    """AC-4.2: macd 列恒等于 2 × (dif − dea)。"""
    res = indicators.macd(rising_close)
    np.testing.assert_allclose(
        res["macd"].values,
        (2 * (res["dif"] - res["dea"])).values,
        rtol=1e-9, atol=1e-9, equal_nan=True,
    )


def test_kdj_j_identity(rising_close):
    """AC-4.3: j 列恒等于 3 × k − 2 × d。"""
    high = rising_close + 1.0
    low = rising_close - 1.0
    res = indicators.kdj(high, low, rising_close)
    np.testing.assert_allclose(
        res["j"].values,
        (3 * res["k"] - 2 * res["d"]).values,
        rtol=1e-9, atol=1e-9, equal_nan=True,
    )


def test_kdj_zero_range_produces_no_nan_or_inf():
    """AC-4.4: high==low（分母为零）时不产生 NaN/inf，也不抛异常。"""
    flat = pd.Series([10.0] * 30)
    res = indicators.kdj(flat.copy(), flat.copy(), flat.copy())
    for col in ("k", "d", "j"):
        values = res[col]
        assert not values.isna().any(), f"{col} 出现 NaN"
        assert np.isfinite(values.values).all(), f"{col} 出现 inf"


@pytest.mark.parametrize("reversed_order,comparison,threshold", [
    (False, "gt", 90),   # 单调递增 → RSI > 90
    (True, "lt", 10),    # 单调递减 → RSI < 10
])
def test_rsi_extremes(reversed_order, comparison, threshold):
    """AC-4.5: 单调递增 RSI 末值 >90；单调递减 <10。"""
    values = [float(i) for i in range(1, 61)]
    if reversed_order:
        values = list(reversed(values))
    last = indicators.rsi(pd.Series(values)).iloc[-1]
    if comparison == "gt":
        assert last > threshold, f"递增序列 RSI 末值 {last} 应 > {threshold}"
    else:
        assert last < threshold, f"递减序列 RSI 末值 {last} 应 < {threshold}"


def test_boll_symmetry_around_mid(rising_close):
    """AC-4.6: upper + lower 恒等于 2 × mid（上下轨关于中轨对称）。"""
    res = indicators.boll(rising_close)
    np.testing.assert_allclose(
        (res["upper"] + res["lower"]).values,
        (2 * res["mid"]).values,
        rtol=1e-9, atol=1e-9, equal_nan=True,
    )
