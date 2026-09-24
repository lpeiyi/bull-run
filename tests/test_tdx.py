# -*- coding: utf-8 -*-
"""core/tdx.py 回归测试：语法检查、公式求值、指标属性访问。

对应 AC-5.1 ~ AC-5.4。

注意：evaluate_tdx 返回的是二元组 (结果字典, 信号)，不是单条序列；
本文件所有 K 线输入来自 conftest 的 kline_factory（固定等差数据，无需网络）。
"""
import pandas as pd
import pytest

from core import tdx

INVALID_FORMULAS = [
    "",               # 空公式
    "选股: 1 + ",     # 表达式不完整
    "选股: (C",       # 括号不匹配
    "选股: MA(C,",    # 函数参数不完整
]


@pytest.mark.parametrize("code", INVALID_FORMULAS)
def test_syntax_check_rejects_invalid(code):
    """AC-5.1: 非法公式返回失败且携带错误信息，不抛未捕获异常。"""
    ok, msg = tdx.check_tdx_syntax(code)
    assert ok is False
    assert isinstance(msg, str)
    assert msg.strip() != ""


def test_evaluate_returns_equal_length_bool_series(kline_factory):
    """AC-5.2: 布尔公式的输出序列与输入 K 线等长且为布尔类型。"""
    df = kline_factory(n=60)
    results, _signal = tdx.evaluate_tdx("选股: C > MA(C,5);", df)
    out = results["选股"]
    assert len(out) == len(df)
    assert out.dtype == bool


@pytest.mark.parametrize("formula", [
    "选股: KDJ.J > 80;",
    "选股: KDJ.K > 50;",
    "选股: KDJ.D < 50;",
    "选股: MACD.DIF > 0;",
    "选股: MACD.DEA > 0;",
    "选股: BOLL.UP > C;",
    "选股: BOLL.LOW < C;",
    "选股: CROSS(KDJ.K, KDJ.D);",
    "选股: KDJ.J > 80 AND C > MA(C,5);",
])
def test_evaluate_attr_access(formula, kline_factory):
    """AC-5.3: 指标属性（KDJ.J / MACD.DIF / BOLL.UP 等）应能参与比较与逻辑运算。

    回归背景：属性展开为 KDJ(...)[2] 这类下标后缀后，比较运算的项提取
    未能识别 ']'，导致表达式畸形、公式静默失效（缺陷已修复）。
    """
    df = kline_factory(n=60)
    results, _signal = tdx.evaluate_tdx(formula, df)
    assert "选股" in results
    assert len(results["选股"]) == len(df)


def test_evaluate_is_deterministic(kline_factory):
    """AC-5.4: 同一公式与同一 DataFrame 重复求值两次结果完全一致。"""
    df = kline_factory(n=60)
    code = "选股: C > MA(C,5) AND KDJ.J > 50;"
    r1, _ = tdx.evaluate_tdx(code, df)
    r2, _ = tdx.evaluate_tdx(code, df)
    pd.testing.assert_series_equal(r1["选股"], r2["选股"])


def test_evaluate_signal_is_bool_or_none(kline_factory):
    """AC-5.4 补充：信号值为布尔或 None，不产生异常类型。"""
    df = kline_factory(n=60)
    _results, signal = tdx.evaluate_tdx("选股: C > MA(C,5);", df)
    assert signal is None or isinstance(signal, bool)
