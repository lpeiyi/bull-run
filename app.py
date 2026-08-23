# -*- coding: utf-8 -*-
"""
牛来 - 本地网页应用入口
双击 start.bat 启动后，浏览器打开 http://127.0.0.1:8000 即可使用
"""
import json
import os
import threading
import time
from collections import Counter

import pandas as pd

from flask import Flask, render_template, request, jsonify

from core import backtest, emotion_history, market, rules, sentiment
from core.data import real_quotes, kline, kline_range
from core.notifier import send_feishu

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")

app = Flask(__name__)


# ── 配置读写 ────────────────────────────────────────
def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── 路由页面 ────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── API ────────────────────────────────────────────
@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    body = request.get_json(force=True)
    code = str(body.get("code", "")).strip()
    indicator = body.get("indicator", "macd")
    params = body.get("params") or {}
    days = int(body.get("days", 250))
    if not code:
        return jsonify({"error": "请填写标的代码"}), 400
    try:
        df = kline(code, days=days, adjust="qfq")
    except Exception as e:
        return jsonify({"error": f"数据拉取失败: {e}"}), 500
    if df.empty:
        return jsonify({"error": "未取到K线数据，请检查代码是否正确"}), 404
    try:
        result = backtest.backtest(df, indicator, params)
    except Exception as e:
        return jsonify({"error": f"回测失败: {e}"}), 500
    qi = real_quotes([code])
    result["name"] = qi.get(code, {}).get("name", "")
    result["code"] = code
    return jsonify(result)


@app.route("/api/quotes", methods=["POST"])
def api_quotes():
    body = request.get_json(force=True)
    codes = body.get("codes") or []
    return jsonify(real_quotes(codes))


_OVERVIEW_CACHE = {"ts": 0.0, "data": None}


@app.route("/api/overview")
def api_overview():
    """市场概览：指数 + 情绪 + 涨停/炸板/跌停池 + 板块，60秒缓存"""
    now = time.time()
    force = request.args.get("force") == "1"
    if not force and _OVERVIEW_CACHE["data"] and now - _OVERVIEW_CACHE["ts"] < 60:
        return jsonify(_OVERVIEW_CACHE["data"])
    s = sentiment.get_sentiment()
    date = s.get("trade_date")
    zt = market.get_zt_pool(date) if date else []
    zb = market.get_zb_pool(date) if date else []
    dt = market.get_dt_pool(date) if date else []
    ladder = [{"days": k, "count": v}
              for k, v in sorted(Counter(x["limit_days"] for x in zt).items())]
    td = s.get("trade_date")
    data = {
        "trade_date": f"{td[:4]}-{td[4:6]}-{td[6:8]}" if td else None,
        "index_order": market.INDEX_CODES,
        "indexes": market.get_indexes(),
        "sentiment": s,
        "ladder": ladder,
        "zt_pool": zt,
        "zb_pool": zb,
        "dt_pool": dt,
        "boards": market.get_boards(),
    }
    _OVERVIEW_CACHE["ts"] = now
    _OVERVIEW_CACHE["data"] = data
    return jsonify(data)


@app.route("/api/sentiment")
def api_sentiment():
    return jsonify(sentiment.get_sentiment())


_LN_CACHE = {"ts": 0.0, "data": None}


@app.route("/api/liangneng")
def api_liangneng():
    """市场量能：沪深实际/预测量能 + 昨日量能 + 成交额走势。120秒缓存。"""
    now = time.time()
    if _LN_CACHE["data"] and now - _LN_CACHE["ts"] < 120:
        return jsonify(_LN_CACHE["data"])
    data = market.get_liangneng()
    _LN_CACHE["ts"] = now
    _LN_CACHE["data"] = data
    return jsonify(data)


# 情绪趋势图里可叠加对比的指数
INDEX_TREND = [
    ("sh000001", "上证指数"),
    ("sh000905", "中证500"),
    ("sh000688", "科创50"),
    ("sz399006", "创业板指"),
    ("sh000300", "沪深300"),
]


@app.route("/api/emotion_trend")
def api_emotion_trend():
    """历史情绪分序列 + 叠加指数归一化曲线。
    默认近15日，可用 ?days=N 拉长（N<=0 表示全部历史）。"""
    force = request.args.get("force") == "1"
    days = int(request.args.get("days", 15))
    trend = emotion_history.get_emotion_trend(days, force=force)
    dates = [t["date"] for t in trend]
    # 指数叠加覆盖同等长度（腾讯日K接口单次上限约1000根）
    kline_days = 1000 if days <= 0 else min(days + 20, 1000)
    indexes = []
    for code, name in INDEX_TREND:
        try:
            df = kline(code, days=kline_days)
            m = {d.strftime("%Y%m%d"): float(c) for d, c in zip(df["date"], df["close"])}
        except Exception:
            continue
        vals = [m.get(d) for d in dates]
        base = next((v for v in vals if v), None)
        if not base:
            continue
        indexes.append({
            "name": name,
            "values": [round(v / base * 100, 2) if v else None for v in vals],
        })
    return jsonify({
        "dates": dates,
        "labels": [t["label"] for t in trend],
        "scores": [t["score"] for t in trend],
        "zt_count": [t["zt_count"] for t in trend],
        "dt_count": [t.get("dt_count", 0) for t in trend],
        "break_rate": [t["break_rate"] for t in trend],
        "promo_rate": [t["promo_rate"] for t in trend],
        "max_height": [t["max_height"] for t in trend],
        "levels": [t["level"] for t in trend],
        "indexes": indexes,
        "latest": trend[-1] if trend else None,
    })


_LOW_NEXT_CACHE = {"ts": 0.0, "data": None}
_IDX_CLOSE_CACHE = {}


def _idx_closes(code):
    """拉全量指数日K并缓存 {YYYYMMDD: close}，失败返回空 dict"""
    if code not in _IDX_CLOSE_CACHE:
        try:
            df = kline_range(code, start="2020-01-01")
            _IDX_CLOSE_CACHE[code] = {d.strftime("%Y%m%d"): float(c) for d, c in zip(df["date"], df["close"])}
        except Exception:
            _IDX_CLOSE_CACHE[code] = {}
    return _IDX_CLOSE_CACHE[code]


@app.route("/api/emotion_low_next")
def api_emotion_low_next():
    """情绪低点(<=threshold) 下一交易日各指数涨跌幅 + 统计。?days=0 表示全部历史。600秒缓存。"""
    threshold = int(request.args.get("threshold", 30))
    days = int(request.args.get("days", 0))
    key = (threshold, days)
    now = time.time()
    if (_LOW_NEXT_CACHE["data"] and _LOW_NEXT_CACHE["ts"]
            and now - _LOW_NEXT_CACHE["ts"] < 600
            and _LOW_NEXT_CACHE["data"].get("_k") == key):
        return jsonify(_LOW_NEXT_CACHE["data"])

    lows = emotion_history.get_low_points(threshold, days)
    indexes = []
    for code, name in INDEX_TREND:
        closes = _idx_closes(code)
        if not closes:
            continue
        dates_sorted = sorted(closes)
        pos = {d: i for i, d in enumerate(dates_sorted)}
        items, valid = [], []
        for ld in lows:
            d = ld["date"]
            base = closes.get(d)
            i = pos.get(d)
            ret = nd = None
            if base is not None and i is not None and i + 1 < len(dates_sorted):
                nd = dates_sorted[i + 1]
                ret = round((closes[nd] / base - 1) * 100, 2)
                valid.append(ret)
            items.append({"date": d, "next_date": nd, "ret": ret})
        n = len(valid)
        avg = round(sum(valid) / n, 2) if n else None
        win = round(sum(1 for r in valid if r > 0) / n * 100, 1) if n else None
        indexes.append({"name": name, "items": items, "stats": {"n": n, "avg": avg, "win_rate": win}})

    data = {
        "_k": key,
        "threshold": threshold,
        "days": days,
        "low_dates": [x["date"] for x in lows],
        "low_scores": [x["score"] for x in lows],
        "indexes": indexes,
    }
    _LOW_NEXT_CACHE["ts"] = now
    _LOW_NEXT_CACHE["data"] = data
    return jsonify(data)


# 指数K线图：可切换指数
INDEX_KLINE = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sh000016", "上证50"),
    ("sh000905", "中证500"),
    ("sh000300", "沪深300"),
    ("sh000852", "中证1000"),
]
_IDX_NAME = dict(INDEX_KLINE)
_KLINE_CACHE = {}


def _fmt_series(s):
    """Series -> [None 或 round(float,2)] 列表，NaN 记为 None 供前端断线"""
    return [None if pd.isna(v) else round(float(v), 2) for v in s]


@app.route("/api/index_kline")
def api_index_kline():
    """指数日K（蜡烛 + MA5/10/20 均线 + 成交量），600秒缓存"""
    code = request.args.get("code", "sh000001")
    days = int(request.args.get("days", 120))
    key = (code, days)
    cached = _KLINE_CACHE.get(key)
    if cached and time.time() - cached["ts"] < 600:
        return jsonify(cached["data"])
    try:
        df = kline(code, days=days + 150)  # 多取150根，保证120日均线也能从头有值
    except Exception:
        df = None
    if df is None or df.empty:
        return jsonify({"error": "数据拉取失败"}), 500
    ma5 = _fmt_series(df["close"].rolling(5).mean())
    ma10 = _fmt_series(df["close"].rolling(10).mean())
    ma20 = _fmt_series(df["close"].rolling(20).mean())
    ma60 = _fmt_series(df["close"].rolling(60).mean())
    ma120 = _fmt_series(df["close"].rolling(120).mean())
    df = df.tail(days)
    data = {
        "code": code,
        "name": _IDX_NAME.get(code, code),
        "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
        "kline": [[round(float(o), 2), round(float(c), 2), round(float(lo), 2), round(float(hi), 2)]
                  for o, c, hi, lo in zip(df["open"], df["close"], df["high"], df["low"])],
        "volume": [int(v) for v in df["volume"]],
        "ma5": ma5[-days:],
        "ma10": ma10[-days:],
        "ma20": ma20[-days:],
        "ma60": ma60[-days:],
        "ma120": ma120[-days:],
    }
    _KLINE_CACHE[key] = {"ts": time.time(), "data": data}
    return jsonify(data)


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(load_config())
    body = request.get_json(force=True)
    cfg = load_config()
    for key in ("watchlist", "feishu_webhook", "rules", "index_code", "index_name"):
        if key in body:
            cfg[key] = body[key]
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/rules/check", methods=["POST"])
def api_rules_check():
    """手动触发一次规则检查，触发项立即推送飞书"""
    cfg = load_config()
    triggered, metrics = rules.check_rules(cfg)
    sent = 0
    for t in triggered:
        ok, _ = send_feishu(cfg.get("feishu_webhook"), "【牛来提醒】" + t["name"], t["message"])
        if ok:
            sent += 1
    return jsonify({"triggered": triggered, "metrics": metrics, "sent": sent})


# ── 后台：定期检查规则并推送 ──────────────────────────
def background_monitor(interval=180):
    """每 interval 秒检查一次规则，命中且过冷却期则推送飞书"""
    while True:
        try:
            cfg = load_config()
            triggered, _ = rules.check_rules(cfg)
            for t in triggered:
                send_feishu(cfg.get("feishu_webhook"), "【牛来提醒】" + t["name"], t["message"])
        except Exception:
            pass
        time.sleep(interval)


if __name__ == "__main__":
    import webbrowser

    def _open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

    def _warmup_emotion():
        # 后台预计算历史情绪，避免首次打开情绪页等30秒
        try:
            emotion_history.get_emotion_trend(15)
        except Exception:
            pass

    threading.Thread(target=_warmup_emotion, daemon=True).start()
    threading.Thread(target=background_monitor, daemon=True).start()
    threading.Thread(target=_open_browser, daemon=True).start()
    print("=" * 52)
    print("牛来已启动")
    print("请在浏览器打开: http://127.0.0.1:8000")
    print("停止: 关闭此窗口 或 Ctrl+C")
    print("=" * 52)
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)