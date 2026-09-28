# -*- coding: utf-8 -*-
"""core/sentiment.py 回归测试：_calc_score 五维度算法 + 涨跌停判定。

对应 AC-2.1 ~ AC-2.10、AC-3.1 ~ AC-3.4，
以及 app / core 涨跌停阈值合并后的 limit_threshold / is_limit_stock 用例。
"""
import pytest

from core.sentiment import _calc_score, _is_dt_stock, is_limit_stock, limit_threshold

CONTRIB_KEYS = {"涨停家数", "连板高度", "晋级率", "炸板率", "跌停惩罚"}


def _level_of(score):
    """按实现的等级规则由 score 反推等级，用于一致性校验。"""
    if score <= 25:
        return "冰点"
    if score <= 45:
        return "偏冷"
    if score <= 65:
        return "正常"
    if score <= 80:
        return "偏热"
    return "过热"


# ── AC-2.x 情绪分算法 ──────────────────────────────────────────

def test_calc_score_zero_zt_count():
    """AC-2.1: zt_n=0 → score=0 且涨停家数贡献为 0。"""
    score, _level, contrib = _calc_score(0, 0, 0, 0.0, 0.0)
    assert score == 0
    assert contrib["涨停家数"] == 0.0


def test_calc_score_base_lower_bound():
    """AC-2.2: zt_n=18（对数映射下界）→ 涨停家数贡献 0。"""
    _score, _level, contrib = _calc_score(18, 0, 0, 0.0, 0.0)
    assert contrib["涨停家数"] == 0.0


@pytest.mark.parametrize("zt_n", [150, 151, 200, 400])
def test_calc_score_base_upper_clamp(zt_n):
    """AC-2.3: zt_n>=150 → 涨停家数贡献钳制为 90。"""
    _score, _level, contrib = _calc_score(zt_n, 0, 0, 0.0, 0.0)
    assert contrib["涨停家数"] == 90.0


@pytest.mark.parametrize("max_height,expected", [
    (0, 0), (3, 0), (4, 1), (5, 2), (6, 3), (7, 4), (8, 5), (12, 5),
])
def test_calc_score_height_contribution(max_height, expected):
    """AC-2.4: 连板高度贡献 3→0 / 4→1 / 5→2 / 6→3 / 7→4 / 8→5。"""
    _score, _level, contrib = _calc_score(50, 0, max_height, 0.0, 0.0)
    assert contrib["连板高度"] == expected


@pytest.mark.parametrize("promo_rate,expected", [
    (20.0, 2), (16.0, 2), (15.9, 1), (13.0, 1), (12.9, 0), (8.0, 0),
    (7.9, -1), (6.0, -1), (5.9, -2), (0.0, -2),
])
def test_calc_score_promo_contribution(promo_rate, expected):
    """AC-2.5: 晋级率贡献五档 [16,∞)/[13,16)/[8,13)/[6,8)/[0,6)。"""
    _score, _level, contrib = _calc_score(50, 0, 0, promo_rate, 0.0)
    assert contrib["晋级率"] == expected


@pytest.mark.parametrize("break_rate,expected", [
    (0.0, 0), (39.9, 0), (40.0, 0), (40.1, -2), (80.0, -2),
])
def test_calc_score_break_rate_contribution(break_rate, expected):
    """AC-2.6: 炸板率 >40 才扣 2 分，否则 0。"""
    _score, _level, contrib = _calc_score(50, 0, 0, 0.0, break_rate)
    assert contrib["炸板率"] == expected


@pytest.mark.parametrize("dt_n,expected", [
    (0, 0.0), (30, 0.0), (31, -0.04), (50, -0.8), (80, -2.0),
])
def test_calc_score_dt_penalty(dt_n, expected):
    """AC-2.7: 跌停惩罚 ≤30 家为 0；超出部分每家家 -0.04（50 家 = -0.8）。"""
    _score, _level, contrib = _calc_score(50, dt_n, 0, 0.0, 0.0)
    assert contrib["跌停惩罚"] == pytest.approx(expected)


def test_calc_score_clamped_and_int():
    """AC-2.8: 极端输入下 score 仍为 [0,100] 内的整数。"""
    for args in [(10000, 0, 20, 100.0, 0.0), (1, 10000, 0, 0.0, 0.0)]:
        score, _level, _contrib = _calc_score(*args)
        assert isinstance(score, int)
        assert 0 <= score <= 100


@pytest.mark.parametrize("args,expected_level", [
    ((33, 0, 3, 7.0, 0.0), "冰点"),    # score = 25
    ((33, 0, 3, 10.0, 0.0), "偏冷"),   # score = 26
    ((52, 0, 3, 10.0, 0.0), "偏冷"),   # score = 45
    ((53, 0, 3, 10.0, 0.0), "正常"),   # score = 46
    ((83, 0, 3, 10.0, 0.0), "正常"),   # score = 65
    ((85, 0, 3, 10.0, 0.0), "偏热"),   # score = 66
    ((118, 0, 3, 10.0, 0.0), "偏热"),  # score = 80
    ((120, 0, 3, 10.0, 0.0), "过热"),  # score = 81
])
def test_calc_score_level_boundary(args, expected_level):
    """AC-2.9: 等级五档边界（输入取自 design.md §5.1 手算参考表）。"""
    score, level, _contrib = _calc_score(*args)
    assert level == expected_level, f"score={score} 期望 {expected_level}，实际 {level}"


@pytest.mark.parametrize("zt_n", list(range(1, 300, 3)))
def test_calc_score_level_consistent_with_score(zt_n):
    """AC-2.9: 网格覆盖下 level 与 score 的映射关系恒成立。"""
    score, level, _contrib = _calc_score(zt_n, 0, 4, 10.0, 0.0)
    assert level == _level_of(score)


def test_calc_score_contributions_keys_and_sum():
    """AC-2.10: 键集合固定；未触发钳制时各维度之和四舍五入等于 score。"""
    score, _level, contrib = _calc_score(50, 40, 5, 10.0, 20.0)
    assert set(contrib) == CONTRIB_KEYS
    assert 0 < score < 100, "该用例旨在验证未钳制情形，输入应落在中间区间"
    assert round(sum(contrib.values())) == score


# ── AC-3.x 跌停判定 ────────────────────────────────────────────
# 注意：_is_dt_stock 的入参是「单只股票的字典」，不是散开的位置参数。

@pytest.mark.parametrize("change_pct,expected", [(-29.5, True), (-29.4, False)])
def test_is_dt_stock_bj(change_pct, expected):
    """AC-3.1: 北交所阈值 -29.5%。"""
    stock = {"change_pct": change_pct, "pure_code": "830001", "market": "bj"}
    assert _is_dt_stock(stock) is expected


@pytest.mark.parametrize("pure_code,market", [
    ("300001", "sz"), ("300999", "sz"), ("688001", "sh"), ("688999", "sh"),
])
@pytest.mark.parametrize("change_pct,expected", [(-19.5, True), (-19.4, False)])
def test_is_dt_stock_cyb_kcb(pure_code, market, change_pct, expected):
    """AC-3.2: 创业板(300)/科创板(688)阈值 -19.5%。"""
    stock = {"change_pct": change_pct, "pure_code": pure_code, "market": market}
    assert _is_dt_stock(stock) is expected


@pytest.mark.parametrize("pure_code", ["600000", "000001", "601398"])
@pytest.mark.parametrize("change_pct,expected", [(-9.8, True), (-9.79, False)])
def test_is_dt_stock_main_board(pure_code, change_pct, expected):
    """AC-3.3: 主板阈值 -9.8%。"""
    stock = {"change_pct": change_pct, "pure_code": pure_code, "market": "sh"}
    assert _is_dt_stock(stock) is expected


def test_is_dt_stock_missing_change_pct():
    """AC-3.4: change_pct 键缺失 → False，不抛异常。"""
    assert _is_dt_stock({"pure_code": "600000", "market": "sh"}) is False


def test_is_dt_stock_none_change_pct():
    """AC-3.4: change_pct 为 None → False，不抛异常。"""
    stock = {"change_pct": None, "pure_code": "600000", "market": "sh"}
    assert _is_dt_stock(stock) is False


# ── 涨跌停阈值判定（app / core 合并后新增的共享实现）────────────────
# _is_dt_stock 现在是 is_limit_stock(stock, -1) 的薄包装，
# 以下用例守护共享函数的正确性 + 两者等价性。

@pytest.mark.parametrize("stock,expected", [
    ({"market": "bj", "pure_code": "830001"}, 29.5),
    ({"market": "sz", "pure_code": "300001"}, 19.5),
    ({"market": "sh", "pure_code": "688001"}, 19.5),
    ({"market": "sh", "pure_code": "600000"}, 9.8),
    ({"market": "sz", "pure_code": "000001"}, 9.8),
])
def test_limit_threshold_three_tiers(stock, expected):
    """三档阈值：北交所 29.5% / 创业板科创板 19.5% / 主板 9.8%。"""
    assert limit_threshold(stock) == expected


def test_limit_threshold_missing_fields_defaults_main_board():
    """pure_code / market 均缺失 → 落到主板 9.8%，不抛异常。"""
    assert limit_threshold({}) == 9.8


@pytest.mark.parametrize("stock,threshold", [
    ({"market": "bj", "pure_code": "830001"}, 29.5),
    ({"market": "sz", "pure_code": "300001"}, 19.5),
    ({"market": "sh", "pure_code": "600000"}, 9.8),
])
def test_is_limit_stock_both_directions(stock, threshold):
    """正负方向：恰好触阈为 True，差 0.01 为 False（严格不等式，方向对称）。"""
    up = dict(stock, change_pct=threshold)
    up_off = dict(stock, change_pct=threshold - 0.01)
    down = dict(stock, change_pct=-threshold)
    down_off = dict(stock, change_pct=-(threshold - 0.01))

    assert is_limit_stock(up, 1) is True
    assert is_limit_stock(up_off, 1) is False
    assert is_limit_stock(down, -1) is True
    assert is_limit_stock(down_off, -1) is False
    # 反向不误判：跌停价不触发涨停、涨停价不触发跌停
    assert is_limit_stock(down, 1) is False
    assert is_limit_stock(up, -1) is False


@pytest.mark.parametrize("sign", [1, -1])
def test_is_limit_stock_none_change_pct_both_signs(sign):
    """change_pct 为 None → 两个方向均返回 False，不抛异常。"""
    stock = {"change_pct": None, "pure_code": "600000", "market": "sh"}
    assert is_limit_stock(stock, sign) is False


def test_is_limit_stock_missing_change_pct_both_signs():
    """change_pct 键缺失 → 两个方向均返回 False。"""
    stock = {"pure_code": "600000", "market": "sh"}
    assert is_limit_stock(stock, 1) is False
    assert is_limit_stock(stock, -1) is False


_SAMPLES = [
    {"change_pct": -29.5, "pure_code": "830001", "market": "bj"},
    {"change_pct": -30.0, "pure_code": "830002", "market": "bj"},
    {"change_pct": -29.4, "pure_code": "830003", "market": "bj"},
    {"change_pct": -19.5, "pure_code": "300001", "market": "sz"},
    {"change_pct": -20.0, "pure_code": "688001", "market": "sh"},
    {"change_pct": -19.4, "pure_code": "300002", "market": "sz"},
    {"change_pct": -9.8, "pure_code": "600000", "market": "sh"},
    {"change_pct": -10.02, "pure_code": "000001", "market": "sz"},
    {"change_pct": -5.0, "pure_code": "601398", "market": "sh"},
    {"change_pct": 9.9, "pure_code": "600000", "market": "sh"},
    {"change_pct": None, "pure_code": "600000", "market": "sh"},
    {"pure_code": "600000", "market": "sh"},
]


@pytest.mark.parametrize("stock", _SAMPLES)
def test_is_dt_stock_equivalent_to_is_limit_stock_minus_one(stock):
    """等价性：合并后 _is_dt_stock(stock) 必须恒等于 is_limit_stock(stock, -1)。"""
    assert _is_dt_stock(stock) is is_limit_stock(stock, -1)
