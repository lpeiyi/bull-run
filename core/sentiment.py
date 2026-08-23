# -*- coding: utf-8 -*-
"""
市场情绪指标：把短线情绪量化成 0~100 分（分数越低=越冰点，越高=越过热）
数据源：东方财富涨停/炸板/跌停三池（免费）

对齐「开盘啦」市场情绪中「涨停表现 + 涨跌对比」的口径：
  情绪分 ≈ 涨停家数分(对数,主导) + 连板高度溢价 + 涨停晋级率修正 + 炸板率修正 - 跌停惩罚

⚠️ 数据源限制：东财的跌停池(getTopicDTPool)只保留「当日」，历史日期返回空。
   因此历史情绪序列（近15日曲线）里跌停维度按 0 计算，仅在「当日/实时」情绪分中生效。
"""
import math
import time
import random
from datetime import datetime, timedelta

import requests

from core.data import UA

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last = [0.0]
ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _em_get(url, params):
    """东财接口统一限流（串行，约1秒/次，防封）"""
    wait = 1.0 - (time.time() - _em_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.3))
    try:
        return EM_SESSION.get(url, params=params, timeout=10)
    finally:
        _em_last[0] = time.time()


def _em_pool(endpoint, date, sort="fbt:asc"):
    """拉取东财涨停相关池。注意：昨日涨停池必须用 zs:desc 排序才能取到数据"""
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": sort, "date": date}
    try:
        r = _em_get(url, params)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception:
        return []


def _find_recent_trade_date():
    """从今天往前推找最近交易日（非交易日涨停池返回空）"""
    d = datetime.now()
    for i in range(8):
        t = d - timedelta(days=i)
        if t.weekday() >= 5:
            continue
        ymd = t.strftime("%Y%m%d")
        if _em_pool("getTopicZTPool", ymd):
            return ymd
    return None


def _zt_codes(date):
    """涨停池代码 + 最高连板高度"""
    pool = _em_pool("getTopicZTPool", date)
    return [p["c"] for p in pool], max((p.get("lbc", 0) for p in pool), default=0)


def _zb_count(date):
    return len(_em_pool("getTopicZBPool", date))


def _dt_count(date):
    """跌停家数（东财仅保留当日，历史日期返回 0）"""
    return len(_em_pool("getTopicDTPool", date))


def _promo_rate(date, today_codes):
    """涨停晋级率：昨日涨停池中今日仍封板的比例（接力赚钱效应）"""
    y_pool = _em_pool("getYesterdayZTPool", date, sort="zs:desc")
    y_codes = {p["c"] for p in y_pool}
    if not y_codes:
        return 0.0
    still = y_codes & set(today_codes)
    return round(len(still) / len(y_codes) * 100, 1)


def _calc_score(zt_n, dt_n, max_height, promo_rate, break_rate):
    """算情绪分(0~100)与等级，单日与历史序列共用。

    对齐开盘啦口径的构成：
    - 涨停家数主导（对数映射）：18家≈0分，150家≈90分
    - 连板高度溢价：4板+1 … 8板+5（高度是情绪的领先信号）
    - 涨停晋级率修正：昨日涨停今仍封板比例，越强=接力赚钱效应越好
    - 炸板率修正：封板率过低(炸板率>40%)才扣分，反映板上抛压
    - 跌停惩罚：跌停 ≤30 家视为正常波动，超出部分逐家递减（冰点日关键信号）
    """
    if zt_n <= 0:
        base = 0.0
    else:
        base = max(0.0, min(90.0,
                           90 * (math.log(zt_n) - math.log(18)) / (math.log(150) - math.log(18))))

    height = (5 if max_height >= 8 else 4 if max_height >= 7
              else 3 if max_height >= 6 else 2 if max_height >= 5 else 1 if max_height >= 4 else 0)

    promo = (2 if promo_rate >= 16 else 1 if promo_rate >= 13
             else 0 if promo_rate >= 8 else -1 if promo_rate >= 6 else -2)

    zb = -2 if break_rate > 40 else 0

    dt = -(max(0, dt_n - 30)) * 0.04

    score = int(round(max(0, min(100, base + height + promo + zb + dt))))
    if score <= 25:
        level = "冰点"
    elif score <= 45:
        level = "偏冷"
    elif score <= 65:
        level = "正常"
    elif score <= 80:
        level = "偏热"
    else:
        level = "过热"
    return score, level


def get_sentiment():
    """
    计算当前市场情绪分。返回 {score, level, trade_date, zt_count, dt_count,
    zb_count, break_rate, promo_rate, max_height}
    """
    date = _find_recent_trade_date()
    if not date:
        return {"score": None, "error": "未探测到最近交易日", "trade_date": None}

    zt_codes, max_height = _zt_codes(date)
    zt_n = len(zt_codes)
    zb_n = _zb_count(date)
    dt_n = _dt_count(date)
    promo_rate = _promo_rate(date, zt_codes)
    break_rate = round(zb_n / (zt_n + zb_n) * 100, 1) if (zt_n + zb_n) else 0.0

    score, level = _calc_score(zt_n, dt_n, max_height, promo_rate, break_rate)

    return {
        "score": score, "level": level, "trade_date": date,
        "zt_count": zt_n, "dt_count": dt_n, "zb_count": zb_n,
        "break_rate": break_rate, "promo_rate": promo_rate, "max_height": max_height,
    }