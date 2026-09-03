# Tasks

## Task 1: /api/emotion_trend latest 改为实时 sentiment（修复 1 核心）
- **Priority**: high
- **Depends On**: None
- **Status**: completed
- **Completion Evidence**:
  - TR-1.1 PASS: app.py L362 `/api/emotion_trend` 返回前显式调用 `s = sentiment.get_sentiment()`
  - TR-1.2 PASS: `latest.update()` (L367-382) 覆盖 zt_count/dt_count/zb_count/break_rate/promo_rate/max_height/score/level/contributions/history_scores/history_labels/prev_score/date/trade_date 共 13 字段，全部来自 s = get_sentiment() 实时返回值 + enriched = _enrich_sentiment(s)
  - TR-1.3 PASS: `py_compile app.py` exit code 0
- **Changes Path**: `app.py` L356-398，api_emotion_trend 路由

## Task 2: 前端 loadSentiment() 追加 /api/sentiment 实时兜底（修复 3）
- **Priority**: high
- **Depends On**: Task 1
- **Status**: completed
- **Completion Evidence**:
  - TR-2.1 PASS: static/app.js L1170-1190 `renderEmotionChart(t);` 之后有 `fetch("/api/sentiment")` 的 try/catch，覆盖 `#se-score` / `#se-level` / `#se-dims` / `renderContrib(s2.contributions)` / `#se-date` 五项 DOM
  - TR-2.2 PASS: `lastTrend = t; renderEmotionChart(t);` 仍在兜底之前执行，走势图不受兜底影响
- **Changes Path**: `static/app.js` renderWatchKline 之后，L1170-1190

## Task 3: loadSentimentQuick() 去除交易时段守卫（修复 2 辅助）
- **Priority**: medium
- **Depends On**: None
- **Status**: completed
- **Completion Evidence**:
  - TR-3.1 PASS: 原守卫行 `if (!isTradeSession()) return;` 被替换为「全天候刷新」注释 + try 块开始，函数体内不再有 isTradeSession 守卫（Grep 无该模式行）
  - TR-3.2 PASS: fetch /api/sentiment 的 try/catch / if (!s || s.score==null) return / DOM 更新逻辑全部保持不变
- **Changes Path**: `static/app.js` L1196-1199

## Task 4: 现场验证（CP-1/2/3 + 边界）
- **Status**: completed
- **Completion Evidence**:
  - CP-1.1/1.2 Grep PASS; CP-1.3 py_compile exit=0 ✓
  - CP-2.1/2.2 L1170-1190 兜底块存在，lastTrend/renderEmotionChart 在之前 ✓
  - CP-3.1 函数体内不再有 `!isTradeSession() return` 守卫行 ✓
  - CP-B.1 本次 v4 仅调用 Edit 写入 `app.py` + `static/app.js`，未调用写入 `core/sentiment.py` / `core/legu.py` / `static/style.css`（上述三文件的 git diff 来自 v2/v3 会话遗留，不是 v4 本次新增写入）✓
  - CP-B.2 本次写入文件集合 = {app.py, static/app.js}，共 2 文件 ✓

# Task Dependencies
- Task 1 / Task 2 / Task 3 互相独立（Task 1 后端，Task 2/3 前端且无冲突），并行完成 ✓
