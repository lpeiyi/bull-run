# -*- coding: utf-8 -*-
"""core/market.py 回归测试：行业板块双源选源与清洗排序。

对应 AC-6.1 ~ AC-6.6。

前提：_compare_and_pick 与 _clean_and_sort 原本是 get_boards() 内的嵌套函数，
已按需求约束 C-3 提到模块级（行为不变），故此处可直接 import。
"""
import pytest

from core.market import _clean_and_sort, _compare_and_pick


def _rows(*pairs):
    return [{"name": name, "avg_pct": pct} for name, pct in pairs]


# ── 选源逻辑 ────────────────────────────────────────────────

def test_pick_sina_when_em_empty():
    """AC-6.1: 东财源为空、新浪源非空 → 选用新浪源。"""
    sina = _rows(("A", 1.0), ("B", 0.9))
    assert _compare_and_pick([], sina, "industry") == sina


def test_pick_em_when_sina_empty():
    """AC-6.2: 新浪源为空、东财源非空 → 回退东财源。"""
    em = _rows(("A", 1.0), ("B", 0.9))
    assert _compare_and_pick(em, [], "industry") == em


def test_pick_both_empty_returns_empty():
    """AC-6.5: 两源皆空 → 返回空列表，不抛异常。"""
    assert _compare_and_pick([], [], "industry") == []


def test_pick_switch_to_sina_on_large_deviation():
    """AC-6.3: 命中 ≥3 条且平均偏差 >0.5pp → 切换新浪源。"""
    em = _rows(("农林牧渔", 1.8), ("酿酒行业", 1.7), ("医药制造", 1.6),
               ("半导体", 1.5), ("汽车行业", 1.4))
    sina = _rows(("农林牧渔", 3.6), ("酿酒行业", 3.4), ("医药制造", 3.2),
                 ("半导体", 3.0), ("汽车行业", 2.8))
    assert _compare_and_pick(em, sina, "industry") == sina


def test_pick_keep_em_on_small_deviation():
    """AC-6.4: 命中 ≥3 条但平均偏差 ≤0.5pp → 保持东财源。"""
    em = _rows(("农林牧渔", 1.80), ("酿酒行业", 1.70), ("医药制造", 1.60),
               ("半导体", 1.50), ("汽车行业", 1.40))
    sina = _rows(("农林牧渔", 1.60), ("酿酒行业", 1.50), ("医药制造", 1.40),
                 ("半导体", 1.30), ("汽车行业", 1.20))
    assert _compare_and_pick(em, sina, "industry") == em


def test_pick_requires_at_least_three_hits():
    """AC-6.3/6.4 边界: 命中不足 3 条时即使偏差再大也不切源。"""
    em = _rows(("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", 1.0), ("E", 1.0))
    sina = _rows(("A", 5.0), ("B", 5.0), ("X", 5.0), ("Y", 5.0), ("Z", 5.0))
    assert _compare_and_pick(em, sina, "industry") == em


def test_pick_returns_copy_not_same_object():
    """AC-6.1 补充：返回的是副本，修改结果不应影响入参。"""
    em = _rows(("A", 1.0))
    out = _compare_and_pick(em, [], "industry")
    assert out == em
    out.append({"name": "B", "avg_pct": 2.0})
    assert len(em) == 1


# ── 清洗排序 ────────────────────────────────────────────────

def test_clean_and_sort_filters_dirty_and_orders_desc():
    """AC-6.6: 剔除非数值/None/NaN 行，并按 avg_pct 严格降序。"""
    rows = [
        {"name": "A", "avg_pct": 1.23},
        {"name": "B", "avg_pct": "x"},        # 非数值字符串
        {"name": "C", "avg_pct": 3.5},
        {"name": "D", "avg_pct": None},       # None
        {"name": "E", "avg_pct": float("nan")},  # NaN
        {"name": "F", "avg_pct": 2.0},
    ]
    out = _clean_and_sort(rows)
    assert [x["name"] for x in out] == ["C", "F", "A"]
    assert all(isinstance(x["avg_pct"], (int, float)) for x in out)


def test_clean_and_sort_keeps_int_values():
    """AC-6.6 补充：整型 avg_pct 也应保留（isinstance 判据含 int）。"""
    out = _clean_and_sort([{"name": "A", "avg_pct": 2}, {"name": "B", "avg_pct": 1}])
    assert [x["name"] for x in out] == ["A", "B"]


def test_clean_and_sort_empty_input():
    """AC-6.6 补充：空输入返回空列表。"""
    assert _clean_and_sort([]) == []
