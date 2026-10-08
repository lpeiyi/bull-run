# -*- coding: utf-8 -*-
"""core/em_api.py 的离线用例：全局限流 + 池结果进程内缓存。

需求见 specs/cut-sentiment-latency/（AC-1.1 / AC-2.1 / AC-2.2 / AC-2.3 / AC-4.1 / AC-5.1）。

全部脱网：`_SESSION.get` 换成内存假接口并逐次记录 `(endpoint, date, sort)` 与发生时刻；
`em_api.time` 整体换成可推进的假时钟，从而不断言"真实耗时"而断言"请求间隔"。
conftest 的 `_no_network` 已阻断一切 socket，一旦有真实请求会立刻失败。
"""
import threading

import pytest

from core import em_api


# ── 假接口 ────────────────────────────────────────────

class _Resp:
    def __init__(self, pool):
        self._pool = pool

    def json(self):
        return {"data": {"pool": self._pool}}


class _Clock:
    """可推进的假时钟（替换 em_api.time，只提供它用到的 time() / sleep()）。"""

    def __init__(self, t0=1000.0):
        self.now = t0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


class _Em:
    """假的东财池接口：记录请求三元组与时刻，可按日期配置返回内容或抛异常。"""

    def __init__(self, clock, pools=None, fail_dates=()):
        self.clock = clock
        self.pools = dict(pools or {})
        self.fail_dates = set(fail_dates)
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        params = params or {}
        key = (url.rsplit("/", 1)[-1], params.get("date"), params.get("sort"))
        self.calls.append((key, self.clock.now))
        if params.get("date") in self.fail_dates:
            raise RuntimeError("simulated network error")
        return _Resp(self.pools.get(params.get("date"), [{"c": "600000"}]))


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(em_api, "time", c)
    em_api.reset_state()
    yield c
    em_api.reset_state()


@pytest.fixture
def em(clock, monkeypatch):
    fake = _Em(clock)
    monkeypatch.setattr(em_api._SESSION, "get", fake)
    return fake


# ══════════════════════════════════════════════════════
# 1. 池结果缓存（AC-2.1 / AC-2.2 / AC-2.3）
# ══════════════════════════════════════════════════════

def test_same_key_within_ttl_requests_once(em):
    """TTL 内同 key 只发 1 次真实请求。"""
    em_api.pool("getTopicZTPool", "20260929")
    em_api.pool("getTopicZTPool", "20260929")

    assert len(em.calls) == 1


def test_key_expires_after_ttl(clock, em):
    """超过 TTL 后重新请求。"""
    em_api.pool("getTopicZTPool", "20260929")
    clock.now += em_api.POOL_TTL + 0.1
    em_api.pool("getTopicZTPool", "20260929")

    assert len(em.calls) == 2


def test_different_date_does_not_hit_cache(em):
    """AC-2.2：date 参与 key，跨交易日天然失效（无需额外代码）。"""
    em_api.pool("getTopicZTPool", "20260929")
    em_api.pool("getTopicZTPool", "20260928")

    assert len(em.calls) == 2


def test_different_sort_does_not_hit_cache(em):
    """sort 参与 key：昨日涨停池用 zs:desc，不能与 fbt:asc 混用。"""
    em_api.pool("getTopicZTPool", "20260929", sort="fbt:asc")
    em_api.pool("getTopicZTPool", "20260929", sort="zs:desc")

    assert len(em.calls) == 2


def test_failure_not_cached(clock, monkeypatch):
    """AC-2.3：请求失败不写缓存，也不把失败缓存成"空池"。"""
    fake = _Em(clock, fail_dates={"20260929"})
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    assert em_api.pool("getTopicZTPool", "20260929") == []
    fake.fail_dates = set()                       # 第 2 次改为成功
    assert em_api.pool("getTopicZTPool", "20260929") != []

    assert len(fake.calls) == 2


def test_clear_cache_forces_refetch(em):
    em_api.pool("getTopicZTPool", "20260929")
    assert em_api.cache_info()["entries"] == 1

    em_api.clear_cache()
    assert em_api.cache_info()["entries"] == 0

    em_api.pool("getTopicZTPool", "20260929")
    assert len(em.calls) == 2


# ══════════════════════════════════════════════════════
# 2. 红线：当日空池不缓存（AC-4.1）
# ══════════════════════════════════════════════════════

def test_today_empty_pool_is_not_cached(clock, monkeypatch):
    """当日空池可能是"今天还没涨停"这个会变的中间态 —— 不得缓存。"""
    today = em_api._today()
    fake = _Em(clock, pools={today: []})
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    assert em_api.pool("getTopicZTPool", today) == []
    assert em_api.pool("getTopicZTPool", today) == []

    assert len(fake.calls) == 2, "当日空池被缓存了：交易日探测会因此滞后"


def test_past_empty_pool_is_cached(clock, monkeypatch):
    """非当日空池是"非交易日 / 历史无数据"的稳定事实 —— 照常缓存。"""
    fake = _Em(clock, pools={"20260929": []})
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    em_api.pool("getTopicZTPool", "20260929")
    em_api.pool("getTopicZTPool", "20260929")

    assert len(fake.calls) == 1


# ══════════════════════════════════════════════════════
# 3. 全局限流（AC-1.1）
# ══════════════════════════════════════════════════════

def test_min_interval_has_meaningful_floor():
    """防封底线：最小间隔必须显著大于 0，否则"限流"名存实亡。

    刻意用**字面量**而非引用常量 —— 引用常量会让断言随常量一起变成 0，
    退化成恒真断言（`0 >= 0`），常量被改坏时用例照样全绿。
    """
    assert em_api.EM_MIN_INTERVAL >= 0.3, "限流间隔被调到过小，防封约束失效"


def test_global_min_interval_between_requests(em):
    """相邻两次真实请求的时间差 ≥ 0.3s 下限（不依赖真实耗时）。"""
    em_api.pool("getTopicZTPool", "20260929")
    em_api.pool("getTopicZTPool", "20260928")

    assert len(em.calls) == 2
    gap = em.calls[1][1] - em.calls[0][1]
    assert gap >= 0.3, "相邻请求间隔未达防封下限（限流实际未生效）"


def test_interval_is_global_not_per_module(clock, monkeypatch):
    """限流时间戳全局唯一：screener 之外的第二个调用方不能"另起一份配额"。"""
    fake = _Em(clock)
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    em_api.pool("getTopicZTPool", "20260929")      # 模拟 sentiment
    em_api.pool("getTopicZBPool", "20260929")      # 模拟 market

    assert len(fake.calls) == 2
    assert fake.calls[1][1] - fake.calls[0][1] >= 0.3, "跨模块共享配额失效"


def test_cache_info_reports_intervals(clock, em):
    info = em_api.cache_info()

    assert info["base_interval"] == em_api.EM_MIN_INTERVAL
    assert info["interval"] == em_api.EM_MIN_INTERVAL
    assert info["ttl"] == em_api.POOL_TTL
    assert info["entries"] == 0


# ══════════════════════════════════════════════════════
# 4. 并发 single-flight
# ══════════════════════════════════════════════════════

def test_concurrent_same_key_fetches_once(em):
    """同 key 并发：8 个线程只应产生 1 次真实请求（缓存命中判断在锁内）。"""
    errs = []

    def _work():
        try:
            em_api.pool("getTopicZTPool", "20260929")
        except Exception as e:            # pragma: no cover - 失败时给出可读信息
            errs.append(e)

    threads = [threading.Thread(target=_work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errs == []
    assert len(em.calls) == 1


# ══════════════════════════════════════════════════════
# 5. 失败自适应降速（design §1.3(f)）
# ══════════════════════════════════════════════════════

def test_backoff_on_failures_and_recovery(clock, monkeypatch):
    fake = _Em(clock, fail_dates={"20260929"})
    monkeypatch.setattr(em_api._SESSION, "get", fake)

    for _ in range(em_api.EM_BACKOFF_STREAK):
        em_api.pool("getTopicZTPool", "20260929")     # 失败不缓存 ⇒ 每次都真请求

    assert em_api.cache_info()["interval"] == pytest.approx(em_api.EM_MIN_INTERVAL * 2)

    fake.fail_dates = set()
    for i in range(em_api.EM_RECOVER_STREAK):        # 用不同 key 确保每次都真请求
        em_api.pool("getTopicZTPool", "202608%02d" % (i + 1))

    assert em_api.cache_info()["interval"] == em_api.EM_MIN_INTERVAL
