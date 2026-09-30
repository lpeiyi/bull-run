# -*- coding: utf-8 -*-
"""回归测试共享夹具。

约定（见 specs/add-regression-tests/）：
- 所有测试必须离线可跑：`_no_network` 阻断一切真实网络连接（AC-1.2 / 约束 C-1）。
- 行情数据统一用 `kline_factory` 生成等差 K 线：均线、极值、布林带都有闭式解，
  期望值可手算，避免"跑一遍再把结果抄成期望值"的自证式断言。
"""
import socket

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """阻断真实网络连接，保证测试离线可跑（AC-1.2）。

    被测的四个模块均为纯计算逻辑，本夹具不应对它们造成误伤；
    一旦将来某个函数偷偷发起请求，会立即在此失败并暴露问题。
    """
    def _blocked(*args, **kwargs):
        raise AssertionError(
            "测试期间禁止真实网络访问：请检查被测代码是否新增了外部请求"
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(autouse=True)
def _reset_screener_state():
    """重置 core.screener 的进程级状态，避免用例间互相污染。

    `_LAST_ATTEMPT`（最小重试间隔抑制）会跨用例残留：前一个用例留下的
    「刚拉取失败过」标记会抑制后续用例的真实拉取，导致假失败。
    """
    from core import screener
    screener._LAST_ATTEMPT.update(ts=0.0, usable=False)
    yield
    screener._LAST_ATTEMPT.update(ts=0.0, usable=False)


@pytest.fixture
def kline_factory():
    """生成等差性质的 K 线 DataFrame（供 tdx 等需要完整 OHLCV 的用例使用）。

    默认 60 根：open/high/low/close 随 i 线性递增，volume 固定。
    """
    def _make(n=60, base=10.0, step=0.1, volume=100000):
        close = [base + i * step for i in range(n)]
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [v - step / 2 for v in close],
            "high": [v + step for v in close],
            "low": [v - step for v in close],
            "close": close,
            "volume": [volume] * n,
        })
    return _make
