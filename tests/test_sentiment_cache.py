# -*- coding: utf-8 -*-
"""情绪分取值路径的离线用例（specs/cut-sentiment-latency/）。

验证三件事：

1. 一次 `get_sentiment()` 内不再对同一 `(endpoint, date, sort)` 重复请求（AC-1.1 / AC-1.2）
2. 红线：**当日空池不缓存**，`trade_date` 不会因缓存滞后（AC-4.1）
3. 情绪分路径不再被全市场快照拉取阻塞 —— 改走只读 `peek_stock_list`（AC-3.1 / AC-3.2 / AC-3.3）

全部脱网：东财池接口换成内存假接口并记录请求三元组；乐咕数据置空以强制走
「东财 + 新浪」回退路径；「今天」冻结到 2026-09-30（周三）以便稳定复现交易日探测。
"""
import json
import time
from datetime import datetime

import pytest

from core import em_api, screener, sentiment

# 冻结的「今天」：2026-09-30（周三，交易日）
FROZEN = datetime(2026, 9, 30, 10, 0, 0)
FROZEN_YMD = "20260930"
PREV_YMD = "20260929"          # 上一交易日（周二）


# ── 假接口 ────────────────────────────────────────────

class _Resp:
    def __init__(self, pool):
        self._pool = pool

    def json(self):
        return {"data": {"pool": self._pool}}


class _Em:
    """假的东财池接口：记录 `(endpoint, date, sort)` 序列，按日期返回配置内容。"""

    def __init__(self, zt_by_date=None, dt_pool=None, default_zt=None):
        self.zt = dict(zt_by_date or {})
        self.dt = list(dt_pool or [])
        self.default_zt = (default_zt if default_zt is not None
                           else [{"c": "600000", "lbc": 2, "n": "浦发银行"}])
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        params = params or {}
        endpoint = url.rsplit("/", 1)[-1]
        date = params.get("date")
        self.calls.append((endpoint, date, params.get("sort")))
        if endpoint == "getTopicZTPool":
            return _Resp(self.zt.get(date, self.default_zt))
        if endpoint == "getTopicDTPool":
            return _Resp(self.dt)
        return _Resp([])          # 炸板池 / 昨日涨停池：空


def _rows(n, dt_n=0, price=10.0):
    """构造归一化后的股票行（与 screener._normalize_stock_rows 产出的字段一致）。"""
    out = []
    for i in range(n):
        code = "%06d" % (600000 + i)
        out.append({
            "code": "sh" + code, "pure_code": code, "market": "sh",
            "name": "N" + code, "price": price,
            "change_pct": -10.05 if i < dt_n else 1.0,
        })
    return out


def _write_list_cache(stocks, ts=None, **kw):
    payload = {"ts": time.time() if ts is None else ts,
               "version": 3, "complete": True, "valid": True, "stocks": stocks}
    payload.update(kw)
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _boom(*a, **k):
    raise AssertionError("该路径不应发起请求")


# ── 夹具 ──────────────────────────────────────────────

@pytest.fixture
def frozen(monkeypatch):
    """把「今天」冻结到 2026-09-30：让交易日探测与 TTL 判定可稳定复现。"""
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 30, 10, 0, 0)

    monkeypatch.setattr(sentiment, "datetime", _DT)
    monkeypatch.setattr(em_api, "datetime", _DT)   # `_today()` 需与 sentiment 同一天


@pytest.fixture
def iso(monkeypatch, tmp_path):
    """隔离环境：临时清单文件 + 无乐咕数据（强制走东财 + 新浪回退路径）。"""
    monkeypatch.setattr(screener, "_LIST_FILE", str(tmp_path / "stock_list.json"))
    monkeypatch.setattr(sentiment.legu, "fetch_legu_history", lambda: [])
    return tmp_path


@pytest.fixture
def em(monkeypatch):
    fake = _Em()
    monkeypatch.setattr(em_api._SESSION, "get", fake)
    return fake


# ══════════════════════════════════════════════════════
# 1. 请求去重（AC-1.1 / AC-1.2）
# ══════════════════════════════════════════════════════

def test_get_sentiment_has_no_duplicate_requests(iso, frozen, em):
    """探测交易日拿到的涨停池被主体复用，不再拉第二次同参数请求。"""
    r = sentiment.get_sentiment()

    assert r["trade_date"] == FROZEN_YMD
    assert len(em.calls) == len(set(em.calls)), "出现重复请求：%s" % (em.calls,)
    # 涨停池（探测）只请求一次 —— 这就是改造前白付的那 1.25 秒
    assert em.calls.count(("getTopicZTPool", FROZEN_YMD, "fbt:asc")) == 1
    # 4 次真实请求：ZT(探测) / YesterdayZT(zs:desc) / ZB / DT
    assert len(em.calls) == 4


def test_sentiment_result_fields_unchanged(iso, frozen, em):
    """AC-2.5 / AC-5.2：响应字段集合不因本轮改动增减。"""
    r = sentiment.get_sentiment()

    assert set(r.keys()) == {
        "score", "level", "trade_date", "zt_count", "dt_count", "zb_count",
        "break_rate", "promo_rate", "max_height", "contributions",
    }


# ══════════════════════════════════════════════════════
# 2. 红线：当日空池不缓存（AC-4.1）
# ══════════════════════════════════════════════════════

def test_today_empty_pool_reprobed_on_every_call(iso, frozen, monkeypatch):
    """当日空池是「会变的中间态」：不得缓存，否则 trade_date 会滞后一整天。"""
    fake = _Em(zt_by_date={FROZEN_YMD: []})     # 当日空；上一交易日走默认非空池
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    r1 = sentiment.get_sentiment()
    r2 = sentiment.get_sentiment()

    assert r1["trade_date"] == PREV_YMD
    assert r2["trade_date"] == PREV_YMD
    probes = [c for c in fake.calls if c == ("getTopicZTPool", FROZEN_YMD, "fbt:asc")]
    assert len(probes) == 2, "当日空池被缓存了：一旦盘中出现首只涨停，trade_date 会滞后"


def test_pool_cache_does_not_cross_trade_date(iso, frozen, monkeypatch):
    """AC-4.3：date 参与缓存 key，跨交易日天然失效（零代码）。"""
    fake = _Em()
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    em_api.pool("getTopicZTPool", FROZEN_YMD)
    em_api.pool("getTopicZTPool", PREV_YMD)

    assert len(fake.calls) == 2


# ══════════════════════════════════════════════════════
# 3. 不再被全市场快照阻塞（AC-3.1 / AC-3.2 / AC-3.3）
# ══════════════════════════════════════════════════════

def test_dt_count_uses_snapshot_without_any_request(iso, frozen, monkeypatch):
    """有可用快照时走新浪分档口径（与涨跌统计图同口径），且不发起任何请求。"""
    _write_list_cache(_rows(2000, dt_n=2))
    monkeypatch.setattr(em_api._SESSION, "get", _boom)
    monkeypatch.setattr(screener, "load_stock_list", _boom)

    assert sentiment._dt_count(FROZEN_YMD) == 2


def test_dt_count_falls_back_to_em_without_snapshot(iso, frozen, monkeypatch):
    """无可用快照时回退东财跌停池，而不是主动发起一次全市场拉取（AC-3.2）。"""
    fake = _Em(dt_pool=[{"c": "600001"}, {"c": "600002"}, {"c": "600003"}])
    monkeypatch.setattr(em_api._SESSION, "get", fake)
    monkeypatch.setattr(screener, "load_stock_list", _boom)
    monkeypatch.setattr(screener, "load_stock_list_meta", _boom)

    assert sentiment._dt_count(FROZEN_YMD) == 3


def test_dt_list_sina_returns_none_without_snapshot(iso, frozen, monkeypatch):
    monkeypatch.setattr(screener, "load_stock_list", _boom)

    assert sentiment._dt_list_sina() is None


def test_filter_zt_pool_degrades_without_snapshot(iso, frozen, monkeypatch):
    """无快照：保持既有降级（返回原列表、不过滤）。"""
    monkeypatch.setattr(screener, "load_stock_list", _boom)

    assert sentiment._filter_zt_pool(["600000", "600001"]) == ["600000", "600001"]


def test_filter_zt_pool_works_on_preopen_junk_snapshot(iso, frozen):
    """盘前废快照（price 全为 0、valid=False）里「行是全的」，取名称做 ST 过滤完全够用。

    这正是 `require_valid=False` 的意义 —— 若沿用默认要求，会退化成「不过滤」。
    """
    rows = _rows(2000, price=0.0)
    # 注意：_rows 生成的 pure_code 覆盖 600000~601999，故 ST 样例必须取该区间之外的号段，
    # 否则会与内置行撞码、被字典推导的后者覆盖（即"看起来没过滤"的假象）。
    rows[0]["pure_code"], rows[0]["name"] = "300001", "ST某某"
    rows[1]["pure_code"], rows[1]["name"] = "300002", "*ST某某"
    _write_list_cache(rows, valid=False)          # 无效快照（盘前形态）

    out = sentiment._filter_zt_pool(["300001", "300002", "300003"])

    assert out == ["300003"]


def test_filter_zt_pool_default_requires_valid_snapshot(iso, frozen):
    """对照：同一份废快照在「要求有效」的读者眼里是不可用的。"""
    rows = _rows(2000, price=0.0)
    _write_list_cache(rows, valid=False)

    assert screener.peek_stock_list() == (None, None)
    assert screener.peek_stock_list(require_valid=False)[0] is not None
