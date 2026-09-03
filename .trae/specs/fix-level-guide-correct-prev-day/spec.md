# 修正情绪等级说明卡片日期偏移 Spec

## Why
上一轮 `fix-level-guide-prev-trade-day` 将 `renderLevelGuide` 的取值索引从 `t.dates.length-1` 改成了 `t.dates.length-2`，基于错误假设「趋势数组最后一条 = 今日实时」。实际上 `/api/emotion_trend` 返回的 `dates`/`levels` 数组来自 `emotion_history.get_emotion_trend()` 缓存，**只含历史完整交易日，不含今日**。`latest` 是独立字段，v4 已覆盖为今日实时。因此 `length-2` 取到了前天（2026-09-01），而期望是昨日（2026-09-02）。

## What Changes
- 将 `static/app.js` 中 `const prevIdx = t.dates.length - 2;` 改为 `const prevIdx = t.dates.length - 1;`
- 更新注释，说明趋势数组最后一条 = 昨日完整收盘（不含今日），`latest` 才是今日实时

## Impact
- Affected specs: `fix-level-guide-prev-trade-day`（修正其实现错误）
- Affected code: `static/app.js` L1167-1171

## ADDED Requirements
### Requirement: 等级说明取昨日数据
`renderLevelGuide` 应取 `t.levels[t.dates.length - 1]` 和 `t.dates[t.dates.length - 1]`（趋势数组最后一条 = 昨日完整收盘）。

#### Scenario: 正常 15 日序列
- **WHEN** `/api/emotion_trend` 返回 15 条趋势数据（最后一条 = 2026-09-02）
- **THEN** 等级说明卡片显示「基于 2026-09-02 数据」并高亮昨日等级

#### Scenario: 序列仅 1 条
- **WHEN** `t.dates.length === 1`，`prevIdx = 0`
- **THEN** 取 `t.levels[0]` / `t.dates[0]`，不报错
