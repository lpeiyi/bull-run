# Tasks

- [x] Task 1: 把 Modal DOM 从 script 之后移到 script 之前
  - [x] SubTask 1.1: 用 Read 工具确认 `templates/index.html` 当前 L441-463 的精确内容（最外层 `</div>` 闭合 + 空 line + `<script src="/static/echarts.min.js">` + `<script src="/static/app.js?v=20260826d">` + Modal DOM + `</body></html>`）
  - [x] SubTask 1.2: 用 Edit 工具：
    - **第一步**：删除当前 Modal DOM 段（从 `<!-- ═══ 自选标的K线弹窗 ═══ -->` 到 `</div>` 闭合 `#wk-modal` 整段）
    - **第二步**：在最外层 `</div>`（L441）之后、`<script src="/static/echarts.min.js">` 之前，重新插入 Modal DOM 段
  - [x] SubTask 1.3: 用 Grep 确认 `#wk-modal` 出现在 `<script src="/static/app.js` 之前（通过 Read 查看 Modal 上下文，确认顺序）

- [x] Task 2: 充分测试验证
  - [x] SubTask 2.1: 用 Grep 检查 app.js 中的所有事件绑定代码（`document.getElementById("wk-modal")`、`document.querySelectorAll(".wk-close")`、`document.querySelectorAll("#wk-range .seg-btn")`、`window.addEventListener("resize"`）全部存在
  - [x] SubTask 2.2: 用 Grep 确认 `templates/index.html` 中所有 `addEventListener` 触及的 DOM 节点（`wk-modal`、`wk-close`、`wk-range`、`watch-kline-chart`）都在 `<script>` 标签之前
  - [x] SubTask 2.3: 用 Read 检查文件末尾结构，确认 `</div>` + 空 line + Modal DOM + `<script src=...>` × 2 + `</body></html>` 顺序正确
  - [x] SubTask 2.4: 用 Grep 检查其他重要 DOM 节点（如 `index-kline-chart`、`ik-range`、`ik-code`、`sc-strategy-search`、`r-add`、`backtest`）位置未发生变化

# Task Dependencies
- Task 1 → Task 2（先改完再验证）
- SubTask 1.1 → SubTask 1.2 → SubTask 1.3 串行
- SubTask 2.1-2.4 可并行
