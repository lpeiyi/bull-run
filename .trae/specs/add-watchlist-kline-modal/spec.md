# 自选标的K线弹窗 - Product Requirement Document

## Overview
- **Summary**：在市场概览页自选标的实时行情表格的每行操作列，增加「查看K线」按钮（位于「删除」按钮左侧），点击后弹出模态对话框，展示该标的近 60/120/250 日的蜡烛图 + MA5/MA10/MA20/MA60/MA120 均线 + 成交量副图，视觉和交互参考现有「指数K线」卡片。默认时间范围为 60 日。
- **Purpose**：为自选标的提供快速查看K线和均线的能力，无需跳转外部网站。
- **Target Users**：A股实盘看盘用户，在概览页查看自选行情时需要辅助判断个股/ETF走势。

## Goals
- 自选表格每行操作列有「查看K线」按钮，位置在「删除」左侧
- 点击后弹出 Modal，展示 K 线（蜡烛图）+ MA5/10/20/60/120 均线 + 成交量副图
- Modal 内支持 60 / 120 / 250 日三档切换，默认 60 日高亮
- K 线渲染完全复用指数K线渲染逻辑（蜡烛颜色、tooltip、legend、双 grid 布局），仅数据源不同
- 调用后端 `/api/index_kline`（或兼容 API）直接复用 MA 计算、缓存、to_symbol 市场前缀处理，无需新增后端代码

## Non-Goals (Out of Scope)
- 不做分时/周线/月线切换，只做日K蜡烛图
- 不改变现有自选增删改查逻辑（loadWatch / addWatch / delWatch / CONFIG.watchlist）
- 不引入新的后端 API（直接复用 `/api/index_kline` 或极小参数兼容封装）
- 不做自选标的搜索、分组、分组导入等高级功能
- 不做画线、DMI/MACD/KDJ 等副图指标（只显示成交量副图）

## Background & Context
- **自选表结构**：`templates/index.html` L181-184 7 列表格（名称/代码/现价/涨跌幅/成交额/换手率/操作），操作列目前只有「删除」按钮。`renderWatch()`（[app.js L1576](file:///d:/job/Repository/bull-run/static/app.js#L1576)）拼 HTML 并在删除按钮上绑 click。
- **代码格式**：watchlist 存 6 位纯数字（无前缀），`to_symbol()` 在 core/data.py L27-38 负责自动加 sh/sz/bj 前缀，`kline()` 内部自动调用 `to_symbol()`，所以 `/api/index_kline` 接受无前缀 6 位代码或带前缀代码均可。
- **K线渲染参考**：`renderIndexKline()`（[app.js L824](file:///d:/job/Repository/bull-run/static/app.js#L824)）已实现完整蜡烛图+MA5~MA120+成交量双 grid 布局，颜色、tooltip formatter、双 X/Y 轴完全可复用。
- **Modal 基础**：`.modal-bg` + `.modal` CSS 已存在（style.css L95-97），支持居中遮罩、圆角 14px、92vw 宽度、86vh 最大高度滚动。可直接复用。
- **后端 `/api/index_kline`**：[app.py L444](file:///d:/job/Repository/bull-run/app.py#L444) 接受 `?code=xxx&days=N`，返回 `{code,name,dates,kline,volume,ma5,ma10,ma20,ma60,ma120}`，并已做 `_KLINE_CACHE` 600秒缓存和 MA 多取 150 根处理。接口名 index_kline 虽叫"指数"但实际调用通用 `kline()` 支持个股/ETF，无需改名。

## Functional Requirements
- **FR-1 自选表操作列新增「查看K线」按钮**：`renderWatch()` 拼 HTML 时，操作列先放「查看K线」button（`.btn.ghost.sm.w-kline`），再放「删除」button（`.btn.danger.sm.w-del`）；两按钮之间不换行。
- **FR-2 Modal 打开与关闭**：点击「查看K线」时，以 modal 方式弹出。Modal 内容包含：顶部标题栏（标的名称 + 代码 + 时间范围 seg 控件）、ECharts canvas 容器（宽高自适应）、底部说明 note。关闭方式：点击遮罩层（`.modal-bg`）关闭，或按 ESC 关闭，或右上角 X 关闭。
- **FR-3 K线加载与渲染**：打开 Modal 时，调用 `/api/index_kline?code=${toSymbolStyle(code)}&days=${currentDays}`（toSymbolStyle 调用时由后端 to_symbol 自动补前缀，前端直接传 6 位代码即可），返回数据后调用 `renderWatchKline(d)`（视觉与 renderIndexKline 一致：蜡烛图 + MA5/10/20/60/120 + 成交量）。
- **FR-4 时间范围切换**：Modal 内 `#wk-range` seg 控件提供 3 档：近60日（`data-days="60" on` 默认高亮）/ 近120日 / 近250日；点击切换高亮并重新请求接口、重新渲染。
- **FR-5 响应式 resize**：Modal 打开后自动 `echarts.init()` 并 `resize()`；Modal 大小变化（如 resize 事件）时图表自适应。

## Non-Functional Requirements
- **NFR-1 复用指数K线渲染逻辑**：蜡烛/均线/成交量颜色、tooltip、legend、双 grid 布局参数与 renderIndexKline 完全一致，不做两套不同样式
- **NFR-2 无控制台新错误**：打开/切换/关闭 Modal 全过程无 console error / uncaught TypeError
- **NFR-3 后端零新增**：不新增 API，不修改 app.py / core/*，所有改动在 templates/index.html + static/app.js

## Constraints
- **Technical**：
  - 后端零改动：全部改动在前端 templates/index.html + static/app.js
  - 复用 `/api/index_kline` 接口 + `renderIndexKline` 渲染选项结构
  - Modal 复用 `.modal-bg.on / .modal` 现有样式
  - 自选代码从 `CONFIG.watchlist[i].code` 取（6 位纯数字），传 index_kline 时直接用 6 位或由后端 to_symbol 自动补前缀均可
- **Business**：
  - 默认 60 日、三档 60/120/250
  - MA 颜色与指数K线一致：MA5 黄/MA10 青/MA20 紫/MA60 红/MA120 青绿
- **Dependencies**：无新 npm 包 / pip 包

## Assumptions
1. `/api/index_kline?code=6位纯数字` 后端会正确调用 `to_symbol(code)` 自动补 sh/sz/bj 前缀（core/data.py L117 `sym = to_symbol(code)` 确保）
2. ECharts 在 modal 从 display:none 切到 flex 后需 `setTimeout(chart.resize(), 50)` 或 IntersectionObserver 才能正确测量尺寸
3. `echarts.init()` 可复用已加载的 echarts 实例（window.echarts 已全局可用）

## Acceptance Criteria

### AC-1: 自选表格每行有「查看K线」按钮在「删除」左侧
- **Given**: 概览页自选表有 ≥1 条标的
- **When**: 检查任一行操作列 DOM
- **Then**: 操作列包含两个 button，顺序从左到右为「查看K线」→「删除」；两按钮相邻、间距正常
- **Verification**: `programmatic`

### AC-2: 点击按钮弹出 K 线 Modal，内容正确
- **Given**: 有自选标的（如 510300）
- **When**: 点击「查看K线」
- **Then**: Modal 打开，遮罩层出现；Modal 顶部标题含标的名称（如"沪深300ETF"）+ 代码（如"510300"） + 3 档 seg（近60日高亮 on）；中部有 ECharts canvas，能看到蜡烛图 + MA 均线 + 成交量柱子 + legend（MA5/10/20/60/120）
- **Verification**: `human-judgment`

### AC-3: 默认显示近 60 日，切换档位刷新正确
- **Given**: Modal 已打开，默认高亮近60日
- **When**: 点击「近120日」
- **Then**: 按钮 on 高亮切到 120；网络面板出现 `/api/index_kline?days=120` 请求；图表重新渲染显示 120 根蜡烛（数量≈120）
- **When**: 再点「近250日」
- **Then**: 高亮和请求切换到 250；图表≈250 根蜡烛
- **Verification**: `programmatic` + `human-judgment`

### AC-4: MA5/MA10/MA20/MA60/MA120 五条均线显示
- **Given**: Modal 打开，时间档位 60 日（MA120 在 60 日前可能无值，属正常）
- **When**: 检查图表 legend 和 hover tooltip
- **Then**: legend 有 MA5/MA10/MA20/MA60/MA120 五项；tooltip hover 时对有值的 MA 显示数值；颜色与指数K线一致（黄/青/紫/红/青绿）
- **Verification**: `human-judgment`

### AC-5: 关闭 Modal 三种方式均可用
- **Given**: Modal 已打开
- **When**: ①点击遮罩层空白处 或 ②按 ESC 键 或 ③点击 Modal 右上角 X
- **Then**: Modal 关闭（`.modal-bg.on` 类移除），ECharts 实例可保留或 dispose（下次打开重建也可，无泄漏为底线）
- **Verification**: `programmatic`

### AC-6: 切换多个自选标的 K 线正确
- **Given**: 自选表有 A/B 两条标的
- **When**: 依次点击 A 的「查看K线」→ 关闭 → 点击 B 的「查看K线」
- **Then**: 第二次打开时标题名称/代码为 B 的，K 线数据为 B 的，不残留 A 的
- **Verification**: `human-judgment`

## Open Questions
- [ ] 无（直接复用 index_kline 接口，无开放问题）
