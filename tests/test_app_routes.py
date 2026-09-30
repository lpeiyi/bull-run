# -*- coding: utf-8 -*-
"""app.py 路由层契约测试（ROADMAP 第 6 项 · app.py 路由瘦身）。

为什么要有这个文件
------------------
app.py 原本零测试覆盖（267 个既有用例全在 core 层面）。在第 6 项里要把算法
从路由下沉到 core，且承诺「响应一字未变」—— 没有这个文件，这个承诺无法被证明。

三条纪律
--------
1. **离线**：所有数据源一律打桩（另有 conftest 的 socket 阻断夹具兜底）。
2. **期望值可手算**：mock 数据用等差序列，归一化 / 收益率 / 均值都有闭式解，
   不采用「先跑一遍再把输出抄成期望值」的自证式断言。
3. **先立契约后动刀**：本文件必须在**未重构**的 app.py 上先跑绿，
   之后每一次搬迁都不得让它变红。见 specs/slim-app-routes/design.md §5。

打桩为什么这么啰嗦（重要）
--------------------------
app.py 顶部写的是 `from core.data import kline` —— 这是把函数**引用复制**了一份，
所以 `monkeypatch.setattr(core.data, "kline", fake)` 对 app.py **无效**，
必须打到 `app` 模块属性上。

而本次重构会把调用点从 app.py 搬进 core（market / emotion_history），打桩目标又要跟着变。
于是这里对**所有可能持有引用的模块**（app / market / emotion_history / screener / core.data）
一次性打桩，保证同一套用例在重构前后都有效；并返回调用记录，
由用例断言「桩确实被调用过」—— 否则漏打桩会让用例悄悄失去意义。
"""
import pandas as pd
import pytest

import app as app_module
from core import data as core_data
from core import emotion_history, market, sentiment, screener

# 可能持有 kline / kline_range 引用的模块
_KLINE_HOLDERS = (app_module, core_data, emotion_history, market, screener)

# 会被用例互相污染的模块级缓存（重构前后可能位于不同模块，故两处都处理）
_RESETTABLE = app_module, emotion_history


# ── 通用夹具 ──────────────────────────────────────────

@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _reset_module_caches():
    """复位模块级缓存，避免用例之间串味。

    注意 `_IDX_CLOSE_CACHE` 会随重构从 app.py 搬到 emotion_history.py，
    所以这里对两个模块都处理，保证用例在重构前后都成立。
    """
    def _reset():
        for mod in _RESETTABLE:
            idx = getattr(mod, "_IDX_CLOSE_CACHE", None)
            if isinstance(idx, dict):
                idx.clear()
            for name in ("_OVERVIEW_CACHE", "_LN_CACHE", "_GOLD_CACHE",
                         "_KLINE_CACHE", "_LOW_NEXT_CACHE"):
                c = getattr(mod, name, None)
                if isinstance(c, dict):
                    c["ts"] = 0.0
                    c["data"] = None
            cmp_cache = getattr(mod, "_IDX_CMP_CACHE", None)
            if isinstance(cmp_cache, dict):
                for v in cmp_cache.values():
                    if isinstance(v, dict):
                        v["ts"] = 0.0
                        v["data"] = None

    _reset()
    yield
    _reset()


def _kline_df(closes, start="2024-01-01"):
    """按给定收盘价序列造 K 线 DataFrame（日期为连续自然日）。"""
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range(start, periods=n),
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


class _KlineStub:
    """kline / kline_range 的假实现，同时记录调用序列。"""

    def __init__(self):
        self.calls = []          # [(kind, code, days_or_start), ...]
        self.kline_map = {}
        self.range_map = {}

    # 供用例登记桩数据
    def put(self, code, closes, start="2024-01-01"):
        self.kline_map[code] = _kline_df(closes, start)
        return self

    def put_range(self, code, closes, start="2020-01-01"):
        self.range_map[code] = _kline_df(closes, start)
        return self

    def kline_calls(self):
        return [(c, d) for kind, c, d in self.calls if kind == "kline"]

    def range_calls(self):
        return [c for kind, c, _ in self.calls if kind == "kline_range"]

    def reset(self):
        self.calls.clear()


@pytest.fixture
def stub_kline(monkeypatch):
    """把 kline / kline_range 打桩到所有可能持有引用的模块上（见模块 docstring）。"""
    stub = _KlineStub()

    def _fake_kline(code, days=250, adjust="qfq"):
        stub.calls.append(("kline", code, days))
        df = stub.kline_map.get(code)
        if df is None:
            raise ValueError("测试未为 %s 登记 K 线桩数据" % code)
        return df

    def _fake_kline_range(code, start=None, end=None, adjust="qfq"):
        stub.calls.append(("kline_range", code, start))
        df = stub.range_map.get(code)
        if df is None:
            raise ValueError("测试未为 %s 登记区间 K 线桩数据" % code)
        return df

    for mod in _KLINE_HOLDERS:
        if hasattr(mod, "kline"):
            monkeypatch.setattr(mod, "kline", _fake_kline)
        if hasattr(mod, "kline_range"):
            monkeypatch.setattr(mod, "kline_range", _fake_kline_range)
    return stub


# ── 通用桩数据 ────────────────────────────────────────

def _sent(score=88, level="过热", trade_date="20240902"):
    """sentiment.get_sentiment() 的返回结构"""
    return {
        "score": score, "level": level, "trade_date": trade_date,
        "zt_count": 150, "dt_count": 2, "zb_count": 10,
        "break_rate": 6.2, "promo_rate": 30.0, "max_height": 5,
        "contributions": {"zt": 40, "height": 20, "promo": 10, "break": 5, "dt": -2},
    }


def _trend_row(date, score=60, level="正常"):
    """emotion_history.get_emotion_trend() 单个元素的结构（见 _build_trend）"""
    return {
        "date": date, "label": "%s-%s" % (date[4:6], date[6:8]),
        "score": score, "level": level,
        "zt_count": 50, "zb_count": 5, "dt_count": 3, "break_rate": 9.1,
        "promo_rate": 20.0, "max_height": 4,
        "contributions": {"zt": 30, "height": 10, "promo": 0, "break": 0, "dt": 0},
    }


_TREND_3D = [_trend_row("20240902", 55, "正常"),
             _trend_row("20240903", 60, "正常"),
             _trend_row("20240904", 65, "偏热")]


@pytest.fixture
def patch_sentiment(monkeypatch):
    """把 sentiment.get_sentiment 打桩（返回可配置的实时情绪）。"""
    holder = {"value": _sent(), "calls": []}

    def _fake():
        holder["calls"].append(1)
        if isinstance(holder["value"], Exception):
            raise holder["value"]
        return dict(holder["value"])

    monkeypatch.setattr(sentiment, "get_sentiment", _fake)
    return holder


@pytest.fixture
def patch_trend(monkeypatch):
    """把 emotion_history.get_emotion_trend 打桩（历史序列）。"""
    holder = {"value": [dict(r) for r in _TREND_3D], "calls": []}

    def _fake(days=15, force=False):
        holder["calls"].append((days, force))
        return [dict(r) for r in holder["value"]]

    monkeypatch.setattr(emotion_history, "get_emotion_trend", _fake)
    return holder


# ══════════════════════════════════════════════════════
# 1. /api/market_distribution
# ══════════════════════════════════════════════════════

def _stk(symbol, pct):
    """按 screener._normalize_stock_rows 的产物结构造一只股票。

    注意 change_pct 在真实数据里由 _safe_float 产出，恒为 float（不会为 None）。
    """
    return {"code": symbol, "pure_code": symbol[2:], "name": "T" + symbol[2:],
            "market": symbol[:2], "price": 10.0, "change_pct": pct,
            "amount_yi": 1.23, "turnover_pct": 1.5}


@pytest.fixture
def patch_stock_list(monkeypatch):
    holder = {"stocks": [], "meta": {}}

    def _fake_meta(force=False):
        holder["force"] = force
        meta = {"degraded": False, "count": len(holder["stocks"]),
                "fetched_at": 0.0, "reason": "", "valid": True, "stale": False}
        meta.update(holder.get("meta") or {})
        return holder["stocks"], meta

    def _fake(force=False):
        holder["force"] = force
        return holder["stocks"]

    # app.py 里是 `screener.load_stock_list_meta(...)` / `screener.load_stock_list(...)`
    # （模块属性），故 patch 源头即有效
    monkeypatch.setattr(screener, "load_stock_list_meta", _fake_meta)
    monkeypatch.setattr(screener, "load_stock_list", _fake)
    return holder


def test_market_distribution_range_boundaries(client, patch_stock_list):
    """9 个区间的边界值各归其位 —— 含 0.001 / -0.001 这组刻意设计。

    归类用的是「从高到低级联判断」而非 ranges 里的 min/max 字段，
    所以 -2.0 落在「-2~0%」而不是「-5~-2%」（后者实际是开区间）。
    """
    cases = [(7.0, 0), (6.99, 1), (5.0, 1), (2.0, 2), (0.001, 3), (0.0, 4),
             (-0.001, 5), (-2.0, 5), (-5.0, 6), (-7.0, 7), (-7.1, 8)]

    patch_stock_list["stocks"] = [_stk("sh6000%02d" % i, pct)
                                  for i, (pct, _) in enumerate(cases)]

    body = client.get("/api/market_distribution").get_json()

    expected = [0] * 9
    for _, idx in cases:
        expected[idx] += 1

    assert [r["count"] for r in body["ranges"]] == expected
    assert body["total"] == len(cases)
    assert sum(expected) == len(cases), "每只股票必须只计入一个区间"


def test_market_distribution_limit_counts(client, patch_stock_list):
    """涨停/跌停家数按三档阈值判定（主板 9.8 / 创业板科创板 19.5 / 北交所 29.5）。"""
    patch_stock_list["stocks"] = [
        _stk("sh600000", 10.0),    # 主板涨停
        _stk("sz300001", 20.0),    # 创业板涨停
        _stk("sh688001", 20.0),    # 科创板涨停
        _stk("bj430001", 30.0),    # 北交所涨停
        _stk("sh600001", 9.7),     # 差一点，不算
        _stk("sh600002", -10.0),   # 主板跌停
        _stk("sz300002", -19.6),   # 创业板跌停
        _stk("sh600003", -9.7),    # 差一点，不算
        _stk("sh600004", 0.0),     # 平盘
    ]

    body = client.get("/api/market_distribution").get_json()

    assert body["zt_count"] == 4
    assert body["dt_count"] == 2
    assert body["up_count"] == 5      # 10.0 / 20.0 / 20.0 / 30.0 / 9.7
    assert body["down_count"] == 3    # -10.0 / -19.6 / -9.7
    assert body["total"] == 9


def test_market_distribution_passes_force(client, patch_stock_list):
    """?force=1 应透传给清单拉取（决定是否强制刷新股票池缓存）。"""
    patch_stock_list["stocks"] = [_stk("sh600000", 1.0)]

    client.get("/api/market_distribution?force=1")
    assert patch_stock_list["force"] is True

    client.get("/api/market_distribution")
    assert patch_stock_list["force"] is False


# ══════════════════════════════════════════════════════
# 2. /api/emotion_trend
# ══════════════════════════════════════════════════════

_LATEST_FIELDS = ("score", "level", "date", "trade_date", "zt_count", "dt_count",
                  "zb_count", "break_rate", "promo_rate", "max_height",
                  "contributions", "history_scores", "history_labels", "prev_score")

_TOP_FIELDS = ("dates", "labels", "scores", "zt_count", "dt_count", "break_rate",
               "promo_rate", "max_height", "levels", "contributions",
               "indexes", "latest")


def test_emotion_trend_response_shape(client, patch_trend, patch_sentiment, stub_kline):
    """顶层字段与 latest 的字段清单必须齐全（前端 4 张卡片依赖它们）。"""
    stub_kline.put("sh000001", [100.0, 101.0, 102.0], start="2024-09-02")

    body = client.get("/api/emotion_trend").get_json()

    for key in _TOP_FIELDS:
        assert key in body, "缺少顶层字段 %s" % key
    for key in _LATEST_FIELDS:
        assert key in body["latest"], "latest 缺少字段 %s" % key

    assert body["dates"] == ["20240902", "20240903", "20240904"]
    assert body["scores"] == [55, 60, 65]
    assert body["levels"] == ["正常", "正常", "偏热"]


def test_emotion_trend_latest_overridden_by_realtime(client, patch_trend, patch_sentiment):
    """latest 必须被实时情绪覆盖，不能沿用历史序列的最后一条。"""
    body = client.get("/api/emotion_trend").get_json()

    assert body["latest"]["score"] == 88          # 实时值，而非 trend[-1] 的 65
    assert body["latest"]["level"] == "过热"
    assert body["latest"]["zt_count"] == 150
    assert body["latest"]["trade_date"] == "20240902"
    assert body["latest"]["date"] == "20240902"


def test_emotion_trend_index_overlay_normalized(client, patch_trend, patch_sentiment, stub_kline):
    """指数叠加：按序列首个非零值归一化，首值恒为 100，等差收盘可手算。"""
    stub_kline.put("sh000001", [100.0, 101.0, 102.0], start="2024-09-02")
    stub_kline.put("sh000905", [200.0, 210.0, 220.0], start="2024-09-02")

    body = client.get("/api/emotion_trend").get_json()

    by_name = {x["name"]: x["values"] for x in body["indexes"]}
    assert by_name["上证指数"] == [100.0, 101.0, 102.0]
    assert by_name["中证500"] == [100.0, 105.0, 110.0]
    # 未登记桩数据的指数应被跳过，而不是让接口报错
    assert len(body["indexes"]) == 2
    assert stub_kline.kline_calls(), "指数叠加必须真的去取过 K 线（否则用例失去意义）"


def test_emotion_trend_all_history_requests_1000_bars(client, patch_trend, patch_sentiment, stub_kline):
    """days<=0（全部历史）时，指数 K 线按接口上限 1000 根请求。"""
    client.get("/api/emotion_trend?days=0")

    assert stub_kline.kline_calls(), "应发起过 K 线请求"
    assert all(days == 1000 for _, days in stub_kline.kline_calls())


def test_emotion_trend_single_point_duplicated(client, patch_trend, patch_sentiment):
    """历史只有 1 个点时，history_scores 复制为 2 个相同点（ECharts 单点不画线的既有修复）。

    注意这里的 date 用带横线的格式：实时情绪的 trade_date 归一化后是 YYYY-MM-DD，
    只有两者相等才不会"因补当天数据"而变成 2 个点 —— 那样就测不到单点复制这条分支了。
    """
    patch_trend["value"] = [{
        "date": "2024-09-02", "label": "09-02", "score": 65, "level": "偏热",
        "zt_count": 50, "zb_count": 5, "dt_count": 3, "break_rate": 9.1,
        "promo_rate": 20.0, "max_height": 4, "contributions": {},
    }]

    body = client.get("/api/emotion_trend").get_json()

    hs = body["latest"]["history_scores"]
    assert len(hs) == 2
    assert hs[0] == hs[1] == 65
    assert len(body["latest"]["history_labels"]) == 2


def test_emotion_trend_survives_index_failure(client, patch_trend, patch_sentiment, stub_kline):
    """所有指数都取数失败时，indexes 为空但接口仍返回 200。"""
    resp = client.get("/api/emotion_trend")

    assert resp.status_code == 200
    assert resp.get_json()["indexes"] == []


def test_emotion_trend_survives_sentiment_failure(client, patch_trend, patch_sentiment):
    """实时情绪计算失败时，latest 回退为历史序列最后一条，接口仍 200。"""
    patch_sentiment["value"] = RuntimeError("实时情绪不可用")

    resp = client.get("/api/emotion_trend")

    assert resp.status_code == 200
    latest = resp.get_json()["latest"]
    assert latest["score"] == 65      # trend[-1] 的值
    assert latest["level"] == "偏热"


# ══════════════════════════════════════════════════════
# 3. /api/emotion_low_next
# ══════════════════════════════════════════════════════

def _patch_low_points(monkeypatch, lows, calls=None):
    def _fake(threshold, days):
        if calls is not None:
            calls.append((threshold, days))
        return [dict(x) for x in lows]
    monkeypatch.setattr(emotion_history, "get_low_points", _fake)


def test_emotion_low_next_return_is_hand_computable(client, monkeypatch, stub_kline):
    """冰点日次日收益 = (次日收盘 / 当日收盘 - 1) * 100，用等差收盘可手算。"""
    _patch_low_points(monkeypatch, [{"date": "20240902", "score": 20}])
    stub_kline.put_range("sh000001", [100.0, 101.0, 103.0], start="2024-09-02")

    body = client.get("/api/emotion_low_next").get_json()

    sh = next(x for x in body["indexes"] if x["name"] == "上证指数")
    assert sh["items"] == [{"date": "20240902", "next_date": "20240903", "ret": 1.0}]
    assert sh["stats"] == {"n": 1, "avg": 1.0, "win_rate": 100.0}
    assert body["low_dates"] == ["20240902"]
    assert body["low_scores"] == [20]
    assert body["threshold"] == 30
    assert stub_kline.range_calls(), "应通过 kline_range 取指数全量日 K"


def test_emotion_low_next_without_next_day(client, monkeypatch, stub_kline):
    """冰点日没有次一交易日时 ret 为 None，且不计入 n / avg / win_rate。"""
    _patch_low_points(monkeypatch, [{"date": "20240902", "score": 20}])
    stub_kline.put_range("sh000001", [100.0], start="2024-09-02")   # 只有一天

    body = client.get("/api/emotion_low_next").get_json()

    sh = next(x for x in body["indexes"] if x["name"] == "上证指数")
    assert sh["items"] == [{"date": "20240902", "next_date": None, "ret": None}]
    # n == 0 时 avg / win_rate 必须是 None，不能是 0
    assert sh["stats"] == {"n": 0, "avg": None, "win_rate": None}


def test_emotion_low_next_win_rate_rounding(client, monkeypatch, stub_kline):
    """3 个样本中 2 个上涨 → 胜率 66.7（保留 1 位）；均值保留 2 位。"""
    _patch_low_points(monkeypatch, [{"date": "20240902", "score": 10},
                                    {"date": "20240903", "score": 15},
                                    {"date": "20240904", "score": 20}])
    # 20240902→0903: 100→101 (+1.0)；0903→0904: 101→100 (-0.99)；0904→0905: 100→103 (+3.0)
    stub_kline.put_range("sh000001", [100.0, 101.0, 100.0, 103.0], start="2024-09-02")

    body = client.get("/api/emotion_low_next").get_json()

    sh = next(x for x in body["indexes"] if x["name"] == "上证指数")
    assert [it["ret"] for it in sh["items"]] == [1.0, -0.99, 3.0]
    assert sh["stats"]["n"] == 3
    assert sh["stats"]["avg"] == 1.0          # (1.0 - 0.99 + 3.0) / 3 = 1.0033 → 1.0
    assert sh["stats"]["win_rate"] == 66.7    # 2 / 3


def test_emotion_low_next_passes_threshold_and_days(client, monkeypatch, stub_kline):
    """threshold / days 查询参数应原样传给冰点日检索。"""
    calls = []
    _patch_low_points(monkeypatch, [], calls=calls)

    client.get("/api/emotion_low_next?threshold=45&days=30")

    assert calls == [(45, 30)]


def test_emotion_low_next_cache_keyed_by_params(client, monkeypatch, stub_kline):
    """600 秒缓存按 (threshold, days) 分桶：同参数命中，异参数不命中。"""
    calls = []
    _patch_low_points(monkeypatch, [], calls=calls)

    client.get("/api/emotion_low_next")
    client.get("/api/emotion_low_next")
    assert len(calls) == 1, "同参数第二次应命中缓存"

    client.get("/api/emotion_low_next?threshold=40")
    assert len(calls) == 2, "参数不同不应命中同一份缓存"


# ══════════════════════════════════════════════════════
# 4. /api/index_compare
# ══════════════════════════════════════════════════════

def test_index_compare_normalized_series(client, stub_kline):
    """4 指数归一化到首值 100，等差收盘可手算。"""
    for code in ("sh000001", "sz399001", "sz399006", "sh000300"):
        stub_kline.put(code, [100.0, 102.0, 104.0], start="2024-09-02")

    body = client.get("/api/index_compare").get_json()

    assert body["dates"] == ["20240902", "20240903", "20240904"]
    assert [s["name"] for s in body["series"]] == \
        ["上证指数", "深证成指", "创业板指", "沪深300"]
    for s in body["series"]:
        assert s["values"] == [100.0, 102.0, 104.0]


def test_index_compare_uses_date_intersection(client, stub_kline):
    """只保留 4 个指数都有数据的日期（取交集）。"""
    stub_kline.put("sh000001", [100.0, 101.0, 102.0, 103.0], start="2024-09-01")  # 0901-0904
    stub_kline.put("sz399001", [100.0, 101.0, 102.0, 103.0], start="2024-09-02")  # 0902-0905
    stub_kline.put("sz399006", [100.0, 101.0, 102.0], start="2024-09-03")         # 0903-0905
    stub_kline.put("sh000300", [100.0, 101.0, 102.0], start="2024-09-02")         # 0902-0904

    body = client.get("/api/index_compare").get_json()

    # 四个日期集合的交集 = {0903, 0904}
    assert body["dates"] == ["20240903", "20240904"]


def test_index_compare_normalizes_days_before_fetch(client, stub_kline):
    """days 只接受 15/30/60，非法值（45）按 60 处理 —— 在请求 K 线之前就完成规范化。"""
    client.get("/api/index_compare?days=45")

    assert stub_kline.kline_calls(), "应发起过 K 线请求"
    # days + 10 的既有约定：60 → 70
    assert all(days == 70 for _, days in stub_kline.kline_calls())


def test_index_compare_skips_failed_index(client, stub_kline):
    """某个指数取数失败时，该系列缺席，其余指数正常返回。"""
    for code in ("sz399001", "sz399006", "sh000300"):
        stub_kline.put(code, [100.0, 101.0], start="2024-09-02")
    # sh000001 不登记 → 抛异常 → 应被跳过

    resp = client.get("/api/index_compare")

    assert resp.status_code == 200
    names = [s["name"] for s in resp.get_json()["series"]]
    assert names == ["深证成指", "创业板指", "沪深300"]


# ══════════════════════════════════════════════════════
# 5. /api/overview
# ══════════════════════════════════════════════════════

_OVERVIEW_FIELDS = ("trade_date", "index_order", "indexes", "sentiment", "ladder",
                    "zt_pool", "zb_pool", "dt_pool", "boards")


@pytest.fixture
def patch_market_pools(monkeypatch):
    """把 overview 用到的 market 取数函数全部打桩，并记录调用次数。"""
    calls = {"indexes": 0, "boards": 0, "zt": 0}
    zt = [{"code": "sh600000", "name": "甲", "limit_days": 1},
          {"code": "sh600001", "name": "乙", "limit_days": 2},
          {"code": "sh600002", "name": "丙", "limit_days": 2}]

    def _f_indexes():
        calls["indexes"] += 1
        return [{"code": "sh000001", "name": "上证指数", "price": 3000.0}]

    def _f_boards():
        calls["boards"] += 1
        return [{"name": "林业Ⅲ", "pct": 5.83}]

    def _f_zt(date):
        calls["zt"] += 1
        return [dict(x) for x in zt]

    monkeypatch.setattr(market, "get_indexes", _f_indexes)
    monkeypatch.setattr(market, "get_boards", _f_boards)
    monkeypatch.setattr(market, "get_zt_pool", _f_zt)
    monkeypatch.setattr(market, "get_zb_pool", lambda date: [])
    monkeypatch.setattr(market, "get_dt_pool", lambda date: [])
    return calls


def test_overview_response_shape_and_ladder(client, patch_trend, patch_sentiment,
                                            patch_market_pools):
    """顶层字段齐全；ladder 按涨停池的连板高度汇总。"""
    body = client.get("/api/overview").get_json()

    for key in _OVERVIEW_FIELDS:
        assert key in body, "缺少字段 %s" % key
    assert body["trade_date"] == "2024-09-02"     # YYYYMMDD → YYYY-MM-DD
    assert body["index_order"] == market.INDEX_CODES
    assert body["ladder"] == [{"days": 1, "count": 1}, {"days": 2, "count": 2}]
    assert body["sentiment"]["score"] == 88


def test_overview_caches_expensive_parts(client, patch_trend, patch_sentiment,
                                         patch_market_pools):
    """60 秒缓存：板块/指数等重活第二次不再重复执行。"""
    client.get("/api/overview")
    client.get("/api/overview")

    assert patch_market_pools["boards"] == 1
    assert patch_market_pools["indexes"] == 1


def test_overview_sentiment_always_realtime(client, patch_trend, patch_sentiment,
                                            patch_market_pools):
    """情绪分必须每次实时计算，即使其它字段命中了 60 秒缓存。"""
    client.get("/api/overview")
    client.get("/api/overview")

    assert len(patch_sentiment["calls"]) == 2


def test_overview_force_bypasses_cache(client, patch_trend, patch_sentiment,
                                       patch_market_pools):
    """/api/overview?force=1 应绕过缓存重新取数。"""
    client.get("/api/overview")
    client.get("/api/overview?force=1")

    assert patch_market_pools["boards"] == 2
