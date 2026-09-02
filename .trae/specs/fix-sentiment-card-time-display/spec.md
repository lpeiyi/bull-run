# 修复情绪卡片时间显示 Spec（fix-sentiment-card-time-display）

## Why
市场概览页短线市场情绪卡片右上角时间显示为"近 15 个交易日 · 最新 2026-09-01"，显示的是后端返回的最近交易日日期（`trade_date`），而非数据刷新时间。用户在交易时段看到"前一天"的日期会困惑——情绪分是实时的，时间标注却停留在昨天。同时，情绪等级说明卡片未标注等级对应的数据日期，用户不清楚当前高亮的等级是基于哪天的数据。

## What Changes
- **短线市场情绪卡片 `#se-date` 时间显示改为刷新时间**：将"近 N 个交易日 · 最新 YYYY-MM-DD"改为"刷新于 YYYY/M/D HH:MM:SS"，使用前端本地刷新时间戳（每次 `loadSentiment()` / `loadSentimentQuick()` 成功获取数据后更新）
- **情绪等级说明卡片增加数据日期标注**：在 `#se-levels` 卡片标题旁或卡片顶部显示"基于 YYYY-MM-DD 数据"，明确等级对应的是 `trade_date` 所代表的那个交易日

## Impact
- Affected code: `static/app.js`（`loadSentiment()`、`loadSentimentQuick()`、`renderLevelGuide()` 三个函数）
- Non-affected: 后端 `app.py`、`core/sentiment.py`、`core/emotion_history.py` 不改动（`trade_date` 数据来源和格式不变）

## ADDED Requirements

### Requirement: 短线市场情绪卡片显示刷新时间
`#se-date` SHALL 仅显示数据刷新的本地时间（如"刷新于 2026/9/2 11:22:36"），不再显示后端 `trade_date`（最近交易日日期），也不保留"近 N 个交易日"前缀。

#### Scenario: 首次加载显示刷新时间
- **WHEN** 用户打开/刷新概览页，`loadSentiment()` 成功获取 `/api/emotion_trend` 数据
- **THEN** `#se-date` 显示"刷新于 YYYY/M/D HH:MM:SS"（时间为本地当前时间）
- **AND** 不再出现"最新 YYYY-MM-DD"或"近 N 个交易日"字样

#### Scenario: 交易时段定时刷新更新时间
- **WHEN** 处于 A 股交易时段，`loadSentimentQuick()` 成功获取 `/api/sentiment` 实时数据
- **THEN** `#se-date` 的刷新时间更新为本次 `loadSentimentQuick()` 调用时的本地时间

#### Scenario: 非交易时段不更新时间
- **WHEN** 非交易时段 `loadSentimentQuick()` 内部 `isTradeSession()` 返回 false 提前退出
- **THEN** `#se-date` 保持上一次成功刷新的时间不变

### Requirement: 情绪等级说明卡片标注数据日期
`#se-levels` 卡片 SHALL 显示当前情绪等级对应的数据日期（`trade_date`），格式为"基于 YYYY-MM-DD 数据"。

#### Scenario: loadSentiment 标注日期
- **WHEN** `loadSentiment()` 成功获取数据，调用 `renderLevelGuide(s.level, s.date)`
- **THEN** `#se-levels` 卡片显示"基于 YYYY-MM-DD 数据"（YYYY-MM-DD 由 `s.date` 即 `trade_date` 格式化而来）
- **AND** 当前等级高亮逻辑不变

#### Scenario: loadSentimentQuick 标注日期
- **WHEN** 交易时段 `loadSentimentQuick()` 成功获取数据，调用 `renderLevelGuide(s.level, s.trade_date)`
- **THEN** `#se-levels` 卡片的"基于 YYYY-MM-DD 数据"更新为本次实时数据的 `trade_date`
- **AND** 当前等级高亮随实时等级变化

## MODIFIED Requirements

### Requirement: 情绪卡片时间显示（原显示 trade_date）
原 `#se-date` 显示 `近 ${t.labels.length} 个交易日 · 最新 ${fmtDate(s.date)}`，其中 `s.date` 为后端返回的最近交易日。修改为仅显示前端本地刷新时间"刷新于 YYYY/M/D HH:MM:SS"，去掉"近 N 个交易日"前缀和"最新 YYYY-MM-DD"。

### Requirement: 情绪等级说明卡片不随实时数据更新（V2 修正）
情绪等级说明卡片的日期标注和等级高亮 SHALL 仅在 `loadSentiment()` 调用时更新（对应前一个交易日的数据），**不随** `loadSentimentQuick()` 交易时段实时刷新而更新。短线情绪卡片的 `#se-score`/`#se-level`/`#se-dims`/`#se-contrib` 仍按原有逻辑实时刷新。

#### Scenario: 交易时段定时刷新不更新等级卡片
- **WHEN** 交易时段 `loadSentimentQuick()` 成功获取实时数据
- **THEN** `#se-score`、`#se-level`、`#se-dims`、`#se-contrib`、`#se-date` 正常更新
- **AND** `#se-levels` 卡片保持上一次 `loadSentiment()` 时的日期标注和等级高亮不变

### Requirement: 情绪等级五卡片同一行布局还原
`.lvl-grid` 中的五个等级卡片 SHALL 在同一行并排显示。日期标注 `.lvl-date` SHALL 跨越整行（`grid-column: 1 / -1`），不占据单个 grid 单元格，避免第六个元素导致换行。

#### Scenario: 日期标注不挤压等级卡片
- **WHEN** `renderLevelGuide` 在 `.lvl-grid` 内插入 `.lvl-date` + 5 个 `.lvl-card`
- **THEN** `.lvl-date` 占满第一行整宽
- **AND** 5 个 `.lvl-card` 在第二行并排排列（不换行到第三行）

## Constraints
- **数据格式兼容**：`loadSentiment()` 的 `s.date` 为 `YYYYMMDD` 格式（来自 emotion_trend latest.date），`loadSentimentQuick()` 的 `s.trade_date` 也为 `YYYYMMDD` 格式（来自 sentiment trade_date）。两者格式一致，`renderLevelGuide` 需统一格式化为 `YYYY-MM-DD`
- **后端零改动**：不修改 `app.py`、`core/sentiment.py`、`core/emotion_history.py`，仅改前端 `static/app.js`
- **刷新时间格式**：使用 `toLocaleString()` 默认格式或自定义 `YYYY/M/D HH:MM:SS`，与用户示例"2026/9/2 11:22:36"一致
