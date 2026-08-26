# 市场概览页问题修复 Spec（fix-optimize-market-overview-issues）

## Overview
- **Summary**：针对 optimize-market-overview 项目当前存在的 16 个用户反馈问题进行系统性修复，覆盖：全卡自动刷新架构、自选刷新按钮移除、黄金三品种数据来源更正、黄金历史走势切换为伦敦金、近15日情绪图空图修复、量能分时曲线 X 轴错位修复、涨跌双色进度条斜杠加粗 + 两端斜角（Task 1-7，已完成）；追加 6 项（Task 8-13，已完成）：刷新按钮 DATA:-- 修复 + 休市自动刷新、量能分时末端 X 轴对齐根因修复、近15日情绪图空图根因修复（日期格式 + 单点可见性）、行业领涨领跌 Top10 为空修复、黄金按交易时间实时刷新、黄金走势标题与 Y 轴字体重叠修复；再追加 3 项（Task 14-16）：getTradeSession 缺少下午交易时段判断导致自动刷新失效修复、刷新时间显示改为相对时间"xx前刷新"、重启 Flask 验证情绪图/行业 Top10 数据生效。
- **Purpose**：消除功能回归、数据错误和视觉体验问题，确保概览页所有卡片数据实时性正确、数据来源准确、图表渲染无误、视觉细节精致。
- **Target Users**：A股实盘看盘用户（概览页 Tab 1 概览的所有访问者）。

## Goals
1. 概览页所有卡片（指数行情条、情绪、行业 Top10、量能、涨跌统计、自选、黄金、指数对比、指数 K 线）均按合理频率自动刷新，无遗漏。
2. 自选标的实时行情的"刷新行情"按钮移除，由自动刷新承担。
3. 综合黄金行情第三品种由 AU0（沪金主连）更正为 AU9999（上金所 Au99.99 现货），名称与价格准确。
4. 金色线条的金价走势切换为伦敦金（现货黄金 XAUUSD）近30日收盘价，不再使用国内黄金 ETF 518880 代理。
5. 市场情绪卡的近15日情绪走势图在有数据的情况下正常渲染折线 + 6刻度 + 渐变背景，不为空。
6. 市场量能卡的分时预测量能曲线末端数据点在 X 轴上严格对齐对应时刻（如 11:10），而非被"max=15:00"挤压拉满到收盘位置。
7. 涨跌双色进度条的灰色斜向分割条加粗（约 6~8px 主体可见厚度），且红色段右边沿、绿色段左边沿各加工一条与灰色斜杠平行的 45° 斜角。
8. 顶部"刷新数据"按钮点击后 `#data-time` 立即更新为当前时间，不再停留 `DATA: --`；休市（非 A 股交易时段）也触发自动刷新（降频但不停止）。
9. 市场量能卡分时预测量能曲线末端数据点严格对齐 X 轴对应时刻（如 11:10），不再因后端强制补 15:00 点而被等距拉伸。
10. 市场情绪卡的近15日情绪走势图在任何情况下都不为空：日期格式归一化（YYYYMMDD → YYYY-MM-DD），单点数据复制为 2 条让 ECharts 可见。
11. 行业领涨领跌 Top10 两侧均有 ≤10 行数据，新浪接口反爬时降级到东方财富接口兜底。
12. 黄金数据按实际交易时间实时刷新：AU99.99 日间 09:00-15:30 / 夜间 20:00-次日 02:30；伦敦金、纽约黄金按各自交易时间；SPOTS 第 2 项名称改为"纽约黄金"。
13. 近30日伦敦金近似走势标题与金色线条的金价走势 Y 轴字体不再重叠，有明显间距。
14. 修复 getTradeSession 缺少 13:00-14:57 下午交易时段判断的 bug，该 bug 导致下午时段 isTradeSession() 返回 false，startOvAutoRefresh 走非交易分支不调 loadOverview，所有卡片数据不刷新、#data-time 停留旧时间。
15. 顶部状态栏刷新时间显示简化为相对时间"xx前刷新"（如"1小时20分50秒前刷新"），随时间累加每秒更新，不再显示多个绝对时间。
16. 重启 Flask 服务确保 Task 10/11 的后端改动（_enrich_sentiment 日期归一化、get_boards 东财备用源）生效，验证情绪图和行业 Top10 有数据。
17. **市场情绪近15日走势可靠渲染**：解决五次修复仍未彻底解决的"空图/无线条"问题，从多层兜底（后端 scores 数字类型保障 + 前端 ECharts 容错 + 原生 HTML 折线降级 + 响应式重建）确保任意场景下折线可见、永不空白。
18. **状态栏时间进一步简化**：`#data-time` 只显示相对时间"xx秒前刷新"（或 xx分xx秒 / xx小时xx分xx秒 / 刚刚刷新 / 未刷新），不再显示 `DATA: 盘中/盘后 · ` 前缀。
19. **市场量能分时曲线实现"随时间右移"效果**：预测量能橙色曲线不再沾满整个图表宽度，而是类似股票分时图——X 轴始终显示完整交易时段（9:30-11:30 / 13:00-15:00）242 个分钟刻度，曲线只绘制到当前实际时刻（未来时刻留空），随交易时间推进逐步向右延伸。

## Non-Goals (Out of Scope)
- 不新增任何卡片或改变三行布局结构（三行整宽：情绪因子 → 行业Top10 → 黄金；指数对比曲线独立）。
- 不重构自选标的增删改查逻辑（仅移除刷新按钮）。
- 不修改市场情绪分算法和量能预测算法的数学公式（仅修复渲染层和数据层 bug）。
- 不做移动端/非桌面分辨率的额外响应式适配（现有 ≤900px 断点保持）。
- 不引入新的第三方 API 供应商（伦敦金历史优先复用已验证的稳定接口）。

## Background & Context
- 当前自动刷新：`startOvAutoRefresh()`（[app.js:463-466](file:///d:/job/Repository/bull-run/static/app.js#L463-L466)）仅 12 秒调用 `refreshIndexStrip`，其余 8 张卡仅在首次 `loadOverview` 时加载一次，用户反映"自选标的"等卡片数据不更新。
- 黄金三品种 SPOTS 定义（[core/gold.py:26-30](file:///d:/job/Repository/bull-run/core/gold.py#L26-L30)）：第 3 项是 `AU0 / 沪金主连 / shfe`，按期货 28 段解析（单位元/克，~500-600 元/克为正常价位）。用户明确要求改为 `AU9999`（上金所 9999 现货）并修正数据口径。
- 黄金历史走势目前使用 A 股黄金 ETF 518880（[core/gold.py:123-147](file:///d:/job/Repository/bull-run/core/gold.py#L123-L147)）作为国内代理。需求改为伦敦金（XAUUSD）现货收盘价。
- 近15日情绪图可能为空的根因：`core.emotion_history.get_emotion_trend` 依赖 `legu.fetch_legu_history()`，若该接口返回空或 `_build_trend` 异常，则 scores=[]，前端显示"暂无历史情绪数据"。
- 量能 X 轴错位根因：`buildIntradayOption` 的 `xAxis.max: "15:00"` 与 ECharts category 类型不兼容。后端 `core/market.py:363-365` 已在 `intraday` 数组末尾补了 `{time:"15:00", chg:last}`，前端再设 max 导致中间点的 X 坐标被等距拉长至 15:00 位置。
- 双色进度条斜杠现状：`.dist-divider::before` 主体宽 3px、`skewX(-45deg)`。需求：加粗（5~8px 级别）且 `.dist-seg.up` 右边沿、`.dist-seg.down` 左边沿加与斜杠平行的 45° 斜角。
- Task 8 根因 A（DATA:--）：`loadOverview()` 的 try 块内 `renderOverviewSentiment` → `renderSentimentMini` 若抛异常，catch 捕获后 `updateDataTime()` 永不执行，`#data-time` 停留 `DATA: --`。
- Task 8 根因 B（休市不刷新）：`startOvAutoRefresh()` 仅在 `isTradeSession()` 为 true 时启 fast=60s + slow=300s 双档；非交易时段仅 slow=600s（10 分钟），用户要求休市也自动刷新。
- Task 9 根因（量能末端错位）：`core/market.py` 在 intraday 数组末尾强制补 `{time:"15:00", chg:last}`。盘中 11:10 时数组含 [..., {11:10}, {15:00}]，ECharts category 轴等距排列，11:10 的数据点视觉被拉到接近 15:00 标签处。
- Task 10 根因 A（日期格式）：`sentiment.get_sentiment()` 返回的 `trade_date` 是 "YYYYMMDD" 格式，`_enrich_sentiment` 直接用作 `today_date`，`today_label = today_date[5:]` 得到 "826" 而非 "08-26"；与 trend 中 "YYYY-MM-DD" 格式比较时永不等，导致重复追加格式错误的点。
- Task 10 根因 B（单点不可见）：trend 返回空且 `s.get("score")` 为 None 时，fallback 创建 1 个 score=50 的点，ECharts line 图只有 1 个数据点时不画线只画点，视觉几乎不可见。
- Task 11 根因（行业 Top10 为空）：`get_boards()` 请求新浪板块接口，公司网络下被反爬或返回非 JSON 格式，`re.search` 匹配失败 → 返回空 → 前端显示"暂无行业板块数据"。
- Task 12 根因（黄金非交易时段刷新慢）：`isTradeSession()` 仅判断 A 股交易时段，AU99.99 夜盘 20:00-02:30 时返回 false → slow=600s → 黄金每 10 分钟才刷新一次。SPOTS 第 2 项名称"COMEX黄金 GC"不直观，用户要求改为"纽约黄金"。
- Task 13 根因（标题与 Y 轴重叠）：`renderGoldHistory` 的 ECharts `grid.top: 20` 太小，Y 轴 `name: '收盘价（美元/盎司）'` + `nameLocation: 'end'` 导致 name 文字出现在图表顶部边缘，与上方 `#gold-history-label` 文本紧贴重叠。
- Task 14 核心根因（下午不刷新）：`getTradeSession()`（[app.js:33-45](file:///d:/job/Repository/bull-run/static/app.js#L33-L45)）仅覆盖 9:30-11:30（570-690）的"持续交易"，缺少 13:00-14:57（780-897）的下午交易时段判断。13:00-14:57 落入 `return "休市"` 兜底分支 → `isTradeSession()` 返回 false → `startOvAutoRefresh` 走 `else if (isGoldTradeSession())` 分支 → fast=120s 调 `doNonTradeFastRefresh`（只调 loadGold）→ 不调 loadOverview → updateDataTime 不更新（时间停留）+ 情绪图/行业 Top10 不刷新。此外 `startOvAutoRefresh()` 在 loadOverview 的 try 块内（L104），fetch 失败或渲染异常时 catch 捕获后不执行。
- Task 15 根因（时间显示繁杂）：`updateDataTime()` 显示 `DATA: 2026-08-26 盘后 · 刷新于 13:36:42`，与 `#clock` 的 `2026-08-26 13:59:15` 并列，多个绝对时间让用户困惑。需改为相对时间"xx前刷新"，由 tick 函数每秒计算更新。
- Task 16 根因（后端改动未生效）：Task 10（_enrich_sentiment 日期归一化）和 Task 11（get_boards 东财备用源）的代码改动已写入文件，但 Flask 服务未重启，运行中的进程仍是旧代码。python -c 验证后端函数返回正确（scores=15、industry=49），但 /api/overview 运行时返回旧数据。
- **Task 17 根因（情绪图五次修复仍为空）**：存在多层未覆盖的失败路径：① 后端 `_enrich_sentiment` 的 `scores = [t.get("score", 50) for t in trend]` 若 `t.get("score")` 是 `str`（emotion_history 经 JSON 序列化可能是字符串），则 series.data 为字符串数组而非 number 数组，ECharts value 轴 Y 值无法解析 → 折线不绘制；② 前端 renderSentimentMini 的 echarts try/catch 吞掉 setOption 异常后仅 `console.warn`，没有替代渲染（box.innerHTML 被清空后 canvas 不生成 → 视觉为纯空白）；③ rAF 重试时 _sentMiniRetry 计数器跨次调用未重置（下次渲染仍>3 次直接放弃）；④ 父容器 flex 布局动画、首次加载时 display/visibility 过渡，导致 3 次 rAF 内容器仍为 0 尺寸；⑤ 浏览器缓存旧 app.js（无版本号），新代码未加载。
- **Task 18 根因（状态栏前缀仍保留）**：Task 15 简化为 `DATA: 盘中 · xx前刷新`，但用户要求"只显示 xx秒前刷新"——需要移除 `DATA: 盘中/盘后 · ` 前缀，只留相对时间主体。
- **Task 19 根因（量能曲线沾满整图）**：当前 `buildIntradayOption`（app.js 779-818）的 `xAxis.data = intra.map(x=>x.time)` 仅包含"已有数据点的时刻"。例如盘中 10:00 时 intraday 数组约含 90 个分钟（9:31-11:00），X 轴只有 90 个 category，ECharts 等距排列后，曲线正好占满整个图表宽度，视觉上"沾满整幅"，不像分时图。正确的股票分时图效果应该是：X 轴始终显示**完整交易时段 242 个分钟刻度**（9:30-11:30 121 个 + 13:00-15:00 121 个），series.data 中已有数据的分钟填值、未来时刻填 `null`（不绘制、留白）。这样 10:00 时曲线只画到左侧约 30% 处，右侧大量留白，随时间逐步向右延伸。

## Functional Requirements
- **FR-1 全卡自动刷新调度器**：新增统一概览自动刷新调度（复用现有 `ovRefreshTimer`），刷新频率遵循各接口缓存 TTL 的 1.1x 保守节奏（避免频繁未命中）：
  - 高刷卡组（缓存 TTL 60~120s）：每 60s 一次，包含：指数行情条（refreshIndexStrip，调用 /api/overview force=0 或轻量接口）、市场量能（loadLiangneng，/api/liangneng TTL120s）、涨跌统计（loadDistribution，/api/market_distribution TTL60s）、自选（loadWatch，/api/quotes 无缓存）
  - 中刷卡组（缓存 TTL 300~600s）：每 300s 一次，包含：行业Top10（随 /api/overview 返回的 boards 字段，随 overview 刷新即更新；若单独刷即重拉 /api/overview?force=0）、黄金（loadGold，/api/gold TTL300s）、指数对比（loadIndexCompare，/api/index_compare TTL600s）
  - 低频卡组：指数K线（loadIndexKline，/api/index_kline TTL 默认）每日首启加载一次，中午12:00 和 收盘后 15:30 各一次；或按 600s 兜底刷新
  - 交易时段才自动刷新（`isTradeSession()` 判断），非交易时段停止或降频至 10 分钟一次
  - 切换到其他 Tab 停止，返回概览页重启（沿用 Tab 切换逻辑）
- **FR-2 移除自选刷新按钮**：删除 HTML 中 `#w-refresh` 刷新行情按钮与其容器 `<div style="text-align:right">`，删除 JS 中 `$("#w-refresh").addEventListener("click", loadWatch)` 绑定，保留 loadWatch 函数供调度器调用。
- **FR-3 黄金第三品种改为 AU9999**：`core/gold.py` 的 SPOTS 数组第 3 项改为 `("shAU9999", "Au99.99 AU9999", "spot")` 或其他新浪实际代码；解析分支新增 `stype == "spot"` 的字段拆分（基于实采验证）；名称、价格、昨收、涨跌幅、高、低、开、昨收 8 字段准确。若 shAU9999 反爬或无返回，降级为 AU0（沪金主连）并在 msg 字段说明。
- **FR-4 黄金历史走势改为伦敦金 XAUUSD**：
  - `core/gold.py` 新增 `get_gold_history_xau(days=30)`，优先调用伦敦金历史 K 接口（可尝试：新浪 hf_XAU kline、东方财富 XAUUSD 日线、或英为财情等稳定源），返回 `[{date, close}]` 30 条，close 单位美元/盎司，保留 2 位小数。
  - 若伦敦金历史接口受反爬，保留 518880 作为 fallback，但前端 label 和 tooltip 文案需按实际数据源动态切换（显示"伦敦金 XAUUSD 收盘价 美元/盎司"或兜底"黄金ETF 518880 代理"）。
  - 前端 `renderGoldHistory` 的 tooltip / Y 轴 name / axisLabel 文案改为对应美元口径（当数据源为伦敦金时 name='收盘价（美元/盎司）'，formatter 保留 2 位小数）。
  - HTML 中 `#gold-history-label` 文字改为动态：默认「近30日 伦敦金 XAUUSD 走势（现货黄金）」，兜底才显示 ETF 代理。
- **FR-5 近15日情绪图空图修复**：
  - 后端 `app.py` `_enrich_sentiment`：若 `get_emotion_trend(20)` 返回 0 条，调用 `force=True` 再重试一次；若仍空，回退为"仅用当日 score 构造 1 点序列"（labels=[today_date], scores=[当日得分]），确保前端 scores.len≥1 可渲染。
  - 同时检查 `legu.fetch_legu_history()` 和 `_build_trend` 的异常捕获，确保静默失败不返回空。
- **FR-6 量能分时曲线 X 轴错位修复**：
  - `app.js` `buildIntradayOption` 移除 `xAxis.max: "15:00"` 一行；如果仍想显示收盘空白范围，改为：在 xAxis.data 末尾补 `14:30/15:00` 等分类名但 series data 不补值（或 category 改为 `showMaxLabel: true`），确保每个数据点的 X 轴位置严格对齐 intra[i].time 本身。
  - 后端 `core/market.py:363-365` 补 `15:00` 点的逻辑保留（让曲线有收盘延续性），但前端渲染时 X 轴不设 max，让其自然对齐。
- **FR-7 双色进度条斜杠加粗 + 两端斜角**：
  - `.dist-divider::before`：`width: 3px` 提升到 `6px`，颜色保持 `#8a96b5`。
  - `.dist-seg.up`（红段）：右边沿 45° 斜角 `clip-path: polygon(0 0, 100% 0, calc(100% - 10px) 100%, 0 100%)`（与 `skewX(-45deg)` 斜角方向平行）
  - `.dist-seg.down`（绿段）：左边沿 45° 斜角 `clip-path: polygon(10px 0, 100% 0, 100% 100%, 0 100%)`
  - 单边为 0 时不渲染斜杠的逻辑保留（A.2 已有），clip-path 在单边时不影响显示（单边不出现另一端斜角）。
- **FR-8 顶部刷新按钮 DATA:-- 修复 + 休市自动刷新**：
  - `static/app.js` `loadOverview()`：将 `updateDataTime()` 从 try 块内移到 try/catch 之后（或 finally），保证无论 `/api/overview` 成功或抛异常（含 renderSentimentMini 崩溃），`#data-time` 都会更新为当前时间，不再停留 `DATA: --`。
  - `startOvAutoRefresh()`：非交易时段（`!isTradeSession()`）也启 fast 档（降频到 120s）+ slow 档（600s），不再只保留 slow=600s。交易时段仍为 fast=60s + slow=300s。
- **FR-9 量能分时末端 X 轴对齐修复（后端补点条件收紧）**：
  - `core/market.py` 补 15:00 点的条件从 `if intraday and intraday[-1]["time"] != "15:00":` 收紧为 `if intraday and intraday[-1]["time"] != "15:00" and now.hour * 60 + now.minute >= 900:`（仅在 15:00 后才补）。盘中（<15:00）不补 15:00 点，让曲线末端严格对齐最后一个真实数据点的时间。
  - 前端 `buildIntradayOption` 已删 `xAxis.max`（Task 6 完成），无需再改。
- **FR-10 近15日情绪图空图根因修复**：
  - `app.py` `_enrich_sentiment`：取 `today_date` 后做格式归一化：若长度 8 且无 `-`，转为 `f"{td[:4]}-{td[4:6]}-{td[6:8]}"`；`today_label = today_date[5:]` 得到正确 "MM-DD"。
  - 当 trend 最终只有 1 条时，复制为 2 条相同值的点（让 ECharts 至少画出一条水平短线可见）。
- **FR-11 行业 Top10 为空修复（东财备用源）**：
  - `core/market.py` `get_boards()`：新浪接口加 try/except，失败时请求东方财富板块接口 `https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fields=f12,f14,f3&fs=m:90+t:2`（行业板块）。
  - 东财返回 JSON，解析 `data.diff` 数组，每项 `{f12:代码, f14:名称, f3:涨跌幅}`，映射为 `{name, avg_pct, ...}` 结构。
  - 两源均失败时返回 `{"industry": [], "concept": []}` 不报错。
- **FR-12 黄金按交易时间实时刷新**：
  - `static/app.js` 新增 `isGoldTradeSession()`：非周末均视为黄金交易时段（伦敦金近 24 小时交易，AU99.99 夜盘 20:00-02:30，纽约黄金有夜间盘）。
  - `startOvAutoRefresh`：若 `isGoldTradeSession()` 为 true 且当前非 A 股交易时段，仍启 fast=120s 档让黄金每 2 分钟刷新一次。
  - `core/gold.py` `SPOTS` 第 2 项展示名从 "COMEX黄金 GC" 改为 "纽约黄金"。
- **FR-13 黄金走势标题与 Y 轴字体重叠修复**：
  - `static/app.js` `renderGoldHistory`：ECharts `grid.top` 从 `20` 改为 `35`，给 Y 轴 name 留出空间。
  - `static/style.css` `.note` 规则追加 `margin-bottom: 4px`，让 `#gold-history-label` 与图表间有间距。
- **FR-14 修复 getTradeSession 缺少下午交易时段 + startOvAutoRefresh 移出 try 块**：
  - `static/app.js` `getTradeSession()`：在 `if (hm >= 690 && hm < 780) return "午间休市"` 之后、`if (hm >= 897 && hm < 900) return "收盘竞价"` 之前，增加 `if (hm >= 780 && hm < 897) return "持续交易";`（13:00-14:57 下午持续交易时段）。
  - `static/app.js` `loadOverview()`：将 `startOvAutoRefresh()` 从 try 块内（L104）移到 try/catch 之后（与 updateDataTime 同位置），保证 fetch 失败或渲染异常时定时器仍启动。
- **FR-15 刷新时间改为相对时间"xx前刷新"**：
  - `static/app.js` 新增全局变量 `lastRefreshTs = 0` 记录上次刷新时间戳。
  - `updateDataTime()`：设置 `lastRefreshTs = Date.now()`，不再直接写绝对时间文本；改为调用 `renderRefreshAgo()` 渲染相对时间。
  - 新增 `renderRefreshAgo()` 函数：计算 `Date.now() - lastRefreshTs`，格式化为"刚刚刷新"/"xx秒前刷新"/"xx分xx秒前刷新"/"xx小时xx分xx秒前刷新"。
  - `tick()` 函数每秒调用 `renderRefreshAgo()`，让相对时间随时间累加更新。
  - 简化 `#data-time` 显示：`DATA: 盘中 · xx前刷新` 或 `DATA: 盘后 · xx前刷新`（去掉日期和绝对时间，与 #clock 不重复）。
- **FR-16 重启 Flask 服务验证后端改动生效**：
  - 重启 Flask 服务（如 `python app.py`），确保 Task 10/11 的后端改动（_enrich_sentiment 日期归一化 + 单点复制、get_boards 东财备用源）加载到运行进程。
  - 验证 `/api/overview?force=1` 返回的 `sentiment.history_scores` len ≥ 2 且 `boards.industry` len ≥ 1。
  - 验证前端情绪图渲染折线、行业 Top10 显示数据条。

## Non-Functional Requirements
- **NFR-1 数据一致性**：黄金三品种 spot 字段价格与对应交易市场价格误差 ≤0.5%（实采验证）。
- **NFR-2 刷新性能**：单轮全卡自动刷新总网络请求数 ≤7 条（合并可合并的请求，例如 overview 接口已带 boards、sentiment，无需单独刷行业 Top10）。
- **NFR-3 无新增控制台错误**：修复后浏览器 JS 控制台无新增红色 Error。
- **NFR-4 缓存兼容**：自动刷新默认不带 force=1，遵循接口 TTL；仅用户手动刷新按钮（若存在）带 force。

## Constraints
- **Technical**：
  - 框架：Flask + Jinja2 SPA（不路由跳转，单页），ECharts 5.x，原生 JS（无框架），CSS 自定义。
  - 代理：公司网络走系统注册表代理，`requests.Session` 清掉 HTTP_PROXY 环境变量（与 core/data.py 一致），gold.py 保持此模式。
  - 数据来源：实时行情优先新浪 hq.sinajs.cn（已验证）；伦敦金历史需选稳定源。
- **Business**：
  - 自动刷新频率不得超过 60s/次（高频卡组），避免触发反爬。
  - 自选刷新按钮移除后，自选数据更新频率需与指数行情条同级（≤60s），用户体验不退化。
- **Dependencies**：core/gold.py 依赖 core/data.kline（518880 fallback），不引入新 pip 包。

## Assumptions
1. 新浪 hq.sinajs.cn 可通过 `shAU9999` 代码请求到 Au99.99 现货行情（或代码格式为 `sgeAU9999` / `hf_AU9999`，实采后以实际可用代码为准）。
2. 伦敦金 XAUUSD 历史 K 线至少有一个公开接口可稳定获取（若所有接口均被反爬则降级为 518880，并在 label 上明确标注）。
3. `legu.fetch_legu_history()` 返回空的主要原因是日级缓存过期，`force=True` 可修复；若根本接口不可用，则 fallback 到当日单点不报错。
4. ECharts category 轴删除 `max` 属性后，X 轴末端可正常显示最后一个真实时间点（如 11:10），用户可接受"未到收盘 X 轴不走到 15:00"。

## Acceptance Criteria

### AC-1 全卡自动刷新覆盖
- **Given**：处于交易日交易时段（9:30-11:30 / 13:00-14:57），且处于概览 Tab
- **When**：等待 ≥65 秒不做任何操作
- **Then**：以下所有卡的内容被刷新（可通过数据时间戳 / 价格变化 / 或网络面板请求确认）：指数行情条、市场情绪卡（含迷你图）、行业Top10、市场量能（数值+曲线）、涨跌统计（柱状图+双色进度条）、自选标的实时行情表格、综合黄金行情（3 品种+折线）、指数走势对比曲线
- **Verification**: `programmatic`
- **Notes**: Chrome DevTools Network 面板确认 60s 内 /api/overview、/api/liangneng、/api/market_distribution、/api/quotes、/api/gold、/api/index_compare 6 类接口均出现至少 1 次

### AC-2 非交易时段降频 & 切 Tab 停止
- **Given**：切到选股/情绪/回测 Tab 或处于非交易时段（非集合竞价/持续交易/收盘竞价）
- **When**：等待 ≥3 分钟
- **Then**：切 Tab 后概览接口不再自动请求；非交易时段若调度器跑，每 10 分钟才一次
- **Verification**: `programmatic`

### AC-3 自选刷新按钮移除
- **Given**：打开概览页底部自选标的区域
- **When**：检查 DOM
- **Then**：不存在 id=w-refresh 的按钮，也不再有 `<button class="btn ghost">刷新行情</button>` 的文字；JS 中不再绑定 w-refresh 的 click 监听
- **Verification**: `programmatic`

### AC-4 黄金第三品种 AU9999 价格正确
- **Given**：调用 `/api/gold?force=1`
- **When**：检查返回 spot 数组第 3 项（若 spot.len≥3）
- **Then**：symbol="shAU9999"（或实际可用正确代码），name 含 "AU9999" 或 "Au99.99"，price≈500-800 元/克（元/克口径），pct 合理（±3% 日内范围）；若接口降级则 msg 字段明确说明
- **Verification**: `programmatic`
- **Notes**: 用户提的"过一千"可能是单位误解（伦敦金是美元/盎司≈2000+），按国内 Au99.99 实际价位验证即可

### AC-5 金色线条历史走势为伦敦金
- **Given**：调用 `/api/gold?force=1`，并渲染综合黄金卡折线
- **When**：悬停折线任一数据点
- **Then**：tooltip 文案显示「伦敦金 XAUUSD 收盘」而非 ETF；Y 轴 name 为「收盘价（美元/盎司）」；history_xau 每项 close ≈ 1800~2500 美元/盎司（国际金价口径）；HTML `#gold-history-label` 文字与数据源一致
- **Verification**: `human-judgment` & `programmatic`

### AC-6 近15日情绪图非空
- **Given**：`/api/overview?force=1` 返回 sentiment.history_scores.len≥1
- **When**：渲染 sent-card 中部近15日情绪图
- **Then**：肉眼可见折线 + 圆点 + X 轴日期标签 + Y 轴 6 刻度；浏览器控制台无 renderSentimentMini 相关报错
- **Verification**: `programmatic` & `human-judgment`

### AC-7 量能分时曲线末端 X 轴对齐
- **Given**：盘中 11:10 左右访问，`/api/liangneng` 返回 intraday 数组末端 time="11:10"（再补一个 15:00 固定点）
- **When**：悬停曲线末端最后一个数据点（11:10 对应的预测值）
- **Then**：tooltip 显示时间"11:10"，且该点在 X 轴上的视觉位置与 11:10 刻度严格对齐；不再出现 11:10 的值贴到 15:00 X 轴标签
- **Verification**: `programmatic` & `human-judgment`
- **Notes**: 后端补的 15:00 延伸点如存在，允许曲线到 15:00，但中间点（如 11:10）不得被挤压

### AC-8 双色进度条斜杠加粗 + 两端斜角
- **Given**：上涨/下跌家数均 > 0，出现 .dist-divider
- **When**：肉眼查看进度条或 DevTools 检查
- **Then**：
  1. `.dist-divider::before` 宽度 ≥6px（视觉明显加粗）
  2. 红段（.dist-seg.up）右边沿有与灰色斜杠平行的 45° 斜切角（clip-path 生效）
  3. 绿段（.dist-seg.down）左边沿有与灰色斜杠平行的 45° 斜切角
  4. 单边为 0 时斜角和斜杠均不出现、无视觉毛边
- **Verification**: `human-judgment`

### AC-9 py_compile 通过 & 接口正常
- **Given**：修复完成
- **When**：执行 `python -m py_compile app.py core/gold.py core/market.py core/emotion_history.py`
- **Then**：全部退出码 0；/api/gold?force=1、/api/overview?force=1、/api/liangneng 返回合法 JSON（无 500 / 字段缺失）
- **Verification**: `programmatic`

### AC-10 顶部刷新按钮 DATA:-- 修复 + 休市自动刷新
- **Given**：非 A 股交易时段（周末/午间休市/盘后），概览页已加载
- **When**：点击"刷新数据"按钮，或等待 120 秒
- **Then**：点击后 `#data-time` 立即更新为 `DATA: YYYY-MM-DD 盘后 · 刷新于 HH:MM:SS`，不再停留 `DATA: --`；即使 `/api/overview` 返回 500 或 JSON 解析失败，`updateDataTime()` 仍执行；等待 120s 内 Network 出现 `/api/overview` 请求 ≥1 次
- **Verification**: `programmatic`

### AC-11 量能分时末端 X 轴对齐（后端补点收紧）
- **Given**：盘中 11:10 左右访问，`/api/liangneng` 返回 intraday
- **When**：检查 intraday 数组末尾
- **Then**：盘中（<15:00）intraday 末尾 time 为最后一个真实数据点（如 "11:10"），不含 "15:00"；前端 X 轴 data 长度 = intraday.length，曲线末端严格对齐最后一个真实时间点。收盘后（≥15:00）intraday 末尾含 "15:00" 点（后端仍补），曲线自然延伸到收盘
- **Verification**: `programmatic`

### AC-12 近15日情绪图非空（日期归一化 + 单点可见）
- **Given**：`/api/overview?force=1` 返回 sentiment
- **When**：`_enrich_sentiment` 处理 trade_date="YYYYMMDD" 格式
- **Then**：`history_labels` 中每个 label 格式为 "MM-DD"（如 "08-26"），不含 "826" 残片；当 trend 返回空时 `history_scores.len >= 2`（至少 2 点让 ECharts 可见）；labels 与 scores 等长；浏览器中 sent-card 近15日情绪走势图肉眼可见折线（即使只有 1 天数据也至少有 1 条短水平线）
- **Verification**: `programmatic` & `human-judgment`

### AC-13 行业 Top10 非空（东财备用源）
- **Given**：新浪板块接口被反爬或返回非 JSON
- **When**：`get_boards()` 降级请求东方财富板块接口
- **Then**：`get_boards()["industry"]` len ≥ 1（至少有行业数据）；浏览器中"行业领涨领跌 Top10"两侧各有 ≤10 行数据条，不再显示"暂无行业板块数据"
- **Verification**: `programmatic` & `human-judgment`

### AC-14 黄金按交易时间实时刷新 + 名称更正
- **Given**：AU99.99 夜盘 20:00-02:30 或伦敦金交易时段，非 A 股交易时段
- **When**：访问概览页等待 120s
- **Then**：`app.js` 存在 `isGoldTradeSession()` 函数；120s 内 `/api/gold` 出现 ≥1 次自动请求；SPOTS 第 2 项 name 包含 "纽约黄金"（不再是 "COMEX黄金"）
- **Verification**: `programmatic`

### AC-15 黄金走势标题与 Y 轴字体重叠修复
- **Given**：综合黄金卡的金色折线图已渲染
- **When**：肉眼查看
- **Then**：`renderGoldHistory` 的 option.grid.top ≥ 35；"近30日 伦敦金近似走势..."标题文本与 Y 轴 "收盘价（美元/盎司）" 文字不再重叠，有明显间距
- **Verification**: `programmatic` & `human-judgment`

### AC-16 下午交易时段自动刷新生效
- **Given**：处于 13:00-14:57 下午持续交易时段，概览页已加载
- **When**：等待 ≥65 秒
- **Then**：`getTradeSession()` 返回"持续交易"（非"休市"）；`isTradeSession()` 返回 true；`startOvAutoRefresh` 走 fast=60s 分支；65s 内 `#data-time` 的相对时间重置为"刚刚刷新"（证明 loadOverview 被调用、updateDataTime 执行）；情绪图和行业 Top10 数据被刷新
- **Verification**: `programmatic`

### AC-17 刷新时间显示为相对时间"xx前刷新"
- **Given**：概览页已加载，#data-time 已渲染
- **When**：观察 #data-time 文本随时间变化
- **Then**：显示 `DATA: 盘中 · xx前刷新` 或 `DATA: 盘后 · xx前刷新`（无日期、无绝对时间）；刷新后显示"刚刚刷新"，随后每秒累加为"xx秒前刷新"→"xx分xx秒前刷新"→"xx小时xx分xx秒前刷新"；不再与 #clock 的绝对时间重复
- **Verification**: `programmatic` & `human-judgment`

### AC-18 Flask 重启后情绪图和行业 Top10 有数据
- **Given**：Flask 服务已重启，加载了 Task 10/11 的最新代码
- **When**：访问 `/api/overview?force=1`
- **Then**：`sentiment.history_scores` len ≥ 2（日期格式为 MM-DD）；`boards.industry` len ≥ 1；前端情绪图渲染折线（非"暂无历史情绪数据"空态）；行业 Top10 两侧各有 ≤10 行数据条（非"暂无行业板块数据"空态）
- **Verification**: `programmatic` & `human-judgment`

## 追加 Functional Requirements（FR-17/18/19 对应 Goal 17/18/19）
- **FR-17 市场情绪近15日走势可靠渲染（多层兜底）**：
  - 后端保障：`_enrich_sentiment`（app.py）生成的 `history_scores` 数组元素强制 `int()` 转换，若为 NaN/非数字则 fallback 到 50；scores 长度 < 2 时按就近数据点扩展为 2 条（避免 ECharts line 1 点不画线）；返回 JSON 前校验所有 score 字段是 number。
  - 前端保障：`renderSentimentMini`：① echarts.init/setOption 前用 `Number(val) || 50` 确保 scores/labels 安全；② setOption 失败 3 次后，**不再返回空白**，fallback 到**原生 HTML/SVG 折线渲染**（用 CSS 线性渐变背景 + 6 段 Y 刻度 + SVG polyline 连接 scores 的折线，视觉风格尽量接近 ECharts，标注 score 数值点），保证"能看到折线"为最底线；③ `_sentMiniRetry` 改为函数内静态变量或封装的闭包计数器，每次调用 renderSentimentMini 时重置；④ rAF 重试上限从 3 次提升到 6 次，并在第 1/3/6 次分别使用 getBoundingClientRect + ResizeObserver（若可用）主动触发容器尺寸测量；⑤ 若 6 次后容器尺寸仍不可用（如 Tab 切换隐藏），立即进入原生 HTML/SVG 降级。
  - 缓存保障：`index.html` 静态资源 `static/app.js` 引用加查询字符串 `?v=20260826c`（或基于文件修改时间），硬绕过浏览器缓存确保新代码 100% 加载。
- **FR-18 状态栏时间只显示相对时间（无前缀）**：
  - `renderRefreshAgo()`（app.js L79-103）输出从 `DATA: ${tag} · ${agoText}` 改为直接 `el.textContent = agoText`；agoText 仍保持 Task 15 的四档：刚刚刷新（<5s）、xx秒前刷新（<60s）、xx分xx秒前刷新（<3600s）、xx小时xx分xx秒前刷新（≥3600s）、未刷新（lastRefreshTs=0）。
  - `isTradeSession()` 的 盘中/盘后 tag 不再在 #data-time 显示（状态仍由 `#top-status` 顶部左侧显示，不受影响）。
- **FR-19 市场量能分时曲线实现"随时间右移"效果**：
  - 前端 `buildIntradayOption`（app.js 779-818）重写：① 生成完整交易分钟列表 xData：上午 9:30~11:30（121 分钟，9:30,9:31,...,11:30），下午 13:00~15:00（121 分钟，13:00,13:01,...,15:00），共 242 项；② 建 chgMap = `{time: chg}`（从 d.intraday 提取，key 与 xData 格式均为 "HH:MM"）；③ `xAxis.data = xData`；④ `series.data = xData.map(t => chgMap[t] != null ? chgMap[t] : null)`；⑤ `series.connectNulls = false`（午休时段不跨接），`smooth: false`（分时图折线应尖锐点线，平滑会抹平节点，更像传统分时图），`symbol: "none"` 保持无点。
  - 原有 xAxis `interval: idx%30===0 || val==="15:00"` 保留，因 xData 共 242 项每 30 项一标签正好半小时一标签，视觉正确；tooltip formatter 对 null 值返回空串。
  - 后端 `core/market.py` 的 15:00 补点（L404-405）仍保留（盘后补点），与前端新方案不冲突；非交易时段 intraday 可能为空时前端按 buildIntradayOption 仍显示完整 x 轴但 series.data 全 null，若视觉不可接受则空态时仍走 `暂无量能历史数据` 占位。

## 追加 Acceptance Criteria

### AC-19 市场情绪近15日走势可靠渲染永不空白
- **Given**：概览页已加载，浏览器缓存已清空（加载最新 app.js 带 ?v= 版本）
- **When**：刷新页面并检查 `#ov-sent-big` 容器
- **Then**：① 后端 `/api/overview?force=1` 的 `sentiment.history_scores` 每一项均为 `int`（JSON typeof number）；② renderSentimentMini 在首次加载时能绘制 ECharts 折线或 3 次重试后进入原生 HTML/SVG 降级——无论哪种方式，容器内部要么有 canvas 且有绘制像素，要么有 `<svg>`/`<div>` 原生折线 DOM，**绝不能是空白且无任何 DOM 子节点**；③ 切换 Tab（如选股→概览）后重新进入，情绪图重新渲染并显示（ResizeObserver 兜底激活）；④ 无任何 JS 运行时异常（`console.error` / `uncaught TypeError`）使折线丢失
- **Verification**: `programmatic` & `human-judgment`

### AC-20 状态栏 #data-time 仅显示相对时间
- **Given**：概览页已加载
- **When**：查看 #data-time 文本
- **Then**：显示内容仅为以下五种之一且不含任何前缀："未刷新"、"刚刚刷新"、"N秒前刷新"、"N分N秒前刷新"、"N小时N分N秒前刷新"；字符串中不得出现 "DATA"、"盘中"、"盘后"、"·" 字符
- **Verification**: `programmatic` & `human-judgment`

### AC-21 量能分时曲线随交易时间右移（右侧留白）
- **Given**：盘中交易时段（如上午 10:00），概览页已加载，切换到「当日追测」
- **When**：查看量能卡橙色预测量能分时曲线
- **Then**：① X 轴显示完整交易时段（包含 9:30、10:00、11:00、11:30、13:00、14:00、15:00 等典型标签），X 轴长度占满整个图表宽度；② 橙色曲线（含面积渐变）仅绘制到当前实际分钟（如 10:00 时，末端大约在图表横轴 33% 位置，接近 10:00 标签）；③ 当前时间之后的区域（右侧约 67% 宽度区域）无曲线、无面积填充、留白；④ 午休 11:30-13:00 之间曲线不连接（connectNulls=false）；⑤ 悬停 tooltip 只在已绘制部分弹出，右侧空白分钟不弹出有效数据 tooltip
- **Verification**: `human-judgment` & `programmatic`（检查 xAxis.data.length === 242；series.data 中非 null 的最大 dataIndex 对应的 X 值 ≤ 当前时刻）

## Open Questions
- [ ] AU9999 在新浪 hq.sinajs.cn 的实际可用代码格式：`shAU9999` / `sgeAU9999` / `hf_AU9999`？（需实采 6 种候选后选定，若均失败则保留 AU0 并在 UI 说明）
- [ ] 伦敦金 XAUUSD 近 30 日日线的稳定数据源（需实采 3~5 种候选后选定；全部失败则 518880 兜底并 UI 动态切换文案）
