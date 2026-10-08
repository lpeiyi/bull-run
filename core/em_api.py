# -*- coding: utf-8 -*-
"""东财 push2ex 接口统一访问层：全局限流 + 池结果进程内缓存。

为什么需要这一层（见 specs/cut-sentiment-latency/design.md §1）：

1. 改造前 `core/sentiment.py` 与 `core/market.py` 各有一份**逐字相同**的 `_em_get`，
   各自持有独立的 `_em_last` —— 也就是说"1 秒/次防封"从来不是全局的：两个模块
   交替请求时，对东财的实际速率是设计值的 2 倍。收敛成单一全局间隔后，
   "防封"这条约束才第一次真正成立；`/api/overview` 也一并受益。
2. 同一 `(endpoint, date, sort)` 在一屏之内会被请求多次（如
   `_find_recent_trade_date()` 探测交易日时的涨停池，与 `get_sentiment()` 主体
   为拿涨停池又拉的一次，参数完全相同）。30 秒进程内缓存把这几处合成 1 次真实请求。

设计要点（参数与理由见 design §1.3 / §3）：

- **锁内 sleep + 锁内请求**：让所有东财请求严格串行 —— 这正是"限流"的定义。
- **缓存命中判断也在锁内（double-check）**：否则并发同 key 会各自发一次请求。
- **失败不写缓存**：区分"请求失败"与"成功但池为空"。
- **当日空池不写缓存**（红线 AC-4.1）：空池可能是"当天还没涨停"这个会变的中间态，
  缓存它会让交易日探测回退到前一日并卡住整个 TTL。
"""
import logging
import random
import threading
import time
from datetime import datetime

import requests

from core.data import UA

EM_BASE_URL = "https://push2ex.eastmoney.com"

# 全局最小请求间隔（秒）
# ⚠️ 本模块唯一有外部风险的常量：调小可能触发东财限流/封禁。
#    回滚方式 = 把这一行改回 1.0，其余改动均不受影响。建议观察 1~2 个交易日。
EM_MIN_INTERVAL = 0.35
EM_JITTER = (0.05, 0.15)      # 间隔抖动区间：避免多进程/多线程同时发起
POOL_TTL = 30                 # 池结果进程内缓存有效期（秒）
EM_TIMEOUT = 10               # 单请求超时（秒）。sentiment 原为 10、market 原为 12，统一取 10

# 失败自适应降速（可选子项，见 design §1.3(f)）：把"防封"从静态常量变成带反馈的闭环
EM_BACKOFF_STREAK = 3         # 连续失败达此数 → 有效间隔翻倍
EM_BACKOFF_MAX = 2.0          # 退避上限（秒）
EM_RECOVER_STREAK = 10        # 连续成功达此数 → 恢复基准间隔

ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"

_log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA})

# 用 RLock：pool() 持锁期间会调用 get()，二者共用同一把锁（RLock 允许同线程重入）
_LOCK = threading.RLock()
_last = [0.0]                  # 上一次真实请求结束时刻（全局唯一一份，不再按模块各持一份）
_INTERVAL = [EM_MIN_INTERVAL]  # 当前有效间隔（可被失败退避临时调高）
_fail_streak = [0]             # 连续失败计数
_ok_streak = [0]               # 连续成功计数
_CACHE = {}                    # {(endpoint, date, sort): (ts, pool)}


def _today():
    """今日 YYYYMMDD。

    刻意用 datetime 而非 time.strftime：本模块的 `time` 会被单测整体替换成假时钟
    来验证限流间隔，`_today()` 不能受其影响。
    """
    return datetime.now().strftime("%Y%m%d")


def _sleep_to_interval():
    """等待到满足全局最小间隔。**调用方必须已持有 _LOCK。**

    锁内 sleep 是关键：若在锁外睡，多线程会同时睡、同时发，限流形同虚设。
    """
    wait = _INTERVAL[0] - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(*EM_JITTER))


def _feedback(ok):
    """失败自适应降速。**调用方必须已持有 _LOCK。**"""
    if ok:
        _fail_streak[0] = 0
        _ok_streak[0] += 1
        if _ok_streak[0] >= EM_RECOVER_STREAK and _INTERVAL[0] != EM_MIN_INTERVAL:
            _INTERVAL[0] = EM_MIN_INTERVAL
            _log.info("[em_api] 连续 %d 次请求成功，限流间隔恢复 %.2fs",
                      _ok_streak[0], EM_MIN_INTERVAL)
    else:
        _ok_streak[0] = 0
        _fail_streak[0] += 1
        if _fail_streak[0] >= EM_BACKOFF_STREAK and _INTERVAL[0] < EM_BACKOFF_MAX:
            _INTERVAL[0] = min(EM_BACKOFF_MAX, _INTERVAL[0] * 2)
            _log.warning("[em_api] 连续 %d 次请求失败，限流间隔临时上调至 %.2fs",
                         _fail_streak[0], _INTERVAL[0])


def get(url, params, timeout=EM_TIMEOUT):
    """东财接口统一请求（全局限流，串行）。异常向上抛，由调用方决定降级方式。"""
    with _LOCK:
        _sleep_to_interval()
        ok = False
        try:
            r = _SESSION.get(url, params=params, timeout=timeout)
            ok = True
            return r
        finally:
            _last[0] = time.time()
            _feedback(ok)


def _request_pool(endpoint, date, sort):
    """真实请求一个池。返回 (pool, ok)：失败返回 ([], False)，成功即使空池也返回 ok=True。"""
    url = "%s/%s" % (EM_BASE_URL, endpoint)
    params = {"ut": ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": sort, "date": date}
    try:
        r = get(url, params)
        return (r.json().get("data") or {}).get("pool") or [], True
    except Exception as e:
        _log.warning("[em_api] %s date=%s 请求失败：%s", endpoint, date, e)
        return [], False


def pool(endpoint, date, sort="fbt:asc"):
    """拉取东财涨停相关池（全局限流 + 30s 进程内缓存）。对外主入口。

    返回 pool 列表；请求失败返回 []（且**不写缓存**）。注意：昨日涨停池必须用
    `zs:desc` 排序才能取到数据，所以 `sort` 参与缓存 key。

    缓存规则：
      - key = (endpoint, date, sort)，date 参与 key ⇒ 跨交易日天然失效（AC-2.2）
      - 命中判断在锁内（double-check）⇒ 同 key 并发只发 1 次真实请求（single-flight）
      - 请求失败不写缓存（AC-2.3）
      - **当日空池不写缓存**（AC-4.1 红线）：见模块 docstring
      - 非当日空池照常缓存：那是"非交易日 / 历史无数据"的稳定事实
    """
    key = (endpoint, date, sort)
    with _LOCK:
        ent = _CACHE.get(key)
        if ent is not None and (time.time() - ent[0]) < POOL_TTL:
            _log.debug("[em_api] 缓存命中 %s", key)
            return ent[1]

        rows, ok = _request_pool(endpoint, date, sort)
        if not ok:
            return []
        if rows or date != _today():
            _CACHE[key] = (time.time(), rows)
        return rows


def clear_cache():
    """清空池缓存（测试 / 排障用）。不重置限流时间戳与间隔。"""
    with _LOCK:
        _CACHE.clear()


def cache_info():
    """返回缓存条目数与当前有效限流间隔（测试断言 / 排障用）。"""
    with _LOCK:
        return {
            "entries": len(_CACHE),
            "interval": _INTERVAL[0],
            "base_interval": EM_MIN_INTERVAL,
            "ttl": POOL_TTL,
        }


def reset_state():
    """重置全部进程级状态（测试夹具用）：清缓存、复位时间戳/间隔/失败计数。"""
    with _LOCK:
        _CACHE.clear()
        _last[0] = 0.0
        _INTERVAL[0] = EM_MIN_INTERVAL
        _fail_streak[0] = 0
        _ok_streak[0] = 0
