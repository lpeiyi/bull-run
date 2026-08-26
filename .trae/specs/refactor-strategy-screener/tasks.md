# Tasks

- [ ] Task 1: 页面重命名与 Tab 调整
  - [ ] SubTask 1.1: 在 `templates/index.html` 将顶部 Tab「智能选股」改为「策略选股」
  - [ ] SubTask 1.2: 移除主区域 `data-tab="backtest"` 的 Tab 按钮和 `data-pane="backtest"` 的 Tab 内容区全部 HTML

- [ ] Task 2: 选股结果表格新增操作列
  - [ ] SubTask 2.1: 在 `templates/index.html` 选股结果表头新增「操作」列
  - [ ] SubTask 2.2: 在 `static/app.js` 选股结果渲染函数中新增操作列的「回测」按钮
  - [ ] SubTask 2.3: 实现点击「回测」按钮跳转到回测中心页并自动填入股票代码的逻辑（需与回测中心页约定 URL 参数或全局变量传递）

- [ ] Task 3: 清理回测相关 JS 逻辑
  - [ ] SubTask 3.1: 在 `static/app.js` 移除回测 Tab 相关的事件绑定、回测执行、结果渲染函数
  - [ ] SubTask 3.2: 在 `static/app.js` 移除对 `sc-bt-*` 系列 DOM 元素的引用

# Task Dependencies
- Task 2 依赖 Task 1（先移除回测 Tab 再调整结果表格）
- Task 3 与 Task 1 可并行（HTML 和 JS 可同步清理）
