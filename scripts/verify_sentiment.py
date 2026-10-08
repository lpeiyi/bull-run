# -*- coding: utf-8 -*-
"""联网自检：打印一次 `get_sentiment()` 的真实东财请求序列与分段耗时。

用途（见 specs/cut-sentiment-latency/tasks.md 任务 12）：

1. **交付证据** —— 改造后一次情绪分应只发 4 次东财请求，且**无重复三元组**
   （改造前 5 次、其中 2 次参数完全相同，白付约 1.25 秒）。
2. **排障** —— 观察相邻请求间隔是否 ≥ `em_api.EM_MIN_INTERVAL`、
   是否出现请求失败（403 / 空响应）。

用法::

    python scripts/verify_sentiment.py

注意：本脚本会**真实联网**。非交易日或盘前运行时，池数据可能为空，
耗时与请求数仍具参考价值（请求序列是稳定的）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import em_api, sentiment          # noqa: E402


def main():
    calls = []
    orig = em_api._SESSION.get

    def spy(url, params=None, timeout=None):
        params = params or {}
        endpoint = url.rsplit("/", 1)[-1]
        t0 = time.time()
        try:
            r = orig(url, params=params, timeout=timeout)
            ok = True
        except Exception:
            ok = False
            raise
        finally:
            calls.append({
                "endpoint": endpoint,
                "date": params.get("date"),
                "sort": params.get("sort"),
                "elapsed": round(time.time() - t0, 3),
                "ok": ok,
                "at": time.time(),
            })
        return r

    em_api._SESSION.get = spy
    t0 = time.time()
    try:
        result = sentiment.get_sentiment()
    finally:
        total = time.time() - t0
        em_api._SESSION.get = orig

    print("=" * 74)
    print("情绪分一次取数的真实请求序列")
    print("=" * 74)
    print("%-3s %-16s %-10s %-9s %8s %8s %6s"
          % ("#", "endpoint", "date", "sort", "耗时s", "距上次s", "ok"))
    prev = None
    for i, c in enumerate(calls, 1):
        gap = "" if prev is None else "%.3f" % (c["at"] - prev)
        print("%-3d %-16s %-10s %-9s %8.3f %8s %6s"
              % (i, c["endpoint"], c["date"], c["sort"], c["elapsed"],
                 gap, "Y" if c["ok"] else "N"))
        prev = c["at"]

    triples = [(c["endpoint"], c["date"], c["sort"]) for c in calls]
    dups = sorted({t for t in triples if triples.count(t) > 1})

    print("-" * 74)
    print("请求次数        : %d" % len(calls))
    print("重复三元组      : %s" % (dups or "无 ✅"))
    print("最小请求间隔    : %.3fs（常量 %.2fs）"
          % (min([calls[i]["at"] - calls[i - 1]["at"]
                  for i in range(1, len(calls))], default=0.0),
             em_api.EM_MIN_INTERVAL))
    print("get_sentiment() : %.2fs" % total)
    print("结果            : trade_date=%s score=%s(%s) zt=%s dt=%s zb=%s"
          % (result.get("trade_date"), result.get("score"), result.get("level"),
             result.get("zt_count"), result.get("dt_count"), result.get("zb_count")))
    print("=" * 74)


if __name__ == "__main__":
    main()
