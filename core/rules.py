# -*- coding: utf-8 -*-
"""
规则引擎：按用户预设条件判断市场是否符合，符合则返回触发项（带冷却，避免重复推送）
条件示例：{"metric": "sentiment", "op": "<", "value": 30}
metric 支持：sentiment / zt_count / zb_count / break_rate / promo_rate / max_height / index_pct
op 支持：<  <=  >  >=  ==
"""
import os
import json
import time

from core import sentiment
from core.data import real_quotes

_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "rule_state.json")

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
}


def get_metrics(config):
    """计算所有规则可能用到的市场指标"""
    s = sentiment.get_sentiment()
    metrics = {
        "sentiment": s.get("score"),
        "zt_count": s.get("zt_count"),
        "zb_count": s.get("zb_count"),
        "break_rate": s.get("break_rate"),
        "promo_rate": s.get("promo_rate"),
        "max_height": s.get("max_height"),
    }
    idx_code = config.get("index_code", "sh000001")
    q = real_quotes([idx_code])
    metrics["index_pct"] = q.get(idx_code, {}).get("change_pct")
    return metrics, s


def _load_state():
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_state(state):
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def check_rules(config):
    """评估所有规则，返回 (触发列表, 当前指标)"""
    metrics, s = get_metrics(config)
    state = _load_state()
    triggered = []
    now = time.time()
    changed = False

    for rule in config.get("rules", []):
        if not rule.get("enabled", True):
            continue
        actual = metrics.get(rule.get("metric"))
        op = _OPS.get(rule.get("op"))
        if actual is None or op is None:
            continue
        if op(float(actual), float(rule.get("value"))):
            cooldown = int(rule.get("cooldown_minutes", 60)) * 60
            last = state.get(rule.get("name"), 0)
            if now - last >= cooldown:
                triggered.append({**rule, "actual": actual})
                state[rule.get("name")] = now
                changed = True

    if changed:
        _save_state(state)
    return triggered, metrics