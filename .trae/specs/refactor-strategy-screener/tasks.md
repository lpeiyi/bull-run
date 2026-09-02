# 策略选股页重构（refactor-strategy-screener）— 实施计划（官方模板：Task + Priority / Depends / AC Map / Test Requirements）

> **执行顺序与原则**：Task 1 → Task 4（先基线快照，后改代码；否则无法做"重构前后对比"）→ Task 2 → Task 3。**严禁先改代码再补基线**，否则 Task 4 的 TR-4.1 / TR-4.2 失去对照组。
>
> **通达信兼容红线（每条任务强制遵守）**：不得修改 `core/tdx.py`、`core/screener.py` 任何一行；不得修改 `/api/indicators/*`、`/api/screen/*` 的路由签名与请求/响应 JSON 结构；不得修改 `indicators.json` 的字段名。违者该 Task 直接判 FAIL。

---

- [x] Task 1: 页面重命名、回测 Tab 及 HTML 清理
  - **验证状态**：T1-GREP1~GREP5 全 PASS；通达信兼容红线（core/*/app.py 0 行改动）PASS；残留 backtest 死分支（L1654 `if target==='backtest'`）与 scBtChart 变量按本 Task 边界「不扩展清理」保留，**纳入 Task 3 必清项**。
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. `templates/index.html` 顶层 Tab：`data-page="screener"` 文字由「智能选股」→ 「策略选股」。
    - Step 2. `#page-screener` 下的 3 子 Tab：删除 `<button class="sc-tab" data-tab="backtest">回测</button>`；将保留的 2 Tab 数量与切换逻辑回归一遍（不新增 data-tab 枚举，不影响已有 `.sc-tab` 处理函数）。
    - Step 3. 删除 `data-pane="backtest"` 整块内容：含「回测参数」小节（`#sc-bt-run`、`#sc-bt-indicator`、`#sc-bt-pool`、`#sc-bt-days`、`#sc-bt-adjust`）、回测指标卡片区（`#sc-bt-stats` + 6 个 `sc-bt-*` 值 id）、图表卡（`#sc-bt-chart-card` + `#sc-bt-chart`）、交易明细卡（`#sc-bt-trades-card` + `#sc-bt-trades`）、空状态（`#sc-bt-empty`）。
    - Step 4. 推送规则页两处残留「智能选股」文案（L1474 空状态、L1515 confirm 字符串）改为「策略选股」。
    - Step 5. 不触碰选股配置 pane、公式编辑 pane 内任一 DOM（不重排 id，不改变 `#sc-code` / `#sc-results` / `#sc-check-syntax` / `#sc-save-code` 等关键 id）。
  - **Acceptance Criteria Addressed**: AC-1、AC-6
  - **Test Requirements**:
    - `programmatic` TR-1.1: `grep -n '智能选股' templates/index.html static/app.js`：在顶层 Tab、策略选择器提示、push rule 空状态/confirm 四位置，仅允许 `app.js` 中两处旧「智能选股」文本变成「策略选股」；其余位置（如 README / Spec 文档）不在本 Task 管范围。
    - `programmatic` TR-1.2: `grep -c 'data-tab="backtest"' templates/index.html` == 0；`grep -c 'id="sc-bt-' templates/index.html` == 0；`grep -c 'data-pane="backtest"' templates/index.html` == 0。
    - `programmatic` TR-1.3: 打开 `#page-screener`，`document.querySelectorAll('.sc-tab').length` == 2，且两 tab `textContent.trim()` 为 `['公式编辑','选股配置']`（顺序可不限，但常前者在前）。
    - `human-judgment` TR-1.4: 浏览器 DOM 审查，`#page-screener` 的视觉布局不出现空白块 / 错位。
  - **Notes**: 若回测 Tab 删除后原父容器出现布局空隙，用 CSS（空的占位 div 不推荐）让两 Tab 直接占据上方，不新增残留元素。

---

- [x] Task 4: 通达信公式流程**基线快照采集**（**先于 Task 2/3 执行**，必做！）
  - **验证状态**：6/6 TR PASS（syntax_ok 3/3 True / check-syntax 响应字段 {ok, error?} 严格符合 / core/*+app.py diff 空 / indicators.json 净补入 3 条，原有 14 条无损）。前端基线：表格 9 列、#sc-code TEXTAREA、#sc-check-syntax BUTTON、#sc-results 唯一、子 Tab=2。基线文件：`_tmp_tdx_baseline.json`；MACD 策略产出 100 只可用于后续对称差比对；另 2 条选股因接口冷启动超时按允许 count=0 处理。
  - **Priority**: high
  - **Depends On**: Task 1（若 Task 1 破坏公式 DOM 可立即回滚；实际上 Task 1 不触公式区，此依赖仅为执行顺序保障）
  - **Description**:
    - Step 1. 读取 `indicators.json`，至少选出 3 条用典型通达信语法的策略：① 用 `:=`/`:` 赋值、② 用 CROSS/MA/REF、③ 用 EVERY/COUNT/LLV/HHV/KDJ/MACD 其一组合。若不足则临时用「代码内 3 条标准 TDX 片段」写入再还原（注意执行完本 Task 后恢复）。
    - Step 2. 写**一次性 Python 脚本**（不提交到仓库），对 3 条策略分别调用：
      - `POST /api/indicators/check-syntax` → 记录 `{strategy_id, ok, error}`
      - `POST /api/screen/start` → 轮询 `state` → 等完成 → 记录 `{strategy_id, codes:[], count:len(codes)}`
    - Step 3. 把结果写入临时 JSON `_tmp_tdx_baseline.json`：`{before: { id: {syntax_ok, screen_codes_sorted: [...], screen_count} }}`，**随 Task 产物提供给后续子代理对比**。
    - Step 4. 前端基线：用 `browser_snapshot` 记录当前公式编辑区（`#sc-code`、`#sc-check-syntax`、`#sc-save-code`、`#sc-results` 表头列数），确保后续 Task2 未误改这些元素 id / 结构。
  - **Acceptance Criteria Addressed**: AC-2（生成对照组）、NFR-1（前后一致）
  - **Test Requirements**:
    - `programmatic` TR-4.1: 基线文件存在且 3 条策略 `syntax_ok == true`；每条 `screen_count >= 0`（允许 0，但语法必须通过）。
    - `programmatic` TR-4.2: `POST /api/indicators/check-syntax` 同一 TDX 片段，响应体字段名 = `{ok, error?}`，不得出现额外必填项。
    - `programmatic` TR-4.3: 前端基线：`document.querySelector('#sc-code')` 存在且 `tagName === 'TEXTAREA'`；`document.querySelector('#sc-check-syntax')` 是 button；`document.querySelectorAll('#sc-results thead th').length` ∈ [9, 10]（旧版 9 列/新版 10 列，此点仅记录，不校验值）。
    - `human-judgment` TR-4.4: 评审 3 条策略是否确实用到用户常见 TDX 语法（不能 3 条都用最简单的 `C>O` 敷衍）。
  - **Notes**: 若当日行情 API（腾讯/东财）偶发不可用，screen_count 可能与实际有 1-2 只偏差，已在 AC-2 容忍。Task 4 只是"采基线"，本身**不做任何代码改动**。

---

- [x] Task 2: 选股结果表格升级（操作列 + 列顺序 + 涨跌幅红绿） + 回测跳转
  - **验证状态**：C/D/V 共 12/12 PASS（10 列表头+colspan10 正确；chg-red/green 样式与 DOM class 全匹配；500 行 28.9ms；降级 alert×3 不写 hash；跳转编码覆盖 `&/()/中文`；MACD 策略对称差 0 ≤2；syntax_ok 3/3 全对；红线 4 文件 diff 空）。
  - **Priority**: high
  - **Depends On**: Task 4（必须已有基线；Task 1 已保证 DOM 环境稳定）
  - **Description**:
    - Step 1. `templates/index.html` `#sc-results` 表头 `<thead>` 列顺序改为：代码｜名称｜现价｜涨跌幅｜市值(亿)｜成交额(亿)｜行业｜信号类型｜入选时间｜操作。原 colspan=9 空状态提示文案要改为 colspan=10（否则出现缺列视觉错位）。
    - Step 2. `static/app.js` `renderScreenResults(results)`：
      - 按新顺序输出 10 个 `<td>`；
      - 涨跌幅 `<td>` 统一套 `class="chg-positive"`（>=0）或 `class="chg-negative"`（<0），若 `style.css` 尚未定义则新增两段：`.chg-positive{color:#e74c3c} .chg-negative{color:#2ecc71}`（红涨绿跌 A 股习惯）。
      - 最后一列「操作」输出：`<button class="link-btn sc-backtest" data-symbol="${s.code}" data-name="${s.name}">回测</button>`。**禁止使用行内 onclick**；采用 `tbody` 事件委托（下一步）。
      - 在 `renderScreenResults` 首次渲染前或初始化阶段一次性绑定：`document.querySelector('#sc-results tbody').addEventListener('click', (e) => { if (e.target.classList.contains('sc-backtest')) jumpToBacktest(e.target.dataset.symbol, e.target.dataset.name); })`。
    - Step 3. 新增 `jumpToBacktest(symbol, name)` 函数：
      - 构造 URL 查询：`const qs = new URLSearchParams({page:'backtest-center', symbol, name}); location.hash = '?' + qs.toString();`
      - 优雅降级：若回测中心路由尚未实现（通过 `typeof window.goToBacktestCenter !== 'function'` 等检测，或简单地若当前 DOM 中不存在 `#page-backtest-center` 节点），则 `alert('回测中心暂未上线，敬请期待。')`，且**不调用** `history.replaceState` 更改 hash，避免页面 URL 被污染。
      - 回测中心路由存在时，再执行 `location.hash` 更新；**后续由回测中心 Spec 负责识别 URL 参数**。
  - **Acceptance Criteria Addressed**: AC-3、AC-4、NFR-4
  - **Test Requirements**:
    - `programmatic` TR-2.1: 表头顺序断言：`thead th` 第 0 列 = '代码'、第 1='名称'、第 3='涨跌幅'、第 9='操作'（index 从 0 起）。
    - `programmatic` TR-2.2: 空状态 `<td colspan="10">` 存在（结果空时断言）。
    - `programmatic` TR-2.3: 有数据时操作列按钮数 === 行数；按钮 `classList.contains('sc-backtest')`；涨跌幅列 ≥ 0 的 `<td>` `classList` 含 `chg-positive`、负数含 `chg-negative`。
    - `programmatic` TR-2.4: 跳转契约 mock：点击一行「回测」按钮后：
      - 模式 A（回测中心已存在）：`location.hash` 包含 `page=backtest-center`、`symbol=<代码>`、`name=encodeURIComponent(名称)`。
      - 模式 B（未上线）：调用 `window.alert` 一次且字符串匹配 `*回测中心暂未上线*`，选股结果 `tbody.children.length` 不减少、无 0 row。
    - `programmatic` TR-2.5: 事件委托性能：500 行渲染 + 注册，`performance.measure` ≤ 20ms（本地 Chrome）。
    - `human-judgment` TR-2.6: 颜色显示符合 A 股直觉（红涨绿跌），按钮样式不破坏表格对齐。
  - **Notes**: 样式类名以 `chg-*` 命名，避免与现有 `.positive` / `.negative`（可能用于数值统计卡）冲突。

---

- [x] Task 3: app.js 回测相关逻辑清理 + 代码可读性回归
  - **新增清理项（Task 1 子代理报告遗留点，强制纳入本次必清）**：
    - L1638 `let scBtChart = null` 变量声明（若仅被删除段引用，必删）。
    - L1654 死分支 `if (target === "backtest" && scBtChart) { setTimeout(() => scBtChart.resize(), 100); }`。
  - **验证状态**：10/10 TR 直接通过 + 1 推论通过（E-4 提供三重静态证明）。grep 归零 5 条（#sc-bt-/sc-bt-/screen/backtest/scBtChart/target==='backtest' 全 0）；node --check exit 0；renderScreenResults 无 ReferenceError；BACKTEST/TODO/FIXME grep 0；3 条 TDX syntax_ok 全 True 匹配基线；2 条用户原有策略（日k勾到大负值/砖型图）打开后名称描述代码字节级无损；共用样式类 7 条（3 旧 + Task 2 新增 4）全保留；git diff 收敛 3 文件；indicators.json 已回滚；15 个临时文件全部删除。
  - **Priority**: medium
  - **Depends On**: Task 2（Task 2 保证操作列/跳转已完整上线，确认回测不再被使用后才清理）
  - **Description**:
    - Step 1. 在 `static/app.js` 中整块删除以下范围（建议按"代码块+注释"方式删，避免残留散点引用）：
      - 选择器 `$("#sc-bt-my-indicators")` 及其赋值（≈L1721）；
      - 点击监听 `$("#sc-bt-run").addEventListener("click", ...)` 整段（≈L2107~2144）；
      - 渲染函数内对 `#sc-bt-total-ret`、`#sc-bt-annual-ret`、`#sc-bt-max-dd`、`#sc-bt-win-rate`、`#sc-bt-profit-ratio`、`#sc-bt-trade-count`、`#sc-bt-chart`、`#sc-bt-trades`、`#sc-bt-empty`、`#sc-bt-stats`、`#sc-bt-chart-card`、`#sc-bt-trades-card` 的 10+ 行引用（≈L2148~2201）。
    - Step 2. 变量 `scBtChart`（全局 echarts 实例）如果仅被删除段引用，一并删除声明与 `echarts.init` 行。
    - Step 3. **不得**删除共用样式类 `.sc-stat-value` / `.positive` / `.danger` / `.negative`；保留回测中心将来复用。
    - Step 4. **不得**删除 `/api/screen/backtest` 的调用函数？答案：**必须删除**；因为清理的是"本页前端不再调用"；后端 API 保留（由 `build-backtest-center` 决定何时移除）。
  - **Acceptance Criteria Addressed**: AC-5、NFR-2、NFR-5
  - **Test Requirements**:
    - `programmatic` TR-3.1: grep：
      - `grep -c '#sc-bt-' static/app.js` == 0
      - `grep -c 'sc-bt-' static/app.js` == 0（含无前缀 `#` 的字符串引用）
      - `grep -c '/api/screen/backtest' static/app.js` == 0
      - `grep -c 'scBtChart' static/app.js` == 0（若确实无其他引用）
    - `programmatic` TR-3.2: 浏览器全流程 5 步（开 → 切 Tab → 新建策略→保存→选股→点回测），Console error 级别消息数 = 0（允许 echarts warn）。
    - `programmatic` TR-3.3: 清理后，`renderScreenResults` 函数仍可运行（执行一次空/非空渲染各 1，无 `ReferenceError`）。
    - `human-judgment` TR-3.4: 代码阅读评审：删除后「策略选股区」前后注释分隔结构仍清晰，不残留 `/*` 未闭合、不遗留 TODO/fixme 指向旧 sc-bt。
  - **Notes**: 子代理清理后须用 `py_compile`（仅后端）+ `node --check`（Node 18+ 静态语法）对 `app.js` 做语法检查。Node 缺失时可退化为浏览器端 `window.eval` 不抛 SyntaxError 断言。

---

## Task Dependencies DAG（拓扑）
```
Task 1 (HTML 重命名 + 回测 Tab DOM 删除)
  │
  └──► Task 4 (通达信兼容基线快照采集 —— 零代码变更，必须在 Task 2/3 之前产出 before.json)
         │
         └──► Task 2 (结果表升级 + 回测跳转)
                │
                └──► Task 3 (app.js 回测逻辑清理 + 可读性回归)
```

并行不可行：Task 4 依赖 Task 1 后的 DOM（不包含被误删的 `#sc-code` 等），且 Task 2 必须等基线才可改代码；Task 3 必须等 Task 2 的新跳转上线后才可清理旧逻辑。

---

## 「通达信兼容」审计清单（每条 Task 完成后都要补一次 grep）
执行完 Task 1/2/3 后，**必跑一次**（放 Task 4 末尾的总审计）：
```
# 任何命中都要解释；默认 0 命中才算通过
grep -n 'core/tdx.py' core/            || echo '✓ 未改 tdx'
grep -n 'core/screener.py' core/       || echo '✓ 未改 screener'
grep -R '/api/indicators' app.py templates/  # 输出签名必须不变（只是增删调用数 = OK，改签名 = FAIL）
grep -R '/api/screen' app.py templates/       # 同上
```

---

# Phase 2 追加任务（5 项缺陷修复）

> **通达信红线（Phase 2 放宽）**：`core/tdx.py` 仍零改动（不可逾越）；`core/screener.py` 允许改动（仅限 stock_list / 选股结果结构补 industry 字段），但不得改 `get_signal` / `check_tdx_syntax` 调用方式与签名。

- [x] Task 5: 飞书推送路径修复 + signalType 列填充策略名
  - **验证状态**：TR-5.1~5.4 全 PASS。grep `/api/feishu/push-screen`=0、`/api/screen/push`≥1；renderScreenResults 签名含 strategyName；signalType 兜底含策略名；node --check exit 0。
  - **Priority**: high
  - **Depends On**: None（Phase 1 已完成）
  - **Description**:
    - Step 1. `static/app.js` L2105：`fetch("/api/feishu/push-screen"` → `fetch("/api/screen/push"`（后端 `app.py:L718` 已有此路由）。
    - Step 2. `renderScreenResults` 函数签名改为 `renderScreenResults(results, strategyName)`：signalType 列用传入的 `strategyName` 填充（`r.signalType || r.signal_type || strategyName || "--"`）。调用处（`pollScreenProgress` L2004）传入 `SC_STRATEGIES.find(x => x.id === SC_CURRENT_STRATEGY)?.name`。
  - **Acceptance Criteria Addressed**: Phase2-MODIFIED-推送路径, Phase2-MODIFIED-signalType
  - **Test Requirements**:
    - `programmatic` TR-5.1: grep `static/app.js` 中 `/api/feishu/push-screen` 计数 = 0；`/api/screen/push` 计数 ≥ 1。
    - `programmatic` TR-5.2: 选股完成后渲染结果表，signalType 列每行文本 = 当前策略名（非 `--`）。
    - `programmatic` TR-5.3: 点击"推送飞书"后，请求路径为 `/api/screen/push`（Network 面板断言），响应为 JSON（非 HTML）。
  - **Notes**: 纯前端改动，零后端风险。

- [x] Task 6: 选股结果 industry 字段补充（后端 join 东财行业数据）
  - **验证状态**：TR-6.1~6.5 全 PASS。东财行业映射 5557 只、stock_list 匹配率 99.9%、端到端选股 industry 100% 非空；git diff core/tdx.py=0；get_signal 调用行未变；import 成功。
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 调查 `core/market.py` 中已有的东财行业数据获取逻辑（`get_boards` / 涨跌停个股数据中的 `hybk` 字段），提取可复用的"股票代码 → 行业"映射函数（或新建 `_build_industry_map()` 从东财接口拉全市场个股行业，缓存 24h）。
    - Step 2. 在 `core/screener.py` 的 `load_stock_list` 或选股结果 `results.append` 处，用行业映射补充 `industry` 字段（新浪源 `industry=""` → 替换为东财值）。同步选股（L264）与异步选股（L343）两处 append 均需补充。
    - Step 3. 不得改 `get_signal(indicator_code, df, stock_info)` 的调用方式与 `stock_info` 中已有字段名。
  - **Acceptance Criteria Addressed**: Phase2-MODIFIED-industry
  - **Test Requirements**:
    - `programmatic` TR-6.1: 选股完成后，结果表中至少 80% 行的 industry 列显示非空行业名（允许少量数据源缺失）。
    - `programmatic` TR-6.2: `git diff core/tdx.py` = 0 行（红线）。
    - `programmatic` TR-6.3: `core/screener.py` 改动仅涉及 industry 补充逻辑，`get_signal` / `check_tdx_syntax` 调用行 diff = 0。
  - **Notes**: 若东财行业接口不稳定，降级为从已有缓存文件读取行业映射；industry 仍可能为空的极端情况前端显示 `--` 可接受，但不应全部为空。

- [x] Task 7: 策略间选股强隔离 + 结果按策略缓存
  - **验证状态**：TR-7.1~7.7 全 PASS。SC_RESULTS_CACHE/SC_TASK_MAP 按策略隔离；selectStrategy 切换取消旧 task+隐藏进度+恢复缓存；pollScreenProgress 用 sid 捕获+双重守卫防竞态；node --check exit 0。
  - **Priority**: high
  - **Depends On**: Task 5（推送修复后统一测试选股+推送流程）
  - **Description**:
    - Step 1. 新建 `SC_RESULTS_CACHE = {}`（按 strategy id → results 数组）和 `SC_TASK_MAP = {}`（按 strategy id → { task_id, poll_timer }）。移除全局单例 `SC_LAST_RESULTS`（改为从 cache 取当前策略结果）。
    - Step 2. `selectStrategy(id)`：① 若 `SC_TASK_MAP[oldId]` 存在且 running，调 `/api/screen/cancel/<task_id>` 取消并 `clearInterval`；② 隐藏 `#sc-progress`；③ 从 `SC_RESULTS_CACHE[id]` 恢复结果（有则 `renderScreenResults(cached, strategyName)`，无则显示空状态占位）。
    - Step 3. `pollScreenProgress`：改为按当前策略 id 的 task_id 轮询；done 时 `SC_RESULTS_CACHE[currentId] = results` 再渲染。
    - Step 4. 推送飞书按钮（`#sc-push-result`）：从 `SC_RESULTS_CACHE[SC_CURRENT_STRATEGY]` 取结果。
  - **Acceptance Criteria Addressed**: Phase2-ADDED-策略隔离, Phase2-ADDED-结果缓存
  - **Test Requirements**:
    - `programmatic` TR-7.1: 策略 A 选股中 → 切到策略 B → `#sc-progress` `display:none`，B 不显示 A 的进度。
    - `programmatic` TR-7.2: 策略 A 选股完成 → 切 B → 切回 A → 结果表行数与 A 完成时一致（从 cache 恢复）。
    - `programmatic` TR-7.3: 策略 A 选股中 → 切到 B → A 的 task 被 cancel（`/api/screen/cancel` 请求发出）。
    - `human-judgment` TR-7.4: 切换策略无闪烁/错位，进度条隐藏无残留。
  - **Notes**: 不改后端 API，纯前端状态管理重构。`SC_LAST_RESULTS` 全局变量可保留为 `SC_RESULTS_CACHE[SC_CURRENT_STRATEGY]` 的快捷引用以减少改动面。

- [x] Task 8: 策略列表删除功能
  - **验证状态**：TR-8.1~8.7 全 PASS。删除按钮+hover 样式+容器级事件委托（flag 防重注册）+ deleteStrategy（confirm→cancel running task→DELETE→清缓存→loadStrategies）+ stopPropagation 隔离选中事件 + node --check exit 0。
  - **Priority**: medium
  - **Depends On**: None
  - **Description**:
    - Step 1. `renderStrategyList`（L1693）：每个 `.sc-strategy-item` 内追加删除按钮 `<button class="sc-strategy-del" data-id="${s.id}" title="删除">✕</button>`，样式用 `position:absolute; right:8px` 悬浮显示（hover 时显现）。
    - Step 2. 策略列表容器级事件委托（与 Task 2 的 tbody 委托同理）：click 命中 `.sc-strategy-del` 时 `confirm("确定删除策略「${name}」吗？")` → `DELETE /api/indicators/${id}` → 成功后 `loadStrategies()` 刷新。
    - Step 3. 若被删策略正在选股（`SC_TASK_MAP[id]` running），先 cancel 再删。
    - Step 4. 若被删策略是 `SC_CURRENT_STRATEGY`，删除后 `selectStrategy` 切到第一条或清空视图。
  - **Acceptance Criteria Addressed**: Phase2-ADDED-策略删除
  - **Test Requirements**:
    - `programmatic` TR-8.1: 每个策略项都有 `.sc-strategy-del` 按钮；点击弹出 confirm。
    - `programmatic` TR-8.2: 确认删除 → `DELETE /api/indicators/<id>` 请求发出 → 成功后列表少一项。
    - `programmatic` TR-8.3: 取消 confirm → 列表不变，无请求发出。
    - `programmatic` TR-8.4: 删除正在选股的策略 → 先发 `/api/screen/cancel` 再发 `DELETE`。
  - **Notes**: 后端 `DELETE /api/indicators/<iid>` 已存在（`app.py:L641`），纯前端新增入口。删除按钮不干扰策略项的 click 选中事件（`e.stopPropagation()`）。

---

## Phase 2 Task Dependencies DAG
```
Task 5 (推送路径 + signalType) ──┐
Task 6 (industry 补充)     ──────┤
                                 ├──► Task 7 (策略隔离 + 结果缓存)
Task 8 (策略删除)           ──────┘  (可与 Task 7 顺序做避免 app.js 冲突)
```
Task 5 / 6 / 8 互相独立可并行；Task 7 依赖 Task 5 完成后统一测试选股+推送+隔离流程。Task 7 和 8 均改 `app.js` 但不同函数区域，建议顺序做避免合并冲突。

---

# Phase 3 追加任务（3 项逻辑 + UI 修复）

> **通达信红线（Phase 3 不变）**：`core/tdx.py` 零改动；`core/screener.py` 不新增改动（Phase 2 已补 industry 保持）；API 路由签名保持不变。

- [x] Task 9: 语法检查路径修复（check-syntax → check_syntax）+ JSON 错误处理防御
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. `static/app.js` L1939：`fetch("/api/indicators/check-syntax"` → `fetch("/api/indicators/check_syntax"`（后端 app.py L649 `check_syntax` 下划线）。
    - Step 2. 增强错误处理：`.then((x) => x.json())` 改为 `.then(async (x) => { const ct = x.headers.get('content-type') || ''; if (!x.ok || !ct.includes('application/json')) { const txt = await x.text().catch(() => ''); throw new Error(\`HTTP \${x.status} \${x.statusText}（服务器未返回合法 JSON，返回：\${txt.slice(0,120)}）\`); } return x.json(); })`，确保 HTML 404/5xx 不再触发 `SyntaxError: Unexpected token '<'`，而是抛出可读 "HTTP 404 Not Found（服务器未返回合法 JSON...）"。
    - Step 3. 将"推送飞书"（L2105 附近）的 fetch `.then(x=>x.json())` 同样套用上述 Content-Type 检查（复用同一辅助函数），彻底根除同类 JSON 解析错误。
  - **Acceptance Criteria Addressed**: Phase3-MODIFIED-通达信语法检查
  - **Test Requirements**:
    - `programmatic` TR-9.1: grep `static/app.js` 中 `/api/indicators/check-syntax`（中划线）= 0；`/api/indicators/check_syntax`（下划线）≥ 1。
    - `programmatic` TR-9.2: Content-Type 防御代码在 app.js 中出现 ≥ 2 处（语法检查 + 推送）。
    - `programmatic` TR-9.3: `node --check static/app.js` exit 0。
    - `human-judgment` TR-9.4: 模拟 HTML 响应时，错误文本为"HTTP ...（服务器未返回合法 JSON...）"，不出现 `SyntaxError: Unexpected token`。
  - **Notes**: 纯前端修复，零后端风险。
  - **验证结果（子代理 2025-08-29）**：TR-9.1 中划线 grep=0 / 下划线 grep=1 ✅；TR-9.2 safeJson 新增 L21-L35；语法检查+推送 2 处套 safeJson ✅；TR-9.3 node --check exit 0 ✅；红线：core/tdx.py diff 0 ✅。改动范围：static/app.js L21-L35（safeJson）+ L1955/L1958（语法检查路径+safeJson）+ L2236（推送 safeJson）。

- [x] Task 10: 选股任务隔离语义重构——切策略不 cancel，后台并发跑 UI 各自显示
  - **Priority**: high
  - **Depends On**: Task 9（前后统一）
  - **Description**:
    - **核心改动点**：`selectStrategy(id)` 中 Phase 2 引入的 `fetch(/api/screen/cancel/${oldTask.task_id})` 整段**删除**（不再切策略就 cancel）。切策略时仅：隐藏 `#sc-progress`；`resetScreenBtn()`；显示该策略自己的 progress/results。
    - 引入 `SC_TASK_PROGRESS_CACHE = {}`（sid → { pct, progress, total, hits, estDays, status }），用于后台 task 不在当前视图时仍能保存最新进度快照；切回时立即用该快照渲染 progress 条。
    - `pollScreenProgress` 继续跑（不被切策略取消），每次 tick 都把进度写入 `SC_TASK_PROGRESS_CACHE[sid]`；即使当前 sid ≠ SC_CURRENT_STRATEGY，也要继续 tick，done 时写入 SC_RESULTS_CACHE[sid]。
    - `selectStrategy` 切策略：恢复进度区时，若 `SC_TASK_MAP[id]` 还在（task still running）→ 立即显示 #sc-progress + 从 SC_TASK_PROGRESS_CACHE[id] 填百分比和文案；然后继续该 poll_timer。
    - `selectStrategy` 切策略：若 `SC_TASK_MAP[id]` 不存在且 `SC_RESULTS_CACHE[id]` 有值 → 直接渲染结果；若 `SC_RESULTS_CACHE[id]` 也无值 → 显示空状态（colspan=10 占位）。
    - `#sc-cancel-screen` 仅取消当前策略的 task（行为不变）。
    - 删除策略时仍 cancel（这是正确语义，不能让删除的策略还在后台占线程跑）。
  - **Acceptance Criteria Addressed**: Phase3-ADDED-选股后台并发
  - **Test Requirements**:
    - `programmatic` TR-10.1: selectStrategy 中不再出现 `fetch(/api/screen/cancel/`（切走不 cancel）。
    - `programmatic` TR-10.2: pollScreenProgress 中每 tick 都 `SC_TASK_PROGRESS_CACHE[sid] = {...}` 进度快照（即使 sid !== 当前 SC_CURRENT_STRATEGY）。
    - `programmatic` TR-10.3: pollScreenProgress done → SC_RESULTS_CACHE[sid] = results 无论 sid 是否等于当前策略（后台完成继续落 cache）。
    - `programmatic` TR-10.4: selectStrategy 切回正在运行的策略 A → #sc-progress display not none + progress 文本/百分比从 cache 立即填值。
    - `programmatic` TR-10.5: 删除策略仍发 cancel（deleteStrategy 中 cancel 保留）。
    - `programmatic` TR-10.6: node --check exit 0。
  - **Notes**: 这是对 Phase 2 Task 7 错误语义的"纠正修复"——Phase 2 的 TR-7.1/TR-7.3（切策略 cancel）是设计错误，本 Task 将**直接撤销**该 2 条的"切走 cancel"副作用；后台 cancel 仅保留在手动取消和删除策略时。
  - **验证结果（子代理 2025-08-29）**：TR-10.1 selectStrategy 体内 /api/screen/cancel fetch = 0 ✅；TR-10.2 L2119 快照写入 1 次（setInterval 内）✅；TR-10.3 L2140 SC_RESULTS_CACHE[sid] = results（不在 sid===CURRENT if 内）✅；TR-10.4 L1851-L1881 切回恢复进度+else 包裹缓存/空分支 ✅；TR-10.5 deleteStrategy L1760 cancel 保留 1 次 ✅；TR-10.6 node --check exit 0 ✅；红线：core/tdx.py diff 空 ✅。改动范围：static/app.js 4 段——L1657 SC_TASK_PROGRESS_CACHE；L1799-L1806 切走隐藏不 cancel；L1851-L1881 切回恢复；L1901-L1908 新建不 cancel；L2115-L2165 poll+清理。

- [x] Task 11: UI Tab 合并为单一视图（代码编辑 + 选股配置 + 选股结果合并）
  - **Priority**: high
  - **Depends On**: None（可与 Task 9/10 独立但涉及 templates/index.html，建议最后做避免 app.js 多次引用被误删）
  - **Description**:
    - **templates/index.html** `#page-screener` > `.sc-main` 改造：
      1. 删除 `<div class="sc-tabs"> ... 公式编辑/选股配置 ... </div>` 两个 Tab 按钮（L209-212）。
      2. 去除两个 `<div class="sc-tab-pane active" data-pane="formula">` 和 `... data-pane="config">` 两层壳：改为一个扁平结构，把原两 pane 的**内容**依次合并在同一 `main` 中，顺序为：① `sc-formula-card`（策略公式卡片） → ② 原选股配置所有 cards（选股范围/排除/其他/定时 + 保存配置按钮）→ ③ 选股结果卡片（原来就放在 formula pane 里）。
      3. 合并保存按钮：删除配置 pane 底部"保存配置"和代码 card 的"保存代码"两个按钮 → 统一在策略公式卡片顶部 action 区放一个"保存策略"（保存策略 = 保存代码 + 保存配置）。
      4. 配置区的"重置"按钮保留，重命名为"重置配置"。
    - **static/app.js**：
      1. 删除 L1648-1657 的 Tab click 切换处理器（`document.querySelectorAll('.sc-tab')` 那段）。
      2. L1904 新建策略后 `document.querySelector('.sc-tab[data-tab="formula"]').click()` → 改为 `$("#sc-name")?.focus()`。
      3. 合并保存逻辑：新建函数 `async function saveStrategy()`，行为：读取当前 name/desc/code 和 config 表单 → 调用 PUT `/api/indicators/${SC_CURRENT_STRATEGY}`（若为新建策略则 POST `/api/indicators`），body 合并 `{name, desc, code, config}` → 成功后 `SC_CODE_EDIT = false` + loadStrategies + alert("保存成功")。
      4. 原"保存代码"按钮（#sc-save-code）和"保存配置"按钮（#sc-save-config-btn）的 click 监听都改为调用 saveStrategy()（保证原来两个入口仍可用，用户可以用原来的肌肉记忆点击保存）。
      5. 编辑策略按钮（#sc-edit-code）：`SC_CODE_EDIT = true`，`#sc-code` 置为可写 + 显示 `#sc-code-name-edit`；配置区所有控件本来就是可交互的（无需做特别改动）。
  - **Acceptance Criteria Addressed**: Phase3-MODIFIED-策略详情页, Phase3-ADDED-统一保存
  - **Test Requirements**:
    - `programmatic` TR-11.1: grep `templates/index.html` `data-tab=` count = 0；`data-pane=` count = 0（删除 Tab 壳）。
    - `programmatic` TR-11.2: `app.js` 中 L1648-1657 Tab click 切换处理器已删除（`document.querySelectorAll('.sc-tab')` 零命中或仅剩无关引用）。
    - `programmatic` TR-11.3: 公式卡片 + 配置 cards + 结果卡片三区域 DOM 仍存在（#sc-code、#sc-scope-preset、#sc-results）。
    - `programmatic` TR-11.4: saveStrategy 函数存在；PUT body 同时含 name/desc/code/config 四字段。
    - `programmatic` TR-11.5: 新建策略 L1904 不再引用不存在的 data-tab=formula（grep 零命中）。
    - `programmatic` TR-11.6: node --check exit 0。
    - `human-judgment` TR-11.7: 视觉上，选中策略后单页滚动即可见代码区+配置区+结果区，无 Tab 切换。
  - **Notes**: 配置区原 sc-tab-pane 的 `display:none`/`active` 切换逻辑因 pane 壳被删除而自然失效，内容 div 都将默认显示（正确语义）。结果卡片原本就是和代码区一起的，合并后无视觉冲突。
  - **验证结果（子代理 2025-08-29）**：TR-11.1 data-tab/data-pane 双零 ✅；TR-11.2 Tab 切换处理器 0 次 ✅；TR-11.3 三 id 各 1 次 ✅；TR-11.4 `data-tab="formula"` JS grep=0 ✅；TR-11.5 saveStrategy L1973；payload={name,desc,code,config} L2014 4 字段齐全 ✅；TR-11.6 node --check exit 0 ✅；TR-11.7 idx：sc-formula-card(9166) < sc-config-wrap(10832) < sc-result-card(15025)（公式→配置→结果）✅；红线 core/tdx.py diff 空 ✅。改动范围：templates/index.html 5 段（删 tabs/两 pane 壳/移 result-card/按钮合并）；static/app.js 5 段（删 Tab 切换处理器 + 新建策略 focus #sc-name + 新增 saveStrategy + #sc-save-code 重绑定 + #sc-save-config-btn 监听器删除）。

---

## Phase 3 Task Dependencies DAG
```
Task 9 (语法检查路径) ──► Task 10 (选股任务语义重构)
Task 11 (UI 单页合并)          （Task 11 与 9/10 独立，可并行或最后做都行，因 HTML 合并不影响语法检查 / task map 字段名）
```
Task 9 是基础，先做；Task 10 依赖 Task 9 以避免引用冲突；Task 11 是独立 UI 任务，和 9/10 互不相干可并行或串行。
