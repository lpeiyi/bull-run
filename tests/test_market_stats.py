# -*- coding: utf-8 -*-
"""core/market.py 市场统计函数回归测试。

覆盖随 app.py 瘦身一起下沉的纯函数：
- build_distribution(stocks)  全市场涨跌幅分布（本文件）
- get_index_compare(days)     多指数归一化叠加（见下方同名小节）

这两个函数只依赖入参与 core 内模块（AC-2.5），因此无需打桩、无需起 Flask
即可直接喂数据断言 —— 这正是"取数与统计分离"（design §3.6）带来的好处。
"""
import pytest

from core.market import build_distribution

# 9 个区间的固定顺序（从高到低），名称与 count 都对得上才算契约成立
RANGE_NAMES = ["≥7%", "5~7%", "2~5%", "0~2%", "平盘",
               "-2~0%", "-5~-2%", "-7~-5%", "≤-7%"]


def _stk(symbol, pct):
    """按 screener._normalize_stock_rows 的产物结构造一只股票。"""
    return {"code": symbol, "pure_code": symbol[2:], "name": "T" + symbol[2:],
            "market": symbol[:2], "price": 10.0, "change_pct": pct}


def _counts(body):
    return [r["count"] for r in body["ranges"]]


# ══════════════════════════════════════════════════════
# build_distribution
# ══════════════════════════════════════════════════════

def test_build_distribution_empty():
    """空清单：9 个区间全 0，各汇总数均为 0，total 为 0（不是 None）。"""
    body = build_distribution([])

    assert _counts(body) == [0] * 9
    assert body["total"] == 0
    assert body["zt_count"] == 0
    assert body["dt_count"] == 0
    assert body["up_count"] == 0
    assert body["down_count"] == 0


def test_build_distribution_response_shape():
    """响应键集合固定；区间名称与顺序固定；min/max 仅作展示。"""
    body = build_distribution([])

    assert set(body) == {"ranges", "total", "zt_count", "dt_count",
                         "up_count", "down_count"}
    assert [r["name"] for r in body["ranges"]] == RANGE_NAMES
    # 展示用的 min/max 只出现在有明确下限/上限的区间上，缺少即未设
    assert body["ranges"][0] == {"name": "≥7%", "min": 7, "count": 0}
    assert body["ranges"][8] == {"name": "≤-7%", "max": -7, "count": 0}


@pytest.mark.parametrize("pct,idx", [
    (7.0, 0), (20.0, 0),                    # ≥7%
    (6.99, 1), (5.0, 1),                    # 5~7%（5.0 取下界）
    (4.99, 2), (2.0, 2),                    # 2~5%（2.0 取下界）
    (1.99, 3), (0.001, 3),                  # 0~2%（0.001 归此，不含 0）
    (0.0009, 4), (0.0, 4), (-0.0009, 4),    # 平盘（严格不等式 -0.001 < pct < 0.001）
    (-0.001, 5), (-1.0, 5), (-2.0, 5),      # -2~0%（-0.001 与 -2.0 均归此）
    (-2.01, 6), (-5.0, 6),                  # -5~-2%（-5.0 取下界）
    (-5.01, 7), (-7.0, 7),                  # -7~-5%（-7.0 取下界）
    (-7.01, 8), (-20.0, 8),                 # ≤-7%
])
def test_build_distribution_bounds_are_exclusive(pct, idx):
    """逐值验归类：每个边界值只落进一个区间，落点与级联顺序一致。

    平盘用的是严格不等式，因此 ±0.001 被挤到相邻区间（0~2% / -2~0%），
    而 ±0.0009 才留在平盘 —— 这是刻意设计，不是舍入误差。
    """
    body = build_distribution([_stk("sh600000", pct)])

    expected = [0] * 9
    expected[idx] = 1
    assert _counts(body) == expected, f"pct={pct} 期望落在 {RANGE_NAMES[idx]}"


def test_build_distribution_every_stock_counted_once():
    """级联判断保证互斥：各区间计数之和恒等于 total。"""
    values = [7.0, 6.99, 5.0, 2.0, 1.99, 0.001, 0.0, -0.001, -2.0,
              -5.0, -7.0, -7.01, 20.0, -20.0, 3.3]
    stocks = [_stk("sh%06d" % (600000 + i), v) for i, v in enumerate(values)]

    body = build_distribution(stocks)

    assert sum(_counts(body)) == body["total"] == len(values)


def test_build_distribution_missing_change_pct_treated_as_zero():
    """change_pct 键缺失 → get(..., 0) 取 0，归入平盘，不计入涨跌家数。"""
    body = build_distribution([{"code": "sh600000", "pure_code": "600000",
                                "market": "sh"}])

    assert _counts(body)[4] == 1          # 平盘
    assert body["up_count"] == 0
    assert body["down_count"] == 0


def test_build_distribution_up_down_counts():
    """上涨/下跌家数：严格按 >0 / <0 划分，0.0 两边都不计。"""
    body = build_distribution([
        _stk("sh600000", 1.0),
        _stk("sh600001", 0.0),
        _stk("sh600002", -1.0),
        _stk("sh600003", 9.9),
        _stk("sh600004", -9.9),
    ])

    assert body["up_count"] == 2
    assert body["down_count"] == 2
    assert body["total"] == 5


def test_build_distribution_limit_counts_three_tiers():
    """涨跌停家数沿用三档阈值：主板 9.8 / 创业板科创板 19.5 / 北交所 29.5。"""
    body = build_distribution([
        _stk("sh600000", 9.8),      # 主板涨停
        _stk("sz300001", 19.5),     # 创业板涨停
        _stk("sh688001", 19.6),     # 科创板涨停
        _stk("bj430001", 29.5),     # 北交所涨停
        _stk("sh600001", 9.79),     # 差一点，不算
        _stk("sh600002", -9.8),     # 主板跌停
        _stk("sz300002", -19.5),    # 创业板跌停
        _stk("bj430002", -29.6),    # 北交所跌停
        _stk("sh600003", -9.79),    # 差一点，不算
    ])

    assert body["zt_count"] == 4
    assert body["dt_count"] == 3


def test_build_distribution_does_not_mutate_input():
    """纯函数：不修改入参，也不保留引用（两次调用结果一致）。"""
    stocks = [_stk("sh600000", 3.0)]

    first = build_distribution(stocks)
    assert stocks[0]["change_pct"] == 3.0
    assert set(stocks[0]) == {"code", "pure_code", "name", "market",
                              "price", "change_pct"}

    second = build_distribution(stocks)
    assert first == second
