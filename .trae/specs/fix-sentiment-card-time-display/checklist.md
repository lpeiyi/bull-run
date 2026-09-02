# Checklist

## Task 1: 短线市场情绪卡片 `#se-date` 时间显示改为刷新时间

### 代码实现
- [x] `static/app.js` 存在全局变量 `let sentRefreshTs = 0;`
- [x] `static/app.js` 存在 `fmtRefreshTime(ts)` 函数，格式为 `YYYY/M/D HH:MM:SS`
- [x] `loadSentiment()` 成功获取数据后设置 `sentRefreshTs = Date.now()`
- [x] `loadSentiment()` 中 `$("#se-date").textContent` 显示 `刷新于 ${fmtRefreshTime(sentRefreshTs)}`，不再含 `fmtDate(s.date)` 或"近 N 个交易日"
- [x] `loadSentimentQuick()` 成功获取数据后设置 `sentRefreshTs = Date.now()` 并更新 `#se-date` 文本

### 功能验证
- [x] 打开概览页，`#se-date` 显示"刷新于 YYYY/M/D HH:MM:SS"（时间为当前本地时间）
- [x] `#se-date` 不再出现"最新 YYYY-MM-DD"或"近 N 个交易日"字样
- [x] 交易时段等待 60s 后 `loadSentimentQuick()` 触发，`#se-date` 的刷新时间更新为新时间
- [x] 非交易时段 `#se-date` 保持上一次成功刷新的时间不变

## Task 2: 情绪等级说明卡片增加数据日期标注

### 代码实现
- [x] `renderLevelGuide` 函数签名包含 `tradeDate` 参数
- [x] `renderLevelGuide` 在 `#se-levels` 容器内插入 `<div class="lvl-date">基于 YYYY-MM-DD 数据</div>`
- [x] `loadSentiment()` 调用 `renderLevelGuide(s.level, s.date)`
- [x] `loadSentimentQuick()` 调用 `renderLevelGuide(s.level, s.trade_date)`
- [x] `static/style.css` 存在 `.lvl-date` 样式

### 功能验证
- [x] 打开概览页，`#se-levels` 卡片显示"基于 YYYY-MM-DD 数据"（YYYY-MM-DD 为最近交易日）
- [x] 当前情绪等级高亮正常
- [x] 交易时段 `loadSentimentQuick()` 触发后，`#se-levels` 的日期和等级随实时数据更新
- [x] `tradeDate` 为空/undefined 时不显示日期标注行（不报错）

## Task 3: 情绪等级说明卡片追加优化（不随实时更新 + 五卡片同一行布局还原）

### 代码实现
- [x] `loadSentimentQuick()` 中不再调用 `renderLevelGuide`（删除 L1193 的 `renderLevelGuide(s.level, s.trade_date);`）
- [x] `static/style.css` 的 `.lvl-date` 包含 `grid-column: 1 / -1;`

### 功能验证
- [x] 交易时段 `loadSentimentQuick()` 触发后，`#se-levels` 的日期标注和等级高亮保持不变（不随实时数据更新）
- [x] 短线情绪卡片的 `#se-score`/`#se-level`/`#se-dims`/`#se-contrib` 仍正常实时更新
- [x] 五个情绪等级卡片在同一行并排显示，"过热"不被挤到第二行
- [x] 日期标注 `.lvl-date` 占满第一行整宽，等级卡片在下方一行排列
