# -*- coding: utf-8 -*-
"""
数据层：A股 / 基金ETF 的实时行情 + 历史K线（全免费、低延迟）
实时行情：腾讯 qt.gtimg.cn（秒级，A股/ETF 通用）
历史K线：腾讯 ifzq.gtimg.cn（日K，支持前复权 qfq / 后复权 hfq / 不复权）
"""
import os
import urllib.request
import requests
import pandas as pd

# 关键：删除沙箱代理环境变量，否则国内行情接口会被代理拦截
for _k in list(os.environ):
    if "proxy" in _k.lower():
        os.environ.pop(_k)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA})


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


_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def _parse_kline(d, sym, adjust):
    """解析腾讯日K返回体为 DataFrame（腾讯字段顺序: [日期,开,收,高,低,成交量]）"""
    node = (d.get("data") or {}).get(sym) or {}
    rows = node.get(f"{adjust}day") or node.get("day") or []
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    recs = []
    for it in rows:
        try:
            recs.append({
                "date": it[0],
                "open": float(it[1]),
                "close": float(it[2]),
                "high": float(it[3]),
                "low": float(it[4]),
                "volume": float(it[5]) if len(it) > 5 else 0.0,
            })
        except (ValueError, TypeError, IndexError):
            continue
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def kline(code, days=250, adjust="qfq"):
    """历史日K线，返回 DataFrame(date, open, high, low, close, volume)"""
    sym = to_symbol(code)
    url = f"{_KLINE}?param={sym},day,,,{days},{adjust}"
    r = _SESSION.get(url, timeout=12)
    return _parse_kline(r.json(), sym, adjust)


def kline_range(code, start="2020-01-01", end="2099-01-01", adjust="qfq"):
    """按日期范围拉日K（绕过单次约1000根上限），用于全量历史"""
    sym = to_symbol(code)
    url = f"{_KLINE}?param={sym},day,{start},{end},2000,{adjust}"
    r = _SESSION.get(url, timeout=12)
    return _parse_kline(r.json(), sym, adjust)