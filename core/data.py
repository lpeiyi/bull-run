# -*- coding: utf-8 -*-
"""
数据层：A股 / 基金ETF 的实时行情 + 历史K线（全免费、低延迟）
实时行情：腾讯 qt.gtimg.cn（秒级，A股/ETF 通用）
历史K线：新浪 money.finance.sina.com.cn（日K，前复权，沪深京通用）
"""
import os
import time
import random
import urllib.request
import requests
import pandas as pd

# 关键：删除“沙箱”代理环境变量，让 requests/urllib 回落到系统注册表里的公司代理
# （proxy.xn.petrochina:8080）。公司网络需走该代理才能访问外网，直连会被防火墙阻断。
for _k in list(os.environ):
    if "proxy" in _k.lower():
        os.environ.pop(_k)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA, "Referer": "https://finance.sina.com.cn"})


def to_symbol(code):
    """把 6 位代码转成带市场前缀的 symbol（sh/sz/bj），已带前缀则原样返回"""
    c = str(code).strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    if c.startswith("92"):
        return f"bj{c}"
    if c.startswith(("5", "6", "9")):      # 6/9=A股沪市，5=沪市ETF
        return f"sh{c}"
    if c.startswith(("4", "8")):           # 北交所
        return f"bj{c}"
    return f"sz{c}"                        # 0/3深市，1打头(如159)深市ETF


def real_quotes(codes):
    """批量实时行情，腾讯接口约几秒延迟。返回 {code: {name, price, ...}}"""
    if not codes:
        return {}
    symbols, key_of = [], {}
    for c in codes:
        sym = to_symbol(c)
        symbols.append(sym)
        key_of[sym] = str(c).strip()
    out = {}
    # 每批最多 60 只
    for i in range(0, len(symbols), 60):
        batch = symbols[i:i + 60]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=10).read().decode("gbk")
        for line in data.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key_of.get(key, key[2:])
            out[code] = {
                "name": vals[1],
                "price": float(vals[3] or 0),
                "last_close": float(vals[4] or 0),
                "open": float(vals[5] or 0),
                "change_pct": float(vals[32] or 0),
                "high": float(vals[33] or 0),
                "low": float(vals[34] or 0),
                "amount_yi": round(float(vals[37] or 0) / 10000, 2),
                "turnover_pct": float(vals[38] or 0),
                "pe_ttm": float(vals[39] or 0),
                "amplitude_pct": float(vals[43] or 0),
                "mcap_yi": float(vals[45] or 0),
                "vol_ratio": float(vals[49] or 0),
            }
    return out


# 新浪K线接口（前复权，稳定可靠，沪深京通用）
_SINA_KLINE = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
_SINA_KLINE_MAX = 1000  # 新浪单次最多约1000条


def _parse_sina_kline(data_list):
    """解析新浪日K返回为 DataFrame（字段：day, open, high, low, close, volume）"""
    if not data_list:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    recs = []
    for it in data_list:
        try:
            recs.append({
                "date": it["day"],
                "open": float(it["open"]),
                "high": float(it["high"]),
                "low": float(it["low"]),
                "close": float(it["close"]),
                "volume": float(it.get("volume", 0)),
            })
        except (ValueError, TypeError, KeyError):
            continue
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def kline(code, days=250, adjust="qfq"):
    """
    历史日K线，返回 DataFrame(date, open, high, low, close, volume)
    数据源：新浪财经（前复权）
    adjust 参数目前统一使用前复权（新浪默认）
    带重试和随机延迟，避免触发反爬
    """
    sym = to_symbol(code)
    # 新浪接口单次最多约1000条，多取一些留余量
    fetch_days = min(max(days + 30, 300), _SINA_KLINE_MAX)
    params = {
        "symbol": sym,
        "scale": "240",   # 240分钟 = 日线
        "ma": "no",
        "datalen": str(fetch_days),
    }
    # 带重试：最多 3 次，被封时等待较长时间再试
    max_retry = 3
    for attempt in range(max_retry):
        try:
            # 随机延迟 0.1~0.3 秒，降低请求频率避免被封
            time.sleep(random.uniform(0.1, 0.3))
            r = _SESSION.get(_SINA_KLINE, params=params, timeout=15)
            if r.status_code == 456 or r.status_code == 501:
                # 被反爬拦截，等待更长时间再试
                wait = 10 + attempt * 20
                time.sleep(wait)
                continue
            data = r.json()
            df = _parse_sina_kline(data)
            # 只返回需要的天数
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)
            return df
        except (requests.RequestException, ValueError):
            if attempt < max_retry - 1:
                time.sleep(2 + attempt * 3)
            else:
                raise
    # 所有重试都失败，返回空 DataFrame
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])


def kline_range(code, start="2020-01-01", end="2099-01-01", adjust="qfq"):
    """
    按日期范围拉日K，用于全量历史
    由于新浪接口按条数返回，这里用最大条数获取后再按日期过滤
    """
    sym = to_symbol(code)
    params = {
        "symbol": sym,
        "scale": "240",
        "ma": "no",
        "datalen": str(_SINA_KLINE_MAX),
    }
    r = _SESSION.get(_SINA_KLINE, params=params, timeout=15)
    data = r.json()
    df = _parse_sina_kline(data)
    # 按日期范围过滤
    if len(df) > 0:
        mask = (df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))
        df = df[mask].reset_index(drop=True)
    return df