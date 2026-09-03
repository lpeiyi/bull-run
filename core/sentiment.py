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

import logging
from core import legu
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


def _is_dt_stock(stock):
    """判断单只股票是否跌停。
    依赖新浪 change_pct 字段（单位百分比，如 -10.02 表示跌 10.02%）。
    规则：主板 <= -9.8%，创业板(300)/科创板(688) <= -19.5%，北交所(bj) <= -29.5%。
    """
    pct = stock.get("change_pct")
    if pct is None:
        return False
    pure_code = stock.get("pure_code", "")
    market = stock.get("market", "")
    if market == "bj":
        return pct <= -29.5
    if pure_code.startswith("300") or pure_code.startswith("688"):
        return pct <= -19.5
    return pct <= -9.8


def _dt_list_sina():
    """基于新浪全市场行情返回当日跌停股票列表。
    load_stock_list 有 24 小时缓存，不会频繁请求。
    返回: 跌停股票列表（list）；失败返回 None（用于调用方回退东财）。
    """
    try:
        from core.screener import load_stock_list
        stocks = load_stock_list()
    except Exception:
        return None
    return [s for s in stocks if _is_dt_stock(s)]


def _dt_count(date):
    """跌停家数。
    当日实时：用新浪全市场行情计算（load_stock_list 有 24 小时缓存，覆盖全市场）。
    历史日期：新浪列表只有当日数据，回退东财 getTopicDTPool 兜底（可能不全）。
    """
    today = datetime.now().strftime("%Y%m%d")
    if date == today:
        dt_list = _dt_list_sina()
        if dt_list is not None:
            return len(dt_list)
    return len(_em_pool("getTopicDTPool", date))


def _promo_rate(date, today_codes):
    """涨停晋级率：昨日涨停池中今日仍封板的比例（接力赚钱效应）"""
    y_pool = _em_pool("getYesterdayZTPool", date, sort="zs:desc")
    y_codes = {p["c"] for p in y_pool}
    if not y_codes:
        return 0.0
    still = y_codes & set(today_codes)
    return round(len(still) / len(y_codes) * 100, 1)


def _filter_zt_pool(zt_list):
    """过滤涨停池：排除 ST/*ST 股票和上市不足 60 日的新股，对齐开盘啦口径。

    东财涨停池 c 字段为 pure_code 格式（如 "600903"），故映射 key 用 pure_code。
    load_stock_list 无 list_date 字段，新股过滤会被跳过（不影响 ST 过滤）。
    """
    try:
        from core.screener import load_stock_list
        stocks = load_stock_list()  # 有 24h 缓存
        stock_map = {s.get("pure_code", ""): s for s in stocks}
        cutoff = datetime.now() - timedelta(days=60)
        filtered = []
        for code in zt_list:
            s = stock_map.get(code, {})
            name = s.get("name", "")
            # 排除 ST/*ST
            if "ST" in name or "*ST" in name:
                continue
            # 排除新股（上市不足 60 日）—— list_date 字段缺失时跳过此检查
            list_date = s.get("list_date")
            if list_date:
                try:
                    ld = datetime.strptime(str(list_date)[:10], "%Y-%m-%d")
                    if ld > cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            filtered.append(code)
        return filtered
    except Exception:
        return zt_list  # 过滤失败返回原列表


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
    # 各维度对总分的正负贡献明细（用于前端可视化）
    contributions = {
        "涨停家数": round(base, 2),
        "连板高度": height,
        "晋级率": promo,
        "炸板率": zb,
        "跌停惩罚": round(dt, 2),
    }
    return score, level, contributions


def get_sentiment():
    """
    计算当前市场情绪分。返回 {score, level, trade_date, zt_count, dt_count,
    zb_count, break_rate, promo_rate, max_height, contributions}

    数据来源：优先走乐咕 API（涨停/跌停/炸板数+炸板率），东财仅补充连板高度和晋级率。
    乐咕缓存不是当日或失败时回退东财+新浪逻辑（涨停池过滤 ST/新股对齐开盘啦口径）。
    """
    date = _find_recent_trade_date()
    if not date:
        return {"score": None, "error": "未探测到最近交易日", "trade_date": None}

    # 东财涨停池：过滤 ST/新股后用于连板高度、晋级率和回退涨停数
    pool = _em_pool("getTopicZTPool", date)
    zt_codes = _filter_zt_pool([p["c"] for p in pool])
    zt_set = set(zt_codes)
    # 用过滤后的涨停池重算最高连板高度（排除 ST/新股的连板）
    max_height = max((p.get("lbc", 0) for p in pool if p["c"] in zt_set), default=0) if zt_set else 0
    promo_rate = _promo_rate(date, zt_codes)

    # 优先用乐咕 API 获取主因子（涨停/跌停/炸板数+炸板率），口径与历史一致
    zt_n = zb_n = dt_n = 0
    break_rate = 0.0
    trade_date = date  # 默认用东财探测到的交易日
    legu_ok = False
    try:
        rows = legu.fetch_legu_history()
        # 仅当乐咕最后一条日期 == 当日时才采用，避免用到早盘缓存的不完整前一日数据
        if rows and rows[-1].get("date", "") == date:
            last = rows[-1]
            zt_n = last.get("zt_count", 0)
            dt_n = last.get("dt_count", 0)
            zb_n = last.get("zb_count", 0)
            break_rate = last.get("break_rate", 0.0)
            trade_date = last.get("date", date)  # 乐咕返回的 YYYYMMDD
            legu_ok = True
    except Exception as e:
        logging.warning(f"乐咕 API 失败，回退东财+新浪: {e}")

    # 乐咕缓存不是当日或失败时回退东财+新浪逻辑
    if not legu_ok:
        zt_n = len(zt_codes)
        zb_n = _zb_count(date)
        dt_n = _dt_count(date)
        break_rate = round(zb_n / (zt_n + zb_n) * 100, 1) if (zt_n + zb_n) else 0.0

    score, level, contributions = _calc_score(zt_n, dt_n, max_height, promo_rate, break_rate)

    return {
        "score": score, "level": level, "trade_date": trade_date,
        "zt_count": zt_n, "dt_count": dt_n, "zb_count": zb_n,
        "break_rate": break_rate, "promo_rate": promo_rate, "max_height": max_height,
        "contributions": contributions,
    }