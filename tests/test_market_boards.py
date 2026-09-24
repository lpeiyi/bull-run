# -*- coding: utf-8 -*-
"""core/market.py 回归测试：板块数据源选择、清洗排序与层级去重。

对应 specs/fix-boards-source-selection 的 AC-1 ~ AC-5。

前提：`_parse_sina` / `_parse_em` / `_pick_source` / `_clean_and_sort` 等
原为 `get_boards()` 内的嵌套函数，已按需求约束 C-2 提到模块级（行为不变），
故此处可直接 import。
"""
import pytest

import core.market as market
from core.market import (
    _base_name,
    _clean_and_sort,
    _dedup_by_level,
    _parse_em,
    _pick_source,
)


def _rows(*pairs):
    return [{"name": name, "avg_pct": pct} for name, pct in pairs]


def _em_rows(n=100, start=1.0):
    """构造 n 条降序的东财风格行，用于测试「条数是否充足」分支。"""
    return [{"name": f"东财板块{i}", "avg_pct": round(start - i * 0.01, 2)}
            for i in range(n)]


# ── 东财请求参数（本次缺陷的回归防线）────────────────────────

def test_parse_em_uses_fid_sort_param(monkeypatch):
    """AC-1.2: 东财请求必须用 fid=f3 + po=1 排序，不得再出现无效的 fl。

    这是本轮修复的核心：原代码写 `"fl": "f3"`，而 fl 是「返回哪些字段」
    的参数、毫无排序作用，接口退回按板块代码返回，导致候选池变成
    「代码序前 100 个」而非「涨幅最高的 100 个」。
    """
    captured = {}

    class _Resp:
        @staticmethod
        def json():
            return {"data": {"diff": []}}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    monkeypatch.setattr(market.requests, "get", fake_get)
    _parse_em("m:90+t:2")

    p = captured["params"]
    assert p["fid"] == "f3", "排序字段必须用 fid=f3"
    assert p["po"] == 1, "po=1 表示降序"
    assert "fl" not in p, "fl 不是排序参数，不应再出现"
    assert p["fs"] == "m:90+t:2"


def test_parse_em_parses_pct_and_fields(monkeypatch):
    """AC-1.3: f3 为整数化涨跌幅（583 → 5.83%），f6 单位为元需转亿。"""
    payload = {"data": {"diff": [
        {"f12": "BK1502", "f14": "林业Ⅲ", "f3": 583, "f6": 1234567890},
        {"f12": "BK1255", "f14": "林业Ⅱ", "f3": 583, "f6": None},
    ]}}

    class _Resp:
        @staticmethod
        def json():
            return payload

    monkeypatch.setattr(market.requests, "get", lambda *a, **kw: _Resp())
    rows = _parse_em("m:90+t:2")

    assert [r["name"] for r in rows] == ["林业Ⅲ", "林业Ⅱ"]
    assert rows[0]["avg_pct"] == 5.83
    assert rows[0]["amount_yi"] == 12.35      # 1234567890 / 1e8
    assert rows[0]["code"] == "BK1502"
    assert rows[1]["amount_yi"] == 0.0        # f6 为 None 时兜底 0


def test_parse_em_returns_empty_on_request_error(monkeypatch):
    """AC-2.2 支撑: 东财请求异常 → 返回 []，不向外抛。"""
    def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(market.requests, "get", boom)
    assert _parse_em("m:90+t:2") == []


# ── 选源逻辑 ────────────────────────────────────────────────

def test_pick_em_when_enough_rows():
    """AC-2.1: 东财条数充足 → 使用东财源（即便新浪也有数据）。"""
    em = _em_rows(100)
    sina = _rows(("新浪行业", 0.19))
    assert _pick_source(em, sina, "industry") == em


def test_pick_sina_when_em_empty():
    """AC-2.2: 东财为空、新浪非空 → 回退新浪。"""
    sina = _rows(("A", 1.0), ("B", 0.9))
    assert _pick_source([], sina, "industry") == sina


def test_pick_sina_when_em_insufficient():
    """AC-2.4: 东财条数不足阈值、新浪有数据 → 视为不可靠并回退新浪。"""
    em = _em_rows(5)
    sina = _rows(("A", 1.0))
    assert _pick_source(em, sina, "industry") == sina


def test_pick_keeps_partial_em_when_sina_empty():
    """AC-2.4 补充: 东财不足但新浪也空 → 沿用东财（聊胜于无），不返回空。"""
    em = _em_rows(5)
    assert _pick_source(em, [], "industry") == em


def test_pick_both_empty_returns_empty():
    """AC-2.3: 两源皆空 → 返回空列表，不抛异常。"""
    assert _pick_source([], [], "industry") == []


def test_pick_returns_copy_not_same_object():
    """AC-2.1 补充: 返回的是副本，修改结果不应影响入参。"""
    em = _em_rows(100)
    out = _pick_source(em, [], "industry")
    out.append({"name": "X", "avg_pct": 9.9})
    assert len(em) == 100


def test_pick_source_no_longer_compares_names():
    """AC-2.5: 新逻辑不再依赖「两源同名板块交叉比对」。

    原机制的失效根因是两源名称体系不同（重合率仅 12.2%），命中数恒为 0。
    此处构造两源名称完全不同的极端场景：结果仍取东财，但依据是
    「东财条数充足」，而非比对结论。
    """
    em = [{"name": f"东财板块{i}", "avg_pct": 1.0} for i in range(100)]
    sina = [{"name": f"新浪行业{i}", "avg_pct": 3.0} for i in range(49)]
    assert _pick_source(em, sina, "industry") == em


# ── 层级去重 ────────────────────────────────────────────────

def test_base_name_strips_level_suffix():
    """AC-3.1 支撑: 去掉名称末尾的罗马数字层级标记。"""
    assert _base_name("林业Ⅲ") == "林业"
    assert _base_name("其他家电Ⅱ") == "其他家电"
    assert _base_name("风电设备") == "风电设备"
    assert _base_name("") == ""
    assert _base_name(None) == ""


def test_dedup_by_level_removes_duplicate_levels():
    """AC-3.1: 同一行业的不同层级只保留靠前（涨幅更高）的一条。"""
    rows = _rows(("林业Ⅲ", 5.83), ("林业Ⅱ", 5.83),
                 ("其他医疗服务", 4.29),
                 ("其他家电Ⅲ", 4.24), ("其他家电Ⅱ", 4.24))
    assert [x["name"] for x in _dedup_by_level(rows)] == [
        "林业Ⅲ", "其他医疗服务", "其他家电Ⅲ"]


def test_dedup_by_level_keeps_higher_one():
    """AC-3.1: 去重保留靠前的一条，故调用前必须先降序排列。"""
    rows = _rows(("林业Ⅲ", 5.83), ("林业Ⅱ", 4.10))
    assert [x["name"] for x in _dedup_by_level(rows)] == ["林业Ⅲ"]


def test_dedup_by_level_keeps_names_without_suffix():
    """AC-3.1 补充: 不带层级后缀的名称原样保留，不受影响。"""
    rows = _rows(("风电设备", 2.15), ("棉纺", 1.74), ("纺织制造", 1.31))
    assert len(_dedup_by_level(rows)) == 3


def test_dedup_by_level_empty_input():
    """AC-3.1 补充: 空输入返回空列表。"""
    assert _dedup_by_level([]) == []


# ── get_boards 整体 ─────────────────────────────────────────

def test_get_boards_returns_sorted_deduped(monkeypatch):
    """AC-1.1 / AC-1.4 / AC-4.1: 返回结构不变、结果降序、层级去重、字段齐全。"""
    em_ind = [
        {"name": "林业Ⅲ", "stock_count": 0, "avg_pct": 5.83,
         "amount_yi": 1.0, "leader_name": "", "leader_pct": 0.0, "code": "BK1502"},
        {"name": "林业Ⅱ", "stock_count": 0, "avg_pct": 5.83,
         "amount_yi": 1.0, "leader_name": "", "leader_pct": 0.0, "code": "BK1255"},
        {"name": "风电设备", "stock_count": 0, "avg_pct": 2.15,
         "amount_yi": 2.0, "leader_name": "", "leader_pct": 0.0, "code": "BK1032"},
    ]
    em_con = [
        {"name": "机器人执行器", "stock_count": 0, "avg_pct": 0.74,
         "amount_yi": 3.0, "leader_name": "", "leader_pct": 0.0, "code": "BK1100"},
    ]
    monkeypatch.setattr(market, "_parse_em",
                        lambda fs: em_ind if fs.endswith("t:2") else em_con)
    # 东财条数不足阈值 → 会请求新浪；让新浪返回空，验证不抛异常
    monkeypatch.setattr(market, "_sina_or_empty", lambda url: [])

    out = market.get_boards()

    assert set(out) == {"industry", "concept"}
    names = [x["name"] for x in out["industry"]]
    assert names == ["林业Ⅲ", "风电设备"]          # 层级去重生效
    pcts = [x["avg_pct"] for x in out["industry"]]
    assert pcts == sorted(pcts, reverse=True)      # 严格降序
    for x in out["industry"]:
        assert {"name", "stock_count", "avg_pct", "amount_yi",
                "leader_name", "leader_pct"} <= set(x)


# ── 清洗排序 ────────────────────────────────────────────────

def test_clean_and_sort_filters_dirty_and_orders_desc():
    """AC-1.1 支撑: 剔除非数值/None/NaN 行，并按 avg_pct 严格降序。"""
    rows = [
        {"name": "A", "avg_pct": 1.23},
        {"name": "B", "avg_pct": "x"},           # 非数值字符串
        {"name": "C", "avg_pct": 3.5},
        {"name": "D", "avg_pct": None},          # None
        {"name": "E", "avg_pct": float("nan")},  # NaN
        {"name": "F", "avg_pct": 2.0},
    ]
    out = _clean_and_sort(rows)
    assert [x["name"] for x in out] == ["C", "F", "A"]
    assert all(isinstance(x["avg_pct"], (int, float)) for x in out)


def test_clean_and_sort_keeps_int_values():
    """AC-1.1 支撑: 整型 avg_pct 也应保留（isinstance 判据含 int）。"""
    out = _clean_and_sort([{"name": "A", "avg_pct": 2},
                           {"name": "B", "avg_pct": 1}])
    assert [x["name"] for x in out] == ["A", "B"]


def test_clean_and_sort_empty_input():
    """AC-1.1 支撑: 空输入返回空列表。"""
    assert _clean_and_sort([]) == []
