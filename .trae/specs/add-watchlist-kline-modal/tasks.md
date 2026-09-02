# 自选标的K线弹窗 - The Implementation Plan

## [x] Task 1: 在 HTML 中添加 Modal 模板和表操作列结构升级
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 在 `templates/index.html` 自选标的表格下方（L184 `</div>` 之前或单独加一个 template/全局 modal 容器更优），插入一个全局 `<div class="modal-bg" id="wk-modal">` + `<div class="modal">`，用于展示 K 线。注意 `.modal-bg` 与 `.modal` 已在 style.css 定义（L95-97）。
  - Modal 内部结构：顶部标题（含 #wk-title 名称代码、右上角 X 关闭按钮） + 工具栏 seg 控件（#wk-range，三档 60/120/250，60 日默认 on） + ECharts 容器（`#watch-kline-chart`，建议 `.chart-big` 或 `style="width:100%;height:480px"`） + 底部 note 说明。
  - Modal 容器为全局唯一：只在最末尾 `</body>` 前插入一次，不跟每行 DOM 绑定。
  - 操作列的 DOM 结构升级不在 HTML 中做，由 JS `renderWatch()` 生成（更符合现有代码模式）。
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: 页面加载后 DOM 中存在 `id="wk-modal"` 节点和 `id="watch-kline-chart"` 节点
  - `programmatic` TR-1.2: Modal 内存在 `#wk-range`，包含三个 `data-days="60|120|250"` 子 button，且 60 日 button 带 `on` class
  - `programmatic` TR-1.3: Modal 内存在关闭按钮（`.wk-close` 或带 data-action="close"），点击能移除 `.on` class
- **Notes**: Modal 插入位置建议 `</body>` 前，避免嵌套影响布局。

## [x] Task 2: `renderWatch()` 操作列增加「查看K线」按钮并绑定事件
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 修改 `renderWatch()`（app.js L1576）：原来 `const del = '<td><button class="btn danger sm w-del" data-code="...">删除</button></td>'`；在同一 td 内、删除 button 左边追加 `'<button class="btn ghost sm w-kline" data-code="${w.code}" data-name="${qq.name || w.name}">查看K线</button> '`（注意两按钮间留空格或用 `.btn + .btn` margin）。
  - `tb.querySelectorAll(".w-kline")` 绑定点击事件，调用 `openWatchKline(b.dataset.code, b.dataset.name)`（Task 3 实现此函数）。
- **Acceptance Criteria Addressed**: AC-1, AC-6
- **Test Requirements**:
  - `programmatic` TR-2.1: Grep `renderWatch` 输出的操作列 td 中，`.w-kline` 在 `.w-del` 之前（可通过生成的字符串顺序验证）
  - `programmatic` TR-2.2: 每个 `.w-kline` button 有 `data-code`（6 位数字）和 `data-name` 属性
  - `programmatic` TR-2.3: 点击 `.w-kline` 触发 `openWatchKline()` 调用（可用事件绑定 presence 验证）

## [x] Task 3: 实现 `openWatchKline()` / `loadWatchKline()` / `renderWatchKline()` + Modal 关闭
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**:
  - **全局变量**（在 loadWatch 附近）：`let wkChart = null;` `let wkCode = "";` `let wkDays = 60;` `let wkName = "";`
  - **`openWatchKline(code, name)`**：
    1. 设置 `wkCode = code; wkName = name; wkDays = 60;`
    2. 设置 modal 标题：`#wk-title` = `${name}（${code}）`
    3. 重置 seg 高亮：#wk-range 中 `data-days="60"` 加 on，其余 remove on
    4. 显示 modal：`$("#wk-modal").classList.add("on")`
    5. **关键**：Modal 从 display:none 切到 flex 后 canvas 尺寸为 0，需 `requestAnimationFrame(() => { wkChart?.resize(); loadWatchKline(); })` 或 `setTimeout(..., 30)` 保证容器尺寸就绪
    6. 初始化 wkChart：`if (!wkChart) wkChart = echarts.init(document.getElementById("watch-kline-chart"))`
  - **`loadWatchKline()`**：调用 `/api/index_kline?code=${wkCode}&days=${wkDays}` 走 safeJson 或直接 fetch.then.json（返回 {error?}），成功后调用 `renderWatchKline(d)`；失败 console.error 即可
  - **`renderWatchKline(d)`**：基本复用 `renderIndexKline(d)` 的 option 结构（L824-871），**仅改动两处**：
    1. `#index-kline-chart` 替换为 `#watch-kline-chart`，`ikChart` 替换为 `wkChart`
    2. legend.data 和 MA 颜色保持一致（直接复制即可）
    3. tooltip formatter、grid、x/yAxis 全部原样复制
  - **`closeWatchKline()`**：移除 `.modal-bg.on`；可保留 wkChart（下次 open 再 setOption）
  - **事件绑定**（在 `$("#w-add-btn").addEventListener` 附近）：
    1. `#wk-modal`（遮罩层）点击 e.target === $("#wk-modal")[0] 时 close
    2. `$(".wk-close")` 点击时 close
    3. `document.addEventListener("keydown")` → ESC 键（keyCode 27 / key === 'Escape'）时若 modal 打开则 close
    4. `#wk-range` 的 seg-btn 点击切换 on，设置 `wkDays = Number(b.dataset.days)`，调用 `loadWatchKline()`
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - `programmatic` TR-3.1: `loadWatchKline()` 请求 URL 包含 `code=` 和 `days=`；切换档位 days 变化
  - `programmatic` TR-3.2: `renderWatchKline()` 的 option 包含 5 条 MA series（MA5/10/20/60/120）、1 条 candlestick、1 条 bar 成交量
  - `programmatic` TR-3.3: `window.addEventListener("resize")` 触发时 `wkChart.resize()` 被调用（可选：最好在 openWatchKline 内注册一次性 resize 监听或全局监听）
  - `human-judgement` TR-3.4: 打开 modal 后蜡烛、均线、成交量清晰可见，不重叠、不空白、不缩成一条线
  - `human-judgement` TR-3.5: 切换 60→120→250 图表平滑更新，无报错
- **Notes**: 最常见坑是 Modal display:none 时 echarts 初始化拿到 0x0 尺寸导致空白，必须等 modal 显示后再 init/resize。

## [x] Task 4: 样式微调（按钮间距、Modal K线图高度）
- **Priority**: medium
- **Depends On**: Task 1
- **Description**:
  - `static/style.css` 追加少量样式：
    1. `#watch-kline-chart { width: 100%; height: 480px; }`（确保有确定尺寸，不依赖 .chart-big）
    2. `.w-kline + .w-del, .btn + .btn { margin-left: 6px; }`（操作列两个按钮留间距）
    3. `#wk-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }`（标题+关闭按钮对齐）
    4. `.wk-close { background: none; border: none; color: #8a96b5; cursor: pointer; font-size: 18px; }`（关闭按钮样式）
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-4.1: Grep style.css 存在 `#watch-kline-chart` 尺寸定义
  - `human-judgement` TR-4.2: 操作列「查看K线」与「删除」按钮不重叠，间距自然

## Task Dependencies
- Task 1 → Task 2（HTML 存在才能绑定）
- Task 1 + Task 2 → Task 3
- Task 1 → Task 4（独立小改动，可并行）
- Task 4 与 Task 2/3 互相独立

# Global Implementation Notes
- 不要改 app.py 或 core/*.py，全部改动在 templates/index.html + static/app.js + static/style.css
- `renderWatchKline` 复制 `renderIndexKline` 的代码结构，保持一致性；如果有必要可提取公共函数 `renderKlineGeneric(d, chart, el)` 但不强制
- 自选代码 6 位纯数字直接传给 `/api/index_kline`，后端 `to_symbol()` 会自动补 sh/sz/bj 前缀
