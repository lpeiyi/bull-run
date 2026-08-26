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

# 三品种定义：新浪代码、展示名、类型（hf=海外现货/期货，shfe=国内期货，spot=国内现货）
SPOTS = [
    ("hf_XAU",     "伦敦金 XAUUSD",     "hf"),
    ("hf_GC",      "纽约黄金",          "hf"),
    ("SGE_AU9999", "Au99.99 AU9999",   "spot"),
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

        fallback_msg = ""
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
            elif stype == "spot" and n >= 18:
                # 上金所 Au99.99 SGE_AU9999（新浪 18 段，实采字段反推）：
                # [0]代码[1]简称[2]标准名[3]最新价[4]?[5]昨收[6]今开[7]最高[8]最低[9-11]相关价格
                # [12-15]量额[16]时间(YYYY-MM-DD HH:MM:SS)[17]涨跌幅(带%)
                name = parts[2] or default_name
                price = _float(parts[3])
                last_close = _float(parts[5])
                open_p = _float(parts[6])
                high = _float(parts[7])
                low = _float(parts[8])
                # 优先按昨收重算 pct；若昨收为 0 则尝试从 17 段解析带 % 的字符串
                if last_close and price:
                    pct = round((price - last_close) / last_close * 100, 2)
                else:
                    try:
                        pct = round(float(parts[17].rstrip("%")), 2)
                    except (ValueError, IndexError):
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

        # AU0 兜底：若 spot 不足 3 条（通常是 SGE_AU9999 解析失败），追加沪金主连 AU0
        if len(spot) < 3:
            try:
                au0_payload = kv.get("AU0")
                if au0_payload:
                    parts = au0_payload.split(",")
                    n = len(parts)
                    if n >= 28:
                        name = parts[0] or "沪金主连 AU0（AU9999 接口不可用降级）"
                        open_p = _float(parts[2])
                        high = _float(parts[3])
                        low = _float(parts[4])
                        price = _float(parts[8])
                        settle = _float(parts[10])
                        candidates_last = [settle, _float(parts[7])]
                        last_close = next((x for x in candidates_last if x > 100), 0.0)
                        pct = round((price - last_close) / last_close * 100, 2) if last_close and price else 0.0
                        spot.append({
                            "symbol": "AU0",
                            "name": name,
                            "price": price,
                            "pct": pct,
                            "high": high,
                            "low": low,
                            "open": open_p,
                            "last_close": last_close,
                        })
                        fallback_msg = "AU9999 接口不可用，降级为沪金主连 AU0"
            except Exception:
                fallback_msg = "AU9999 接口不可用，降级为沪金主连 AU0"
        return spot, fallback_msg
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


def get_gold_history_xau(days=30):
    """
    获取伦敦金 XAUUSD 近 days 日历史收盘价。优先真实历史接口，失败走系数折算或 ETF 兜底。
    返回 dict: {"source": str, "history": [{date, close}], "msg": str}
    source ∈ {"XAUUSD", "518880xratio", "fallback_518880"}
    history 升序 30 条；date YYYY-MM-DD；close XAUUSD 口径保留 2 位小数；fallback 口径仍保留原精度。
    """
    msg = ""
    source = "fallback_518880"
    history = []

    # 1) 实采方案 A 的历史接口；若任一成功，直接返回 source=XAUUSD
    plan_a_success = False
    try:
        ts = int(time.time() * 1000)
        a_urls = [
            f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20t1_hf_XAU=/InnerFuturesNewService.getDailyKLine?symbol=hf_XAU&_={ts}",
            "http://push2his.eastmoney.com/api/qt/stock/kline/get?secid=113.XAUUSD&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=0&end=20500101&lmt=" + str(days),
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hf_XAU,day,,," + str(days) + ",qfq",
        ]
        for url in a_urls:
            try:
                r = _SESSION.get(url, timeout=10)
                r.encoding = "utf-8"
                txt = r.text.strip()
                if not txt or len(txt) < 50:
                    continue
                import json as _json
                parsed = None
                # 新浪 JSONP
                if "InnerFuturesNewService" in url and "(" in txt and ")" in txt:
                    inner = txt[txt.index("(") + 1:txt.rindex(")")]
                    if inner and inner.lower() != "null":
                        parsed = _json.loads(inner)
                elif "push2his" in url:
                    d = _json.loads(txt)
                    data = d.get("data") if isinstance(d, dict) else None
                    if data and isinstance(data, dict):
                        klines = data.get("klines") or []
                        if isinstance(klines, list) and len(klines) >= 10:
                            out = []
                            for k in klines:
                                parts = k.split(",") if isinstance(k, str) else []
                                if len(parts) >= 6:
                                    ds = parts[0][:10]
                                    close_v = _float(parts[2])
                                    if close_v > 100:
                                        out.append({"date": ds, "close": round(close_v, 2)})
                            if len(out) >= 10:
                                parsed = out[-days:]
                elif "ifzq.gtimg.cn" in url:
                    d = _json.loads(txt)
                    data = d.get("data", {}) if isinstance(d, dict) else {}
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, dict):
                                day_data = v.get("day") or v.get("qfqday")
                                if isinstance(day_data, list) and len(day_data) >= 10:
                                    out = []
                                    for row in day_data:
                                        if isinstance(row, list) and len(row) >= 3:
                                            ds = str(row[0])[:10]
                                            close_v = _float(row[2])
                                            if close_v > 100:
                                                out.append({"date": ds, "close": round(close_v, 2)})
                                    if len(out) >= 10:
                                        parsed = out[-days:]
                                        break
                if isinstance(parsed, list) and len(parsed) >= 10:
                    history = parsed[-days:]
                    source = "XAUUSD"
                    plan_a_success = True
                    break
            except Exception:
                continue
    except Exception:
        plan_a_success = False

    if plan_a_success:
        return {"source": source, "history": history, "msg": msg}

    # 2) 若 A 全失败，走 B：518880 × 系数折算
    try:
        spot_list, _ = get_gold_spot()
        xau = next((s for s in spot_list if s["symbol"] == "hf_XAU"), None)
        if xau and xau.get("last_close") and xau["last_close"] > 100:
            etf_hist = get_gold_history(days=days + 1)
            if isinstance(etf_hist, list) and len(etf_hist) >= 2:
                etf_yesterday_close = etf_hist[-2]["close"]
                if etf_yesterday_close > 0:
                    xau_last_close = xau["last_close"]
                    ratio = xau_last_close / etf_yesterday_close
                    hist30 = etf_hist[-days:]
                    history = []
                    for h in hist30:
                        history.append({
                            "date": h["date"],
                            "close": round(h["close"] * ratio, 2),
                        })
                    if len(history) >= 10:
                        source = "518880xratio"
                        msg += "伦敦金历史接口被反爬，采用 518880 × 每日系数折算，数值为近似估计"
    except Exception:
        pass

    if source == "518880xratio":
        return {"source": source, "history": history, "msg": msg}

    # 3) 若 B 也失败，走 C：fallback_518880，复用 get_gold_history(days)
    try:
        history = get_gold_history(days)
        source = "fallback_518880"
        msg += "伦敦金历史 + 518880 系数折算均失败，兜底使用黄金ETF 518880 代理（人民币）"
    except Exception:
        history = []
        source = "fallback_518880"
        msg += "伦敦金历史 + 518880 系数折算均失败，兜底使用黄金ETF 518880 代理（人民币）"

    return {"source": source, "history": history, "msg": msg}


def get_gold_overview(days=30):
    """app.py 聚合用接口：spot + history_xau + 错误提示拼接。"""
    err1 = err2 = ""
    spot = []
    hist_source = "fallback_518880"
    hist = []
    try:
        spot, err1 = get_gold_spot()
    except Exception as e:
        err1 = f"实时行情: {type(e).__name__}:{e}"
    try:
        xau_res = get_gold_history_xau(days)
        hist_source = xau_res.get("source", "fallback_518880")
        hist = xau_res.get("history", [])
        if xau_res.get("msg"):
            err2 = xau_res["msg"]
    except Exception as e:
        err2 = f"XAUUSD历史失败({type(e).__name__}:{e})，已兜底 ETF 代理"
        try:
            hist = get_gold_history(days)
            hist_source = "fallback_518880"
        except Exception as e2:
            hist = []
            err2 += f"；ETF兜底也失败({type(e2).__name__}:{e2})"
    msg_parts = []
    if err1:
        msg_parts.append(err1)
    if err2:
        msg_parts.append(err2)
    msg = "；".join(msg_parts)
    return {
        "spot": spot,
        "history_xau": hist,
        "history_source": hist_source,
        "msg": msg,
    }
