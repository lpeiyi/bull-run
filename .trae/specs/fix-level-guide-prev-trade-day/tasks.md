# Tasks: 情绪等级说明改为昨日（fix-level-guide-prev-trade-day）

## Task 1: 改 loadSentiment() renderLevelGuide 取序列倒数第 2 个交易日
- **Priority**: high
- **Depends On**: None
- **Scope**: `static/app.js` L1167 附近，将原 `renderLevelGuide(s.level, s.date)` 改为：
  1. 计算 `const prevIdx = t.dates.length - 2;`
  2. 若 `prevIdx >= 0`：`renderLevelGuide(t.levels[prevIdx], t.dates[prevIdx])`
  3. 否则（序列只有 1 条）：兜底 `renderLevelGuide(s.level, s.date)`
  4. 加 1 行中文注释「情绪等级说明卡片始终基于前一个交易日（昨日完整收盘），不随今日盘中实时变动」
- **Test Requirements**
  - TR-1.1 (rule): Grep `loadSentiment` 函数体，`renderLevelGuide(...)` 的实参不再是 `s.level`/`s.date` 直接量，而是访问了 `t.levels[xxx]` 和 `t.dates[xxx]`
  - TR-1.2 (rule): 源代码中存在 `t.dates.length - 2` 或等价表达式用于确定昨日索引
  - TR-1.3 (rule): 存在 `prevIdx < 0` 或等价的 fallback 分支（回退 latest.level/latest.date）
  - TR-1.4 (rubric 0-2, threshold=2): 代码改动 ≤ 8 行，加中文注释清晰解释「昨日 = 序列倒数第二，非最后」，可读性满分

## Task 2: 代码回归验证 + 边界约束
- **Priority**: high
- **Depends On**: Task 1
- **Scope**: Grep + 静态检查，不运行 Flask
- **Test Requirements**
  - TR-2.1 (rule, AC-3): Grep `function loadSentimentQuick` 起 25 行内**无** `renderLevelGuide(`
  - TR-2.2 (rule, AC-3): Grep `/api/sentiment 兜底失败` 附近 25 行内**无** `renderLevelGuide(`
  - TR-2.3 (rule, AC-4): `loadSentiment` 内 `const s = t.latest;` 行存在；`$("#se-level").textContent = s.level;` 存在；`$("#se-dims").innerHTML` 存在；`renderContrib(s.contributions);` 存在；`lastTrend = t;` 存在；`renderEmotionChart(t);` 存在 —— 6 句均存在即通过
  - TR-2.4 (rule, AC-5): 本轮调用 Edit 写入工具仅写到 `static/app.js`；没写 app.py/core/*.py/style.css/templates/index.html
  - TR-2.5 (rule): app.py py_compile exit code 0（确保本轮未破坏 Python 端，虽然我们不改它）

# Task Dependencies
- Task 2 depends on Task 1（改完才验证）
