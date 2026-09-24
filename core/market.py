# -*- coding: utf-8 -*-
"""
市场概览数据：多指数行情 + 涨停/炸板/跌停池明细 + 热点板块（全部免费源）
指数/行情：腾讯（秒级）；涨停四池：东财；板块：新浪
"""
import logging
import math
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


def _compare_and_pick(em_rows, sina_rows, label):
    """东财 vs 新浪名值交叉比对：偏差 > 0.5pp 切新浪；空源直接选另一源。"""
    if not sina_rows and not em_rows:
        return []
    if not sina_rows:  # 新浪失败回退东财
        return list(em_rows)
    if not em_rows:    # 东财失败直接用新浪
        return list(sina_rows)
    # 取双方前 5 名按 name 交叉比对 avg_pct 平均偏差
    em_map = {x.get("name", ""): x.get("avg_pct") for x in em_rows[:5]}
    diffs = []
    hits = 0
    for s in sina_rows[:5]:
        sname = s.get("name", "")
        spct = s.get("avg_pct")
        if not isinstance(spct, (int, float)):
            continue
        if sname in em_map and isinstance(em_map[sname], (int, float)):
            diffs.append(abs(em_map[sname] - spct))
            hits += 1
    # 命中 ≥3 条 且 平均偏差 > 0.5pp → 切新浪（证明东财口径系统性偏了）
    if hits >= 3 and sum(diffs) / len(diffs) > 0.5:
        logging.getLogger(__name__).info(
            "[boards] %s: 东财与新浪 avg_pct 偏差过大(hits=%d, avgΔ=%.2fpp)，切换新浪为主源",
            label, hits, sum(diffs) / len(diffs))
        return list(sina_rows)
    # 否则仍使用东财（保留其默认排序/更多字段）
    return list(em_rows)


def _clean_and_sort(rows):
    """isinstance + 非 NaN 空值过滤 + avg_pct 降序"""
    out = []
    for x in rows:
        p = x.get("avg_pct")
        if isinstance(p, (int, float)) and not (isinstance(p, float) and math.isnan(p)):
            out.append(x)
    out.sort(key=lambda x: x["avg_pct"], reverse=True)
    return out


def get_boards():
    """行业 + 概念板块，按平均涨幅降序。东财主源失败时回退新浪备用源。"""
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
        f3 为整数化涨跌幅(81 表示 0.81%)，需 /100 与新浪单位对齐。
        f6 为成交额，单位为元，/1e8 转成亿。
        fl=f3 指定按涨跌幅字段降序（po=1），保证返回顺序稳定。"""
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fl": "f3",
                  "fields": "f12,f14,f3,f6", "fs": fs_code}
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
                    "amount_yi": round(float(item.get("f6") or 0) / 1e8, 2),  # f6 单位为元，转亿
                    "leader_name": "",               # 东财该接口未返回领涨股
                    "leader_pct": 0.0,
                    "code": item["f12"],             # 板块代码，供扩展使用
                })
            except (KeyError, ValueError, TypeError):
                continue
        return rows

    # 双源校准：同时拉取东财和新浪，再做名值交叉比对切换主源。
    # （东财 f3 是板块指数涨跌幅，不等同于"成分股平均涨幅 avg_pct"，系统性偏低；
    #  新浪 newSinaHy / newFLJK 返回的 parts[4] 即为成分股平均涨幅，口径与用户期望一致。）
    em_ind = _parse_em("m:90+t:2")
    em_con = _parse_em("m:90+t:3")
    try:
        sina_ind = _parse_sina("https://money.finance.sina.com.cn/q/view/newSinaHy.php")
    except Exception:
        sina_ind = []
    try:
        sina_con = _parse_sina("https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class")
    except Exception:
        sina_con = []

    ind = _clean_and_sort(_compare_and_pick(em_ind, sina_ind, "industry"))
    con = _clean_and_sort(_compare_and_pick(em_con, sina_con, "concept"))
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


def _sina_index_amount(code, days):
    """新浪日K线获取指数成交量(亿股)，返回 [{date:'YYYY-MM-DD', volume_yi}] 升序

    新浪K线对指数返回的 volume 字段是成交量(股)，非成交额(元)。
    调用处需用本地缓存的 成交额/成交量 比率(约18-19元/股)转换为成交额(亿元)。
    """
    from core.data import kline
    try:
        df = kline(code, days=days + 10)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        try:
            vol = float(row.get("volume", 0))
            if vol > 0:
                d = row["date"]
                if hasattr(d, "strftime"):
                    d = d.strftime("%Y-%m-%d")
                # 返回成交量(亿股)，调用处乘以均价转为成交额(亿元)
                out.append({"date": d, "volume_yi": round(vol / 1e8, 4)})
        except (ValueError, TypeError):
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


# 开盘啦校准的分时累积权重锚点 [(elapsed_min, cum_weight)]
# V5.1 用 8/28 真实腾讯分时 cum(e) × 截图目标 r(%) 反推：w = cum / (Y × (r/100+1))
# 新增 (15, 0.2229) 锚点，保证 09:30-10:00 下探段曲线形状平滑；w 全程严格单调增
_KPL_ANCHORS = [
    (0,   0.0010),  # 保护点：避免除零
    (1,   0.0354),  # 09:31 首分钟 反推 0.03541 → 目标 +17.94%
    (5,   0.1061),  # 09:35        反推 0.10612 → 目标 +8.97%
    (15,  0.2229),  # 09:45        反推 0.22289 → 目标 +4.50%
    (30,  0.3305),  # 10:00        反推 0.33048 → 目标 +4.00%
    (60,  0.4849),  # 10:30        反推 0.48489 → 目标 +1.00%
    (120, 0.6729),  # 11:30        反推 0.67288 → 目标 -0.50%
    (180, 0.8325),  # 14:00        反推 0.83254 → 目标 -3.00%
    (240, 1.0000),  # 15:00 收盘约束 = 1.0（反推 1.00002，精度取整到 1.0）
]


def _kpl_cum_weight(elapsed_min):
    """KPL 校准的分时累积权重（预测专用；非真实成交量占比）。

    返回值：float，夹在 [0.001, 1.000]；任意分钟在 _KPL_ANCHORS 之间做线性插值。
    - elapsed_min <= 0 -> 0.001（避免除零）
    - elapsed_min >= 240 -> 1.000（收盘 = 100%）
    - 其他时间：在 _KPL_ANCHORS 上找相邻两点做线性插值
    """
    if elapsed_min is None:
        return 0.001
    try:
        e = int(elapsed_min)
    except (ValueError, TypeError):
        return 0.001
    if e <= 0:
        return 0.001
    if e >= 240:
        return 1.000
    # 在 _KPL_ANCHORS 中定位上下界（数组已按 e 升序）
    for i in range(1, len(_KPL_ANCHORS)):
        e_lo, w_lo = _KPL_ANCHORS[i - 1]
        e_hi, w_hi = _KPL_ANCHORS[i]
        if e <= e_hi:
            span = e_hi - e_lo
            if span <= 0:
                w = w_lo
            else:
                frac = (e - e_lo) / float(span)
                w = w_lo + (w_hi - w_lo) * frac
            return min(1.000, max(0.001, w))
    # 理论不会走到（240 已在前面 return），兜底最后一个权重
    return 1.000


def _elapsed_min_by_datetime(now):
    """按 now.datetime 计算 A 股开盘以来整数分钟。

    返回：
    - None：周末 / 非交易时段（9:30 之前 / 15:00 之后）
    - 1..120：上午 9:30-11:30；午休 11:30-13:00 返回 120（上午收盘位）
    - 121..240：下午 13:01-15:00；恰好 15:00 返回 240
    """
    if now is None:
        return None
    if now.weekday() >= 5:
        return None
    t = now.hour * 60 + now.minute
    if t < 9 * 60 + 30:   # < 09:30
        return None
    if t <= 11 * 60 + 30:  # 09:30 ~ 11:30
        return t - (9 * 60 + 30)
    if t < 13 * 60:         # 11:30 ~ 13:00（午休）
        return 120
    if t <= 15 * 60:        # 13:00 ~ 15:00
        return 120 + (t - (13 * 60))
    return 240               # > 15:00


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
        d = r["date"]
        # 统一 date 格式为 YYYY-MM-DD（东财接口可能返回 YYYYMMDD）
        if isinstance(d, str) and len(d) == 8 and "-" not in d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        em[d] = em.get(d, 0) + r["amount_yi"]

    # 实时成交额
    q = real_quotes(["sh000001", "sz399001"])
    actual = round(sum((q.get(c) or {}).get("amount_yi", 0) or 0
                       for c in ("sh000001", "sz399001")), 2)

    # 加载本地缓存（需在新浪合并前，用于计算成交量→成交额的转换比率）
    cache = _load_amount_cache()
    now = datetime.now()
    # 交易日盘后：把当日全天成交额回填到本地缓存
    if now.weekday() < 5 and now.hour * 60 + now.minute >= 15 * 60 and actual > 0:
        cache[now.strftime("%Y-%m-%d")] = actual
        _save_amount_cache(cache)

    # 新浪K线作为东财的补充源（东财被反爬时兜底）
    # 新浪返回成交量(股)，需乘以均价(元/股)转换为成交额(元)
    sina_sh = _sina_index_amount("sh000001", days)
    sina_sz = _sina_index_amount("sz399001", days)
    sina_vol = {}  # {date: 沪深合计成交量(亿股)}
    for r in sina_sh + sina_sz:
        d = r["date"]
        sina_vol[d] = sina_vol.get(d, 0) + r["volume_yi"]
    # 从本地缓存计算转换比率：找最近一个同时有缓存成交额和新浪成交量的日期
    ratio = 18.0  # 默认均价(元/股)，A股约18-19元
    for d in sorted(cache.keys(), reverse=True):
        if d in sina_vol and sina_vol[d] > 0:
            ratio = cache[d] / sina_vol[d]  # 亿元 / 亿股 = 元/股
            break
    # 补充em中缺失的日期（东财优先，新浪仅补缺）
    for d, vol_yi in sina_vol.items():
        if d not in em:
            em[d] = round(vol_yi * ratio, 2)

    # 合并东财历史与本地缓存，得到近 days 日成交额序列（升序）
    merged = {}
    for d, v in em.items():
        merged[d] = round(v, 2)
    for d, v in cache.items():
        if d not in merged and isinstance(v, (int, float)):
            merged[d] = round(v, 2)
    # 交易日实时：把"今日"实际成交额并入，保证 rows[-1] 对齐今日、rows[-2] 对齐昨日
    if now.weekday() < 5 and actual > 0:
        merged[now.strftime("%Y-%m-%d")] = actual
    # 至少取 40 天（保证回看窗口覆盖 1+ 个月交易日）
    take_days = max(days, 40)
    rows = [{"date": d, "amount": v} for d, v in sorted(merged.items())][-take_days:]
    if len(rows) < 22:
        logging.warning(
            "get_liangneng: 历史柱子不足 22 根（当前 %d 根）。"
            " 东财接口=%d 条，新浪=%d 条，本地缓存=%d 条。",
            len(rows), len(em), len(sina_vol), len(cache))

    yesterday = rows[-2]["amount"] if len(rows) >= 2 else None

    # 预测量能：盘中用 KPL 校准累积权重外推（对齐开盘啦 08-28 截图）
    import math  # isinf / isnan 兜底
    elapsed = _elapsed_min_by_datetime(now)
    if elapsed is None or elapsed >= 240:
        # 非交易 / 盘后：预测 = 实际，change_pct 直接算实际 vs 昨日
        predict = actual
        if yesterday and not math.isinf(yesterday) and not math.isnan(yesterday):
            change_pct = round((actual / yesterday - 1) * 100, 2) if actual else None
            if change_pct is not None and (math.isinf(change_pct) or math.isnan(change_pct)):
                change_pct = None
        else:
            change_pct = None
    else:
        # 盘中：KPL 校准权重外推；分母 >= 0.001 不会除零
        w_kpl = _kpl_cum_weight(elapsed)
        try:
            predict = round(actual / w_kpl, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            predict = actual
        if (not yesterday) or math.isinf(yesterday) or math.isnan(yesterday):
            change_pct = None
            predict = actual
        else:
            try:
                change_pct = round((predict / yesterday - 1) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                change_pct = None
                predict = actual
        # clamp + 非有限值兜底
        if change_pct is None or math.isinf(change_pct) or math.isnan(change_pct):
            change_pct = None
            predict = actual
        else:
            change_pct = min(30.0, max(-30.0, float(change_pct)))
            change_pct = round(change_pct, 2)
    if predict is not None and yesterday is not None:
        try:
            change_abs = round(predict - yesterday, 2)
        except (TypeError, ValueError):
            change_abs = None
    else:
        change_abs = None

    # 分时预测量能曲线：KPL 校准权重；全程连续有值；±30% 硬 clamp
    intraday = []
    if yesterday and not math.isinf(yesterday) and not math.isnan(yesterday) and yesterday > 0:
        sh_min = _index_minute_cum("sh000001")
        sz_min = _index_minute_cum("sz399001")
        for t in sorted(set(sh_min) | set(sz_min)):
            e = _elapsed_min(t)
            if e <= 0:
                continue
            cum = (sh_min.get(t) or 0) + (sz_min.get(t) or 0)
            w_kpl = _kpl_cum_weight(e)
            # 防止 w_kpl=0 极端（实际夹到了 0.001，这里再兜底）
            if not w_kpl or w_kpl <= 0:
                w_kpl = 0.001
            pred = cum / w_kpl
            # 计算 change_pct 并 clamp；极端情况 chg -> None 会让曲线断点，尽量都 clamp 成有效数字
            try:
                raw = (pred / yesterday - 1) * 100.0
                if math.isinf(raw):
                    chg = 30.0 if raw > 0 else -30.0
                elif math.isnan(raw):
                    # cum/yesterday 极端：把 pred/yesterday 视作 1（相对昨日 0%）
                    chg = 0.0
                else:
                    chg = min(30.0, max(-30.0, raw))
                chg = round(chg, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                chg = 0.0  # 兜底保持曲线连续
            intraday.append({"time": f"{t[:2]}:{t[2:4]}", "chg": chg})

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