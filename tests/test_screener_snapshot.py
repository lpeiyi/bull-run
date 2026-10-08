# -*- coding: utf-8 -*-
"""全市场行情快照的「时效 + 有效性」回归测试。

需求见 specs/fix-stocklist-snapshot-freshness/。全部离线：
- `_sina_get` 换成内存假接口（并记录请求过的页）
- `time.sleep` 置空，避免真的等退避
- 时钟用注入的假 time 模块控制，从而可稳定复现「盘前 09:20」等时段
"""
import json
import threading
from datetime import datetime

import pytest

from core import screener


# ── 构造助手 ──────────────────────────────────────────

def _mk_item(symbol, trade="10.00", changepercent="1.23"):
    """构造一条新浪原始条目。

    `changepercent` 一律非零 —— 这正是盘前废快照的真实形态：
    trade 被重置为 0，但涨跌幅还残留着上一交易日的值。
    """
    return {
        "symbol": symbol,
        "code": symbol[2:],
        "name": "N" + symbol,
        "trade": trade,
        "changepercent": changepercent,
        "amount": "123000000",
        "turnoverratio": "1.50",
        "per": "20.0",
        "mktcap": "123456.78",
        "nmc": "100000.00",
    }


def _items(total, zero_ratio=0.0):
    """生成 total 条原始条目，前 zero_ratio 比例的 trade 置 0（模拟盘前废快照）。"""
    zero_n = int(round(total * zero_ratio))
    out = []
    for i in range(total):
        market = ("sh", "sz", "bj")[i % 3]
        out.append(_mk_item("%s%06d" % (market, 600000 + i),
                            trade="0.00" if i < zero_n else "10.00"))
    return out


def _pages(items, page_size=100):
    return [items[i:i + page_size] for i in range(0, len(items), page_size)]


def _norm(total, zero_ratio=0.0):
    """归一化后的股票列表（用于构造缓存文件内容）。"""
    return screener._normalize_stock_rows(_items(total, zero_ratio))


class _Sina:
    """假的分页接口：记录请求过的页序列，支持指定页失败若干次。

    fail = {页码: 剩余失败次数}；值为 -1 表示该页永久失败。
    """

    def __init__(self, pages, fail=None):
        self.pages = pages
        self.fail = dict(fail or {})
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, node, page, num=100):
        with self._lock:
            self.calls.append(page)
            left = self.fail.get(page, 0)
            if left != 0:
                if left > 0:
                    self.fail[page] = left - 1
                raise RuntimeError("simulated network error")
        idx = page - 1
        return self.pages[idx] if idx < len(self.pages) else []


class _Clock:
    """可推进的假时钟，替换 screener.time 以稳定复现各交易时段。"""

    def __init__(self, dt):
        self.now = dt.timestamp()

    def time(self):
        return self.now

    def sleep(self, *a, **k):     # 退避不真的等待
        pass

    def advance(self, sec):
        self.now += sec


@pytest.fixture
def iso(monkeypatch, tmp_path):
    """隔离环境：临时清单文件 + 屏蔽退避等待。返回安装假接口的助手。"""
    monkeypatch.setattr(screener, "_LIST_FILE", str(tmp_path / "stock_list.json"))
    monkeypatch.setattr(screener.time, "sleep", lambda *a, **k: None)

    def _install(pages, fail=None):
        fake = _Sina(pages, fail)
        monkeypatch.setattr(screener, "_sina_get", fake)
        return fake

    return _install


@pytest.fixture
def clock(monkeypatch):
    """把 screener.time 换成假时钟，默认 2026-09-30 10:00（周三盘中）。"""
    c = _Clock(datetime(2026, 9, 30, 10, 0))
    monkeypatch.setattr(screener, "time", c)
    return c


def _write_cache(ts, stocks, **kw):
    """写入清单缓存；未给出的键不写入（便于构造 v1/v2 旧格式）。"""
    payload = {"ts": ts, "stocks": stocks}
    payload.update(kw)
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _cache_bytes():
    with open(screener._LIST_FILE, "rb") as f:
        return f.read()


def _no_fetch(monkeypatch):
    """让任何真实拉取直接失败，用来证明「走了缓存直用路径」。"""
    def _boom(*a, **k):
        raise AssertionError("不应发起网络请求")
    monkeypatch.setattr(screener, "_sina_get", _boom)


# ══════════════════════════════════════════════════════
# 1. 有效性判定（纯函数）
# ══════════════════════════════════════════════════════

@pytest.mark.parametrize("zero_n, expected", [(0, 1.0), (10, 0.9), (11, 0.89), (100, 0.0)])
def test_snapshot_valid_ratio(zero_n, expected):
    stocks = _norm(100, zero_n / 100)
    assert screener.snapshot_valid_ratio(stocks) == pytest.approx(expected)


def test_snapshot_valid_ratio_empty():
    assert screener.snapshot_valid_ratio([]) == 0.0


@pytest.mark.parametrize("zero_n, expected", [(0, True), (10, True), (11, False), (100, False)])
def test_snapshot_is_valid_threshold(zero_n, expected):
    """边界：占比恰为 90% 判有效，89% 判无效。"""
    assert screener.snapshot_is_valid(_norm(100, zero_n / 100)) is expected


def test_snapshot_is_valid_small_sample_exempt():
    """样本不足 _MIN_VALID_SAMPLE 时豁免判定（非全市场样本无统计意义）。"""
    assert screener.snapshot_is_valid(_norm(99, 1.0)) is True
    assert screener.snapshot_is_valid([]) is True


def test_invalid_judgement_ignores_change_pct():
    """盘前废快照的 change_pct 非零 —— 若按涨跌幅判定就会误判为有效。"""
    stocks = _norm(200, 0.635)
    assert all(s["change_pct"] != 0 for s in stocks)
    assert screener.snapshot_valid_ratio(stocks) == pytest.approx(0.365)
    assert screener.snapshot_is_valid(stocks) is False


# ══════════════════════════════════════════════════════
# 2. 行情窗口与 TTL 分层
# ══════════════════════════════════════════════════════

@pytest.mark.parametrize("h, m, inside", [
    (8, 59, False), (9, 14, False), (9, 15, True), (10, 0, True),
    (11, 30, True), (11, 31, False), (12, 30, False),
    (13, 0, True), (14, 59, True), (15, 0, True), (15, 1, False), (22, 0, False),
])
def test_quote_window_boundaries(h, m, inside):
    """2026-09-30 是周三。窗口 09:15~11:30、13:00~15:00（午休在窗口外）。"""
    ts = datetime(2026, 9, 30, h, m).timestamp()
    assert screener._in_quote_window(ts) is inside


def test_quote_window_excludes_weekend():
    """2026-10-03 是周六、10-04 是周日。"""
    for day in (3, 4):
        ts = datetime(2026, 10, day, 10, 0).timestamp()
        assert screener._in_quote_window(ts) is False


def test_cache_ttl_layered_by_window():
    in_win = datetime(2026, 9, 30, 10, 0).timestamp()
    lunch = datetime(2026, 9, 30, 12, 0).timestamp()
    after = datetime(2026, 9, 30, 16, 0).timestamp()

    assert screener._cache_ttl(in_win) == screener._TTL_TRADING
    assert screener._cache_ttl(lunch) == screener._TTL_IDLE
    assert screener._cache_ttl(after) == screener._TTL_IDLE
    assert screener._TTL_TRADING < screener._TTL_IDLE


def test_cache_fresh_119s_reused(iso, clock, monkeypatch):
    """窗口内 119 秒：仍新鲜 → 直用，不发请求。"""
    _write_cache(ts=clock.now - 119, stocks=_norm(200),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    _no_fetch(monkeypatch)

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert len(stocks) == 200
    assert meta["degraded"] is False
    assert meta["stale"] is False


def test_cache_expired_121s_refetched(iso, clock):
    """窗口内 121 秒：超期 → 重新拉取。"""
    _write_cache(ts=clock.now - 121, stocks=_norm(200),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    fake = iso(_pages(_items(2000)))

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert fake.calls, "超期缓存必须触发重新拉取"
    assert len(stocks) == 2000
    assert meta["degraded"] is False


def test_idle_window_11_9h_reused(iso, clock, monkeypatch):
    """收盘后（窗口外 TTL 12h）：11.9 小时仍可用。"""
    clock.now = datetime(2026, 9, 30, 16, 0).timestamp()
    _write_cache(ts=clock.now - int(11.9 * 3600), stocks=_norm(200),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    _no_fetch(monkeypatch)

    stocks, _meta = screener.load_stock_list_meta(force=False)

    assert len(stocks) == 200


def test_idle_window_12_1h_expired(iso, clock):
    """收盘后 12.1 小时（跨夜）→ 超期，重新拉取。"""
    clock.now = datetime(2026, 9, 30, 16, 0).timestamp()
    _write_cache(ts=clock.now - int(12.1 * 3600), stocks=_norm(200),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    fake = iso(_pages(_items(2000)))

    stocks, _meta = screener.load_stock_list_meta(force=False)

    assert fake.calls
    assert len(stocks) == 2000


def test_cross_session_cache_expires_after_open(iso, clock):
    """AC-2.3：昨晚 20:00 的缓存到次日上午 10:00 必须失效（无需专门的跨时段逻辑）。"""
    clock.now = datetime(2026, 9, 30, 10, 0).timestamp()
    _write_cache(ts=datetime(2026, 9, 29, 20, 0).timestamp(), stocks=_norm(2000),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    fake = iso(_pages(_items(2000)))

    stocks, _meta = screener.load_stock_list_meta(force=False)

    assert fake.calls, "跨时段的旧缓存不得继续直用"
    assert len(stocks) == 2000


# ══════════════════════════════════════════════════════
# 3. 有效性闸门：不污染、回退、空态
# ══════════════════════════════════════════════════════

def test_invalid_snapshot_not_written_and_falls_back(iso, clock):
    """完整但 price>0 仅 36.5% → 判无效、不写缓存、回退旧的有效缓存。"""
    old = _norm(200)
    _write_cache(ts=clock.now - 60, stocks=old,
                 version=screener._LIST_VERSION, complete=True, valid=True)
    before = _cache_bytes()
    iso(_pages(_items(2000, zero_ratio=0.635)))

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert meta["degraded"] is True
    assert "行情快照无效" in meta["reason"]
    assert _cache_bytes() == before, "无效快照不得覆盖已有缓存"
    assert stocks == old, "应回退到上一份有效缓存"
    assert meta["valid"] is True
    assert meta["stale"] is False


def test_invalid_snapshot_without_usable_cache_returns_empty(iso, clock):
    """无可用旧缓存 + 快照无效 → 返回空并标 degraded，不得冒充正常结果。"""
    iso(_pages(_items(2000, zero_ratio=0.635)))

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert stocks == []
    assert meta["degraded"] is True
    assert meta["valid"] is False
    assert meta["count"] == 0


def test_invalid_v2_fallback_cache_rejected(iso, clock):
    """回退路径上的 v2 旧缓存若是废数据 → 当场判定无效 → 返回空。

    若"一律放行"，升级后那份盘前写的废缓存会在回退时复活，问题原地复现。
    """
    _write_cache(ts=clock.now - 60, stocks=_norm(2000, 0.635),
                 version=2, complete=True)      # v2：无 valid 标记
    iso(_pages(_items(2000, zero_ratio=0.635)))

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert stocks == []
    assert meta["degraded"] is True
    assert meta["valid"] is False


def test_stale_flag_set_when_falling_back_to_old_snapshot(iso, clock):
    """AC-1.3 / AC-5.5：回退到「非当前时段」的旧快照须标 stale。"""
    clock.now = datetime(2026, 9, 30, 9, 0).timestamp()      # 盘前，窗口外
    old_ts = datetime(2026, 9, 29, 15, 0).timestamp()        # 昨日收盘快照
    _write_cache(ts=old_ts, stocks=_norm(2000),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    iso(_pages(_items(100)), fail={1: -1})                   # 拉取失败

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert len(stocks) == 2000
    assert meta["degraded"] is True
    assert meta["stale"] is True
    assert "回退" in meta["reason"]


def test_v3_cache_marked_invalid_is_not_reused(iso, clock):
    """防御性分支：v3 缓存带 valid=false → 不直用，触发重拉。"""
    _write_cache(ts=clock.now - 10, stocks=_norm(200, 0.5),
                 version=screener._LIST_VERSION, complete=True, valid=False)
    fake = iso(_pages(_items(2000)))

    stocks, _meta = screener.load_stock_list_meta(force=False)

    assert fake.calls
    assert len(stocks) == 2000


def test_v1_cache_not_directly_usable(iso, clock):
    """v1 旧格式（无 version/complete）不享受直用，成功拉取后修正为 v3。"""
    _write_cache(ts=clock.now - 10, stocks=_norm(200))
    fake = iso(_pages(_items(2000)))

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert fake.calls
    assert len(stocks) == 2000
    assert meta["degraded"] is False
    d = json.loads(_cache_bytes().decode("utf-8"))
    assert d["version"] == screener._LIST_VERSION == 3
    assert d["valid"] is True


# ══════════════════════════════════════════════════════
# 4. 盘前场景核心回归（本 spec 的主用例）
# ══════════════════════════════════════════════════════

def test_preopen_junk_snapshot_never_returned(iso, clock, tmp_path):
    """09:20 拉到 63.5% price=0 的废快照 → 不返回废数据、不落库。"""
    clock.now = datetime(2026, 9, 30, 9, 20).timestamp()
    iso(_pages(_items(2000, zero_ratio=0.635)))

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert stocks == []
    assert meta["degraded"] is True
    assert meta["valid"] is False
    assert not (tmp_path / "stock_list.json").exists(), "废快照不得写入缓存"


def test_preopen_junk_then_real_quotes_after_open(iso, clock, monkeypatch):
    """09:20 废快照 → 10:00 真实行情：必须拿到新数据。

    旧实现下 09:20 写入的「完整」缓存会被直用，开盘后全天都是盘前废数据。
    """
    clock.now = datetime(2026, 9, 30, 9, 20).timestamp()
    monkeypatch.setattr(screener, "_sina_get",
                        _Sina(_pages(_items(2000, zero_ratio=0.635))))

    first, meta1 = screener.load_stock_list_meta(force=True)
    assert first == []
    assert meta1["degraded"] is True

    # 开盘后：行情变为真实值，且已超过最小重试间隔
    clock.now = datetime(2026, 9, 30, 10, 0).timestamp()
    monkeypatch.setattr(screener, "_sina_get", _Sina(_pages(_items(2000))))

    second, meta2 = screener.load_stock_list_meta(force=False)

    assert len(second) == 2000
    assert meta2["degraded"] is False
    assert meta2["valid"] is True
    assert meta2["stale"] is False


# ══════════════════════════════════════════════════════
# 5. 防惊群与最小重试间隔
# ══════════════════════════════════════════════════════

def test_single_flight_concurrent_requests(iso, clock):
    """并发 8 个请求 + 过期缓存 → 只发起一份真实拉取。"""
    _write_cache(ts=clock.now - 100000, stocks=_norm(200),
                 version=screener._LIST_VERSION, complete=True, valid=True)
    fake = iso(_pages(_items(2000)))

    results = []

    def _worker():
        results.append(screener.load_stock_list_meta(force=False))

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert all(len(r[0]) == 2000 for r in results)
    assert fake.calls.count(1) == 1, "第 1 页只应被拉取一次（single-flight）"


def test_min_retry_interval_suppresses_repeat(iso, clock):
    """判定无效后的 60 秒内不得重复空转拉取。"""
    clock.now = datetime(2026, 9, 30, 9, 20).timestamp()
    fake = iso(_pages(_items(2000, zero_ratio=0.635)))

    _s1, meta1 = screener.load_stock_list_meta(force=False)
    assert meta1["degraded"] is True
    n1 = fake.calls.count(1)
    assert n1 == 1

    clock.advance(10)                      # 10 秒后
    _s2, meta2 = screener.load_stock_list_meta(force=False)
    assert fake.calls.count(1) == n1, "最小重试间隔内不得再次拉取"
    assert meta2["degraded"] is True
    assert "不足" in meta2["reason"]

    clock.advance(60)                      # 累计 70 秒，超过间隔
    _s3, _meta3 = screener.load_stock_list_meta(force=False)
    assert fake.calls.count(1) == n1 + 1, "超过最小重试间隔后应重新拉取"


def test_force_bypasses_retry_interval(iso, clock):
    """AC-2.4：force=1 穿透最小重试间隔（用户主动刷新时必须真的重拉）。"""
    clock.now = datetime(2026, 9, 30, 9, 20).timestamp()
    fake = iso(_pages(_items(2000, zero_ratio=0.635)))

    screener.load_stock_list_meta(force=False)
    n1 = fake.calls.count(1)

    clock.advance(5)
    screener.load_stock_list_meta(force=True)

    assert fake.calls.count(1) == n1 + 1


# ══════════════════════════════════════════════════════
# 6. 并发拉取的等价性与确定性
# ══════════════════════════════════════════════════════

def test_concurrent_result_matches_serial_and_sorted(iso):
    """并发产物与串行归一化逐条等价，且按 code 升序（顺序确定）。"""
    items = _items(2500)
    iso(_pages(items))

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is True
    assert len(stocks) == 2500
    assert [s["code"] for s in stocks] == sorted(s["code"] for s in stocks)
    assert stocks == sorted(screener._normalize_stock_rows(items),
                            key=lambda r: r["code"])


def test_page_limit_constant_covers_market():
    """页数上限须覆盖当前全市场（5571 只）。"""
    assert screener._MAX_PAGE * screener._PAGE_SIZE >= 6000
    assert screener._FETCH_WORKERS >= 2


def test_meta_keeps_backward_compatible_keys(iso, clock):
    """C-4：meta 原有四键保持存在，新增键只增不改。"""
    iso(_pages(_items(2000)))

    _stocks, meta = screener.load_stock_list_meta(force=True)

    for k in ("degraded", "count", "fetched_at", "reason"):
        assert k in meta, "既有键不得移除：%s" % k
    assert meta["valid"] is True
    assert meta["stale"] is False


# ══════════════════════════════════════════════════════
# 7. 只读入口 peek_stock_list（见 specs/cut-sentiment-latency/design.md §2.2）
# ══════════════════════════════════════════════════════

def test_peek_returns_fresh_snapshot(iso, clock, monkeypatch):
    """新鲜快照可直接读出，且全程不发起网络请求。"""
    _no_fetch(monkeypatch)
    _write_cache(clock.now - 30, _norm(2000), version=3, complete=True, valid=True)

    stocks, ts = screener.peek_stock_list()

    assert stocks is not None and len(stocks) == 2000
    assert ts == clock.now - 30


def test_peek_expired_snapshot_is_unavailable_without_fetch(iso, clock, monkeypatch):
    """窗口内 TTL=120s：300 秒前的快照不可用，且**不得**触发拉取。"""
    _no_fetch(monkeypatch)
    _write_cache(clock.now - 300, _norm(2000), version=3, complete=True, valid=True)

    assert screener.peek_stock_list() == (None, None)


def test_peek_max_age_can_be_relaxed(iso, clock, monkeypatch):
    """放宽 max_age 后同一份快照变得可用（跌停家数用 10 分钟口径即靠此）。"""
    _no_fetch(monkeypatch)
    _write_cache(clock.now - 300, _norm(2000), version=3, complete=True, valid=True)

    stocks, ts = screener.peek_stock_list(max_age=600)

    assert stocks is not None
    assert ts == clock.now - 300


def test_peek_missing_file_returns_none(iso, clock, monkeypatch):
    _no_fetch(monkeypatch)

    assert screener.peek_stock_list() == (None, None)


def test_peek_too_few_rows_returns_none(iso, clock, monkeypatch):
    """条数不足 _MIN_STOCK_COUNT 的一律视为不可用（防止用残缺文件做统计）。"""
    _no_fetch(monkeypatch)
    _write_cache(clock.now - 10, _norm(100), version=3, complete=True, valid=True)

    assert screener.peek_stock_list() == (None, None)


def test_peek_validity_gate_and_override(iso, clock, monkeypatch):
    """v2 旧缓存（无 valid 标记）当场判定：默认拒绝废快照，显式放开后可用。"""
    _no_fetch(monkeypatch)
    junk = _norm(2000, 0.635)                       # price>0 仅 36.5%，盘前形态
    _write_cache(clock.now - 30, junk, version=2, complete=True)

    assert screener.peek_stock_list() == (None, None)

    stocks, _ts = screener.peek_stock_list(require_valid=False)
    assert stocks is not None and len(stocks) == 2000


def test_peek_does_not_change_load_stock_list_meta_behavior(iso, clock, monkeypatch):
    """peek 是纯读：调用它不得影响正式取数入口的判据。"""
    _no_fetch(monkeypatch)
    _write_cache(clock.now - 30, _norm(2000), version=3, complete=True, valid=True)

    screener.peek_stock_list()
    stocks, meta = screener.load_stock_list_meta()

    assert len(stocks) == 2000
    assert meta["degraded"] is False
