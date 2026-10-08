# -*- coding: utf-8 -*-
"""
选股引擎：全市场股票列表 + K线缓存 + 通达信指标选股 + 过滤条件
"""
import os
import time
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests

from core.data import kline, real_quotes, to_symbol, UA
from core.tdx import get_signal, evaluate_tdx, check_tdx_syntax, estimate_tdx_days

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_BASE, "data", "screener")
_KLINE_DIR = os.path.join(_CACHE_DIR, "klines")
_LIST_FILE = os.path.join(_CACHE_DIR, "stock_list.json")

os.makedirs(_KLINE_DIR, exist_ok=True)

_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": UA})

# 清单拉取容错参数（见 specs/fix-stocklist-and-cache-health/）
_MIN_STOCK_COUNT = 2000      # 合理性下限：低于此判为拉取失败，不落库
_PAGE_MAX_RETRY = 3          # 单页请求重试上限
_MAX_CONSECUTIVE_FAIL = 3    # 连续失败页达到此数即判定网络不可用，提前结束拉取
_PAGE_SIZE = 100             # 单页条数（实测新浪 num 无法放大，恒定 100）

# 时效与有效性参数（见 specs/fix-stocklist-snapshot-freshness/）
_LIST_VERSION = 3            # 清单缓存结构版本（v1=无 version；v2=有 complete 无 valid；v3=含 valid）
_TTL_TRADING = 120           # 行情窗口内缓存有效期（秒）
_TTL_IDLE = 12 * 3600        # 行情窗口外缓存有效期（秒）
_VALID_PRICE_RATIO = 0.90    # 有效快照判据：price > 0 占比下限
_MIN_VALID_SAMPLE = 100      # 样本不足此数时跳过有效性判定
_FETCH_WORKERS = 6           # 并发分页线程数
_MAX_PAGE = 60               # 页数上限（60 × 100 = 6000 只，覆盖当前 5571）
_MIN_RETRY_INTERVAL = 60     # 拉取失败/判定无效后的最小重试间隔（秒）

_log = logging.getLogger(__name__)

# 进程级状态：防惊群（single-flight）与最小重试间隔
_FETCH_LOCK = threading.Lock()
_LAST_ATTEMPT = {"ts": 0.0, "usable": False}


def _safe_float(v, default=0.0):
    """安全转 float，处理 '-' 等非数值"""
    try:
        if v is None or v == "-" or v == "":
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


# ── 时效与有效性纯函数（可脱网单测） ──────────────────

def snapshot_valid_ratio(stocks):
    """快照中 price > 0 的标的占比。空列表返回 0.0。

    判据必须看 price 而不是 change_pct：盘前新浪把绝大多数标的的 trade 重置为 0，
    但 changepercent 仍残留上一交易日的值 —— 只看涨跌幅会把废快照误判为有效。
    """
    if not stocks:
        return 0.0
    n = 0
    for s in stocks:
        if _safe_float((s or {}).get("price")) > 0:
            n += 1
    return n / len(stocks)


def snapshot_is_valid(stocks):
    """快照是否为「有效行情」。

    样本少于 _MIN_VALID_SAMPLE 时返回 True：非全市场样本（测试桩、残缺缓存）
    上算占比没有统计意义，不应据此否决一份可能正常的缓存。
    """
    if len(stocks) < _MIN_VALID_SAMPLE:
        return True
    return snapshot_valid_ratio(stocks) >= _VALID_PRICE_RATIO


def _in_quote_window(now=None):
    """是否处于行情有效窗口：交易日 09:15~11:30、13:00~15:00（不含午休）。

    刻意排除午休：市场停顿 90 分钟，按窗口内 TTL 会白拉约 45 次。
    不识别法定节假日（见 design §3.3 已知取舍），假日拉到的昨日收盘快照本身有效。
    """
    t = datetime.fromtimestamp(now if now is not None else time.time())
    if t.weekday() >= 5:              # 周六 / 周日
        return False
    hm = t.hour * 60 + t.minute
    return (9 * 60 + 15 <= hm <= 11 * 60 + 30) or (13 * 60 <= hm <= 15 * 60)


def _cache_ttl(now=None):
    """当前时刻应采用的清单缓存有效期（秒）。

    跨时段失效无需专门代码：昨晚写入的缓存到次日上午 now - ts 已远超 120s，
    在窗口内自然判定为过期。
    """
    return _TTL_TRADING if _in_quote_window(now) else _TTL_IDLE


def _sina_get(node, page, num=100):
    """新浪股票列表接口"""
    url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    params = {
        "page": page, "num": num, "sort": "symbol", "asc": 1,
        "node": node, "symbol": "", "_s_r_a": "page",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    return r.json()


# ── 全市场股票列表 ────────────────────────────────────

def _read_stock_list_cache():
    """读取本地清单缓存文件（不做时效判断）。

    返回 (stocks, meta)：
      - meta 即缓存文件顶层 dict（含 ts / version / complete）
      - 文件不存在、损坏、或结构非法时返回 None
    - 兼容旧格式：历史文件无 version/complete 字段，按 version=1、complete 视为缺失处理。
    """
    if not os.path.exists(_LIST_FILE):
        return None
    try:
        with open(_LIST_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    stocks = d.get("stocks")
    if not isinstance(stocks, list):
        return None
    return stocks, d


def _write_stock_list_cache(stocks, ts):
    """写入清单缓存（仅在拉取完整**且通过有效性判定**时调用）。

    结构为 v3：{ts, version, complete, valid, stocks}。
    `valid` 是写入时的有效性判定结果（只写 True；不通过判定的一律不落库）。
    """
    payload = {"ts": ts, "version": _LIST_VERSION, "complete": True,
               "valid": True, "stocks": stocks}
    try:
        with open(_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError as e:
        _log.error("[stocklist] 写入清单缓存失败：%s", e)


def _has_known_version(meta):
    """缓存是否带有可识别的 version 标记（v1 历史文件无此字段）。"""
    return isinstance(meta.get("version"), int)


def _meta_valid_or_unknown(stocks, meta):
    """缓存有效性三态判定。

    v3 缓存看 `valid` 标记；v1/v2 无标记则**当场判定**（样本不足时豁免）。
    当场判定是必须的：升级后那份盘前写的废缓存若被一律放行，问题会原地复活。
    """
    v = meta.get("valid")
    if v is True:
        return True
    if v is False:
        return False
    return snapshot_is_valid(stocks)


def _is_stale(fetched_at, now):
    """数据是否已超出它本该有的寿命（= 非当前时段的旧快照）。"""
    if not fetched_at:
        return False
    return (now - fetched_at) >= _cache_ttl(now)


def _ok_meta(stocks, fetched_at, now):
    """构造「正常可用」的 meta（degraded=False）。"""
    return {
        "degraded": False,
        "count": len(stocks),
        "fetched_at": fetched_at,
        "reason": "",
        "valid": True,
        "stale": _is_stale(fetched_at, now),
    }


def _directly_usable(cached, now):
    """缓存是否可直接使用：新鲜 + 完整 + 有版本标记 + 通过有效性判定。"""
    if cached is None:
        return False
    stocks, meta = cached
    if not stocks:
        return False
    if meta.get("complete") is not True:      # 沿用既有语义：不完整不直用
        return False
    if not _has_known_version(meta):          # v1 旧格式：沿用既有行为（重拉修正）
        return False
    if now - meta.get("ts", 0) >= _cache_ttl(now):
        return False
    return _meta_valid_or_unknown(stocks, meta)


def _fallback_or_empty(cached, now, reason):
    """拉取失败 / 快照无效时的降级出口：回退可用旧缓存，否则返回空。

    回退的旧缓存也要过一遍有效性判定 —— 否则一份盘前废数据会从回退路径复活。
    """
    if cached is not None and cached[0] and _meta_valid_or_unknown(cached[0], cached[1]):
        old_stocks, old_meta = cached
        old_ts = old_meta.get("ts", 0) or 0
        when = (datetime.fromtimestamp(old_ts).strftime("%Y-%m-%d %H:%M")
                if old_ts else "时间未知")
        full = "%s，已回退到旧缓存（%s，%d 条）" % (reason, when, len(old_stocks))
        _log.error("[stocklist] %s", full)
        return old_stocks, {
            "degraded": True,
            "count": len(old_stocks),
            "fetched_at": old_ts,
            "reason": full,
            "valid": True,
            "stale": _is_stale(old_ts, now),
        }

    full = reason + "，且无可用缓存"
    _log.error("[stocklist] %s，返回空清单", full)
    return [], {"degraded": True, "count": 0, "fetched_at": 0,
                "reason": full, "valid": False, "stale": False}


def load_stock_list(force=False):
    """
    获取全市场 A 股列表（沪深京）

    返回 [{code, name, market, mcap_yi, fmcap_yi, industry, ...}]
    时效策略见 load_stock_list_meta()（行情窗口内 120s，窗口外 12h）。

    兼容原签名：只返回列表。需要感知「降级」状态时请用 load_stock_list_meta()。
    """
    stocks, _meta = load_stock_list_meta(force)
    return stocks


def load_stock_list_meta(force=False):
    """获取全市场 A 股列表，并附带数据健康状况。

    返回 (stocks, meta)，meta = {
      "degraded":   bool,   # True 表示用的是降级缓存（非本次实时有效结果）
      "count":      int,    # 返回条数
      "fetched_at": float,  # 该数据的拉取时间戳
      "reason":     str,    # degraded 时的原因说明
      "valid":      bool,   # 返回的数据是否通过有效性判定
      "stale":      bool,   # 数据是否已超出应有寿命（非当前时段的旧快照）
    }

    判定顺序（见 specs/fix-stocklist-snapshot-freshness/design.md §3.5）：
      1. 缓存新鲜（按行情窗口分层 TTL）且完整且有效 → 直接用缓存
      2. 加锁（防惊群）→ 双检缓存 → 最小重试间隔抑制 → 实时拉取
      3. 拉取完整且有效（price>0 占比达标）     → 写缓存并返回
      4. 拉取失败 / 快照无效 + 有可用旧缓存      → 不覆盖缓存，回退并标记降级
      5. 拉取失败 / 快照无效 + 无可用缓存        → 返回 [] 并记 error

    注：v1 旧缓存（无 version）与 v2 旧缓存（无 valid）均不享受直用，
    会被重拉修正；回退路径上则按现场统计判定有效性。

    `force=True` 穿透新鲜度判断、双检与最小重试间隔（AC-2.4）。
    """
    now = time.time()
    cached = _read_stock_list_cache()

    if not force and _directly_usable(cached, now):
        stocks, meta = cached
        return stocks, _ok_meta(stocks, meta.get("ts", 0), now)

    # 慢路径加锁：同一时刻只允许一次真实拉取（single-flight）
    with _FETCH_LOCK:
        cached = _read_stock_list_cache()      # 双检：等锁期间可能已被别人刷新
        if not force and _directly_usable(cached, now):
            stocks, meta = cached
            return stocks, _ok_meta(stocks, meta.get("ts", 0), now)

        if (not force
                and now - _LAST_ATTEMPT["ts"] < _MIN_RETRY_INTERVAL
                and not _LAST_ATTEMPT["usable"]):
            return _fallback_or_empty(
                cached, now,
                "距上次拉取失败不足 %d 秒" % _MIN_RETRY_INTERVAL)

        stocks, ok = _fetch_sina_stock_list()
        valid = bool(ok) and snapshot_is_valid(stocks)
        _LAST_ATTEMPT["ts"] = time.time()
        _LAST_ATTEMPT["usable"] = valid

        if valid:
            _write_stock_list_cache(stocks, now)
            return stocks, _ok_meta(stocks, now, now)

        if not ok:
            reason = "清单拉取不完整（失败页或条数不足）"
        else:
            reason = "行情快照无效（price>0 占比 %.1f%%）" % (
                snapshot_valid_ratio(stocks) * 100)
        return _fallback_or_empty(cached, now, reason)


def peek_stock_list(max_age=None, require_valid=True):
    """只读**已落盘**的全市场快照。**绝不发起网络请求。**

    - `max_age=None`        → 用正式时效判据（行情窗口内 `_TTL_TRADING` / 窗口外 `_TTL_IDLE`）
    - `max_age=<秒>`        → 放宽为"年龄不超过该值即算可用"
    - `require_valid=False` → 不要求 price>0 占比达标（取名称等慢变字段时用）

    返回 `(stocks, ts)`；不可用返回 `(None, None)`。

    与 `load_stock_list_meta()` 的分工：后者是"取数"入口，缓存过期时会**联网拉取**；
    本函数是"读数"入口，只认已经躺在地上的快照 —— 供情绪分这类
    "有快照就用、没有就降级"的路径使用，避免被一次数秒的全市场拉取阻塞
    （见 specs/cut-sentiment-latency/design.md §2.2）。
    """
    cached = _read_stock_list_cache()
    if cached is None:
        return None, None
    stocks, meta = cached
    if not stocks or len(stocks) < _MIN_STOCK_COUNT:
        return None, None
    ts = meta.get("ts", 0) or 0
    limit = _cache_ttl() if max_age is None else max_age
    if not ts or (time.time() - ts) > limit:
        return None, None
    if require_valid and not _meta_valid_or_unknown(stocks, meta):
        return None, None
    return stocks, ts


def _normalize_stock_rows(raw_items):
    """新浪原始条目 → 标准结构（纯函数，无网络，便于脱网测试）。

    字段映射与单位换算：
      symbol → code（含市场前缀，如 sh600000）；code → pure_code（6 位）
      mktcap / nmc：新浪单位为「万元」，转「亿元」
      amount：新浪单位为「元」，转「亿元」
    """
    out = []
    for item in raw_items:
        symbol = item.get("symbol", "")   # 如 sh600000 / sz000001 / bj920000
        code = item.get("code", "")
        name = item.get("name", "")
        if not symbol:
            continue

        # 判断市场
        if symbol.startswith("sh"):
            market = "sh"
        elif symbol.startswith("sz"):
            market = "sz"
        elif symbol.startswith("bj"):
            market = "bj"
        else:
            market = "sz"

        # 新浪 mktcap 单位是万元，转成亿
        mktcap_wan = _safe_float(item.get("mktcap"))
        nmc_wan = _safe_float(item.get("nmc"))
        amount_yuan = _safe_float(item.get("amount"))   # 元

        out.append({
            "code": symbol,
            "pure_code": code,
            "name": name,
            "market": market,
            "price": _safe_float(item.get("trade")),
            "change_pct": _safe_float(item.get("changepercent")),
            "amount_yi": round(amount_yuan / 1e8, 2),
            "turnover_pct": _safe_float(item.get("turnoverratio")),
            "pe_ttm": _safe_float(item.get("per")),
            "mcap_yi": round(mktcap_wan / 1e4, 2),   # 万元 → 亿元
            "fmcap_yi": round(nmc_wan / 1e4, 2),
            "industry": "",   # 新浪接口暂无行业字段，由 _industry_map() 补充
        })
    return out


def _fetch_one_page(node, page):
    """拉取单页（含递增退避重试）。返回 (page, diff, err)。

    保留既有单页容错：至多重试 _PAGE_MAX_RETRY 次，退避 1.5s / 3.0s。
    """
    last_err = None
    for attempt in range(_PAGE_MAX_RETRY):
        try:
            return page, _sina_get(node, page, _PAGE_SIZE), None
        except Exception as e:
            last_err = e
            if attempt < _PAGE_MAX_RETRY - 1:
                time.sleep(1.5 * (attempt + 1))
    return page, None, last_err


def _fetch_pages_concurrent(node, pages):
    """并发拉取一批页，返回 [(page, diff, err)]（与入参 pages 同序）。"""
    results = {}
    workers = max(1, min(_FETCH_WORKERS, len(pages)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch_one_page, node, p): p for p in pages}
        for fut in as_completed(futures):
            page, diff, err = fut.result()
            results[page] = (page, diff, err)
    return [results[p] for p in pages]


def _fetch_sina_stock_list():
    """从新浪财经**分批并发**拉全市场 A 股列表（含容错）。

    返回 (stocks, ok)：
      ok=True  —— 所有页均成功且条数达 _MIN_STOCK_COUNT 下限，可安全落库
      ok=False —— 存在失败页或条数不足；stocks 仅供诊断，调用方不得写入缓存

    容错策略（沿用 specs/fix-stocklist-and-cache-health/ 的三条语义）：
      - 单页失败按 1.5s / 3.0s 递增退避重试至多 _PAGE_MAX_RETRY 次；
      - 仍失败则记失败页并继续拉取后续批，不因单页异常终止；
      - 一整批全部失败才累加连续失败数，达 _MAX_CONSECUTIVE_FAIL 时判定网络
        不可用并提前结束（避免断网时空转发满上限）。

    并发按「批」推进（每批 _FETCH_WORKERS 页）而非一次甩出全部页，
    这样断网时只需发一批请求即可停下（AC-3.1 / AC-4.3）。
    """
    node = "hs_a"  # 沪深A股（含北交所）
    all_data = []
    failed_pages = []
    consecutive_fail = 0

    for start in range(1, _MAX_PAGE + 1, _FETCH_WORKERS):
        pages = list(range(start, min(start + _FETCH_WORKERS, _MAX_PAGE + 1)))
        results = _fetch_pages_concurrent(node, pages)

        batch_failed = 0
        reached_end = False
        for page, diff, err in results:
            if err is not None:
                failed_pages.append(page)
                batch_failed += 1
                _log.warning("[stocklist] 第 %d 页重试 %d 次仍失败：%s",
                             page, _PAGE_MAX_RETRY, err)
                continue
            if not diff:
                reached_end = True
                continue
            all_data.extend(diff)
            if len(diff) < _PAGE_SIZE:      # 尾页
                reached_end = True

        if batch_failed == len(pages):
            consecutive_fail += len(pages)
            _log.error("[stocklist] 连续 %d 页请求失败，判定网络不可用，提前结束拉取",
                       consecutive_fail)
            if consecutive_fail >= _MAX_CONSECUTIVE_FAIL:
                break
        else:
            consecutive_fail = 0

        if reached_end:
            break
    else:
        if len(all_data) >= _MAX_PAGE * _PAGE_SIZE:
            _log.warning("[stocklist] 已用尽页数上限 %d，末页仍满 %d 条，"
                         "可能需要上调 _MAX_PAGE", _MAX_PAGE, _PAGE_SIZE)

    out = _normalize_stock_rows(all_data)
    out.sort(key=lambda r: r["code"])   # 并发后顺序不定，排序保证产物确定性
    ok = (not failed_pages) and (len(out) >= _MIN_STOCK_COUNT)
    if not ok:
        _log.error("[stocklist] 拉取不完整：失败页=%s 解析后条数=%d（下限 %d）",
                   failed_pages or "无", len(out), _MIN_STOCK_COUNT)
    return out, ok


# ── 东财行业映射（补充新浪缺字段） ────────────────────────

_INDUSTRY_MAP_FILE = os.path.join(_BASE, "data", "industry_map.json")
_industry_map_cache = None   # 进程内缓存，避免重复读文件


def _fetch_em_industry_map():
    """从东财 clist 接口拉全 A 股列表，构建 {pure_code: industry_name} 映射。

    东财 clist 接口 fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048
    覆盖沪深京全 A 股；f100 为所属行业（东财行业分类）。
    """
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    # fs: 深主板+创业板+沪主板+科创板+北交所
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    out = {}
    page_size = 100
    for page in range(1, 60):   # 上限保护，A股约 5500 只 / 100 ≈ 55 页
        params = {"pn": page, "pz": page_size, "po": 1, "np": 1,
                  "fields": "f12,f100", "fs": fs}
        try:
            r = _EM_SESSION.get(url, params=params, timeout=12)
            diff = (r.json().get("data") or {}).get("diff") or []
        except Exception:
            break
        if not diff:
            break
        for item in diff:
            code = item.get("f12", "")
            ind = item.get("f100", "")
            if code and ind:
                out[code] = ind
        if len(diff) < page_size:
            break
    return out


def _industry_map():
    """惰性加载全市场个股 → 行业映射，缓存 24 小时。

    首次调用时从东财拉取并写入 data/industry_map.json，后续直接读缓存。
    返回 {pure_code: industry_name}；拉取失败时返回空 dict（前端显示 "--"）。
    """
    global _industry_map_cache
    if _industry_map_cache is not None:
        return _industry_map_cache

    now = time.time()
    # 尝试从缓存文件读（24h 有效）
    if os.path.exists(_INDUSTRY_MAP_FILE):
        try:
            with open(_INDUSTRY_MAP_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if now - d.get("ts", 0) < 24 * 3600:
                _industry_map_cache = d.get("map", {})
                return _industry_map_cache
        except (OSError, ValueError):
            pass

    # 缓存过期或不存在，从东财拉取
    m = _fetch_em_industry_map()
    _industry_map_cache = m
    try:
        with open(_INDUSTRY_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "map": m}, f, ensure_ascii=False)
    except OSError:
        pass
    return m


# ── K 线缓存 ──────────────────────────────────────────

def _kline_cache_path(code, adjust):
    """K线缓存文件路径"""
    return os.path.join(_KLINE_DIR, f"{code}_{adjust}.csv")


def get_cached_kline(code, days=250, adjust="qfq"):
    """
    获取 K 线，带本地文件缓存
    当日已缓存则直接读文件；否则重新拉取并保存
    """
    path = _kline_cache_path(code, adjust)
    today = datetime.now().strftime("%Y-%m-%d")
    need_fetch = True

    if os.path.exists(path):
        try:
            df = pd.read_csv(path, parse_dates=["date"])
            # 检查缓存是否是今天的
            cache_date = df["date"].max().strftime("%Y-%m-%d") if len(df) else ""
            if cache_date == today:
                need_fetch = False
                return df.tail(days).reset_index(drop=True)
        except Exception:
            pass

    if need_fetch:
        try:
            df = kline(code, days=max(days + 150, 300), adjust=adjust)
            if len(df) > 0:
                df.to_csv(path, index=False)
            return df.tail(days).reset_index(drop=True)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


# ── 选股范围过滤 ──────────────────────────────────────

def _match_scope(stock, scope):
    """判断股票是否在选股范围内"""
    if not scope:
        return True
    code = stock["pure_code"]
    market = stock["market"]
    # scope 是列表，如 ['sh_main', 'sz_main', 'cyb', 'kcb', 'bj']
    # 先做简单判断：默认全选
    if "all" in scope:
        return True
    in_any = False
    if "sh_main" in scope and market == "sh" and not code.startswith("688"):
        in_any = True
    if "sz_main" in scope and market == "sz" and not code.startswith("300"):
        in_any = True
    if "cyb" in scope and code.startswith("300"):
        in_any = True
    if "kcb" in scope and code.startswith("688"):
        in_any = True
    if "bj" in scope and market == "bj":
        in_any = True
    return in_any


def _match_exclude(stock, exclude):
    """判断是否需要排除"""
    name = stock["name"]
    if not exclude:
        return False
    if "st" in exclude and ("ST" in name.upper() or "*ST" in name.upper()):
        return True
    if "suspend" in exclude and stock.get("price", 0) <= 0:
        return True
    if "new" in exclude:
        # 新股上市未满 N 天暂时不处理（需要上市日期）
        pass
    return False


# ── 选股执行 ──────────────────────────────────────────

_SCREEN_STATE = {}   # 选股任务状态：{task_id: {status, progress, results, error}}


def run_screen(indicator_code, config=None):
    """
    执行选股（同步，用于小范围测试）
    参数:
        indicator_code: 通达信公式代码
        config: 选股配置 dict
            - scope: 选股范围列表，如 ['sh_main', 'sz_main', 'cyb', 'kcb', 'bj']
            - exclude: 排除列表，如 ['st', 'suspend', 'new']
            - adjust: 复权方式 qfq/hfq/bfq
            - days: K线天数（默认 250）
            - limit: 结果上限
            - sort_by: 排序字段
    返回: [stock_info...]
    """
    config = config or {}
    scope = config.get("scope", ["all"])
    exclude = config.get("exclude", ["st"])
    adjust = config.get("adjust", "qfq")
    # 自动估算K线天数，也支持配置里显式指定
    config_days = int(config.get("days", 0) or 0)
    estimated = estimate_tdx_days(indicator_code)
    days = max(config_days, estimated)
    limit = int(config.get("limit", 100))
    sort_by = config.get("sort_by", "change_pct")

    stocks = load_stock_list()
    results = []

    for s in stocks:
        # 范围过滤
        if not _match_scope(s, scope):
            continue
        # 排除过滤
        if _match_exclude(s, exclude):
            continue
        # 拉 K 线
        df = get_cached_kline(s["code"], days=days, adjust=adjust)
        if df.empty or len(df) < min(days, 20):
            continue
        # 计算信号
        stock_info = {
            "code": s["code"],
            "name": s["name"],
            "industry": s.get("industry", ""),
            "mcap_yi": s.get("mcap_yi", 0),
            "fmcap_yi": s.get("fmcap_yi", 0),
        }
        hit = get_signal(indicator_code, df, stock_info)
        if hit:
            results.append({
                "code": s["code"],
                "pure_code": s["pure_code"],
                "name": s["name"],
                "price": s.get("price", 0),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "turnover_pct": s.get("turnover_pct", 0),
                "mcap_yi": s.get("mcap_yi", 0),
                "industry": s.get("industry", "")
                    or _industry_map().get(s.get("pure_code", ""), "")
                    or _industry_map().get(s.get("code", ""), ""),
            })
            if len(results) >= limit:
                break

    # 排序
    results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return results[:limit]


# ── 异步选股（后台线程） ────────────────────────────────

import uuid


def start_screen_async(indicator_code, config=None):
    """启动异步选股任务，返回 task_id"""
    task_id = uuid.uuid4().hex[:8]
    _SCREEN_STATE[task_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "results": [],
        "error": None,
        "start_time": time.time(),
        "cancelled": False,
    }

    def _worker():
        try:
            config_ = config or {}
            scope = config_.get("scope", ["all"])
            exclude = config_.get("exclude", ["st"])
            adjust = config_.get("adjust", "qfq")
            # 自动估算K线天数，也支持配置里显式指定
            config_days = int(config_.get("days", 0) or 0)
            estimated = estimate_tdx_days(indicator_code)
            days = max(config_days, estimated)
            limit = int(config_.get("limit", 100))
            sort_by = config_.get("sort_by", "change_pct")
            min_required = min(days, 20)

            stocks = load_stock_list()
            # 先过滤范围和排除项，得到待选池
            pool = [s for s in stocks if _match_scope(s, scope) and not _match_exclude(s, exclude)]
            total = len(pool)
            _SCREEN_STATE[task_id]["total"] = total
            _SCREEN_STATE[task_id]["est_days"] = days
            results = []

            for idx, s in enumerate(pool):
                # 检查是否被取消
                if _SCREEN_STATE.get(task_id, {}).get("cancelled"):
                    _SCREEN_STATE[task_id]["status"] = "cancelled"
                    return

                df = get_cached_kline(s["code"], days=days, adjust=adjust)
                if df.empty or len(df) < min_required:
                    _SCREEN_STATE[task_id]["progress"] = idx + 1
                    continue
                stock_info = {
                    "code": s["code"],
                    "name": s["name"],
                    "industry": s.get("industry", ""),
                    "mcap_yi": s.get("mcap_yi", 0),
                    "fmcap_yi": s.get("fmcap_yi", 0),
                }
                hit = get_signal(indicator_code, df, stock_info)
                if hit:
                    results.append({
                        "code": s["code"],
                        "pure_code": s["pure_code"],
                        "name": s["name"],
                        "price": s.get("price", 0),
                        "change_pct": s.get("change_pct", 0),
                        "amount_yi": s.get("amount_yi", 0),
                        "turnover_pct": s.get("turnover_pct", 0),
                        "mcap_yi": s.get("mcap_yi", 0),
                        "industry": s.get("industry", "")
                            or _industry_map().get(s.get("pure_code", ""), "")
                            or _industry_map().get(s.get("code", ""), ""),
                    })
                    if len(results) >= limit:
                        _SCREEN_STATE[task_id]["progress"] = total
                        break
                _SCREEN_STATE[task_id]["progress"] = idx + 1

            results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
            _SCREEN_STATE[task_id]["results"] = results[:limit]
            _SCREEN_STATE[task_id]["status"] = "done"
        except Exception as e:
            _SCREEN_STATE[task_id]["status"] = "error"
            _SCREEN_STATE[task_id]["error"] = str(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return task_id


def cancel_screen(task_id):
    """取消正在运行的选股任务"""
    if task_id in _SCREEN_STATE and _SCREEN_STATE[task_id]["status"] == "running":
        _SCREEN_STATE[task_id]["cancelled"] = True
        return True
    return False


def get_screen_state(task_id):
    """获取选股任务状态"""
    return _SCREEN_STATE.get(task_id)


# ── 飞书推送选股结果 ────────────────────────────────────

def push_screen_results(indicator_name, results, webhook):
    """
    把选股结果推送到飞书
    """
    from core.notifier import send_feishu

    if not webhook:
        return False, "未配置 webhook"

    count = len(results)
    title = f"【智能选股】{indicator_name} · 命中 {count} 只"

    if count == 0:
        text = "今日无符合条件的股票。"
    else:
        lines = [f"{'代码':<8}{'名称':<10}{'现价':>8}{'涨跌幅':>8}"]
        lines.append("-" * 40)
        for r in results[:20]:  # 最多显示 20 只
            chg = r.get("change_pct", 0)
            chg_str = f"{chg:+.2f}%"
            lines.append(f"{r.get('pure_code', r.get('code','')):<8}{r.get('name',''):<10}{r.get('price',0):>8.2f}{chg_str:>8}")
        if count > 20:
            lines.append(f"... 还有 {count - 20} 只，详见选股页")
        text = "\n".join(lines)

    ok, msg = send_feishu(webhook, title, text)
    return ok, msg

def backtest_indicator(indicator_code, code, days=250, adjust="qfq"):
    """
    对单个标的回测通达信指标
    返回 {total_ret, annual_ret, max_drawdown, win_rate, trade_count, benchmark_ret, trades, equity, dates}
    """
    df = get_cached_kline(code, days=days, adjust=adjust)
    if df.empty:
        return {"error": "K线数据为空"}

    stock_info = {"code": code, "name": "", "industry": "", "mcap_yi": 0}
    results, _ = evaluate_tdx(indicator_code, df, stock_info)
    if not results:
        return {"error": "指标计算失败"}

    # 找输出变量（最后一个变量如果是 bool 型就作为买卖信号）
    signal_series = None
    for name in reversed(list(results.keys())):
        v = results[name]
        if isinstance(v, pd.Series):
            signal_series = v
            break
    if signal_series is None:
        return {"error": "未找到输出信号"}

    # 将信号转为 1（买入）/-1（卖出）/0（无操作）
    # 信号从 0 变 1 的下一日开盘买入，从 1 变 0 的下一日开盘卖出
    signal_bool = signal_series.astype(bool)
    n = len(df)
    init_cash = 100000.0
    fee_rate = 0.00025

    cash, shares = init_cash, 0.0
    equity, trades = [], []
    buy_date = buy_price = None
    holding = False

    for i in range(n):
        price = float(df["close"].iloc[i])
        date = df["date"].iloc[i]
        sig = bool(signal_bool.iloc[i])

        if sig and not holding:
            # 买入（用收盘价近似，实际应次日开盘）
            shares = cash * (1 - fee_rate) / price
            cash = 0.0
            buy_date, buy_price = date, price
            holding = True
        elif not sig and holding:
            # 卖出
            cash = shares * price * (1 - fee_rate)
            trades.append({
                "buy_date": buy_date.strftime("%Y-%m-%d"),
                "sell_date": date.strftime("%Y-%m-%d"),
                "buy_price": round(buy_price, 4),
                "sell_price": round(price, 4),
                "ret": round(price / buy_price - 1, 4),
                "days": (date - buy_date).days,
            })
            shares = 0.0
            buy_date = buy_price = None
            holding = False

        equity.append(cash + shares * price)

    eq = pd.Series(equity)
    total_ret = float(eq.iloc[-1] / init_cash - 1)
    years = n / 252 if n else 1
    annual_ret = float((eq.iloc[-1] / init_cash) ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    cummax = eq.cummax()
    mdd = float(((eq - cummax) / cummax).min())
    wins = sum(1 for t in trades if t["ret"] > 0)
    win_rate = round(wins / len(trades) * 100, 2) if trades else 0.0
    bh = pd.Series(df["close"] / df["close"].iloc[0] * init_cash)
    bh_ret = float(bh.iloc[-1] / init_cash - 1)

    return {
        "total_ret": round(total_ret * 100, 2),
        "annual_ret": round(annual_ret * 100, 2),
        "max_drawdown": round(mdd * 100, 2),
        "win_rate": win_rate,
        "trade_count": len(trades),
        "benchmark_ret": round(bh_ret * 100, 2),
        "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
        "equity": [round(x, 2) for x in eq],
        "benchmark": [round(x, 2) for x in bh],
        "trades": trades,
    }
