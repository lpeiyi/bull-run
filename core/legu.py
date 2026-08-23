# -*- coding: utf-8 -*-
"""
乐咕乐股「沪深A股涨停板特征统计」历史数据源（免费，2020-02-03 至今）
接口 /api/stockdata/stock-day-limit-total 返回每日：
  涨停家数 / 跌停家数 / 炸板家数 / 连板家数 / 炸板次数 等
用于补齐东财免费接口缺失的历史跌停/炸板数据，拉长情绪曲线。

字段口径（已与东财涨停四池逐一核对）：
  uTotalStock 涨停家数 == 东财 getTopicZTPool 数量
  dTotalStock 跌停家数（东财历史池拿不到，这里每日都有）
  zTotalStock 炸板家数 == 东财 getTopicZBPool 数量
  炸板率 = zTotalStock / (uTotalStock + zTotalStock)
"""
import json
import os
import hashlib
from datetime import datetime

import requests

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_FILE = os.path.join(_BASE, "data", "legu_day_limit_cache.json")
_PAGE = "https://www.legulegu.com/stockdata/stock-day-limit"
_API = "https://www.legulegu.com/api/stockdata/stock-day-limit-total"

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
})


def _token():
    """乐咕接口鉴权 token = MD5(当日日期 YYYY-MM-DD)"""
    return hashlib.md5(datetime.now().strftime("%Y-%m-%d").encode()).hexdigest()


def _fetch_raw():
    """先访问页面建立 cookie 会话，再请求数据接口（接口依赖该 cookie）"""
    _SESSION.get(_PAGE, timeout=20)
    r = _SESSION.get(_API, params={"token": _token()},
                     headers={"Referer": _PAGE}, timeout=30)
    r.raise_for_status()
    return r.json() or []


def _load_cache_rows():
    """读取已缓存历史（不校验日期），失败返回 None"""
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f).get("rows")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fetch_legu_history(force=False):
    """抓取并缓存全量历史涨停数据（当日缓存有效）。返回按日期升序的列表。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if not force:
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("generated") == today and cache.get("rows"):
                return cache["rows"]
        except (OSError, ValueError, KeyError):
            pass

    try:
        raw = _fetch_raw()
    except Exception:
        raw = None
    if raw is None:
        # 抓取失败：回退到旧缓存，保证页面可用
        return _load_cache_rows() or []

    rows = []
    for p in raw:
        try:
            u = int(p.get("uTotalStock") or 0)      # 涨停家数
            z = int(p.get("zTotalStock") or 0)      # 炸板家数
            d = int(p.get("dTotalStock") or 0)      # 跌停家数
            br = round(z / (u + z) * 100, 1) if (u + z) else 0.0
            rows.append({
                "date": str(p.get("tradeDate", "")).replace("-", ""),
                "zt_count": u,
                "zb_count": z,
                "dt_count": d,
                "break_rate": br,
                "limit_times": int(p.get("limitTimes") or 0),  # 连板家数(2板及以上)
            })
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda x: x["date"])
    if not rows:
        return _load_cache_rows() or []

    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"generated": today, "rows": rows}, f, ensure_ascii=False)
    except OSError:
        pass
    return rows


def get_legu_map(force=False):
    """返回 {date: 数据行} 字典，便于按日期查询"""
    return {r["date"]: r for r in fetch_legu_history(force)}