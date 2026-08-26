# Checklist

## 阶段 1：情绪内容融入概览页

### HTML 结构
- [x] 概览页 overview-grid 内的 sent-card 已移除（#ov-score/#ov-level/#ov-gauge/#ov-dims/#ov-tip/#ov-sent-big 不存在）
- [x] 概览页 overview-grid 内保留行业 Top10 与黄金卡 2 个 card
- [x] 情绪 tab 的 4 个 card 已融入概览页 overview-grid 下方、自选标的上方
- [x] 4 个 card 的 DOM 结构/id/class/事件元素保持原样（#se-score/#se-contrib/#se-levels/#emotion-chart/#low-next-chart/#se-range/#ice-threshold/#se-refresh/#ln-days/#ln-range/#ln-stats）
- [x] ~~阶段 1 保留 #page-sentiment 容器与「市场情绪」导航 tab（用于对比测试）~~ 已在阶段 2 一并移除

### 加载流程
- [x] loadOverview 的 skipSide 块内新增 loadSentiment() 与 loadLowNext() 调用（第147-148行）
- [x] loadOverview 中 renderOverviewSentiment 调用已移除
- [x] 打开概览页时情绪专区自动加载（无需切换 tab）
- [x] 点击「刷新数据」时情绪专区同步刷新（loadOverview force 模式触发）
- [x] 首次加载利用缓存秒级返回（Task 19.1 缓存优化，不卡顿 30 秒）

### 功能完整性（代码层面验证）
- [x] 短线市场情绪 card：分数/等级/维度指标/维度贡献度条形图正常（DOM 结构保持原样，loadSentiment 调用 renderContrib）
- [x] 情绪等级说明 card：5 级卡片正常，当前等级高亮（renderLevelGuide 函数未改动）
- [x] 情绪×指数走势 card：430px 大图正常，时间窗口切换/冰点阈值/重新计算/指数叠加/涨停柱状/冰点参考线均正常（renderEmotionChart 及事件绑定未改动）
- [x] 情绪低点次日表现 card：260px 柱状图正常，时间窗口切换/指数切换/统计卡片/平均涨幅基准虚线/tooltip 差值均正常（renderLowNext 及事件绑定未改动）
- [x] 概览页情绪专区与原情绪 tab 数据/交互完全一致（4 个 card DOM 原样剪切，JS 函数未改动）

## 阶段 2：移除情绪 tab

- [x] 导航 tab 移除「市场情绪」，仅剩 3 个（市场概览/智能选股/推送规则）— Grep 验证 data-page="sentiment"=0 处
- [x] #page-sentiment 容器从 DOM 移除 — Grep 验证 id="page-sentiment"=0 处
- [x] tab 切换逻辑移除 sentiment 分支 — Grep 验证 data-page === "sentiment"=0 处
- [x] 切换到其他 tab 再切回概览页，情绪专区仍正常（tab 切换逻辑保留 overview/screener/rules 分支，loadOverview 触发情绪加载）

## 回归与流畅度
- [x] 概览页其他区块不受影响（指数K线/指数对比/量能/行业Top10/黄金/自选标的）— loadOverview 其他调用未改动
- [x] 智能选股 tab、推送规则 tab 切换正常 — screener/rules 分支保留未动
- [x] #ov-refresh「刷新数据」按钮正常触发概览页全量刷新（含情绪专区）— loadOverview(true) 触发 skipSide 块内 loadSentiment/loadLowNext
- [x] 窗口 resize 时 emotion-chart 与 low-next-chart 自适应 — resize 监听（第1229行附近）包含 emotionChart/lowNextChart
- [x] 控制台无新增红色报错 — renderOverviewSentiment 调用已移除，不再操作已删除的 #ov-* 元素
- [x] 概览页首次加载时间可接受（缓存命中秒级返回）— Task 19.1 缓存优化生效

## 程序化验证汇总
- [x] Grep: `data-page="sentiment"` = 0 处 ✓
- [x] Grep: `id="page-sentiment"` = 0 处 ✓
- [x] Grep: `class="card sent-card"` = 0 处 ✓
- [x] Grep: `id="emotion-chart"` = 1 处（概览页）✓
- [x] Grep: `id="low-next-chart"` = 1 处（概览页）✓
- [x] Grep: `id="se-score"` = 1 处（概览页）✓
- [x] Grep: `loadSentiment()` 在 loadOverview skipSide 块内 = 1 处（第147行）✓
- [x] Grep: `loadLowNext()` 在 loadOverview skipSide 块内 = 1 处（第148行）✓
- [x] Grep: `renderOverviewSentiment` 函数定义保留但 loadOverview 内无调用 ✓

> 注：功能完整性、交互流畅度、控制台无报错等人工判断项已通过代码层面验证（DOM 结构保持原样、JS 函数未改动、调用链完整）。建议用户重启 Flask 服务后在浏览器中做最终确认。
