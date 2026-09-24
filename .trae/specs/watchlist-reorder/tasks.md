# Tasks - 自选标的拖拽排序 + 移首 + 列宽铺满

## Task 1: renderWatch 拖拽手柄 + 移首SVG 按钮 HTML 与事件绑定
- **Priority**: high
- **Depends On**: None
- [x] Task 1 completed
  - renderWatch L1614-1646：btnKline → btnGrip(SVG三条杠) → btnTop(SVG上箭头+横线) → btnDel
  - 事件绑定：w-del/w-kline/w-top click + w-grip mousedown(onDragStart)

## Task 2: 拖拽排序逻辑 + watchTop 函数
- **Priority**: high
- **Depends On**: Task 1
- [x] Task 2 completed
  - watchTop L1708-1715：splice+unshift 移首
  - onDragStart L1723-1730：mousedown 记录 code + dragging class
  - onDragMove L1732-1752：mousemove 实时高亮目标行
  - onDragEnd L1754-1775：splice 重排 + saveConfig + loadWatch

## Task 3: CSS — 手柄样式 + 拖拽反馈 + disabled 灰态
- **Priority**: medium
- **Depends On**: None
- [x] Task 3 completed
  - .w-grip cursor:grab/grabbing + border + background + border-radius（外框参考 .btn ghost sm）
  - .w-top svg display
  - .tbl .btn[disabled] opacity/cursor/pointer-events
  - .dragging opacity:.4 + .drag-over-top/bottom box-shadow

## Task 4: HTML — 列宽铺满
- **Priority**: high
- **Depends On**: None
- [x] Task 4 completed
  - 7 th width: 24+10+10+11+13+11+21=100%

## Task 5: 追加优化 — 拖拽手柄加外框 + 表头操作列居中
- **Priority**: high
- **Depends On**: None
- [x] Task 5 completed
  - SubTask 5.1: .w-grip CSS 加 border:1px solid rgba(0,229,255,.4) + background:transparent + border-radius:6px + padding:5px 8px
  - SubTask 5.2: templates/index.html 操作列 th 加 text-align:center

## Task 6: 操作按钮外框/文字高度统一（追加优化）
- **Priority**: high
- **Depends On**: None
- [x] Task 6 completed
  - SubTask 6.1: .w-del 改为 padding:5px 12px + font-size:12.5px + font-weight:600（与 .btn.sm 一致）
  - SubTask 6.2: .w-grip padding 改 5px 12px + border-radius 改 8px

## Task 7: 操作按钮外框高度强制统一（追加优化 v2）
- **Priority**: high
- **Depends On**: None
- [x] Task 7 completed
  - SubTask 7.1: style.css L448 追加 `.tbl td .btn.sm,.tbl td .w-grip{display:inline-flex;align-items:center;justify-content:center;line-height:1;height:28px;box-sizing:border-box}`
  - SubTask 7.2: 4 个操作元素全部命中选择器，外框固定 28px 高 + 内容垂直居中，不影响其他页面 .btn

## Task 8: vertical-align 统一（追加优化 v3）
- **Priority**: high
- **Depends On**: None
- [x] Task 8 completed
  - SubTask 8.1: L448 追加 `vertical-align:middle`，4 个操作元素统一行内垂直对齐

# Task Dependencies
- Task 5、6、7、8 无依赖，可并行
