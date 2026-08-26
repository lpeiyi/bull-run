# -*- coding: utf-8 -*-
"""
黄金行情数据层（实时 + 历史）
- 实时行情：新浪 hq.sinajs.cn（伦敦金 hf_XAU / COMEX金 hf_GC / 沪金主连 AU0）
- 历史走势：518880（黄金 ETF，A股通用 kline 接口稳定）
所有接口均使用 requests Session，天然走系统注册表代理（公司网络可用）。
"""
import os
import time
import random
import requests
import pandas as pd

# 与 core/data.py 一致：清掉本地 proxy 环境变量，让 requests 回落到系统代理
for _k in list(os.environ):
    if "proxy" in _k.lower():
        os.environ.pop(_k)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA, "Referer": "https://finance.sina.com.cn"})

# 三品种定义：新浪代码、展示名、类型（hf=海外现货/期货，shfe=国内期货）
SPOTS = [
    ("hf_XAU", "伦敦金 XAUUSD", "hf"),
    ("hf_GC",  "COMEX黄金 GC",  "hf"),
    ("AU0",    "沪金主连 AU0",  "shfe"),
]


def _float(v):
    """安全转 float，空值或异常返回 0.0"""
    try:
        return float(v) if v not in (None, "", "-") else 0.0
    except (TypeError, ValueError):
        return 0.0


def get_gold_spot():
    """
    黄金三品种实时行情。
    返回: (spot_list, err_msg)
      spot_list 每项: {symbol, name, price, pct, high, low, open, last_close}
      err_msg 无错误为 ""，有错误为描述字符串（不抛异常）。
    """
    spot = []
    symbols = [s[0] for s in SPOTS]
    try:
        # 新浪 hq 列表接口
        url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
        # 随机短延迟，避免反爬
        time.sleep(random.uniform(0.05, 0.15))
        r = _SESSION.get(url, timeout=12)
        r.encoding = "gbk"
        lines = [ln.strip() for ln in r.text.split("\n") if ln.strip() and '"' in ln and "=" in ln]
        # 建立 {key: csv_string} 索引（新浪返回形如 var hq_str_hf_XAU="...,..";）
        kv = {}
        for ln in lines:
            head, _, rest = ln.partition("=")
            key = head.replace("var hq_str_", "").strip()
            payload = rest.split('"')[1] if '"' in rest else rest
            kv[key] = payload

        for symbol, default_name, stype in SPOTS:
            payload = kv.get(symbol)
            if not payload:
                continue
            parts = payload.split(",")
            n = len(parts)
            name = default_name
            last_close = price = open_p = high = low = 0.0
            pct = 0.0
            if stype == "hf" and n >= 14:
                # hf_* (伦敦金/纽约金): [0]price,[1]昨收?,[2]?[3]?[4]高[5]低[6]time[7]?[8]?...[12]date[13]name
                name = parts[13] or default_name
                price = _float(parts[0])
                last_close = _float(parts[1]) or _float(parts[7])  # 昨收或第 8 段兜底
                open_p = _float(parts[2])
                high = _float(parts[4])
                low = _float(parts[5])
                if last_close:
                    pct = round((price - last_close) / last_close * 100, 2)
            elif stype == "shfe" and n >= 28:
                # 沪金 AU0（新浪期货 28 段，基于对 AU0/AU2412 实采数据的字段反推）：
                # [0]name[1]未知id(非数值)[2]今开[3]最高[4]最低[5]买一价[6]买二[7]卖一[8]最新价[9]0
                # [10]昨结算价（作为 pct 计算的昨收基准，最稳定合理）[11-16]成交量相关
                # [17]数据日期(YYYY-MM-DD) [19-26]周/月/年级别高低 [27]误称"涨跌幅"，实为累计/合约级指标，不可用
                name = parts[0] or default_name
                open_p = _float(parts[2])
                high = _float(parts[3])
                low = _float(parts[4])
                price = _float(parts[8])  # 最新价
                settle = _float(parts[10])  # 昨结算价，作为计算日涨跌幅的基准
                # last_close 选择：优先昨结算 settle；若 7 段卖一价在合理价格区间也可兜底
                candidates_last = [settle, _float(parts[7])]
                last_close = next((x for x in candidates_last if x > 100), 0.0)
                # 按昨结算价重算当日涨跌幅（忽略不可靠的 27 段原值）
                if last_close and price:
                    pct = round((price - last_close) / last_close * 100, 2)
                else:
                    pct = 0.0
            else:
                # 字段结构不匹配：跳过
                continue

            spot.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "pct": pct,
                "high": high,
                "low": low,
                "open": open_p,
                "last_close": last_close,
            })
        return spot, ""
    except Exception as e:
        return [], f"get_gold_spot: {type(e).__name__}:{e}"


def get_gold_history(days=30):
    """
    黄金近 N 日历史收盘价。
    外部现货/期货历史 K 接口（hf_XAU）在国内网络环境下普遍被反爬，改用 A 股黄金 ETF 518880 作为代理序列，
    与沪金实际走势高度相关且数据稳定可用。
    返回: [{date: 'YYYY-MM-DD', close: float}] 升序，失败返回 []。
    """
    # 延迟引入避免循环依赖（core.data -> os.environ 清理与本模块一致）
    try:
        from core.data import kline
        df = kline("518880", days=days + 10)  # 多取 10 天给余量
        if df is None or df.empty:
            return []
        df = df.tail(days).reset_index(drop=True)
        out = []
        for _, row in df.iterrows():
            d = row["date"]
            if isinstance(d, (pd.Timestamp,)):
                ds = d.strftime("%Y-%m-%d")
            else:
                ds = str(d)[:10]
            out.append({"date": ds, "close": round(float(row["close"]), 4)})
        return out
    except Exception:
        return []


def get_gold_overview(days=30):
    """app.py 聚合用接口：spot + history_xau + 错误提示拼接。"""
    err1 = err2 = ""
    spot = []
    hist = []
    try:
        spot, err1 = get_gold_spot()
    except Exception as e:
        err1 = f"实时行情: {type(e).__name__}:{e}"
    try:
        hist = get_gold_history(days)
    except Exception as e:
        err2 = f"历史数据: {type(e).__name__}:{e}"
    msg_parts = []
    if err1:
        msg_parts.append(err1)
    if err2:
        msg_parts.append(err2)
    msg = "；".join(msg_parts)
    return {
        "spot": spot,
        "history_xau": hist,  # 命名沿用：实际为 518880 黄金ETF走势，前端展示无需修改
        "msg": msg,
    }
