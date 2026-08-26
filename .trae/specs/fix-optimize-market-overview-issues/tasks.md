# fix-optimize-market-overview-issues - 实施计划

## [x] Task 1: 概览页全卡自动刷新调度器（替换现有单指数刷新为分档调度）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - 重构 `startOvAutoRefresh / stopOvAutoRefresh`，引入双档定时器：高频档（`_ovFastTimer`，60s，交易时段）+ 中/低频档（`_ovSlowTimer`，300s 交易时段 / 600s 非交易时段）
  - 高频档每 60s 触发：`loadOverview()` 不带 force（覆盖指数条+情绪+行业Top10+迷你图，内部走 TTL 缓存）+ 并行 `loadLiangneng()` + `loadDistribution()` + `loadWatch()`
  - 中/低频档每 300s 触发：`loadGold()`（TTL 300s）+ `loadIndexCompare(currentDays)`（TTL 600s，用一个计数器每 2 次才触发一次）；指数 K 线 `loadIndexKline()` 每 600s 触发或只在每日首加载/12:00/15:30 触发（选择实现简单的 600s 兜底即可）
  - 保留 Tab 切换启停：切到其他页 `stopOvAutoRefresh()` 清双定时器；回概览 `startOvAutoRefresh()` 重建
  - 非交易时段（`!isTradeSession()`）不启高频档，只保留中低频且降频（slow 10 分钟一次），避免无效请求
- **Acceptance Criteria Addressed**: AC-1, AC-2, NFR-2
- **Test Requirements**:
  - `programmatic` TR-1.1：DevTools Network 在 65s 内观察到 `/api/overview`、`/api/liangneng`、`/api/market_distribution`、`/api/quotes` 4 个请求各出现 ≥1 次；305s 内观察到 `/api/gold`、`/api/index_compare` 各 ≥1 次
  - `programmatic` TR-1.2：切到选股 Tab 后 70s 内 Network 无 `/api/overview` 新请求（证明停了）
  - `human-judgement` TR-1.3：自选表格的 `#w-time` 每分钟更新一次，证明自动刷新生效
- **Notes**: 现 `refreshIndexStrip` 可保留（单独函数），但不再由定时器调用，改由 `loadOverview()` 内部 `renderIndexStrip(o)` 承担刷新

## [x] Task 2: 移除自选标的"刷新行情"按钮
- **Priority**: medium
- **Depends On**: Task 1（自动刷新已就位）
- **Description**：
  - `templates/index.html`：删除 id=`w-refresh` 的 `<button>` 及外包的 `<div style="text-align:right;margin-top:12px">` 容器（共 1 行或 1 小段落）
  - `static/app.js`：删除 `$("#w-refresh").addEventListener("click", loadWatch)` 绑定行（现约在 1243 行）
  - 保留 `loadWatch` 函数定义（供 Task 1 调度器调用）
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-2.1：`document.getElementById("w-refresh")` 返回 null；`$("#w-tbody").closest("table").nextElementSibling` 或自选区 DOM 中不再包含文字"刷新行情"
  - `programmatic` TR-2.2：app.js 中 grep `w-refresh` 仅可能在注释中出现，不再有 addEventListener 绑定
- **Notes**: 如自选区下方有其他按钮（添加/删除等）不碰；仅删刷新按钮

## [x] Task 3: 黄金第三品种 AU9999 数据来源更正
- **Priority**: high
- **Depends On**: None
- **Description**：
  - 实采验证新浪可用 AU9999 代码：候选 3 组：`shAU9999`、`sgeAU9999`、`hf_AU9999`（分别 `_SESSION.get("https://hq.sinajs.cn/list=" + code)` 验证返回非空且 price>300 且 <1000 元/克）
  - `core/gold.py` 的 `SPOTS` 数组：第 3 项 `("AU0", "沪金主连 AU0", "shfe")` 改为 `(实采可用代码, "Au99.99 AU9999", "spot")`，并在 `get_gold_spot` 解析分支新增 `elif stype == "spot"`：按实际字段数拆解（实采打印后按段数确定：若 >=14 段则与 hf 同；若 28 段则与 shfe 同；若新结构则独立分支），确保 name/price/pct/high/low/open/last_close 8 字段准确
  - 兜底：若 3 组候选全部失败，msg 字段追加 "AU9999 接口无返回，已降级为沪金主连 AU0"，并回退使用 AU0
- **Acceptance Criteria Addressed**: AC-4, NFR-1
- **Test Requirements**:
  - `programmatic` TR-3.1：`py_compile core/gold.py` 通过；curl `/api/gold?force=1` 的 spot[2] symbol 为实采可用代码；name 含 "AU9999" 或 "Au99.99"
  - `programmatic` TR-3.2：spot[2].price 在 400~800 区间（元/克口径）；spot[2].pct 在 ±5% 日内范围合理
  - `human-judgement` TR-3.3：黄金卡三品种中，第 3 列显示 "Au99.99 AU9999"，价格不再是错误值
- **Notes**: 代码候选如均失败，不得硬编 name/price；必须走 AU0 降级并在 msg 字段显式说明

## [x] Task 4: 金色线条历史走势切换为伦敦金 XAUUSD（含数据源验证 & 文案动态切换）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - `core/gold.py` 新增 `get_gold_history_xau(days=30)` 函数，尝试 2~3 个伦敦金日线历史源（按优先级）：
    1. 新浪 `hq.sinajs.cn/list=hf_XAU` 历史需另找 kline 接口；可尝试 `https://finance.sina.com.cn/futures/quotes/XAU.shtml` 或腾讯 kline 接口
    2. 东方财富或 A 股黄金 ETF 518880 与 XAUUSD 相关性拟合（系数=伦敦金昨收/518880昨收 滚动，每日一次校准，30 日乘系数得到近似 XAUUSD 序列，在 msg 注明"近似折算"）
    3. 其他公开免费源，如 `https://api.goldapi.io/` 如未封装则放弃，直接走 2
  - 返回结构 `[{date:YYYY-MM-DD, close:float}]` 升序 30 条，close 保留 2 位小数，单位美元/盎司；同时在返回对象中加 `source: "XAUUSD|518880xratio|fallback_518880"` 字段用于前端文案切换
  - `get_gold_overview`：优先调用新函数，失败/异常则回旧的 `get_gold_history(days)` ETF，并在 msg 字段加降级提示
  - `app.js` `renderGoldHistory`：判断 hist 首项或 d.source，切换 tooltip（"伦敦金 XAUUSD 收盘"/"黄金ETF 518880 收盘"）、Y 轴 name（"收盘价（美元/盎司）"/"收盘价（元）"）、axisLabel formatter（2 位/4 位小数）；折线颜色、渐变仍为金色系不变
  - HTML `#gold-history-label`：默认静态文字改为由 JS 动态写入（`renderGoldHistory` 第一行设置 `.textContent`，source=XAUUSD 写"近30日 伦敦金 XAUUSD 走势（现货黄金，美元/盎司）"，fallback 写旧文案）
- **Acceptance Criteria Addressed**: AC-5, NFR-1
- **Test Requirements**:
  - `programmatic` TR-4.1：curl `/api/gold?force=1` 返回 history_xau len=30；若 source=XAUUSD 则每项 close 在 1800~2500 美元/盎司区间
  - `programmatic` TR-4.2：前端渲染后 `goldHistoryChart.getOption().yAxis[0].name` 与数据源匹配（XAUUSD=美元/盎司，fallback=元）
  - `human-judgement` TR-4.3：悬停折线 tooltip 单位与价格量级匹配；`#gold-history-label` 文案与数据源一致
- **Notes**: 若所有 XAUUSD 历史源均不可用，走 518880 系数折算必须在 msg 字段明确标注"近似折算"，不得伪装为真实 XAUUSD

## [x] Task 5: 近15日情绪图空图修复（后端兜底 + 异常增强）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - `app.py` `_enrich_sentiment`（现约在 81-110 行）：
    1. 原 `trend = emotion_history.get_emotion_trend(20)[-15:]` 改为：先 `trend = emotion_history.get_emotion_trend(20)`；若 len<3 再 `trend = emotion_history.get_emotion_trend(20, force=True)` 重试一次；若仍 <1 则 fallback 单点：`trend = [{"date": today, "label": today_label, "score": s.get("score") or 50}]`（today 由 trade_date 或 datetime 推导）
    2. 确保 `scores` 与 `labels` 等长；if len(scores) > 15 截断到 15 的逻辑保留
  - `core/emotion_history.py` `get_emotion_trend`：`_compute_em_factors` 与 `legu.fetch_legu_history` 外层加 try/except，异常时打印并返回空；`_build_trend` 同样加固，不得抛异常导致上层捕获空返回
  - 前端无需改动（renderSentimentMini 已实现 scores.len≥1 即渲染）
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1：curl `/api/overview?force=1` 必返回 sentiment.history_scores.len≥1（即使 legu 接口全失败，也有当日单点 fallback）
  - `programmatic` TR-5.2：`py_compile app.py core/emotion_history.py` 通过
  - `human-judgement` TR-5.3：sent-card 中部近15日情绪图在任何情况下不再显示"暂无历史情绪数据"空态（除非 trade_date==None 且 score==null 极端情况才保留降级）

## [x] Task 6: 量能分时预测量能曲线 X 轴错位修复
- **Priority**: high
- **Depends On**: None
- **Description**：
  - `static/app.js` `buildIntradayOption`（现约 660-700 行）：删除 `xAxis.max: "15:00"` 一行
  - 为仍让 15:00 时刻的延伸数据点在 X 轴可见，可补充：
    - 若 intra 数组含 15:00（后端已补），ECharts category 轴会自动在末尾显示；无需 max
    - 如需在 X 轴标签上强调 15:00，保留现有 `interval: function (idx, val) { return idx % 30 === 0 || val === "15:00"; }` 逻辑即可（不受影响）
  - 后端 `core/market.py:363-365` 补 15:00 延伸点的逻辑保留（让曲线有收盘延续性，视觉自然）
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-6.1：`buildIntradayOption` 生成的 option.xAxis 不再含 max 键；X 轴 data 长度 = `intraday.length`（含后端补的 15:00），曲线末端即最后一个点，位置与 intra[last].time 对应刻度严格一致
  - `human-judgement` TR-6.2：悬停 intra[i].time="11:10" 的数据点，视觉位置在 11:10 标签处（或接近，不再是 15:00 标签处）
- **Notes**: 如用户仍想显示 X 轴"空走到 15:00"，可在后阶段讨论；本修复目标解决错位，不再主动留白到收盘

## [x] Task 7: 涨跌双色进度条——斜杠加粗 + 红/绿段斜角（两端 45° 平行于斜杠）
- **Priority**: medium
- **Depends On**: None
- **Description**：
  - `static/style.css` `.dist-divider::before`：将 `width: 3px` 调整为 `width: 6px`，颜色 `#8a96b5` 不变；对应 `.dist-divider` 外层宽度由 8px 调至 12px，保持 margin: 0 1px（留白仍在左右）
  - `.dist-seg.up`（红段）：新增 `clip-path: polygon(0 0, 100% 0, calc(100% - 12px) 100%, 0 100%);` 实现右边沿 45° 斜角（角深 ≈12px，与斜杠的 skewX(-45deg) 视觉平行）
  - `.dist-seg.down`（绿段）：新增 `clip-path: polygon(12px 0, 100% 0, 100% 100%, 0 100%);` 实现左边沿 45° 斜角
  - 单边为 0 的场景：因仅当 up>0 && down>0 时才渲染斜杠（renderDistSummary 已保证），单边时 clip-path 仍存在但另一端斜角与进度条端点重合（红单边右上斜角贴到进度条末尾，视觉不破坏；如用户感觉单边 clip-path 不美观，可在 JS 中单边时给 `.dist-seg.up, .dist-seg.down` 加 `class="no-clip"` 去除 clip-path）
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-7.1：DevTools 检查 `.dist-divider::before` 宽度 ≥6px；`.dist-seg.up` computed clip-path 存在 polygon 且含 `calc(100% - 12px)`；`.dist-seg.down` clip-path 含 `12px`
  - `human-judgement` TR-7.2：肉眼观察斜杠加粗明显，红段右上角与绿段左下角各有与斜杠平行的 45° 斜切；层次对齐无明显毛边

## [x] Task 8: 顶部"刷新数据"按钮 DATA:-- 修复 + 休市自动刷新
- **Priority**: high
- **Depends On**: None
- **Description**：
  - **根因 A（DATA:--）**：`loadOverview()` 的 try 块内 `renderOverviewSentiment(o.sentiment, ...)` → `renderSentimentMini(s)` 若抛异常，catch 捕获后 `updateDataTime()` 永远不会执行 → `#data-time` 停留在 `DATA: --`。需将 `updateDataTime()` 从 try 块末尾移到 try 外部（或 finally），保证无论成功失败都更新时间。
  - **根因 B（休市不刷新）**：`startOvAutoRefresh()`（app.js L477-482）仅在 `isTradeSession()` 为 true 时启 fast=60s + slow=300s 双档；非交易时段仅 slow=600s（10 分钟）。用户明确要求"休市时也要触发自动刷新"。改为：非交易时段也启 fast=120s + slow=600s 双档（比交易时段慢一倍但仍有自动刷新），不再完全停 fast 档。
- **Acceptance Criteria Addressed**: AC-1 补充
- **Test Requirements**:
  - `programmatic` TR-8.1：在非交易时段（如周末/午间休市/盘后）访问概览页，120s 内 Network 出现 `/api/overview` 请求 ≥1 次
  - `programmatic` TR-8.2：点击"刷新数据"按钮后 `#data-time` 文本立即更新为 `DATA: YYYY-MM-DD 盘后 · 刷新于 HH:MM:SS`，不再停留 `DATA: --`
  - `programmatic` TR-8.3：即使 `/api/overview` 返回 500 或 JSON 解析失败，`updateDataTime()` 仍被执行（因为已移到 try 外部 / finally）
- **Notes**: `updateDataTime()` 移到 try 块之后（L97 之后、catch 之前不行，因为 catch 会跳过），最佳方案是移到 `loadOverview` 函数末尾 try/catch 之后独立调用，或在 finally 中调用

## [x] Task 9: 量能分时曲线末端 X 轴对齐修复（根因：后端补 15:00 点导致等距拉伸）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - **根因**：`core/market.py` L363-365 在 intraday 数组末尾强制补 `{time:"15:00", chg:last}`。当当前时间 11:10 时，intraday = [..., {time:"11:10"}, {time:"15:00"}]。ECharts category 轴等距排列，11:10 和 15:00 之间只差 1 个 category 间距（与 11:09→11:10 等宽），导致 11:10 的数据点视觉位置被拉到接近 15:00 标签处。
  - **修复方案**：`core/market.py` L363-365：删除"非交易时段补 15:00 点"的逻辑。仅在当前时间 ≥15:00（已收盘）时才补 15:00 点（此时 intraday 自然已含 15:00 附近的数据点）。盘中（9:30-15:00）不补 15:00，让曲线末端严格对齐最后一个真实数据点的时间。
  - 具体改法：将 `if intraday and intraday[-1]["time"] != "15:00":` 改为 `if intraday and intraday[-1]["time"] != "15:00" and now.hour * 60 + now.minute >= 900:`（仅在 15:00 后才补）
- **Acceptance Criteria Addressed**: AC-7 补充
- **Test Requirements**:
  - `programmatic` TR-9.1：盘中 11:10 时 `/api/liangneng` 返回的 intraday 数组最后一个 time 为 "11:10" 附近（不含 15:00），前端 X 轴 data 长度 = intraday.length，曲线末端严格对齐最后一个真实时间点
  - `programmatic` TR-9.2：收盘后（≥15:00）intraday 末尾含 "15:00" 点（后端仍会补），曲线自然延伸到收盘
- **Notes**: 不改前端 buildIntradayOption（Task 6 已删 max，前端已正确），仅改后端补点条件

## [x] Task 10: 近15日情绪图空图修复（根因：trade_date 格式不匹配 + 单点不可见）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - **根因 A（日期格式）**：`sentiment.get_sentiment()` 返回的 `trade_date` 是 "YYYYMMDD" 格式（如 "20260826"），但 `_enrich_sentiment`（app.py L93）直接用 `s.get("trade_date")` 作为 `today_date`，然后 `today_label = today_date[5:]` 得到 "826"（而非 "08-26"）。且与 trend 中 "2026-08-26" 格式的日期比较时永远不等，导致重复追加格式错误的点。
  - **根因 B（单点不可见）**：当 `emotion_history.get_emotion_trend(20)` 返回空且 `s.get("score")` 为 None 时，fallback 创建 1 个 score=50 的点 → ECharts line 图只有 1 个数据点时不画线只画点，视觉上几乎不可见。
  - **修复方案**：
    1. `app.py` `_enrich_sentiment`：在取 `today_date` 后做格式归一化：若长度 8 且无 `-`，则转为 `f"{td[:4]}-{td[4:6]}-{td[6:8]}"`；然后 `today_label = today_date[5:]` 正确得到 "MM-DD"。
    2. 当 trend 最终只有 1 条时，复制为 2 条相同值的点（让 ECharts 至少画出一条水平短线），或在前端 `renderSentimentMini` 中对 len==1 的场景特殊处理（补充一个虚点让线可见）。
- **Acceptance Criteria Addressed**: AC-6 补充
- **Test Requirements**:
  - `programmatic` TR-10.1：`python -c` 直调 `_enrich_sentiment({"trade_date":"20260826","score":35})`，返回 `history_labels` 中每个 label 格式为 "MM-DD"（如 "08-26"），不含 "826" 类残片
  - `programmatic` TR-10.2：当 `emotion_history.get_emotion_trend` 返回空时，`_enrich_sentiment` 返回 `history_scores.len >= 2`（至少 2 点让线可见），且 labels 与 scores 等长
  - `human-judgement` TR-10.3：浏览器中 sent-card 近15日情绪走势图肉眼可见折线（即使只有 1 天数据也至少有 1 条短水平线）

## [x] Task 11: 行业领涨领跌 Top10 为空修复
- **Priority**: high
- **Depends On**: None
- **Description**：
  - **根因**：`core/market.py` `get_boards()`（L138-166）请求新浪板块接口 `https://money.finance.sina.com.cn/q/view/newSinaHy.php`，若公司网络下该接口被反爬或返回非 JSON 格式，`re.search(r"=\s*(\{.*?\})\s*;?\s*$", r.text, re.S)` 匹配失败 → 返回空 → 前端显示"暂无行业板块数据"。
  - **修复方案**：
    1. 在 `get_boards()` 中为新浪接口加 try/except，失败时尝试东方财富板块接口作为备用源（如 `https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fields=f12,f14,f3&fs=m:90+t:2` 行业板块）。
    2. 东财返回 JSON，解析 `data.diff` 数组，每项 `{f12:代码, f14:名称, f3:涨跌幅}`，映射为 `{name, avg_pct, ...}` 结构。
    3. 两源均失败时返回 `{"industry": [], "concept": []}` 并不报错（前端已有空态处理）。
- **Acceptance Criteria Addressed**: AC-1 补充
- **Test Requirements**:
  - `programmatic` TR-11.1：`python -c "from core.market import get_boards; b=get_boards(); print(len(b['industry']))"` 返回 ≥1（至少有行业数据）
  - `programmatic` TR-11.2：`py_compile core/market.py` 通过
  - `human-judgement` TR-11.3：浏览器中"行业领涨领跌 Top10"两侧各有 ≤10 行数据条，不再显示"暂无行业板块数据"

## [x] Task 12: 黄金按交易时间实时刷新
- **Priority**: medium
- **Depends On**: None
- **Description**：
  - **根因**：当前 `isTradeSession()` 仅判断 A 股交易时段（9:30-11:30/13:00-15:00）。AU99.99 夜间交易 20:00-02:30 时 `isTradeSession()` 返回 false → `startOvAutoRefresh` 只启 slow=600s → 黄金每 10 分钟才刷新一次。伦敦金/纽约黄金各有自己的交易时间，需要按品种判断。
  - **修复方案**：
    1. `static/app.js` 新增 `isGoldTradeSession()` 函数：判断是否处于任一黄金品种交易时段内（AU99.99: 9:00-15:30 或 20:00-次日2:30；伦敦金: 周一至周五全球近 24 小时；纽约黄金: 夏令时 20:20-01:30 次日 / 冬令时 21:20-02:30 次日）。简化判断：非周末均视为黄金交易时段（伦敦金几乎 24 小时交易）。
    2. `startOvAutoRefresh` 中 slow 档调用 `loadGold(false)` 的频率不变（300s 交易 / 600s 非交易），但新增逻辑：若 `isGoldTradeSession()` 为 true 且当前非 A 股交易时段，仍启 fast=120s 档让黄金每 2 分钟刷新一次。
    3. `core/gold.py` `get_gold_spot` 中 SPOTS 第 2 项的展示名从 "COMEX黄金 GC" 改为 "纽约黄金"（用户说"没有纽约黄金"，实际是名称不直观）。
  - **约束**：不改变后端缓存 TTL（300s），仅改变前端调度频率；不修改新浪 hq 数据源。
- **Acceptance Criteria Addressed**: AC-1 补充
- **Test Requirements**:
  - `programmatic` TR-12.1：`app.js` 中存在 `isGoldTradeSession()` 函数，返回 boolean
  - `programmatic` TR-12.2：黄金 SPOTS 第 2 项 name 包含 "纽约黄金"（不再是 "COMEX黄金"）
  - `human-judgement` TR-12.3：非 A 股交易时段（如 20:00-23:00 AU99.99 夜盘）访问概览页，120s 内 `/api/gold` 出现 ≥1 次自动请求

## [x] Task 13: 黄金走势标题与 Y 轴字体重叠修复
- **Priority**: medium
- **Depends On**: None
- **Description**：
  - **根因**：`renderGoldHistory`（app.js L1934）的 ECharts `grid.top: 20` 太小，Y 轴 `name: '收盘价（美元/盎司）'` + `nameLocation: 'end'` 导致 name 文字出现在图表顶部边缘，与上方 `#gold-history-label`（.note margin-top:6px）的文本紧贴重叠。
  - **修复方案**：将 `grid.top` 从 `20` 改为 `35`（给 Y 轴 name 留出足够空间）。同时在 `#gold-history-label` 的 `.note` 样式上加 `margin-bottom: 4px`（在 style.css L73 `.note` 规则中追加），让标题和图表之间有间距。
- **Acceptance Criteria Addressed**: AC-5 补充
- **Test Requirements**:
  - `programmatic` TR-13.1：`renderGoldHistory` 生成的 option.grid.top ≥ 35
  - `human-judgement` TR-13.2：浏览器中"近30日 伦敦金近似走势..."标题文本与 Y 轴 "收盘价（美元/盎司）" 文字不再重叠，有明显间距

## [ ] Task 14: 修复 getTradeSession 缺少下午交易时段 + startOvAutoRefresh 移出 try 块
- **Priority**: high
- **Depends On**: None
- **Description**：
  - **核心根因 A（下午不刷新）**：`getTradeSession()`（app.js L33-45）仅覆盖 9:30-11:30（hm 570-690）的"持续交易"，缺少 13:00-14:57（hm 780-897）的下午交易时段判断。13:00-14:57 落入 `return "休市"` 兜底分支 → `isTradeSession()` 返回 false → `startOvAutoRefresh` 走 `else if (isGoldTradeSession())` 分支 → fast=120s 调 `doNonTradeFastRefresh`（只调 loadGold）→ 不调 loadOverview → updateDataTime 不更新 + 情绪图/行业 Top10 不刷新。
  - **根因 B（startOvAutoRefresh 在 try 块内）**：`startOvAutoRefresh()` 在 `loadOverview` 的 try 块内（L104），若 try 块内 fetch 失败或 renderOverviewSentiment/renderBoardsTop10 抛异常，catch 捕获后 startOvAutoRefresh 不执行 → 定时器不启动。
  - **修复 A**：`getTradeSession()` 在 `if (hm >= 690 && hm < 780) return "午间休市"` 之后、`if (hm >= 897 && hm < 900) return "收盘竞价"` 之前，增加 `if (hm >= 780 && hm < 897) return "持续交易";`。
  - **修复 B**：`loadOverview()` 将 `startOvAutoRefresh()` 从 try 块内（L104）移到 try/catch 之后（updateDataTime 旁边），保证 fetch 失败或渲染异常时定时器仍启动。
- **Acceptance Criteria Addressed**: AC-16
- **Test Requirements**:
  - `programmatic` TR-14.1：下午 13:00-14:57 期间 `getTradeSession()` 返回"持续交易"（非"休市"）；`isTradeSession()` 返回 true
  - `programmatic` TR-14.2：`startOvAutoRefresh()` 调用位于 try/catch 之后（grep 确认不在 try 块内）
  - `programmatic` TR-14.3：下午时段 65s 内 `#data-time` 相对时间重置为"刚刚刷新"（证明 doFastRefresh → loadOverview → updateDataTime 执行）

## [x] Task 15: 刷新时间改为相对时间"xx前刷新"
- **Priority**: medium
- **Depends On**: None
- **Description**：
  - **根因**：`updateDataTime()` 显示 `DATA: 2026-08-26 盘后 · 刷新于 13:36:42`，与 `#clock` 的 `2026-08-26 13:59:15` 并列，多个绝对时间让用户困惑。
  - **修复方案**：
    1. 新增全局变量 `let lastRefreshTs = 0;` 记录上次刷新时间戳。
    2. `updateDataTime()`：设置 `lastRefreshTs = Date.now()`，然后调用 `renderRefreshAgo()` 渲染相对时间。
    3. 新增 `renderRefreshAgo()` 函数：计算 `Date.now() - lastRefreshTs` 差值（毫秒），格式化为：
       - <5 秒："刚刚刷新"
       - <60 秒："xx秒前刷新"
       - <3600 秒："xx分xx秒前刷新"
       - ≥3600 秒："xx小时xx分xx秒前刷新"
       - lastRefreshTs==0 时："未刷新"
    4. `#data-time` 显示格式改为：`DATA: 盘中 · xx前刷新` 或 `DATA: 盘后 · xx前刷新`（tag 由 isTradeSession() 决定，去掉日期和绝对时间）。
    5. `tick()` 函数每秒调用 `renderRefreshAgo()`，让相对时间随时间累加更新。
- **Acceptance Criteria Addressed**: AC-17
- **Test Requirements**:
  - `programmatic` TR-15.1：`app.js` 存在 `lastRefreshTs` 全局变量和 `renderRefreshAgo()` 函数
  - `programmatic` TR-15.2：`updateDataTime()` 设置 `lastRefreshTs = Date.now()` 并调用 `renderRefreshAgo()`
  - `programmatic` TR-15.3：`tick()` 函数调用 `renderRefreshAgo()`
  - `human-judgement` TR-15.4：#data-time 显示"DATA: 盘后 · 刚刚刷新"，随后每秒累加为"xx秒前刷新"；不再显示日期和绝对时间

## [x] Task 16: 重启 Flask 服务验证后端改动生效
- **Priority**: high
- **Depends On**: Task 14, Task 15（前端改动需完成后一起验证）
- **Description**：
  - **根因**：Task 10（_enrich_sentiment 日期归一化 + 单点复制）和 Task 11（get_boards 东财备用源）的代码改动已写入文件，python -c 验证函数返回正确（scores=15、industry=49），但 Flask 服务未重启，运行中的进程仍是旧代码，/api/overview 返回旧数据（sentiment 无 history_scores、boards 为空）。
  - **修复方案**：
    1. 重启 Flask 服务（`python app.py`），确保最新后端代码加载。
    2. curl `/api/overview?force=1` 验证 `sentiment.history_scores` len ≥ 2 且 `boards.industry` len ≥ 1。
    3. 浏览器硬刷新（Ctrl+Shift+R）加载最新 app.js，验证情绪图渲染折线、行业 Top10 显示数据条。
- **Acceptance Criteria Addressed**: AC-18
- **Test Requirements**:
  - `programmatic` TR-16.1：Flask 服务重启后 `/api/overview?force=1` 返回 `sentiment.history_scores` len ≥ 2，`history_labels` 格式为 "MM-DD"
  - `programmatic` TR-16.2：`boards.industry` len ≥ 1
  - `human-judgement` TR-16.3：浏览器情绪图渲染折线（非空态），行业 Top10 两侧有数据条（非空态）

## [x] Task 17: 市场情绪近15日走势可靠渲染（多层兜底，彻底修复空图）
- **Priority**: high
- **Depends On**: None（独立，但与 Task 18/19 都改 app.js 或模板，建议串行避免冲突）
- **Description**：
  - **根因拆解（六层失败路径均兜底）**：
    ① **后端数据类型不确保数字**：`_enrich_sentiment` 的 `scores = [t.get("score", 50) for t in trend]` 中 `t.get("score")` 经 emotion_history JSON 反序列化可能是字符串，`str` 进 ECharts value y 轴不解析 → 折线不绘制。
    ② **前端 ECharts setOption 异常后空白兜底缺失**：renderSentimentMini 现有 try/catch 吞掉 setOption 异常后仅 console.warn，box.innerHTML 已被清空但 canvas 未生成 → 视觉为**纯空白**（比"暂无数据"更糟，用户说"没数据"）。
    ③ **_sentMiniRetry 跨次调用未重置**：连续两次 loadOverview（如手动刷新紧跟自动刷新）时，第一次 rAF 重试到 3 次后，第二次调用仍看到 _sentMiniRetry>=3 → 直接放弃不画。
    ④ **rAF 次数不足**：flex 布局有 transition 动画时 3 次 rAF 可能仍处于 0 尺寸。
    ⑤ **Tab 切换后 ResizeObserver/尺寸变更未触发重绘**：切到选股 Tab 再回概览，容器 display 由 none→block，但 ovSentMiniChart 已初始化不会自动 resize。
    ⑥ **浏览器缓存旧 app.js**：index.html 无版本号，用户本地缓存仍为旧代码，修复无效。
  - **修复方案**：
    **A. 后端（app.py _enrich_sentiment）**：
      - 构造 scores 时每个元素强制 `int()`：`scores = [int(t.get("score", 50) or 50) for t in trend]`；若 int() 抛异常（非数字字符串），fallback 到 50。
      - 在 `s["history_scores"] = scores` 之后、`return s` 之前再加一道**最终校验**：遍历 scores，任何非数字（或 <0 或 >100 超出区间）的项都修正为 50。
    **B. 前端（static/app.js renderSentimentMini）**：
      1. 调用入口 `_sentMiniRetry = 0`（每次调用先重置，确保不跨次）。
      2. scores 二次清洗：`scores = scores.map(v => { let n = Number(v); return (Number.isFinite(n) && n>=0 && n<=100) ? n : 50; })`。
      3. rAF 重试上限从 3 提升到 **6 次**；第 1/3/6 次加入**尺寸强制刷新**（`box.getBoundingClientRect()` 触发重排；如浏览器支持则 attach 一次性 `ResizeObserver(box)`，onResize 回调里 dispose+重新 init）。
      4. ECharts 失败 6 次后，**进入原生 HTML/SVG 降级渲染**（Fallback 组件，永不空白）：
         - 在 box 内插入一个 `<div class="sent-fallback">`，高度 280px，样式尽量接近 ECharts：
           * 背景：5 段冷暖渐变（与 ECharts splitArea 同色线性渐变，100% 高度）
           * Y 轴左侧刻度：冰点/过冷/微冷/微热/过热/沸点（同 yLabelMap，left 对齐，行高 = 280/5）
           * X 轴底部标签：labels 数组的 MM-DD（15 个均匀分布，rotate 30°）
           * 折线：`<svg width="100%" height="230">` + `<polyline>` 点坐标按 (i/(len-1)) * width，height 从 bottom 起算 (1 - score/100) * height；points 拼接；stroke=#4d7cff stroke-width=2.5 fill=none
           * 数据点 circle：每个 score 位置一个 6px 圆点，fill=#4d7cff stroke=#0d1526 stroke-width=1.5
         - 要求 Fallback DOM 一旦生成，下一次 renderSentimentMini 被调用时会先清空 Fallback DOM，再次尝试 ECharts（Fallback 是最后手段，不拦截下次正常 ECharts 流程）。
      5. **Tab 切换重建**：在 `startOvAutoRefresh` / Tab 切换 handler（概览→其他→概览）或全局 IntersectionObserver/Tab 切换回调中，当概览页变为可见时，`if (ovSentMiniChart) ovSentMiniChart.resize();`；若 Fallback DOM 存在则立即调用一次 `renderSentimentMini(s)`（s 从缓存获取，如 lnLatest 类似 sentLatest 全局存一份）。实现上最简单：在概览 Tab 的显示回调（或 startOvAutoRefresh 首次启动后）追加一句：`setTimeout(() => { if (ovSentMiniChart) ovSentMiniChart.resize(); }, 50);`（给 flex 布局时间）。
    **C. 缓存旁路（templates/index.html）**：
      - `index.html` 中 `static/app.js` 的 `<script src="static/app.js">` 改为加查询串：`<script src="static/app.js?v=20260826c"></script>`（版本号与修复批次绑定更新，确保任何浏览器绕过 HTTP 304/内存缓存）。静态 CSS 如 `static/style.css` 同样建议加 `?v=20260826c`。
- **Acceptance Criteria Addressed**: AC-19
- **Test Requirements**:
  - `programmatic` TR-17.1：`python -c` 直调 `_enrich_sentiment({"trade_date":"20260826","score":"35"})`（score 为字符串），返回 `history_scores[0]` 为 `int(35)`（类型为 int，非 str）。
  - `programmatic` TR-17.2：Grep renderSentimentMini 存在「原生 SVG polyline / sent-fallback」相关 DOM 构建代码（Fallback 兜底存在）；Grep 有 `_sentMiniRetry = 0` 重置语句（函数入口处）；rAF 重试上限条件为 `< 6`（非 3）。
  - `programmatic` TR-17.3：index.html 的 app.js script src 含 `?v=` 查询串。
  - `human-judgement` TR-17.4：浏览器实查——① 首次加载：#ov-sent-big 非空（有 canvas 或 svg/div Fallback 折线），绝不能出现"容器无任何 DOM 子节点"的纯空白；② 硬刷新 5 次（或隐私窗口）每次均可见折线；③ 切到选股 Tab → 再切回概览 Tab：情绪图仍可见（resize/Fallback 重建生效）。
- **Notes**：Fallback 视觉风格以"能看清 15 个数值点折线"为第一目标，不必追求与 ECharts 100% 一致。Fallback 仅在 ECharts 多次失败时出现，是极端场景兜底。

## [x] Task 18: 状态栏时间 #data-time 去掉前缀仅显示相对时间
- **Priority**: medium
- **Depends On**: None（独立，改 app.js 单行）
- **Description**：
  - **根因**：Task 15 简化为 `DATA: ${tag} · ${agoText}`，但用户要求"只显示 xx秒前刷新"。
  - **修复**：`static/app.js` 的 `renderRefreshAgo()` 函数（约 L79-103）最后一行写入：`if (el) el.textContent = agoText;`（原行为 `DATA: ${tag} · ${agoText}` 已不符合新需求，改为仅写 agoText）。agoText 的五档格式（未刷新/刚刚刷新/N秒/N分N秒/N小时N分N秒）保持不变，tick 每秒调用 renderRefreshAgo 保持累加逻辑不变。
- **Acceptance Criteria Addressed**: AC-20
- **Test Requirements**:
  - `programmatic` TR-18.1：Grep `el.textContent =` 在 renderRefreshAgo 函数内仅赋值 `agoText`，不得包含 "DATA" 字符串字面量；不得包含 `${tag}`。
  - `human-judgement` TR-18.2：浏览器读取 `#data-time.textContent` 为纯 "N秒前刷新"（或其它四档），文本中**不**含 "DATA"/"盘中"/"盘后"/"·"/日期/绝对时间。刷新后显示"刚刚刷新"，3 秒后变为 "3秒前刷新"。

## [x] Task 19: 市场量能分时曲线右侧留白实现"随时间右移"效果
- **Priority**: high
- **Depends On**: None（独立，改 app.js buildIntradayOption）
- **Description**：
  - **根因**：现有 `buildIntradayOption` 的 `xAxis.data = intra.map(x=>x.time)`，X 轴只包含"已有数据点的分钟"，因此 ECharts category 等距排列后，曲线占满整图宽度。
  - **修复（全部在前端 static/app.js buildIntradayOption）**：
    1. **生成完整交易分钟 xData**：用一段纯 JS 生成 242 项数组：
       - 上午段：从 m=9*60+30（570）到 m=11*60+30（690），共 121 个分钟，格式化为 `HH:MM`：`String(Math.floor(m/60)).padStart(2,'0') + ':' + String(m%60).padStart(2,'0')`
       - 下午段：从 m=13*60+0（780）到 m=15*60+0（900），共 121 个分钟
       - xData = [...上午段, ...下午段]，共 242
    2. **建立 chgMap**：`const chgMap = Object.fromEntries(intra.map(x => [x.time, x.chg]));`（注意 intra 的 time 也是 "HH:MM"）
    3. **改写 xAxis**：`data: xData`，其余 axisLine/axisLabel.interval 保留（因 242 项，idx%30===0 即每 30 分钟一标签，idx=241 对应 "15:00" 正好被 `val==="15:00"` 命中显示）。
    4. **改写 series.data**：`data: xData.map(t => (chgMap[t] != null ? Number(chgMap[t]) : null))`；chgMap[t] 可能是字符串时用 Number() 确保为数字。
    5. **改写 series 其余属性**：保留 `name: "预测量能"`, `type: "line"`, `symbol: "none"`；将 `smooth: true` 改为 `smooth: false`（分时图应尖锐折线，传统东方财富/同花顺分时图非平滑）；新增 `connectNulls: false`（午休不跨接，11:30→13:00 之间断开不连线）。
    6. **Tooltip 适配**：`formatter` 中对 null 返回空串。`if (p.value == null) return ""`。
    7. **空态处理**：`if (!intra.length) { ... }` 仍保持"暂无量能历史数据"占位（renderLiangneng 函数 L763-767），不因 xData 有 242 项就强行进入 buildIntradayOption（intra 空时 chgMap 为空，series 全 null，视觉上全空图不如占位文案明确）。故 renderLiangneng 中 `if (!intra.length)` 仍走空态 return。
- **Acceptance Criteria Addressed**: AC-21
- **Test Requirements**:
  - `programmatic` TR-19.1：Grep `buildIntradayOption`：函数内存在生成 242 项 xData 的代码（上午 570-690 + 下午 780-900）；存在 `xData.map(t => (chgMap[t] != null ? ... : null))` 映射；series 有 `connectNulls: false` 且 `smooth: false`。
  - `programmatic` TR-19.2：浏览器 DevTools 读取 `liangnengChart.getOption().xAxis[0].data.length === 242`；series[0].data 中所有非 null 的 dataIndex 最大位置对应的 X 值（时刻）≤ 当前系统时间 HH:MM。
  - `human-judgement` TR-19.3：视觉检查量能图——当前时刻若为上午，曲线只在左侧一段，右侧留白；若跨越午休，11:30 与 13:00 之间曲线断开不连线；15:00 刻度标签在 X 轴最右侧，已收盘时曲线延伸至此。

# 任务依赖关系
- Task 1（全卡调度）独立运行，不依赖其他 Task
- Task 2（去自选刷新）依赖 Task 1（自动刷新已就位后才可删手动按钮）
- Task 3（AU9999 来源）、Task 4（XAUUSD 历史）、Task 5（情绪空图）、Task 6（量能 X 轴）、Task 7（进度条斜角）互相独立，可并行
- Task 8-13 互相独立，可并行；Task 8 修改 startOvAutoRefresh 与 Task 12 有交集但改不同函数不同行，可并行
- Task 14（getTradeSession 修复）是核心根因修复，优先级最高；Task 15（相对时间）修改 updateDataTime/tick，与 Task 14 同文件 app.js 但不同函数，可并行
- Task 16（重启 Flask）依赖 Task 14/15 前端改动完成（需重启后浏览器加载新 app.js + 后端新代码一起验证）
- Task 17 是 Task 5/10 的加固升级（多一层数据类型 + 前端 SVG 兜底），改 app.py + app.js + index.html，**不依赖**其它未完成任务，独立实施
- Task 18 改 app.js 单行，可与 Task 17/19 串行实施（建议 Task 18 → Task 19 → Task 17，从简到难，便于分步验证）
- Task 19 改 app.js 的 buildIntradayOption，与 Task 17/18 改不同函数，可串行或与 Task 18 并行（同文件不同函数无冲突，但串行更稳妥避免误改重叠行）
- Task 17 改完后需要重启 Flask（后端 _enrich_sentiment 改动）+ 刷新模板缓存（index.html 加版本号）
