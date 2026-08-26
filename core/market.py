# -*- coding: utf-8 -*-
"""
市场概览数据：多指数行情 + 涨停/炸板/跌停池明细 + 热点板块（全部免费源）
指数/行情：腾讯（秒级）；涨停四池：东财；板块：新浪
"""
import os
import time
import random
import re
import json
import urllib.request
from datetime import datetime, timedelta

import requests

from core.data import UA, real_quotes, to_symbol

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last = [0.0]
ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"

# 首页顶部指数条
INDEX_CODES = ["sh000001", "sz399001", "sz399006", "sh000688",
               "sh000016", "sh000905", "sh000300", "sh000852"]


def _em_get(url, params):
    """东财接口统一限流（串行，约1秒/次，防封）"""
    wait = 1.0 - (time.time() - _em_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.3))
    try:
        return EM_SESSION.get(url, params=params, timeout=12)
    finally:
        _em_last[0] = time.time()


def _em_pool(endpoint, date):
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": "fbt:asc", "date": date}
    try:
        r = _em_get(url, params)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception:
        return []


def find_trade_date():
    """从今天往前推找最近交易日"""
    d = datetime.now()
    for i in range(8):
        t = d - timedelta(days=i)
        if t.weekday() >= 5:
            continue
        ymd = t.strftime("%Y%m%d")
        if _em_pool("getTopicZTPool", ymd):
            return ymd, t.strftime("%Y-%m-%d")
    return None, None


def _fmt_time(t):
    s = str(t).zfill(6)
    return f"{s[0:2]}:{s[2:4]}:{s[4:6]}"


def get_indexes():
    """多个指数实时行情"""
    return real_quotes(INDEX_CODES)


def get_zt_pool(date):
    """涨停池明细"""
    out = []
    for p in _em_pool("getTopicZTPool", date):
        out.append({
            "code": p["c"], "name": p["n"], "price": round(p["p"] / 1000, 2),
            "pct": round(p["zdp"], 2), "amount_yi": round(p["amount"] / 1e8, 2),
            "turnover": round(p["hs"], 2), "limit_days": p["lbc"],
            "first_seal": _fmt_time(p["fbt"]),
            "seal_fund_yi": round(p["fund"] / 1e8, 2),
            "break_times": p["zbc"], "industry": p.get("hybk", ""),
        })
    return out


def get_zb_pool(date):
    """炸板池明细（曾涨停后开板）"""
    out = []
    for p in _em_pool("getTopicZBPool", date):
        out.append({
            "code": p["c"], "name": p["n"], "price": round(p["p"] / 1000, 2),
            "pct": round(p["zdp"], 2), "turnover": round(p["hs"], 2),
            "amplitude": round(p["zf"], 2), "break_times": p["zbc"],
            "industry": p.get("hybk", ""),
        })
    return out


def get_dt_pool(date):
    """跌停池明细。
    当日实时：用新浪全市场行情构建完整跌停股列表（覆盖更全）。
    历史日期：新浪列表只有当日数据，回退东财 getTopicDTPool 兜底。
    返回结构: [{code, name, price, pct, dt_days, industry}]
    """
    today = datetime.now().strftime("%Y%m%d")
    if date == today:
        try:
            from core.sentiment import _dt_list_sina
            dt_list = _dt_list_sina()
        except Exception:
            dt_list = None
        # dt_list is None 表示新浪拉取失败；空列表表示当日无跌停
        if dt_list is not None:
            out = []
            for s in dt_list:
                out.append({
                    "code": s.get("pure_code") or s.get("code", ""),
                    "name": s.get("name", ""),
                    "price": round(s.get("price") or 0, 2),
                    "pct": round(s.get("change_pct") or 0, 2),
                    "dt_days": 1,  # 新浪数据无连板天数，默认 1
                    "industry": s.get("industry", ""),
                })
            return out
    # 历史日期或新浪失败时兜底：东财接口
    out = []
    for p in _em_pool("getTopicDTPool", date):
        out.append({
            "code": p["c"], "name": p["n"], "price": round(p["p"] / 1000, 2),
            "pct": round(p["zdp"], 2), "dt_days": p.get("days", 0),
            "industry": p.get("hybk", ""),
        })
    return out


def get_boards():
    """行业 + 概念板块，按平均涨幅降序。新浪主源失败时回退东财备用源。"""
    def _parse_sina(url):
        """新浪板块解析：返回 [] 表示拉取/解析失败。"""
        r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        r.encoding = "gbk"
        m = re.search(r"=\s*(\{.*?\})\s*;?\s*$", r.text, re.S)
        if not m:
            return []
        d = json.loads(m.group(1))
        rows = []
        for raw in d.values():
            parts = raw.split(",")
            if len(parts) < 13:
                continue
            try:
                rows.append({
                    "name": parts[1], "stock_count": int(parts[2]),
                    "avg_pct": round(float(parts[4]), 2),
                    "amount_yi": round(float(parts[7]) / 1e8, 2),
                    "leader_name": parts[12], "leader_pct": round(float(parts[9]), 2),
                })
            except (ValueError, IndexError):
                continue
        return rows

    def _parse_em(fs_code):
        """东财板块解析：fs=m:90+t:2 行业、m:90+t:3 概念。
        f3 为整数化涨跌幅(81 表示 0.81%)，需 /100 与新浪单位对齐。"""
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn": 1, "pz": 100, "po": 1, "np": 1,
                  "fields": "f12,f14,f3", "fs": fs_code}
        try:
            r = requests.get(url, headers={"User-Agent": UA}, params=params, timeout=12)
            diff = (r.json().get("data") or {}).get("diff") or []
        except Exception:
            return []
        rows = []
        for item in diff:
            try:
                rows.append({
                    "name": item["f14"],
                    "stock_count": 0,                # 东财该接口未返回成分股数
                    "avg_pct": round(float(item["f3"]) / 100, 2),
                    "amount_yi": 0.0,                # 东财该接口未返回成交额
                    "leader_name": "",               # 东财该接口未返回领涨股
                    "leader_pct": 0.0,
                    "code": item["f12"],             # 板块代码，供扩展使用
                })
            except (KeyError, ValueError, TypeError):
                continue
        return rows

    try:
        ind = _parse_sina("https://money.finance.sina.com.cn/q/view/newSinaHy.php")
        con = _parse_sina("https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class")
    except Exception:
        ind, con = [], []

    # 新浪任一源为空则用东财备用源兜底
    if not ind:
        ind = _parse_em("m:90+t:2")
    if not con:
        con = _parse_em("m:90+t:3")

    ind.sort(key=lambda x: x["avg_pct"], reverse=True)
    con.sort(key=lambda x: x["avg_pct"], reverse=True)
    return {"industry": ind, "concept": con}


# ── 市场量能 ──────────────────────────────────────
def _em_index_amount(secid, days):
    """东财指数日K成交额(亿)，返回 [{date:'YYYY-MM-DD', amount_yi}] 升序"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {"secid": secid, "klt": "101", "fqt": "0", "lmt": str(days + 10),
              "end": "20500101", "fields1": "f1,f2,f3,f4,f5,f6",
              "fields2": "f51,f52,f53,f54,f55,f56,f57"}
    try:
        r = EM_SESSION.get(url, params=params, timeout=12)
        klines = (r.json().get("data") or {}).get("klines") or []
    except Exception:
        return []
    out = []
    for k in klines:
        p = k.split(",")
        if len(p) > 6:
            try:
                out.append({"date": p[0], "amount_yi": round(float(p[6]) / 1e8, 2)})
            except ValueError:
                continue
    return out


def _trade_elapsed_ratio(now):
    """当前时刻已过交易时间占比（A股 9:30-11:30、13:00-15:00）。非交易时段返回 None"""
    if now.weekday() >= 5:
        return None
    t = now.hour * 60 + now.minute
    total = 240.0
    if t < 9 * 60 + 30:
        return None
    if t <= 11 * 60 + 30:
        elapsed = t - (9 * 60 + 30)
    elif t < 13 * 60:
        elapsed = 120.0
    elif t <= 15 * 60:
        elapsed = 120.0 + (t - 13 * 60)
    else:
        return None
    return min(max(elapsed / total, 0.001), 1.0)


# A股典型分时量能分布权重（按 30 分钟一段，共 8 段，合计 1.0）
# U 型曲线：开盘半小时与尾盘各约占 15%，上午其余约 35%，午后约 35%
# 顺序：9:30-10:00, 10:00-10:30, 10:30-11:00, 11:00-11:30,
#       13:00-13:30, 13:30-14:00, 14:00-14:30, 14:30-15:00
_INTRADAY_SEG_WEIGHTS = (0.15, 0.13, 0.11, 0.11, 0.11, 0.11, 0.13, 0.15)


def _intraday_cum_weight(elapsed_min):
    """按 A股分时 U 型分布，返回已过 elapsed_min 分钟的累计量能占比(0~1)。
    elapsed_min: 0~240；段内按线性插值。
    """
    if elapsed_min <= 0:
        return 0.0
    if elapsed_min >= 240:
        return 1.0
    seg = int(elapsed_min // 30)            # 0~7
    offset = elapsed_min - seg * 30        # 段内偏移 0~30
    cum = sum(_INTRADAY_SEG_WEIGHTS[:seg])
    cum += _INTRADAY_SEG_WEIGHTS[seg] * (offset / 30.0)
    return cum


def _intraday_weight_ratio(now):
    """当前时刻按 A股 U 型分时分布应完成的量能占比(0~1)。
    非交易时段返回 None。用于替代线性时间占比做量能预测外推。
    """
    if now.weekday() >= 5:
        return None
    t = now.hour * 60 + now.minute
    if t < 9 * 60 + 30:
        return None
    if t <= 11 * 60 + 30:
        e = t - (9 * 60 + 30)              # 0~120
    elif t < 13 * 60:
        e = 120.0                          # 午休，上午已结束
    elif t <= 15 * 60:
        e = 120.0 + (t - 13 * 60)          # 120~240
    else:
        return None
    return _intraday_cum_weight(e)


def _elapsed_min(t):
    """分时时间 '0931' -> 开盘以来已过分钟数（9:30 集合竞价为 0）。"""
    try:
        h = int(t[:2]); m = int(t[2:4])
    except ValueError:
        return 0
    if h < 12:
        return max(0, (h - 9) * 60 + m - 30)
    return max(0, 120 + (h - 13) * 60 + m)


def _index_minute_cum(code):
    """腾讯分时累计成交额，返回 {HHMM: 成交额(亿)}。失败返回空 dict。"""
    sym = to_symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={sym}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
        node = (((json.loads(raw).get("data") or {}).get(sym) or {}).get("data") or {}).get("data") or []
    except Exception:
        return {}
    out = {}
    for row in node:
        p = row.split(" ")
        if len(p) < 4:
            continue
        try:
            out[p[0]] = float(p[3]) / 1e8
        except ValueError:
            continue
    return out


_AMOUNT_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "amount_history.json")


def _load_amount_cache():
    """读取本地累计的两市成交额 {YYYY-MM-DD: 成交额(亿)}。东财历史接口被代理拦截时兜底。"""
    try:
        with open(_AMOUNT_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_amount_cache(d):
    try:
        with open(_AMOUNT_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_liangneng(days=20):
    """市场量能：沪深实际/预测量能 + 昨日量能 + 近 days 日两市成交额走势"""
    sh = _em_index_amount("1.000001", days)
    sz = _em_index_amount("0.399001", days)
    em = {}
    for r in sh + sz:
        em[r["date"]] = em.get(r["date"], 0) + r["amount_yi"]

    q = real_quotes(["sh000001", "sz399001"])
    actual = round(sum((q.get(c) or {}).get("amount_yi", 0) or 0
                       for c in ("sh000001", "sz399001")), 2)

    # 交易日盘后：把当日全天成交额回填到本地缓存，供东财历史不可用时兜底
    cache = _load_amount_cache()
    now = datetime.now()
    if now.weekday() < 5 and now.hour * 60 + now.minute >= 15 * 60 and actual > 0:
        cache[now.strftime("%Y-%m-%d")] = actual
        _save_amount_cache(cache)

    # 合并东财历史与本地缓存，得到近 days 日成交额序列（升序）
    merged = {}
    for d, v in em.items():
        merged[d] = round(v, 2)
    for d, v in cache.items():
        merged[d] = round(v, 2)
    # 交易日实时：把“今日”实际成交额并入，保证 rows[-1] 对齐今日、rows[-2] 对齐昨日
    if now.weekday() < 5 and actual > 0:
        merged[now.strftime("%Y-%m-%d")] = actual
    rows = [{"date": d, "amount": v} for d, v in sorted(merged.items())][-days:]

    yesterday = rows[-2]["amount"] if len(rows) >= 2 else None

    # 预测量能：盘中按 A股 U 型分时量能分布外推，盘后/非交易时段 = 实际值
    w_ratio = _intraday_weight_ratio(now)
    predict = round(actual / w_ratio, 2) if (w_ratio and 0 < w_ratio < 1) else actual

    change_pct = round((predict / yesterday - 1) * 100, 2) if (predict and yesterday) else None
    change_abs = round(predict - yesterday, 2) if (predict is not None and yesterday is not None) else None

    # 分时预测量能曲线：每分钟按 U 型分时分布外推
    # pred = 两市累计成交额 / 当前时刻应完成量能占比
    intraday = []
    if yesterday:
        sh_min = _index_minute_cum("sh000001")
        sz_min = _index_minute_cum("sz399001")
        for t in sorted(set(sh_min) | set(sz_min)):
            e = _elapsed_min(t)
            if e <= 0:
                continue
            cum = (sh_min.get(t) or 0) + (sz_min.get(t) or 0)
            w = _intraday_cum_weight(e)
            pred = cum / w if w > 0 else cum
            intraday.append({"time": f"{t[:2]}:{t[2:4]}",
                             "chg": round((pred / yesterday - 1) * 100, 2)})

    # 盘后(>=15:00)才补 15:00 收盘点；盘中不补，避免 ECharts 等距 X 轴把末端真实点拉到 15:00 处
    if intraday and intraday[-1]["time"] != "15:00" and now.hour * 60 + now.minute >= 900:
        intraday.append({"time": "15:00", "chg": intraday[-1]["chg"]})

    return {
        "trade_date": rows[-1]["date"] if rows else None,
        "actual": actual,
        "predict": predict,
        "yesterday": yesterday,
        "change_pct": change_pct,
        "change_abs": change_abs,
        "trend": [{"date": r["date"][5:], "amount": r["amount"]} for r in rows],
        "intraday": intraday,
    }