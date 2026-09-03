# Spec: 情绪等级说明卡片改为基于「前一个交易日」数据

## 问题
当前「情绪等级说明」卡片顶部显示「基于 2026-09-03 数据」，这是今天（交易日当日）的实时数据。用户明确规定：**情绪等级说明卡片应显示前一个交易日（完整收盘后的昨日）的情绪等级及对应日期标注**。今日（2026-09-03）打开页面，情绪等级说明应显示「基于 2026-09-02 数据」，并高亮「2026-09-02 收盘后算出的等级」对应的 level 卡片。

### 根因（现场代码）
- `static/app.js loadSentiment() L1167`：`renderLevelGuide(s.level, s.date)` 里 `s = t.latest`，而 `t.latest` 在 v4 修复后被**强制覆盖为今日实时 `sentiment.get_sentiment()`** → 等级说明卡片永远显示当日。
- 之前 Spec「fix-sentiment-card-time-display」已规定「情绪等级说明卡片不随实时刷新更新」，兜底 `L1170-1190` 已不再调用 `renderLevelGuide`（正确），但首次 `loadSentiment()` 自己传的 `s.level / s.date` 仍然是今日实时，日期就是错的。

## 用户 / 影响面
- 主用户：所有使用「市场概览 → 短线情绪板块」的观察者（看情绪等级说明、当日高亮等级卡片）。
- 影响：等级说明卡片高亮的是「今天实时等级」而不是「昨天完整收盘等级」；顶部日期标注为今日，与"前一个交易日"的规定矛盾。

## 目标（Functional Requirements）
- FR-1 `loadSentiment()` 中调用 `renderLevelGuide(curLevel, tradeDate)` 时：
  - **curLevel** = `/api/emotion_trend?days=curDays` 返回的 15 日历史序列中**倒数第二个交易日**（即昨日完整收盘数据）的 `levels[i]`
  - **tradeDate** = 同一条的 `dates[i]`（格式 YYYYMMDD，fmtDate 渲染为 YYYY-MM-DD）
- FR-2 边缘情况：当历史序列只有 1 条（系统新部署或假期刚结束无昨日数据），**兜底用 latest 的 level 和 date**，不抛错。
- FR-3 「情绪等级说明卡片不随实时刷新更新」的原规定**继续保持**：
  - `loadSentimentQuick()`（60s 刷新函数）里**不得**调用 `renderLevelGuide`
  - `L1170-1190` 兜底 fetch("/api/sentiment") 块里**不得**调用 `renderLevelGuide`（已满足，需要 Review 确认不回退）
- FR-4 其它模块（短线情绪卡片 score/level/dims、走势图、贡献度、刷新时间）**完全不受影响**，仍然用今日实时 `latest` + 兜底。
- FR-5 不引入新接口、不改后端代码，仅前端改动。

## 非目标（Non-Goals）
- 不动后端 sentiment.py / app.py / emotion_history.py
- 不改变「短线情绪卡片本体」的实时等级（今日等级仍然实时显示在 score 下）
- 不改变走势图、贡献度、刷新时间

## 约束 & 假设
- 约束 1：只修改 `static/app.js` 1 个文件，≤10 行代码改动
- 约束 2：不新增依赖、不引入新的 fetch 调用
- 假设 1：`t.dates` 与 `t.levels` 下标一一对应（由 `/api/emotion_trend` 返回协议保证，现有代码 renderEmotionChart 也依赖这个对应关系）
- 假设 2：历史序列长度 ≥ 1（`t.dates` 非空），1 条时回退 latest（今日）

## 非功能性要求
- 代码可读：取昨日的逻辑用常量 `t.dates.length - 2`，并加中文注释，避免读者误以为应取 `length-1`（今日）
- 健壮性：历史序列长度 = 1（`length-2 < 0`）时 fallback 不报错
- 无回归：短线情绪卡片 score/level/dims/date/renderContrib/renderEmotionChart 完全不变

## Acceptance Criteria

### AC-1（功能主路径，rule）
当 `/api/emotion_trend` 返回的 `t.dates` 长度 ≥ 2 时，`loadSentiment()` 中 `renderLevelGuide(curLevel, tradeDate)` 的入参满足：
- `curLevel === t.levels[t.dates.length - 2]`
- `tradeDate === t.dates[t.dates.length - 2]`
（即：序列倒数第二个元素 = 昨日完整收盘）

### AC-2（边缘兜底，rule）
当 `t.dates.length === 1` 时，`curLevel === t.latest.level` 且 `tradeDate === t.latest.date`，不抛异常、`#se-levels` DOM 不为空。

### AC-3（不随实时刷新更新，rule）
函数体检查：
- `loadSentimentQuick()` 内**无** `renderLevelGuide(` 调用
- `L1170-1190` 兜底 fetch("/api/sentiment") try 块内**无** `renderLevelGuide(` 调用

### AC-4（其它模块不受影响，rule）
- `loadSentiment()` 中如下代码片段**原封不动**，未被删除或移动：
  1. `const s = t.latest; $("#se-score").textContent = s.score;`
  2. `$("#se-level").textContent = s.level;`（情绪卡片大标题的 level 仍实时）
  3. `$("#se-dims").innerHTML = [涨停 跌停 炸板率 晋级率 最高N板]`（维度仍实时）
  4. `renderContrib(s.contributions);`（贡献度仍实时）
  5. `lastTrend = t; renderEmotionChart(t);`（走势图仍序列实时）

### AC-5（改动边界，rule）
- 本轮实际写入文件集合 = `{static/app.js}`，仅此 1 文件
- 不写入 `app.py` / `core/sentiment.py` / `core/legu.py` / `static/style.css` / `templates/index.html`
