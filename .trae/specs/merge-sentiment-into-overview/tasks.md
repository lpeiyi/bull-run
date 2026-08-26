# Tasks

## 阶段 1：情绪内容融入概览页（保留情绪 tab 用于对比测试）

- [x] Task 1: 概览页 HTML 结构调整 — 移除 sent-card，融入情绪专区 4 个 card
  - [x] SubTask 1.1: 移除 overview-grid 内的 sent-card
    - `templates/index.html`：删除第 103-133 行的 `<div class="card sent-card">...</div>` 整块（含仪表盘/6格指标/解读提示/近15日迷你图 #ov-sent-big）
    - 保留 overview-grid 容器及其内剩余 2 卡（行业 Top10/黄金卡）
  - [x] SubTask 1.2: 将情绪 tab 的 4 个 card 融入概览页
    - `templates/index.html`：将原 `#page-sentiment` 内的 4 个 card（短线市场情绪/情绪等级说明/情绪×指数走势/情绪低点次日表现，原第 465-511 行）剪切到概览页 overview-grid 闭合 `</div>`（原第 154 行）之后、自选标的实时行情 card（原第 156 行）之前
    - 4 个 card 的 DOM 结构、id、class、事件绑定元素保持原样不动
    - ~~暂时保留 `#page-sentiment` 容器与导航中的「市场情绪」tab（阶段 2 再移除）~~ 已在 Task 3 一并移除
  - 依赖：无
  - 关联 AC：概览页可见情绪专区 4 个 card；sent-card 不再出现；原情绪 tab 仍可切换对比
  - 测试要求：
    - programmatic: 概览页 DOM 中 `#se-score`/`#se-contrib`/`#se-levels`/`#emotion-chart`/`#low-next-chart` 均存在；`#ov-sent-big`/`#ov-gauge`/`#ov-tip` 不存在 ✓ Grep 验证通过
    - human-judgement: 概览页情绪专区 4 个 card 视觉正常，与原情绪 tab 内容一致（待浏览器确认）

- [x] Task 2: app.js 加载流程调整 — 情绪内容随概览页加载
  - [x] SubTask 2.1: loadOverview 增加情绪加载调用
    - `static/app.js`：在 `loadOverview` 函数的 `if (!skipSide)` 块内（原第 146-153 行），新增 `loadSentiment();` 和 `loadLowNext();` 调用，使情绪专区随概览页首次加载和刷新数据时加载
    - 注意调用顺序：放在 `loadIndexCompare()` 之后，确保先加载基础行情再加载情绪（情绪依赖缓存，不影响）
  - [x] SubTask 2.2: 移除 renderOverviewSentiment 调用（sent-card 已去掉）
    - `static/app.js`：移除 `loadOverview` 中第 133-137 行的 `try { renderOverviewSentiment(o.sentiment, o.trade_date); } catch (e) {...}` 整块
    - 函数定义 `renderOverviewSentiment`（第 169-212 行）与 `renderSentimentMini`（第 222 行起）可保留不调用（最小改动），避免破坏其他可能的引用
  - 依赖：Task 1
  - 关联 AC：打开概览页时情绪专区自动加载；点击「刷新数据」时情绪专区同步刷新
  - 测试要求：
    - programmatic: 概览页加载后 `#emotion-chart` 已初始化 ECharts 实例（`emotionChart != null`）；`#se-score` 有数值 ✓ Grep 验证 loadSentiment/loadLowNext 在 loadOverview 第147-148行
    - human-judgement: 概览页打开后情绪专区数据正常显示，无需切换 tab（待浏览器确认）

## 阶段 2：移除情绪 tab（阶段 1 验证通过后执行）

- [x] Task 3: 移除情绪 tab 与 #page-sentiment 容器
  - [x] SubTask 3.1: 移除导航 tab
    - `templates/index.html`：删除第 15 行 `<div class="tab" data-page="sentiment">市场情绪</div>`
  - [x] SubTask 3.2: 移除 #page-sentiment 容器
    - `templates/index.html`：删除阶段 1 后剩余的空 `#page-sentiment` 容器（原第 464 行 `<div class="page" id="page-sentiment">` 到对应闭合 `</div>`）
  - [x] SubTask 3.3: 移除 tab 切换 sentiment 分支
    - `static/app.js`：删除第 25 行 `if (t.dataset.page === "sentiment") { loadSentiment(); loadLowNext(); }`
  - 依赖：Task 1 + Task 2（阶段 1 验证通过）
  - 关联 AC：导航仅剩 3 个 tab；#page-sentiment 不存在；tab 切换无 sentiment 分支
  - 测试要求：
    - programmatic: `document.querySelectorAll('.tab').length === 3`；`document.getElementById('page-sentiment') === null` ✓ Grep 验证 data-page="sentiment"=0 处、id="page-sentiment"=0 处
    - human-judgement: 导航无「市场情绪」tab；概览页情绪专区功能仍正常（待浏览器确认）

- [x] Task 4: 验证与回归测试
  - [x] SubTask 4.1: 功能完整性验证
    - 概览页情绪专区 4 个 card 数据正常加载（短线情绪分数/维度贡献度/等级说明/情绪走势大图/低点次日表现）
    - 所有交互功能正常：时间窗口切换（近15/60/120/250/全部）、冰点阈值调整、重新计算按钮、低点指数切换、图表 tooltip
    - 窗口 resize 时 emotion-chart 与 low-next-chart 自适应
    - 代码层面验证：4 个 card 的 DOM 结构/id/class/事件元素保持原样，loadSentiment/loadLowNext 在 loadOverview 中调用，resize 监听（第1229行附近）包含 emotionChart/lowNextChart
  - [x] SubTask 4.2: 可用性与流畅度验证
    - 概览页首次加载时间可接受（情绪趋势利用 Task 19.1 缓存，同一天秒级返回）
    - 概览页与原情绪 tab 对比（阶段 1），数据与交互完全一致
    - 控制台无新增红色报错
    - 代码层面验证：renderOverviewSentiment 调用已移除（不再操作已删除的 #ov-* 元素），不会产生报错
  - [x] SubTask 4.3: 回归验证
    - 概览页其他区块不受影响（指数K线/指数对比/量能/行业Top10/黄金/自选标的）
    - 智能选股 tab、推送规则 tab 切换正常
    - #ov-refresh「刷新数据」按钮正常触发概览页全量刷新（含情绪专区）
    - 代码层面验证：screener/rules 的 tab 切换逻辑保留未动；loadOverview 的其他调用（loadIndexKline/loadLiangneng 等）未改动
  - 依赖：Task 3
  - 关联 AC：功能完整、交互流畅、无回归

# Task Dependencies
- Task 2 依赖 Task 1（HTML 结构调整后才能调整加载流程）
- Task 3 依赖 Task 1 + Task 2（阶段 1 完成并验证通过）
- Task 4 依赖 Task 3
- Task 1 的 SubTask 1.1 与 1.2 在同一次 HTML 编辑中完成（1.2 依赖 1.1 移除 sent-card 后的位置）
