# -*- coding: utf-8 -*-
"""清单拉取容错回归测试（AC-1.1 ~ AC-1.8）。

全部离线：`_sina_get` 被替换为内存假接口，`time.sleep` 被置空以避免退避等待。
需求见 specs/fix-stocklist-and-cache-health/。
"""
import json
import time

import pytest

from core import screener


# ── 假接口与数据构造 ──────────────────────────────────

def _mk_item(symbol, **kw):
    """构造一条新浪原始条目。"""
    item = {
        "symbol": symbol,
        "code": symbol[2:] if len(symbol) > 2 else symbol,
        "name": "N" + symbol,
        "trade": "10.00",
        "changepercent": "1.23",
        "amount": "123000000",       # 元
        "turnoverratio": "1.50",
        "per": "20.0",
        "mktcap": "123456.78",       # 万元
        "nmc": "100000.00",          # 万元
    }
    item.update(kw)
    return item


def _build_items(total):
    """生成 total 条三市交替的原始条目。"""
    out = []
    for i in range(total):
        market = ("sh", "sz", "bj")[i % 3]
        out.append(_mk_item("%s%06d" % (market, 600000 + i)))
    return out


class _Sina:
    """假的分页接口：记录请求过的页序列，支持指定页失败若干次。

    fail = {页码: 剩余失败次数}；值为 -1 表示该页永久失败。
    """

    def __init__(self, pages, fail=None):
        self.pages = pages
        self.fail = dict(fail or {})
        self.calls = []

    def __call__(self, node, page, num=100):
        self.calls.append(page)
        left = self.fail.get(page, 0)
        if left != 0:
            if left > 0:
                self.fail[page] = left - 1
            raise RuntimeError("simulated network error")
        idx = page - 1
        return self.pages[idx] if idx < len(self.pages) else []


@pytest.fixture
def iso(monkeypatch, tmp_path):
    """隔离环境：临时清单文件 + 屏蔽退避等待。返回可安装假接口的助手。"""
    monkeypatch.setattr(screener, "_LIST_FILE", str(tmp_path / "stock_list.json"))
    monkeypatch.setattr(screener.time, "sleep", lambda *a, **k: None)

    def _install(pages, fail=None):
        fake = _Sina(pages, fail)
        monkeypatch.setattr(screener, "_sina_get", fake)
        return fake

    return _install


def _pages_for(total, page_size=100):
    items = _build_items(total)
    return [items[i:i + page_size] for i in range(0, len(items), page_size)]


def _read_cache():
    with open(screener._LIST_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── AC-1.1 单页失败重试后成功 ─────────────────────────

def test_page_retry_then_success(iso):
    """第 2 页前两次抛异常、第三次成功 → 结果完整且 ok=True。"""
    fake = iso(_pages_for(screener._MIN_STOCK_COUNT), fail={2: 2})

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is True
    assert len(stocks) == screener._MIN_STOCK_COUNT
    assert fake.calls.count(2) == 3        # 重试了 2 次后第 3 次成功


# ── AC-1.1 / AC-1.2 单页重试耗尽仍继续后续页 ──────────

def test_page_retry_exhausted_continues(iso):
    """第 2 页永久失败 → 记失败页但不中断，后续页仍被请求。"""
    fake = iso(_pages_for(screener._MIN_STOCK_COUNT), fail={2: -1})

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is False
    assert fake.calls.count(2) == screener._PAGE_MAX_RETRY   # 重试用尽
    assert 3 in fake.calls                                   # 未中断，继续拉了第 3 页
    assert len(stocks) == screener._MIN_STOCK_COUNT - 100    # 仅缺第 2 页的 100 条


def test_consecutive_failures_abort_early(iso):
    """全部页失败 → 连续失败达阈值即提前结束，不空转 200 页。"""
    fake = iso(_pages_for(300), fail={p: -1 for p in range(1, 201)})

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is False
    assert stocks == []
    # 仅探测了 _MAX_CONSECUTIVE_FAIL 页，每页重试 _PAGE_MAX_RETRY 次
    assert set(fake.calls) == set(range(1, screener._MAX_CONSECUTIVE_FAIL + 1))
    assert len(fake.calls) == screener._MAX_CONSECUTIVE_FAIL * screener._PAGE_MAX_RETRY


# ── AC-1.4 条数不足判失败 ─────────────────────────────

def test_too_few_rows_fails(iso):
    """仅 100 条（< 下限 2000）→ ok=False。"""
    iso(_pages_for(100))

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is False
    assert len(stocks) == 100


def test_min_stock_count_default_is_2000():
    assert screener._MIN_STOCK_COUNT == 2000


# ── AC-1.7 三市齐全 ───────────────────────────────────

def test_all_three_markets_present(iso):
    iso(_pages_for(screener._MIN_STOCK_COUNT))

    stocks, ok = screener._fetch_sina_stock_list()

    assert ok is True
    counts = {}
    for s in stocks:
        counts[s["market"]] = counts.get(s["market"], 0) + 1
    assert counts.get("sh", 0) > 0
    assert counts.get("sz", 0) > 0
    assert counts.get("bj", 0) > 0


# ── AC-1.3 不写残缺缓存 ───────────────────────────────

def test_incomplete_result_not_written(iso):
    """拉取不完整时不落库，且原缓存文件内容不变。"""
    iso(_pages_for(100))
    original = {"ts": 1.0, "version": 2, "complete": True,
                "stocks": [{"code": "sh600000", "pure_code": "600000"}]}
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False)

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert meta["degraded"] is True
    assert _read_cache() == original          # 缓存未被残缺结果覆盖
    assert stocks == original["stocks"]       # 回退旧缓存


# ── AC-1.5 失败回退旧缓存 ─────────────────────────────

def test_fallback_to_old_cache(iso):
    iso(_pages_for(100), fail={1: -1})
    old = {"ts": time.time() - 100, "version": 2, "complete": True,
           "stocks": [{"code": "sz000001", "pure_code": "000001"}]}
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False)

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert meta["degraded"] is True
    assert meta["count"] == 1
    assert "回退" in meta["reason"]
    assert stocks == old["stocks"]


# ── AC-1.6 无缓存且失败 → 空列表 ──────────────────────

def test_no_cache_and_failure_returns_empty(iso):
    iso(_pages_for(100), fail={1: -1})

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert stocks == []
    assert meta["degraded"] is True
    assert meta["count"] == 0


# ── 缓存直用与落库结构 ────────────────────────────────

def test_fresh_complete_cache_used_without_fetch(iso, monkeypatch):
    """未过期且完整标记的缓存直接使用，不发起网络请求。"""
    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise AssertionError("不应发起网络请求")

    iso([])
    monkeypatch.setattr(screener, "_sina_get", _boom)

    fresh = {"ts": time.time(), "version": 2, "complete": True,
             "stocks": [{"code": "sh600000", "pure_code": "600000"}]}
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(fresh, f, ensure_ascii=False)

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert stocks == fresh["stocks"]
    assert meta["degraded"] is False
    assert calls == []


def test_successful_fetch_writes_v2_cache(iso):
    iso(_pages_for(screener._MIN_STOCK_COUNT))

    stocks, meta = screener.load_stock_list_meta(force=True)

    assert meta["degraded"] is False
    d = _read_cache()
    assert d["version"] == screener._LIST_VERSION == 2
    assert d["complete"] is True
    assert len(d["stocks"]) == len(stocks) == screener._MIN_STOCK_COUNT


def test_legacy_cache_is_refreshed_on_success(iso):
    """旧格式缓存（无 version）被视为可能不完整：成功拉取后应被修正为 v2。"""
    legacy = {"ts": time.time(), "stocks": [{"code": "bj920000", "pure_code": "920000"}]}
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)
    iso(_pages_for(screener._MIN_STOCK_COUNT))

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert meta["degraded"] is False
    assert len(stocks) == screener._MIN_STOCK_COUNT
    assert _read_cache()["complete"] is True


def test_legacy_cache_readable_on_failure(iso):
    """旧格式缓存 + 拉取失败 → 仍可读出，不抛异常，标记降级。"""
    legacy = {"ts": time.time(), "stocks": [{"code": "bj920000", "pure_code": "920000"}]}
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)
    iso(_pages_for(100), fail={1: -1})

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert stocks == legacy["stocks"]
    assert meta["degraded"] is True


def test_load_stock_list_keeps_list_signature(iso):
    """兼容原签名：load_stock_list 只返回列表。"""
    iso(_pages_for(screener._MIN_STOCK_COUNT))

    result = screener.load_stock_list(force=True)

    assert isinstance(result, list)
    assert len(result) == screener._MIN_STOCK_COUNT


def test_corrupt_cache_ignored(iso):
    """缓存文件损坏 → 视为无缓存，正常走拉取。"""
    with open(screener._LIST_FILE, "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    iso(_pages_for(screener._MIN_STOCK_COUNT))

    stocks, meta = screener.load_stock_list_meta(force=False)

    assert meta["degraded"] is False
    assert len(stocks) == screener._MIN_STOCK_COUNT


# ── _normalize_stock_rows 纯函数 ──────────────────────

def test_normalize_field_mapping_and_units():
    rows = screener._normalize_stock_rows([
        _mk_item("sh600000", code="600000", name="浦发银行",
                 mktcap="123456.78", nmc="100000.00", amount="250000000"),
        _mk_item("bj920000", code="920000", name="安徽凤凰"),
    ])

    assert len(rows) == 2
    r = rows[0]
    assert r["code"] == "sh600000"
    assert r["pure_code"] == "600000"
    assert r["name"] == "浦发银行"
    assert r["market"] == "sh"
    # 万元 → 亿元
    assert r["mcap_yi"] == round(123456.78 / 1e4, 2)
    assert r["fmcap_yi"] == round(100000.00 / 1e4, 2)
    # 元 → 亿元
    assert r["amount_yi"] == 2.5
    assert rows[1]["market"] == "bj"


def test_normalize_market_prefixes():
    rows = screener._normalize_stock_rows([
        _mk_item("sh600000"), _mk_item("sz000001"),
        _mk_item("bj920000"), _mk_item("zz123456"),
    ])
    assert [r["market"] for r in rows] == ["sh", "sz", "bj", "sz"]


def test_normalize_skips_items_without_symbol():
    rows = screener._normalize_stock_rows([
        {"code": "600000", "name": "无 symbol"},
        _mk_item("sh600001"),
    ])
    assert len(rows) == 1
    assert rows[0]["code"] == "sh600001"


def test_normalize_handles_dash_values():
    """'-' 等非数值应安全降级为 0，而不是抛异常。"""
    rows = screener._normalize_stock_rows([
        _mk_item("sh600002", per="-", trade="-", amount="", mktcap=None),
    ])
    assert rows[0]["pe_ttm"] == 0.0
    assert rows[0]["price"] == 0.0
    assert rows[0]["amount_yi"] == 0.0
    assert rows[0]["mcap_yi"] == 0.0
