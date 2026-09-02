- [x] Checkpoint 1: Modal DOM 位置正确
  - [x] 1.1 `templates/index.html` 中 `#wk-modal` 整段出现在 `<script src="/static/echarts.min.js">` 之前（L444-460 → L462）
  - [x] 1.2 `#wk-modal` 整段出现在 `<script src="/static/app.js` 之前（L444-460 → L463）
  - [x] 1.3 Modal 内部结构（`wk-title` L446、`wk-range` L451、`watch-kline-chart` L457、`wk-close` L448）保持完整，无丢失

- [x] Checkpoint 2: 文件末尾结构正确
  - [x] 2.1 顺序为：`</div>`（L441）→ 空行 → `<!-- ═══ 自选标的K线弹窗 ═══ -->` + Modal DOM（L443-460）→ `<script src="/static/echarts.min.js">`（L462）→ `<script src="/static/app.js?v=...">`（L463）→ `</body></html>`（L464-465）
  - [x] 2.2 不存在 Modal DOM 残留在 script 之后的情况

- [x] Checkpoint 3: 事件绑定代码完整性
  - [x] 3.1 `static/app.js` 中存在 `document.getElementById("wk-modal").addEventListener("click"`（L1766）
  - [x] 3.2 存在 `document.querySelectorAll(".wk-close").forEach(...)` 关闭按钮绑定（L1770）
  - [x] 3.3 存在 `document.addEventListener("keydown", ...)` ESC 绑定（L1774）
  - [x] 3.4 存在 `document.querySelectorAll("#wk-range .seg-btn").forEach(...)` 档位切换绑定（L1778）
  - [x] 3.5 存在 `window.addEventListener("resize"` 自适应绑定（L1787）

- [x] Checkpoint 4: 其他 DOM 节点位置未受影响
  - [x] 4.1 `index-kline-chart`（L62）、`ik-range`（L56）、`ik-code`（L45）均在 L441 之前
  - [x] 4.2 `index-compare-card`（L67）位置未变
  - [x] 4.3 选股页 `sc-strategy-search`（L197）、提醒规则页 `r-add`（L434）等关键 DOM 节点未移动（均在 L441 之前）

- [x] Checkpoint 5: 后端零改动
  - [x] 5.1 `git diff --name-only app.py core/` 输出为空，`app.py` 和 `core/` 目录下所有文件未修改

- [x] Checkpoint 6: 功能回归（静态推断）
  - [x] 6.1 静态推断：app.js 顶层执行 `document.getElementById("wk-modal")` 时 Modal DOM（L444-460）已就绪（在 script L463 之前），不会抛 TypeError
  - [x] 6.2 静态推断：所有事件绑定代码（L1766-1791）能正常执行，不会中断后续代码
  - [x] 6.3 静态推断：其他功能（指数K线加载、选股、提醒规则）依赖的 DOM 均在 script 之前，不受 Modal 位置调整影响
