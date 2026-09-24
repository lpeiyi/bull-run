# 自选标的拖拽排序 + 移首 Spec

## Why

当前「市场概览 → 自选标的实时行情」卡片操作列仅支持「查看K线」「删除」，用户无法调整标的的显示顺序。新购标的默认追加到末尾，关注的票被压在列表尾部，查看/操作效率低。

## What Changes

- 操作列（第 7 列）在「查看K线」「删除」之间追加 2 个元素：**☰ 拖拽手柄** + **⤒ 移首按钮**

- 拖拽手柄：三条杠 SVG 图标，鼠标左键按住不放可上下拖动行到任意位置，支持跨多行拖动

- 移首按钮：SVG 图标 = 上箭头 + 正上方短横线，暗示「到达顶端」，点击移到首行

- 后端配置不变：CONFIG.watchlist 数组顺序 = 显示顺序，持久化用 saveConfig()

- 列宽铺满：7 列 th 显式 width 百分比合计 100%

- 追加优化：拖拽手柄加外框（参考其他按钮样式）；表头「操作」字段名居中到操作按钮上方

## Impact

- Affected code:

  - `static/app.js`：renderWatch() 按钮模板 + onDragStart/onDragMove/onDragEnd 拖拽逻辑 + watchTop

  - `static/style.css`：.w-grip 手柄样式 + 拖拽反馈 + disabled 灰态

  - `templates/index.html`：th width 百分比 + 操作列 th 居中

## ADDED Requirements

### AC-1 拖拽排序生效

- **AC-1.1 (rule)** 鼠标按住 `.w-grip` 三条杠手柄 mousedown → 被拖行加 `.dragging` class（半透明）

- **AC-1.2 (rule)** 拖动过程中 mousemove 实时计算目标行，目标行加 `.drag-over-top` 或 `.drag-over-bottom` 高亮线

- **AC-1.3 (rule)** 松开 mouseup → 从 CONFIG.watchlist 数组中 splice 取出被拖元素 + 插入目标位置 + await saveConfig() + loadWatch()

- **AC-1.4 (rule)** 支持跨多行拖动（不是一次一格，直接拖到目标位置）

### AC-2 按钮渲染 + disabled 边界

- **AC-2.1 (rule)** 操作列按钮顺序：查看K线(w-kline) → 三条杠手柄(w-grip) → 移首(w-top) → 删除(w-del)

- **AC-2.2 (rule)** 移首按钮 SVG = 顶部短横线 + 向上箭头（竖线 + 箭头头部）

- **AC-2.3 (rule)** 三条杠手柄 SVG = 三条等间距水平线

- **AC-2.4 (rule)** 首行移首按钮 disabled（`w.code === CONFIG.watchlist[0].code`）

### AC-3 持久化/刷新闭环

- **AC-3.1 (rule)** 拖拽松开后 await saveConfig() 再 loadWatch()

- **AC-3.2 (rule)** 移首点击后 await saveConfig() 再 loadWatch()

- **AC-3.3 (rule)** 排序后页面刷新，列表顺序保持不变

### AC-4 不回归

- **AC-4.1 (rule)** 查看K线/删除 按钮行为和事件绑定保持不变

- **AC-4.2 (rule)** 行情渲染 6 列不变

- **AC-4.3 (rule)** 空列表提示 colspan=7 不变

### AC-5 列宽铺满

- **AC-5.1 (rule)** 7 个 th 全部有 width 百分比，合计 100%

- **AC-5.2 (rule)** 名称 ≥ 22%，操作 ≥ 19%

### AC-6 拖拽手柄外框 + 表头居中（追加优化）

- **AC-6.1 (rule)** `.w-grip` 有外框样式（border/padding/background），视觉上与其他 `.btn ghost sm` 按钮一致

- **AC-6.2 (rule)** 表头 `<th>操作</th>` 文字居中（`text-align:center`），使「操作」二字位于操作按钮正上方

### AC-7 操作按钮外框/文字高度统一（追加优化）

- **AC-7.1 (rule)** `.w-del` 不再有独立 padding/font-size 覆盖，继承 `.btn.sm` 的 `padding:5px 12px; font-size:12.5px; font-weight:600`

- **AC-7.2 (rule)** `.w-grip` padding 改为 `5px 12px`（与 `.btn.sm` 一致），border-radius 改为 `8px`（与 `.btn` 一致）

- **AC-7.3 (rule)** 4 个操作元素（w-kline / w-grip / w-top / w-del）外框高度肉眼一致

### AC-8 操作按钮外框高度强制统一（追加优化 v2）

- **AC-8.1 (rule)** `.tbl td .btn.sm` 和 `.tbl td .w-grip` 统一设 `display:inline-flex; align-items:center; justify-content:center; line-height:1; height:28px; box-sizing:border-box`，消除 button 与 span 的 line-height 差异

- **AC-8.2 (rule)** 4 个操作元素外框上下沿完全对齐（固定 28px 高，内容垂直居中）

- **AC-8.3 (rule)** 不影响其他页面的 `.btn` 或 `.btn.sm`（仅限 `.tbl td` 内的操作列按钮）

### AC-9 vertical-align 统一（追加优化 v3）

- **AC-9.1 (rule)** `.tbl td .btn.sm` 和 `.tbl td .w-grip` 统一设 `vertical-align:middle`，消除 button 默认 `vertical-align:baseline` 与 span 的 `vertical-align:middle` 差异

- **AC-9.2 (rule)** 4 个操作元素在行内垂直对齐完全一致（上沿平齐 + 下沿平齐）

## Non-Goals

- 不做拖拽到末尾的专用按钮（拖拽已覆盖）

- 不做多选批量排序

- 不改 HTML table 结构列数

