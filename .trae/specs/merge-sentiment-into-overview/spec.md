# 市场情绪 Tab 融入概览页 Spec

## Why
当前「市场情绪」是独立 tab 页，需切换才能查看完整情绪分析（趋势大图/低点次日表现等），而概览页仅有一个精简的 sent-card（仪表盘+6格指标+迷你图）。用户希望把完整情绪分析直接融入概览页，减少 tab 切换，让情绪信息与行情概览同屏可见，提升浏览流畅度与决策效率。

## What Changes
- **移除概览页 overview-grid 内的 sent-card**（仪表盘/6格指标/解读提示/近15日迷你图），原 sent-card 位置不再保留任何情绪元素
- **将情绪 tab 页的 4 个 card 融入概览页**，放置在 overview-grid 区块下方（行业 Top10/黄金卡之下）、自选标的实时行情之上：
  1. 短线市场情绪（score + level + dims + 维度贡献度条形图）
  2. 情绪等级说明（5 级卡片，当前等级高亮）
  3. 情绪 × 指数走势大图（430px，含时间窗口切换/冰点阈值/重新计算）
  4. 情绪低点 · 次日指数表现（260px，含时间窗口/指数切换/统计卡片）
- **移除导航 tab 中的「市场情绪」tab**（`data-page="sentiment"`），导航保留 3 个 tab：市场概览 / 智能选股 / 推送规则
- **移除独立的 `#page-sentiment` 容器**（原第 464-512 行整块）
- **调整 app.js 加载流程**：情绪内容随概览页 `loadOverview` 加载，不再依赖 tab 切换触发
- **移除 tab 切换中 `sentiment` 分支**（原第 25 行 `if (t.dataset.page === "sentiment") { loadSentiment(); loadLowNext(); }`）

## Impact
- Affected specs: optimize-market-overview（Task 13/17.3 的 sent-card 相关需求被本 spec 取代）
- Affected code:
  - `templates/index.html`：移除 sent-card、移除情绪 tab、移除 #page-sentiment、新增概览页情绪专区
  - `static/app.js`：loadOverview 增加 loadSentiment/loadLowNext 调用；tab 切换移除 sentiment 分支；renderOverviewSentiment/renderSentimentMini 不再被调用（函数定义可选保留）
  - `static/style.css`：sent-card 相关样式保留不影响；overview-grid 1 列布局去掉 1 卡后仍正常
- **BREAKING**：`#page-sentiment` 容器与 `data-page="sentiment"` tab 不再存在，任何依赖该 tab 的外部逻辑（书签/快捷键）会失效

## ADDED Requirements

### Requirement: 情绪内容融入概览页
系统 SHALL 将原「市场情绪」tab 页的全部 4 个 card 融入「市场概览」tab 页，放置在 overview-grid 区块下方、自选标的实时行情之上，作为概览页的情绪专区。

#### Scenario: 概览页可见情绪专区
- **WHEN** 用户打开「市场概览」tab
- **THEN** 概览页依次显示：指数 K 线 → 指数走势对比 → 市场量能 → overview-grid（行业 Top10/黄金卡）→ 情绪专区（4 个 card）→ 自选标的实时行情
- **AND** 情绪专区的 4 个 card 与原情绪 tab 页内容完全一致（短线情绪+维度贡献度、等级说明、情绪×指数走势、低点次日表现）
- **AND** 概览页不再出现原 sent-card（仪表盘/6格指标/解读提示/近15日迷你图）

#### Scenario: 情绪内容随概览页加载
- **WHEN** 用户打开「市场概览」tab 或点击「刷新数据」
- **THEN** 概览页加载流程中触发 `loadSentiment()` 和 `loadLowNext()`，渲染情绪专区的 4 个 card
- **AND** 首次加载利用 Task 19.1 的缓存优化，同一天内秒级返回

### Requirement: 情绪专区交互完整性保留
系统 SHALL 保留情绪专区所有原有交互功能，包括时间窗口切换、冰点阈值调整、重新计算按钮、指数切换、图表 resize。

#### Scenario: 交互功能正常
- **WHEN** 用户在概览页情绪专区操作（切换近15/60/120/250日、改冰点阈值、点重新计算、切换低点指数、悬停 tooltip）
- **THEN** 所有交互响应与原情绪 tab 页完全一致，无功能丢失
- **AND** 窗口 resize 时 emotion-chart 与 low-next-chart 自适应

### Requirement: 分阶段迁移与验证
系统 SHALL 按两阶段实施迁移：阶段 1 融入情绪内容到概览页（保留情绪 tab 用于对比测试）；阶段 2 在验证无误后移除情绪 tab。

#### Scenario: 阶段 1 融入并保留 tab
- **WHEN** 阶段 1 完成
- **THEN** 概览页已包含情绪专区 4 个 card 且功能正常
- **AND** 导航仍保留「市场情绪」tab，可切换到原 #page-sentiment 对比验证

#### Scenario: 阶段 2 移除 tab
- **WHEN** 阶段 1 验证通过后执行阶段 2
- **THEN** 导航移除「市场情绪」tab，仅剩 3 个 tab
- **AND** #page-sentiment 容器从 DOM 移除
- **AND** tab 切换逻辑移除 sentiment 分支

## REMOVED Requirements

### Requirement: 概览页 sent-card 市场情绪卡片
**Reason**: 被情绪 tab 融入的完整情绪专区取代，避免概览页出现重复情绪信息
**Migration**: 概览页原 sent-card 的仪表盘/6格指标/解读提示功能由情绪专区第 1 个 card（短线市场情绪+维度贡献度）替代；近15日迷你图由情绪专区第 3 个 card（情绪×指数走势大图）替代
