# 情绪数据错误最终根治 Spec（diagnose-sentiment-data-path-v4）

## Problem（现场证据）

用户重启 start.bat 后短线情绪卡片仍显示 **涨停 83、跌停 0、炸板率 6.7%、晋级率 20.5%、最高 7 板**（score 71=偏热），与开盘啦口径（52/8/28%/17%/4 板）完全不符。

**Python 直调 + 现场诊断（2026-09-02 23:54）结果**：
```
1. sentiment.get_sentiment() 直调 → score=47, zt=52, dt=8, break_rate=22.4, promo_rate=15.7, max_height=4 ✓
2. legu.fetch_legu_history(force=True) rows[-1] = 20260902, zt=52, dt=8, zb=15  ✓
3. emotion_trend_cache.json generated=2026-09-02 13:58:42（今日下午生成）
   trends['15'][-1] = 20260901  score=71  zt=83  dt=0  zb=6  level=偏热 ❌  ← 这是根因！
4. 端口仅有 1 个 python.exe（PID=25880），非多进程冲突。
```

## 真实根因（数据流链路定位）

前端短线情绪卡片的**首次加载**走 `loadSentiment()`（[app.js L1151-1170](file:///d:/job/Repository/bull-run/static/app.js#L1151-L1170)）：
```js
const t = await fetch("/api/emotion_trend?" + qs).then(r => r.json());
const s = t.latest;      // ← 从 /api/emotion_trend 接口拿 latest！
$("#se-dims").innerHTML = [`涨停 ${s.zt_count}`, `跌停 ${s.dt_count}`, ...];
```
**它调用的是 `/api/emotion_trend`，不是 `/api/overview` 也不是 `/api/sentiment`**！

而 `/api/emotion_trend` 的后端（[app.py L317](file:///d:/job/Repository/bull-run/app.py#L317)）调的是 `emotion_history.get_emotion_trend(days)`，该函数的缓存有效期为**一整天**（`generated == today` 就读缓存，不重算），所以今天 13:58 生成的缓存里 `trends['15'][-1]` 还是**前一日（20260901=83/0/6.7）** 的值，这就是前端显示 83 的原因。

**交易时段的增量刷新** `loadSentimentQuick()`（L1175-1196）调的是无缓存 `/api/sentiment`，应该正确，但它的 guard `if (!isTradeSession()) return;` 仅在 9:30-11:30 / 13:00-15:00 才执行——现在是晚上不执行。首次加载仍显示 83/0/6.7%。

## What Changes

### 修复 1：/api/emotion_trend 的 latest 字段改为实时计算（核心）
`/api/emotion_trend` 返回：
```python
{ "days": [...], "latest": {...} }
```
当前 `latest` 是从缓存序列的最后一天取值（即 `trend[-1]`），**如果趋势缓存不是当日**，`latest` 就是前一日的旧数据。

修改方案：在 `/api/emotion_trend` 处理函数返回前，**强制实时调用 `sentiment.get_sentiment()`** + `_enrich_sentiment()`，合并成新的 `latest` 返回，覆盖趋势缓存的末行。这样前端 `t.latest` 永远是实时正确的。

### 修复 2：loadSentimentQuick() 去掉交易时段守卫，任何时间都可刷新（可选辅助）
去掉或弱化 `isTradeSession()` 守卫：**首次加载后（Tab 切换/首屏渲染）的定时刷新不受交易时段限制**，在非交易时段也会实时显示最近交易日的正确维度。若担心频繁请求，保留 60 秒频率即可，影响极小。

### 修复 3：首次加载 loadSentiment() 在趋势/缓存取 latest 之后也追加实时 sentiment 覆盖（前端兜底）
前端 `loadSentiment()` 拿到 `t.latest`（可能是缓存旧数据）后，**再补一次 `/api/sentiment` 请求**，用实时值覆盖 DOM 的 score / level / dims / contributions。这样即使后端缓存一天失效一次，首次加载也不显示错误。

### 修复 4（可选防御）：删除 `data/emotion_trend_cache.json` + 让 `get_emotion_trend` 缓存跨小时失效或增加 `em_factors` 与 `trends` 分离
但这不是根治（因为就算缓存正确，明天早上的缓存还是滞后的）。

**优先顺序**：修复 1（后端接口层面根治） > 修复 3（前端双重兜底） > 修复 2（跨时段刷新）。

## Impact
- Affected code:
  - `app.py`：`/api/emotion_trend` 返回结构的 `latest` 字段改用实时 sentiment 合成
  - `static/app.js`：`loadSentiment()` 追加 `/api/sentiment` 实时兜底；`loadSentimentQuick()` 弱化 `isTradeSession()` guard
- Non-affected: `core/sentiment.py`（代码已正确，本次不改）、`core/legu.py`

## 约束
- **本次 v4 指定修改范围**：`app.py` / `static/app.js`
- **不用删磁盘缓存**（删了还会再生，治标不治本）；修复 1 是真正不依赖缓存的路径
