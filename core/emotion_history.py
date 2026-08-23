# -*- coding: utf-8 -*-
"""
历史情绪趋势：乐咕乐股提供 2020 至今的涨停/跌停/炸板家数（长历史骨架），
东财涨停池补充近15日的「连板高度」与「晋级率」（这两个因子长历史拿不到）。

情绪分主因子（涨停/跌停/炸板率）整条曲线统一走乐咕，确保口径连续、跌停真实；
近15日额外叠加东财的连板高度与晋级率，与「实时情绪分」口径一致。
"""
import json
import os
from datetime import datetime

from core import legu, sentiment

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_FILE = os.path.join(_BASE, "data", "emotion_trend_cache.json")

# 东财精确窗口：连板高度/晋级率仅此窗口内可查（东财涨停池保留约15个交易日）
_EM_WINDOW = 15


def _compute_em_factors(days):
    """东财精确口径：逐日拉涨停/炸板池，得近 days 日的 {date: {max_height, promo_rate}}"""
    from core.data import kline
    df = kline("sh000001", days=days + 10)
    dates = [d.strftime("%Y%m%d") for d in df["date"]][-(days + 1):]
    prev_codes = set()
    out = {}
    for d in dates:
        zt = sentiment._em_pool("getTopicZTPool", d)
        zb = sentiment._em_pool("getTopicZBPool", d)
        zt_codes = {p["c"] for p in zt}
        zb_n = len(zb)
        if not zt_codes and not zb_n:
            continue  # 节假日或接口保留窗口外
        max_h = max((p.get("lbc", 0) for p in zt), default=0)
        promo = round(len(zt_codes & prev_codes) / len(prev_codes) * 100, 1) if prev_codes else 0.0
        out[d] = {"max_height": max_h, "promo_rate": promo}
        prev_codes = zt_codes
    return out


def _build_trend(rows, em_factors):
    """用乐咕骨架 + 东财近15日高度/晋级率，组装情绪序列"""
    seq = []
    for r in rows:
        d = r["date"]
        em = em_factors.get(d) or {}
        height = em.get("max_height", 0)
        promo = em.get("promo_rate", 0.0)
        score, level = sentiment._calc_score(
            r["zt_count"], r["dt_count"], height, promo, r["break_rate"])
        seq.append({
            "date": d,
            "label": f"{d[4:6]}-{d[6:8]}",
            "score": score, "level": level,
            "zt_count": r["zt_count"], "zb_count": r["zb_count"],
            "dt_count": r["dt_count"], "break_rate": r["break_rate"],
            "promo_rate": promo, "max_height": height,
        })
    # 跨年时 label 补年份，避免混淆
    if seq and seq[0]["date"][:4] != seq[-1]["date"][:4]:
        for t in seq:
            t["label"] = t["date"][:4] + "-" + t["date"][4:6]
    return seq


def _load_cache():
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:
        pass


def get_emotion_trend(days=15, force=False):
    """近 days 个交易日的情绪序列；days<=0 表示全部历史。带当日缓存。"""
    today = datetime.now().strftime("%Y-%m-%d")
    cache = {} if force else _load_cache()
    fresh = cache.get("generated") != today

    if not fresh:
        trend = (cache.get("trends") or {}).get(str(days))
        if trend:
            return trend

    # 东财连板高度/晋级率：与 days 无关，当日只算一次
    em_factors = cache.get("em_factors") if not fresh else None
    if not em_factors:
        em_factors = _compute_em_factors(_EM_WINDOW)

    rows = legu.fetch_legu_history()
    selected = rows if days <= 0 else rows[-days:]
    trend = _build_trend(selected, em_factors)

    cache = {"generated": today, "em_factors": em_factors, "trends": {}}
    cache["trends"][str(days)] = trend
    _save_cache(cache)
    return trend


def get_low_points(threshold=30, days=0):
    """近 days 个交易日中情绪分 <= threshold 的冰点日（days<=0 表示全部历史），升序 [{date, score}]"""
    trend = get_emotion_trend(days=days)
    return [{"date": t["date"], "score": t["score"]} for t in trend if t["score"] <= threshold]