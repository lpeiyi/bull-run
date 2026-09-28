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
    try:
        from core.data import kline
        df = kline("sh000001", days=days + 10)
        dates = [d.strftime("%Y%m%d") for d in df["date"]][-(days + 1):]
        prev_codes = set()
        out = {}
        for d in dates:
            try:
                zt = sentiment._em_pool("getTopicZTPool", d)
                zb = sentiment._em_pool("getTopicZBPool", d)
            except Exception:
                continue
            zt_codes = {p["c"] for p in zt}
            zb_n = len(zb)
            if not zt_codes and not zb_n:
                continue
            max_h = max((p.get("lbc", 0) for p in zt), default=0)
            promo = round(len(zt_codes & prev_codes) / len(prev_codes) * 100, 1) if prev_codes else 0.0
            out[d] = {"max_height": max_h, "promo_rate": promo}
            prev_codes = zt_codes
        return out
    except Exception:
        return {}


def _build_trend(rows, em_factors):
    """用乐咕骨架 + 东财近15日高度/晋级率，组装情绪序列"""
    try:
        seq = []
        for r in rows:
            d = r["date"]
            em = em_factors.get(d) or {}
            height = em.get("max_height", 0)
            promo = em.get("promo_rate", 0.0)
            score, level, _contributions = sentiment._calc_score(
                r["zt_count"], r["dt_count"], height, promo, r["break_rate"])
            seq.append({
            "date": d,
            "label": f"{d[4:6]}-{d[6:8]}",
            "score": score, "level": level,
            "zt_count": r["zt_count"], "zb_count": r["zb_count"],
            "dt_count": r["dt_count"], "break_rate": r["break_rate"],
            "promo_rate": promo, "max_height": height,
            "contributions": _contributions,  # 保留五维度贡献明细，供前端短线情绪卡片渲染条形图
        })
        if seq and seq[0]["date"][:4] != seq[-1]["date"][:4]:
            for t in seq:
                t["label"] = t["date"][:4] + "-" + t["date"][4:6]
        return seq
    except Exception:
        return []


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
    """近 days 个交易日的情绪序列；days<=0 表示全部历史。
    缓存策略：以自然日为 key，同一天内不同 days 的结果分别缓存；
    force=1 或跨天时清空旧缓存重算，否则同一天切换窗口直接读缓存（秒级返回）。
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        cache = {} if force else _load_cache()
        fresh = cache.get("generated") != today

        # 同一天内：优先读该 days 的缓存
        if not fresh:
            trend = (cache.get("trends") or {}).get(str(days))
            if trend:
                return trend

        # 首次/强制/该 days 未缓存：重新计算
        em_factors = cache.get("em_factors") if not fresh else None
        if not em_factors:
            em_factors = _compute_em_factors(_EM_WINDOW)

        rows = legu.fetch_legu_history()
        selected = rows if days <= 0 else rows[-days:]
        trend = _build_trend(selected, em_factors)

        # 更新缓存：fresh/force 时清空旧 trends（跨天数据过期）；否则保留其它 days 的缓存
        if fresh or force:
            cache = {"generated": today, "em_factors": em_factors, "trends": {}}
        cache.setdefault("trends", {})[str(days)] = trend
        _save_cache(cache)
        return trend
    except Exception:
        return []


def get_low_points(threshold=30, days=0):
    """近 days 个交易日中情绪分 <= threshold 的冰点日（days<=0 表示全部历史），升序 [{date, score}]"""
    trend = get_emotion_trend(days=days)
    return [{"date": t["date"], "score": t["score"]} for t in trend if t["score"] <= threshold]

# ── 实时情绪的视图组装 ────────────────────────────────
# 原 app._enrich_sentiment，为让情绪视图逻辑可离线测试而下沉
# （见 specs/slim-app-routes/）。搬迁保持逐行等价，未改任何分支与兜底值。

def enrich_sentiment(s):
    scores = []
    labels = []
    trend = []
    prev_score = None

    # 日期归一化：sentiment 返回的 trade_date 可能是 YYYYMMDD，统一转 YYYY-MM-DD
    def _today():
        d = s.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
        if len(d) == 8 and "-" not in d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    # Task 17：将任意 score 值安全转换为 0~100 的 int，异常兜底 50
    def _to_score(v):
        try:
            n = int(v)
            if n < 0 or n > 100:
                return 50
            return n
        except (TypeError, ValueError):
            try:
                n = int(float(v))
                if n < 0 or n > 100:
                    return 50
                return n
            except (TypeError, ValueError):
                return 50

    try:
        trend = get_emotion_trend(20)
        if len(trend) < 3:
            trend = get_emotion_trend(20, force=True)
    except Exception:
        trend = []
    try:
        if len(trend) < 1 and s.get("score") is not None:
            today_date = _today()
            today_label = today_date[5:]
            trend = [{"date": today_date, "label": today_label, "score": _to_score(s["score"])}]
        if len(trend) < 1:
            today_date = _today()
            today_label = today_date[5:]
            trend = [{"date": today_date, "label": today_label, "score": 50}]
        if s.get("score") is not None:
            today_date = _today()
            last_date = trend[-1].get("date", "") if trend else ""
            if last_date != today_date:
                today_label = today_date[5:]
                trend.append({"date": today_date, "label": today_label, "score": _to_score(s["score"])})
        # Task 17：scores 每个元素都强制 _to_score（兜底 int），杜绝字符串/None 进 series.data
        scores = [_to_score(t.get("score", 50)) for t in trend]
        labels = [t.get("label", t.get("date", "")[5:] if t.get("date") else "") for t in trend]
        if len(scores) > 15:
            scores = scores[-15:]
            labels = labels[-15:]
        min_len = min(len(scores), len(labels))
        scores = scores[:min_len]
        labels = labels[:min_len]
        today_date = _today()
        last_date = trend[-1].get("date", "") if trend else ""
        if last_date == today_date:
            prev_score = scores[-2] if len(scores) >= 2 else None
        else:
            prev_score = scores[-2] if len(scores) >= 2 else None
    except Exception:
        today_date = _today()
        today_label = today_date[5:]
        scores = [50]
        labels = [today_label]
        prev_score = None
    # 单点不可见修复：ECharts line 仅 1 个点不画线，复制为 2 个相同点画出水平短线
    if len(scores) == 1:
        scores = scores * 2
        labels = labels * 2
    # Task 17：返回前最后一道强制校验（兜底保险）
    scores = [_to_score(v) for v in scores]
    s["history_scores"] = scores
    s["history_labels"] = labels
    s["prev_score"] = prev_score
    return s
