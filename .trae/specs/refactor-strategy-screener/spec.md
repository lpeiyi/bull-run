# 策略选股页重构（refactor-strategy-screener）— Product Requirement Document

## Overview
- **Summary**：将现有「智能选股」页（公式编辑 / 选股配置 / 回测三合一 Tab）**只**做 UI 层面的职责切分与跳转重构：页面重命名为「策略选股」，删除嵌入本页的回测 Tab；选股结果表格新增「回测」按钮，作为与独立「回测中心」页的唯一入口。整个重构过程 **不触碰通达信公式解释器与选股执行引擎**（`core/tdx.py` / `core/screener.py` / 对应 API `/api/indicators/*`、`/api/screen/*`），以保证通达信语法兼容为不可逾越的基线。
- **Purpose**：解决「回测功能与选股耦合在同一页面导致职责不清晰、回测形态升级到 Python 代码模式后无法容纳」的结构问题；为并行 Spec `build-backtest-center`（升级为 Python 代码模式独立回测中心）铺好跳转链路，同时把本页**锁定为通达信公式选股**的纯策略容器。
- **Target Users**：A 股中短线交易者：在本页用通达信公式快速选股 → 对命中个股一键送入回测中心做深度买卖策略收益验证。

## Goals
- **G-1 通达信兼容基线零降级**：本页通达信公式编辑、语法检查、保存、选股、回测跳转 5 大步骤的**行为与本次重构前一致**；任何用户已保存的通达信策略在 `indicators.json` 中保持可读、可编辑、可执行、可选股。
- **G-2 职责清晰**：本页只承载「通达信公式选股」能力，原嵌入 Tab 回测能力不再出现在本页。
- **G-3 与回测中心打通**：选股结果每行一个「回测」入口，点击后在回测中心页自动填入该股代码/名称，形成「选股 → 个股深度回测」的最短路径。
- **G-4 交付风险可控**：重构仅涉及 `index.html` 的 Tab/表格结构、`app.js` 的结果表格渲染与事件绑定；**不改动数据模型（indicators.json / config.json）、不增删任何后端 API、不调整 `core/tdx.py`、`core/screener.py` 一行执行逻辑**。

## Non-Goals (Out of Scope)
- **NG-1 公式语法/函数集升级**：不修改通达信解释器，不新增任何 TDX 语法扩展（如 `STICKLINE`、`DRAWICON`、`FOR`/`WHILE` 等）。
- **NG-2 选股引擎改造**：不调整选股范围、排除条件、定时推送逻辑（保留现有推送规则 Tab 与 `core/rules.py`）。
- **NG-3 回测能力实现**：不重建回测 UI、不实现 Python 代码模式回测、不实现回测方案存储；以上全部由 `build-backtest-center` Spec 负责。
- **NG-4 顶部导航栏改版**：本 Spec **不引入**「一级导航栏 / 5 Tab 改为 2 Tab」等全局性导航变化；仍沿用现有 3 顶层 Tab（市场概览 / 策略选股 / 推送规则）。`build-backtest-center` Spec 如需改导航，由其独立评估并在其 Task 中统一变更，避免两个 Spec 交叉破坏。
- **NG-5 样式体系重写**：不新增设计系统、不调整配色主题；涨跌幅红绿配色（A股习惯）为唯一样式变更点。

## Background & Context
### 现状（改动前）
- 顶层导航：`市场概览 / 智能选股 / 推送规则` 3 Tab（`index.html` L13-15）。
- 「智能选股」`#page-screener` 内有 3 个子 Tab：公式编辑 / 选股配置 / 回测（`index.html` L189-L474）。
- 公式编辑：纯文本 `#sc-code` 编辑框 + 语法检查按钮（调用 `POST /api/indicators/check-syntax`，后端走 `core/tdx.check_tdx_syntax`）+ 保存策略（`PUT /api/indicators/<id>`，持久化到 `indicators.json`）。
- 选股：`POST /api/screen/start` 后端 `core/screener.py` 调用 `core/tdx.get_signal` 逐只命中。
- 原回测 Tab：`#sc-bt-*` 系列 DOM（参数/指标卡片/收益曲线/交易明细/空状态）+ `POST /api/screen/backtest` 走 `core/backtest.py` 内置 5 指标可视化回测。

### 基线约束（所有任务必须遵守）
- 「**通达信公式兼容**」是本重构不可触碰的第一优先级：凡涉及公式编辑、语法检查、保存、选股执行的路径，不得出现新的字段要求、不得改变 `parse_tdx`/`evaluate_tdx` 的入参/出参形态、不得把 `indicators.json` 中既有策略的 `code` 字段改为任何其它格式。
- 后端 API 集合 `GET/PUT/POST /api/indicators/*`、`POST /api/screen/start`、`GET /api/screen/state/:id`、`POST /api/screen/cancel/:id`、`GET /api/indicators/check-syntax` 必须签名不变、行为不变。
- 前端 `SC_STRATEGIES` 数据结构、`SC_CURRENT_STRATEGY` 状态机、`renderScreenResults` 渲染器中通达信策略 `name`/`code`/`id` 字段不得改名。

### 姊妹 Spec 依赖
- 与 `build-backtest-center`（独立回测中心）的松耦合契约只通过 **URL 查询参数** 表达：本页「回测」按钮打开 `#?page=backtest-center&symbol=<code>&name=<name>`。回测中心页初始化时读取参数；若回测中心尚未上线，则优雅降级为 `alert('回测中心暂未上线，敬请期待。')`，本页其它行为不受影响。
- 这一「URL 参数 + 优雅降级」契约保证两个 Spec 可独立推进、可独立回滚，不形成双向硬依赖。

## Functional Requirements
- **FR-1（页面重命名 + 回测 Tab 移除）**：顶层 Tab「智能选股」改文字为「策略选股」；`#page-screener` 主工作区的子 Tab 从「公式编辑 / 选股配置 / 回测」减为「公式编辑 / 选股配置」；与回测子 Tab 绑定的 DOM（`data-tab="backtest"` 按钮、`data-pane="backtest"` 面板、所有 `id="sc-bt-*"` 元素）从 HTML 中整体移除。
- **FR-2（通达信公式流程零降级）**：公式编辑、语法检查、策略保存/重命名、策略删除、选股启动/取消/状态轮询、选股结果渲染、定时选股推送配置，八类操作的 DOM id 与 API 调用签名保持不变。
- **FR-3（选股结果表格升级）**：选股结果表列顺序调整为「代码、名称、现价、涨跌幅、市值(亿)、成交额(亿)、行业、信号类型、入选时间、操作」；最后一列的每行提供文字按钮「回测」；涨跌幅列按 A 股习惯（正红负绿）着色；行业/信号类型/入选时间三列对齐与排序视觉一致（统一左对齐/右对齐规范，按表头切换排序）。
- **FR-4（回测跳转契约）**：点击「回测」按钮时，构造 URL `#?page=backtest-center&symbol=<代码>&name=<encodeURIComponent(名称)>` 并切换页面；若回测中心尚未提供路由，则弹出提示（优雅降级），不影响当前选股结果表格和页面状态。
- **FR-5（残留清理）**：`static/app.js` 中 `#sc-bt-*` 相关事件绑定、回测执行与渲染函数（`"#sc-bt-run"` 监听、sc-bt-chart/sc-bt-trades/sc-bt-stats DOM 引用）统一移除；保留的共用样式类 `sc-stat-value` / `positive` / `negative` 不删，供未来回测中心复用。

## Non-Functional Requirements
- **NFR-1（兼容基线）**：任意 3 条现存 `indicators.json` 策略，在重构前后分别执行「语法检查 → 保存 → 选股」三步骤，返回结果 **逐字字节一致**（若后端命中集随机顺序，至少集合相等 + 命中数量一致）。`programmatic` 可测。
- **NFR-2（零控制台错误）**：本页 5 大操作（打开页 → 切 Tab → 保存策略 → 执行选股 → 点击「回测」）过程中，Console `error` 级别消息为 0；`warning` 允许现有的 `echarts` 重绘提示，不允许新增。
- **NFR-3（可回滚）**：本次所有改动文件集合 = `templates/index.html` + `static/app.js`（可选更新 `static/style.css` 的涨跌幅类，若不存在则补齐）；不新增任何文件；回滚 = 三文件 git checkout。
- **NFR-4（性能无感）**：选股结果 500 行以内，「操作列」渲染 + 跳转按钮事件委托总耗时 ≤ 20ms（事件委托使用 `tbody` 级 click 监听，不每行绑定）。
- **NFR-5（代码可读性）**：`app.js` 删除回测逻辑后，「策略选股 / 市场概览 / 推送规则」三块分区仍保留清晰分隔注释与文件内行号稳定。`human-judgment`。

## Constraints
- **Technical**：Python 3 + Flask 2.x 后端；单页应用结构 `templates/index.html`；原生 JS（无 Vue/React 框架）；图表库 echarts 5.x；通达信解释器 `core/tdx.py`（不可改）。
- **Business**：不触碰用户已有 `indicators.json` 策略；不破坏推送规则中对智能选股指标的引用（`renderScreenRules` 文本中「智能选股」需同步改为「策略选股」以匹配命名）。
- **Dependencies**：依赖姊妹 Spec `build-backtest-center` 的 URL 参数契约（但通过优雅降级解耦）；不依赖新 CDN 资源 / 不新增 npm 包。

## Assumptions
- A1：「回测中心」上线后会识别 URL 参数 `page=backtest-center&symbol&name` 并做回填；若其路由命名不同，只需要在跳转函数里替换常量字符串即可，不用回改本 Spec 其它任务。
- A2：当前 `build-backtest-center` Spec 中「顶部导航栏从 5 Tab 改为 2 入口」与当前代码现状（3 Tab）不一致，假设该点由 `build-backtest-center` 独立重审并在其 Tasks 中处理，本 Spec **不做任何导航变更**。
- A3：通达信公式解释器现有 `code` 字段语法（`:=` 中间变量、`:` 输出变量、AND/OR/NOT、大括号注释、指标属性访问如 `KDJ.J`）已经足够覆盖用户存量策略；本 Spec 不引入任何语法扩展。
- A4：原 `/api/screen/backtest` 后端 API 保留（不动），但本页前端不再调用；若 `build-backtest-center` 需要不同的 Python 代码模式回测 API，由其独立新增，不影响本 Spec。

## Acceptance Criteria

### AC-1：页面重命名与结构清理
- **Given**：用户未登录且打开首页 / 刷新
- **When**：查看顶层导航与策略选股子 Tab
- **Then**：顶层 Tab 文字是「策略选股」；子 Tab 仅存「公式编辑」「选股配置」两项；任何包含「回测」文字的子 Tab 按钮与面板不存在
- **Verification**：`programmatic`（`document.querySelectorAll('.tab,.sc-tab')` 的 `textContent` 断言 + grep HTML 无 `data-tab="backtest"`）
- **Notes**：页面标题、其他地方残留的「智能选股」文案（推送规则页的两处提示文字 L1474/L1515）也需同步改「策略选股」，保证命名一致。

### AC-2：通达信公式流程零降级
- **Given**：`indicators.json` 中至少存在 3 条用户策略（MA 金叉、MACD、KDJ 等典型通达信写法），每条策略 `code` 使用 `:=` 赋值、`:` 输出、MA/REF/CROSS/LLV/HHV/EVERY 至少一种组合
- **When**：分别在重构前后对三条策略执行「语法检查 → 保存 → 全市场默认范围选股」
- **Then**：语法检查返回 `ok=true` 一致；保存成功；选股命中集 **集合相等**（股票代码集合，顺序允许不同），数量差 ≤ 1
- **Verification**：`programmatic`（脚本化：调用 `/api/indicators/check-syntax`、`/api/screen/start` → state → 结果数组；前后两版本结果断言）
- **Notes**：若同一交易日数据被东财/腾讯刷新造成微小差异，以「命中代码集合对称差 ≤ 2 只」为容忍区间。

### AC-3：结果表格列顺序与涨跌幅配色
- **Given**：任意一次选股返回 ≥ 10 条结果
- **When**：渲染表格并抽查前 10 行
- **Then**：表头顺序为「代码 | 名称 | 现价 | 涨跌幅 | 市值(亿) | 成交额(亿) | 行业 | 信号类型 | 入选时间 | 操作」；涨跌幅列中 ≥ 0 的值为红色系、< 0 为绿色系；最后一列的每个单元格都有可点击的「回测」文字按钮
- **Verification**：`programmatic`（`document.querySelectorAll('#sc-results thead th').map(t=>t.textContent.trim())` 顺序断言 + 涨跌幅 `<td>` 的 class/style 正则匹配 + `操作列按钮数 == 行数`）

### AC-4：回测跳转契约生效与优雅降级
- **Given**：用户在结果表第 k 行（标的 `510300 沪深300ETF 华泰柏瑞`）点击「回测」按钮
- **When**：① 回测中心页存在；② 回测中心页不存在（未实现）
- **Then**：
  1. 存在 → URL hash 更新为 `#?page=backtest-center&symbol=510300&name=%E6%B2%AA%E6%B7%B1300ETF%E5%8D%8E%E6%B3%B0%E6%9F%8F%E7%91%9E` 或等价编码，回测中心的「回测标的」输入框自动显示该代码+名称
  2. 不存在 → 页面顶部/对话框弹出「回测中心暂未上线，敬请期待。」提示；选股结果不被清空、Console 0 error
- **Verification**：`programmatic`（hash 变更断言 + DOM 回填值断言 + 降级模式 alert mock 捕获）

### AC-5：残留清理与无控制台错误
- **Given**：策略选股页完成所有操作后
- **When**：grep `static/app.js` 与 `templates/index.html` 关键字 + 控制台检查
- **Then**：
  - `app.js` 不再引用任何 `#sc-bt-*` 选择器、不再监听 `"#sc-bt-run"`、不再调用 `/api/screen/backtest`
  - HTML 不再有任何 `id="sc-bt-*"` / `data-tab="backtest"` / `data-pane="backtest"` 节点
  - 打开策略选股页 + 新建策略 + 保存 + 选股 + 点击「回测」五步，Console error 为 0
- **Verification**：`programmatic`（grep 三关键字计数为 0 + `browser_console_messages` 过滤 error 级别为 0）

### AC-6：推送规则页命名一致性
- **Given**：推送规则 Tab 中「暂无选股推送」空状态提示与关闭选股推送的 `confirm` 文本
- **When**：查看两处文字（`app.js` L1474 空状态、L1515 confirm 文案）
- **Then**：文案改为「策略选股」，不再出现「智能选股」字样
- **Verification**：`programmatic`（grep 两字符串：「智能选股」在推送规则相关段落零命中）

### AC-7：用户体验「零意外」
- **Given**：老用户首次打开重构后页面
- **When**：按已有习惯（切策略选股 → 选公式 → 开始选股 → 看结果）操作
- **Then**：除了「不见了回测 Tab、多出操作列」这两个预期变化外，不出现任何其它位置/状态/默认值的变化（如默认选中 Tab 仍是公式编辑、选股配置默认值不变、选股进度条样式不变）
- **Verification**：`human-judgment`（评审走查）

## Open Questions
- [ ] 回测中心最终的路由名是否确实是 `page=backtest-center`？若其独立 Spec 最终决定不同名字（如 `hash='#backtest'`），本 Spec 可在 Task 2.3 里替换一个常量字符串，不需要重审其它章节。
- [ ] 是否需要把「通达信公式语法检查通过后自动保存」做快捷键（如 Ctrl+Enter）？若需要，超出当前「只做 UI 切分 + 兼容」的范围，应作为后续 Spec 新增。
- [ ] 原 `/api/screen/backtest` 是否需要在本 Spec 中 deprecate？决定：**保留不删**，作为可视化回测的 legacy 入口，让 build-backtest-center 自行决定何时移除。

---

# 策略选股页重构 — Phase 2 追加优化（5 项缺陷修复）

## Why
Phase 1 上线后用户反馈 5 个实际问题：
1. **飞书推送报错**：`SyntaxError: Unexpected token '<', "<!doctype"... is not valid JSON` — 前端调用 `/api/feishu/push-screen`，但后端路由实为 `/api/screen/push`，404 返回 HTML。
2. **行业/信号类型恒为 `--`**：新浪数据源 `industry=""` 恒空；选股结果中无 `signalType` 字段。
3. **策略间未隔离**：`SC_TASK_ID` / `#sc-progress` 全局单例，切策略后进度条仍显示他人选股状态。
4. **切换策略结果丢失**：`SC_LAST_RESULTS` 全局单例，`selectStrategy` 清空结果区。
5. **策略重复且无法删除**：前端 `renderStrategyList` 无删除按钮，后端 `DELETE /api/indicators/<id>` 已存在但未被调用。

## What Changes
- **MODIFIED** 飞书推送 API 路径：前端 `/api/feishu/push-screen` → `/api/screen/push`（后端 `app.py:L718` 已有路由）
- **MODIFIED** signalType 列：用当前策略名填充（选股结果即该策略命中，"信号类型" = 策略信号名）
- **MODIFIED** industry 列：后端 `core/screener.py` 选股结果补充 industry 字段（利用 `core/market.py` 东财行业数据 join）
- **ADDED** 策略间选股强隔离：`selectStrategy` 切换时取消当前选股任务 + 隐藏进度条
- **ADDED** 选股结果按策略缓存：`SC_RESULTS_CACHE` Map 按 id 缓存，切换策略恢复上次结果
- **ADDED** 策略删除功能：策略列表每项加删除按钮，调 `DELETE /api/indicators/<id>`

## Impact
- **Affected code**: `static/app.js`（推送路径 / 策略隔离 / 结果缓存 / 删除按钮 / signal 填充）、`core/screener.py`（industry 补充，不改 tdx 调用）
- **通达信红线不变**：`core/tdx.py` 零改动；`/api/indicators/check-syntax`、`/api/screen/start` 签名不变；`indicators.json` 的 id/name/code/desc 字段不变
- **Phase 1 约束放宽**：`core/screener.py` 允许改动（仅限 stock_list / 选股结果结构补 industry 字段），但不得改 `get_signal` / `check_tdx_syntax` 调用方式

## ADDED Requirements

### Requirement: 策略间选股状态强隔离
每个策略的选股任务、进度、结果互相独立。

#### Scenario: 切换策略时隐藏他人进度
- **WHEN** 策略 A 正在选股（进度条显示"已扫描 N 只"），用户点击策略 B
- **THEN** 进度条隐藏，策略 B 不显示策略 A 的选股中状态；策略 B 显示自己的结果或空状态

#### Scenario: 每策略独立结果保留
- **WHEN** 策略 A 选股完成显示结果，用户切到策略 B 再切回 A
- **THEN** 策略 A 的上次选股结果仍完整显示（从缓存恢复），不被清空

### Requirement: 策略删除
策略列表每项提供删除按钮，删除前需二次确认。

#### Scenario: 删除策略
- **WHEN** 用户点击某策略的删除按钮并确认
- **THEN** 调用 `DELETE /api/indicators/<id>`，成功后从列表移除；若该策略正在选股先取消任务

#### Scenario: 阻止误删
- **WHEN** 用户点击删除但取消确认
- **THEN** 不执行删除，列表不变

## MODIFIED Requirements

### Requirement: 飞书推送选股结果
推送路径修正为后端实际路由。

#### Scenario: 推送成功
- **WHEN** 选股完成后点击"推送飞书"
- **THEN** 请求 `POST /api/screen/push`，成功弹"推送成功"，失败弹后端 error 信息（不再 JSON 解析错误）

### Requirement: 选股结果行业与信号类型显示
industry 列显示实际行业，signalType 列显示当前策略名。

#### Scenario: 行业有值
- **WHEN** 选股结果渲染且东财行业数据可用
- **THEN** industry 列显示行业名称（非 `--`）

#### Scenario: 信号类型有值
- **WHEN** 选股结果渲染
- **THEN** signalType 列显示当前策略名（非 `--`）

---

# 策略选股页重构 — Phase 3 追加优化（3 项逻辑+UI 修复）

## Why
Phase 2 上线后暴露 3 个更严重的问题：
1. **语法检查 JSON 解析失败**：前端 `L1939 fetch("/api/indicators/check-syntax"` 用中划线，后端路由 `@app.route("/api/indicators/check_syntax")` 用下划线不匹配，404 返回 HTML → `SyntaxError: Unexpected token '<'`。
2. **立即选股 cancel 逻辑**：Phase 2 Task 7 按"切策略即 cancel 旧任务"实现，但用户真实需求是"切走时后台继续跑，切回来还能看到运行中的进度或完成后的结果"；当前实现导致"切走 → 取消 → 切回看到已取消"，用户称为"很严重的逻辑和功能问题"。
3. **UI 拆分不合理**：公式编辑和选股配置是同一策略的两面，用户在编辑策略时经常要同时改代码和配置，二选一 Tab 让两边值保存困难（尤其新建策略时要切回 config 才能保存配置、切回 formula 才能保存代码）。

## What Changes
- **MODIFIED** 语法检查调用路径：`check-syntax` → `check_syntax`；统一 fetch 错误处理 `r.ok ? .json() : 非 JSON 兜底`。
- **MODIFIED** 选股任务隔离语义："切策略时 cancel 旧任务" → "切策略时隐藏 UI、**不 cancel 后台 task**；poll 仍在后台继续，结果写入各自 SC_RESULTS_CACHE，切回时还原进度或结果"。
- **MODIFIED** 主工作区 UI：删除 2 Tab 栏（公式编辑/选股配置），合并为**单一大卡片**：上半区"策略公式编辑器"+ 中间区"选股配置卡片" + 底部"选股结果卡片（含进度条 + 立即选股按钮）"。保存按钮合并为统一的"保存策略"——同时保存 name/desc/code + config。

## Impact
- **Affected code**: `static/app.js`（语法检查路径 + 选股隔离语义重构 + 编辑/保存合并为一次保存）、`templates/index.html`（Tab → 合并单页）、`static/style.css`（删除 Tab 相关样式可保留或忽略，不产生错误；合并区若需 padding 调整则少量）
- **通达信红线不变**：`core/tdx.py` 零改动；screener 已改的 industry 补充逻辑不变；API 路由签名不变。
- **后端风险**：多个选股 task 同时跑会产生多线程并发，但原实现 `start_screen_async` 本来就是独立线程，天然支持。用户通常不会同时对 N 个策略都点"立即选股"，并发上限是合理的。

## ADDED Requirements

### Requirement: 选股后台并发任务互不干扰
每个策略的选股 task 启动后独立运行，UI 切换不影响其执行。

#### Scenario: 切走不 cancel、切回看进度
- **WHEN** 策略 A 点"立即选股"（进度显示"已扫描 N 只"），用户切到策略 B、再切回 A（A 仍未完成）
- **THEN** A 的 progress 仍显示，进度文本和百分比从 SC_TASK_MAP[sid] 继续实时轮询更新（不会显示"已取消"）；后台线程继续跑。

#### Scenario: 切走时完成，切回看到结果
- **WHEN** A 正在选股 → 切到 B → A 在 B 查看期间后台完成
- **THEN** 切回 A 时，立即看到结果表（SC_RESULTS_CACHE[A.id] 已填充 done 时的结果）

### Requirement: 统一保存策略（代码 + 配置一键保存）
"编辑策略"状态下，代码和配置在同一卡片中，保存时一次提交。

#### Scenario: 编辑后保存
- **WHEN** 用户选中策略 → 点"编辑策略" → 改通达信代码 → 改选股范围/排除条件/其他设置 → 点"保存策略"
- **THEN** 后端调用一次 `PUT /api/indicators/<id>`，body 包含 name、desc、code、config；name/desc、代码、配置四项同时更新落盘。

## MODIFIED Requirements

### Requirement: 通达信语法检查
路径对齐并加 Content-Type 保护。

#### Scenario: 语法检查不出现 HTML 404 JSON 错误
- **WHEN** 用户点"语法检查"
- **THEN** 正确命中后端 `/api/indicators/check_syntax`（下划线），通过则弹"✓ 语法检查通过"；失败弹具体错误；**即使**后端偶发返回非 JSON（如网络 5xx），catch 分支显示可读错误（不再出现 `SyntaxError: Unexpected token '<'`）。

### Requirement: 策略详情页
Tab 栏删除、代码区 + 配置区合并为同一视图。

#### Scenario: 选中策略即看到代码+配置
- **WHEN** 选中任意策略
- **THEN** 代码区（textarea）和配置区（选股范围/排除/其他/定时）都在同一滚动页内可见，无需切换 Tab；"编辑策略"后代码 textarea 可写，配置所有控件都可交互。

## REMOVED Requirements
### Requirement: 子 Tab
**Reason**: 两个视图的合并是本项明确要求；改 Tab 为单页不需要 Tab 切换逻辑。
**Migration**: 删除 `templates/index.html` 的 `.sc-tabs` 栏和两个 `data-pane` 壳（保留实际内容 div，去除 data-pane class）；删除 `app.js` L1648-1657 Tab click 切换处理器（已引用 `formula`/`config` 两个 data-tab，删除后不残留死引用）。
- 新建策略（原 L1904 `document.querySelector('.sc-tab[data-tab="formula"]').click()`）改为不切 Tab 直接 focus `#sc-code-name-edit input#sc-name`。
