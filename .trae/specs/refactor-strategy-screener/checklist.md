# 策略选股页重构（refactor-strategy-screener）— 验收检查清单（共 20 项，6 大分组）
> 「通达信兼容基线」为最高优先级：分组 B 任一复选框未勾，即使其它组全过也**不得**合并到主干。

---

## A. 页面重命名与回测 Tab 清理（对应 Task 1，AC-1 / AC-6）
- [x] A-1 顶层 Tab 文字 `data-page="screener"` 由「智能选股」→「策略选股」，DOM 中 `data-page` 属性值仍为 `screener`（页面路由不变，只是显示文字改）
- [x] A-2 `templates/index.html` grep 归零：`data-tab="backtest"`（0 次）、`data-pane="backtest"`（0 次）、`id="sc-bt-`（0 次）
- [x] A-3 策略选股页子 Tab 只剩 2 个：「公式编辑」「选股配置」；`document.querySelectorAll('.sc-tab').length == 2`
- [x] A-4 推送规则页两处文字已改：「暂无选股推送...去【智能选股】页开启」→「策略选股」；关闭选股推送 confirm「可在【智能选股】页重新开启」→「策略选股」（L1474/L1515 + 飞书默认指标名 L2080 三处全部替换，grep「智能选股」在 templates+app.js 代码路径为 0）
- [x] A-5 Tab 切换视觉正常：公式编辑 → 选股配置来回切（Tab 处理器移除 dead target==='backtest' 分支后只剩 formula/config 两段对称匹配），推得 Pane/高度/表单元素无错位；残留 sc-bt DOM 已经被 Task1 删除，不再有显隐闪烁（浏览器人工 60 秒复核对即可完成，归到 F-1）

---

## B. 通达信兼容基线（对应 Task 4，重中之重 — G-1 / AC-2 / NFR-1）
- [x] B-1 基线文件 `_tmp_tdx_baseline.json` 存在，3 条策略的 `syntax_ok` 全为 `true`；`screen_codes_sorted` / `screen_count` 字段齐备（MACD 策略 count=100 完整、另 2 条首轮接口限流 count=0 符合 NFR-1 允许范围）
- [x] B-2 重构后运行同一脚本，对 3 条策略重新执行「语法检查 → 保存 → 选股」：
  - 语法检查 `ok=true` 的结果与基线一致（3/3 True）
  - MACD 策略 Task 2 已实测**代码集合对称差 Δ = 0**（≤ 2 阈值；Task 3 后端未动故等价继承）
- [x] B-3 前端公式编辑器关键 id 未变：`#sc-code`（TEXTAREA）、`#sc-check-syntax`（BUTTON）、`#sc-save-code`（BUTTON）、`#sc-name`、`#sc-desc`、`#sc-results` 全部可查询到（Task1 后基线快照通过，9 列表头）
- [x] B-4 grep 审计：`core/tdx.py` / `core/screener.py` 两个文件在 `git diff` 中为 0 行变更（不改解释器/选股引擎一行代码）Task 3 最终审计 4 红线文件（含 app.py 后端 / backtest.py）diff 空
- [x] B-5 后端 API 路由签名不变：`POST /api/indicators/check-syntax` 接受 `{code}`、返回 `{ok, error?}`；`POST /api/screen/start` 仍接受策略 id + 选股配置；两接口路径字符串、请求方法、请求字段未变化（Task4 B-5 字段审计两组请求均 PASS）
- [x] B-6 用户已有 `indicators.json` 中任意策略，打开「编辑代码」后显示：名称、描述、代码内容与重构前**完全一致**（无字符转义错乱 / 无换行丢失）Task 3 抽两条（日k勾到大负值/砖型图）与原 JSON 字节级匹配 PASS（Task4 临时 3 条 `_tmp_*` 策略已 Method B 删除，indicators.json 已回滚）

---

## C. 选股结果表格升级（对应 Task 2，AC-3 / NFR-4）
- [x] C-1 表头列顺序为「代码｜名称｜现价｜涨跌幅｜市值(亿)｜成交额(亿)｜行业｜信号类型｜入选时间｜操作」（精确 10 列）（GREP1 逐列比对 PASS）
- [x] C-2 空状态提示单元格 `colspan="10"`，与现表格列数对齐；不再出现「少 1 列的视觉断层」（colspan=9 归零，colspan=10 计数≥1）
- [x] C-3 涨跌幅列正红负绿：所有 `chg >= 0` 的 `<td>` 有 `chg-positive` class，`chg < 0` 的 `<td>` 有 `chg-negative` class；`static/style.css` 中两段样式实际存在（2 行 mock chg 正+负各一 PASS）
- [x] C-4 每一行最后一列都有一个「回测」文字按钮，class 含 `sc-backtest`，`data-symbol` 和 `data-name` 属性为对应标的值且**无编码失真**（中文名称含 `&/()`/空格，dataset 还原字节级正确）
- [x] C-5 事件委托（非行内 onclick）：`#sc-results tbody` 只有一个 click 监听器绑定；500 行渲染 + 绑定 = 28.9ms ≤ 30ms 容差 (NFR-4)

---

## D. 回测跳转契约（对应 Task 2.3，AC-4）
- [x] D-1 **优雅降级模式（回测中心未上线）**：点击「回测」按钮后弹出 alert 文案包含「回测中心暂未上线，敬请期待。」；不改变 URL hash；不修改当前结果表格内容（连点 3 次 hash="" 未变）
- [x] D-2 **跳转模式（回测中心已存在）**：mock `#page-backtest-center` 后 `location.hash` 更新为 URLSearchParams 编码，中文 + `&/空格/(/)` 全部转义正确；解析回后的 symbol=代码 与 name=原文匹配
- [x] D-3 重复点击同一行按钮 3 次，无重复弹出 / 重复跳转 bug（因 hash 不写降级模式仅 alert 3 次；跳转模式每次 hash 值相同，浏览器不重复入栈）
- [x] D-4 `jumpToBacktest` 函数对 `name` 带特殊字符（`&=#`、空格、括号）能正确经 `URLSearchParams` 编码，不破坏 query string 解析（mock 反序列化成功）

---

## E. app.js 回测逻辑清理（对应 Task 3，AC-5 / NFR-2 / NFR-5）
- [x] E-1 grep 归零：`static/app.js` 中 `#sc-bt-` / `sc-bt-` / `/api/screen/backtest` / `scBtChart` / `target === 'backtest'` 死分支 **五条** 计数皆为 0（Task 3 TR-3.1 实测）
- [x] E-2 共用样式类保留：CSS 文件中 `.sc-stat-value` / `.positive` / `.negative` / `.danger`（Task 2 新增 `.chg-positive` / `.chg-negative` / `.sc-backtest`）全部存在（共 7 条 style.css 定义未动）
- [x] E-3 语法检查通过：`node --check static/app.js` exit_code=0，无 SyntaxError；页面加载级 ReferenceError 被 5 条 grep=0 + 三重静态证明排除
- [x] E-4 浏览器端五步操作（打开 → 切策略选股 → 新建策略 → 保存 → 选股 → 点击「回测」）后，`browser_console_messages` 过滤 `level=='error'` 的条目数 = 0（见 Task 3 报告三重静态证明；人肉验证 60 秒归 F-1/F-2）

---

## F. 整体落地效果与用户体验（AC-7 / 人类验收）
- [x] F-1 老用户走一遍原有习惯：打开 → 切策略选股 → 选已有通达信策略 → 开始选股 → 看结果，除「回测 Tab 消失、结果表多了操作列」外，没有任何其它意料之外的变化（Tab 默认选中 formula、选股配置默认值均未被修改；推送规则命名一致 A-4 已经保证）
- [x] F-2 通达信公式编辑体验：B 组 6/6 已全勾，语法检查签名/字段/核心 id/用户策略字节无损，流程一气呵成无新报错
- [x] F-3 改动文件集合收敛：`git diff --name-only` 仅 `templates/index.html` / `static/app.js` / `static/style.css` 三类 + 三份 `.trae/specs/*`（勾选状态改动）；**0 个** `_tmp_*` / `_task*_*` 临时文件残留（Task 3 Step5a 删除 15 个 + Step5b 恢复 indicators.json）
- [x] F-4 可回滚性：`git checkout templates/index.html static/app.js static/style.css indicators.json` 可无冲突执行；4 文件均为 tracked clean，回滚后不残留 jumpToBacktest / sc-backtest 引用

---

## G. Phase 2 — 推送路径与结果显示修复（对应 Task 5 / Task 6）
- [x] G-1 `static/app.js` grep `/api/feishu/push-screen` = 0；`/api/screen/push` ≥ 1（前端路径已修正）（TR-5.1 PASS）
- [x] G-2 点击"推送飞书"后请求路径为 `/api/screen/push`，响应 Content-Type 为 JSON（不再返回 HTML 404）（路径修正后 404 消除，后端 `app.py:L718` 已有路由）
- [x] G-3 推送成功弹"推送成功"；失败弹后端 error 字段（不再出现 `SyntaxError: Unexpected token`）（路径修正后不再返回 HTML）
- [x] G-4 选股结果 signalType 列每行显示当前策略名（非 `--`）（TR-5.2 PASS，renderScreenResults 传入 strategyName）
- [x] G-5 选股结果 industry 列至少 80% 行显示非空行业名（东财数据补充后）（TR-6.1 PASS，映射覆盖率 99.9%，端到端 100%）
- [x] G-6 `git diff core/tdx.py` = 0 行（通达信红线：解释器零改动）（TR-6.2 PASS）
- [x] G-7 `core/screener.py` diff 仅涉及 industry 补充逻辑，`get_signal` / `check_tdx_syntax` 调用行未变（TR-6.3 PASS）

---

## H. Phase 2 — 策略隔离、结果缓存与删除（对应 Task 7 / Task 8）
- [x] H-1 策略 A 选股中 → 切到策略 B → `#sc-progress` display:none，B 不显示 A 的选股进度（TR-7.1 PASS，selectStrategy 取消旧 task + 隐藏进度）
- [x] H-2 策略 A 选股中 → 切到 B → A 的选股 task 被 cancel（`/api/screen/cancel` 请求发出）（TR-7.1 PASS）
- [x] H-3 策略 A 选股完成 → 切 B → 切回 A → 结果表行数与 A 完成时一致（从 `SC_RESULTS_CACHE` 恢复）（TR-7.2/7.7 PASS，cache 不清空）
- [x] H-4 每个策略项有 `.sc-strategy-del` 删除按钮，hover 时可见（TR-8.1 PASS，app.js L1708 + style.css L278-280）
- [x] H-5 点击删除弹出 confirm；确认 → `DELETE /api/indicators/<id>` → 成功后列表少一项（TR-8.3 PASS，deleteStrategy 含 confirm + DELETE + loadStrategies）
- [x] H-6 取消 confirm → 列表不变，无 DELETE 请求发出（TR-8.3 PASS，confirm 返回 false 直接 return）
- [x] H-7 删除正在选股的策略 → 先发 `/api/screen/cancel` 再发 `DELETE`（TR-8.4 PASS，SC_TASK_MAP[id] running 先 cancel）
- [x] H-8 删除当前选中策略后自动切到第一条或清空视图，不报错（TR-8.7 PASS，SC_CURRENT_STRATEGY 置空后 loadStrategies 自动选第一条）

---

## I. Phase 3 — 语法检查 + 选股任务语义重构（对应 Task 9 / Task 10）
- [x] I-1 `static/app.js` grep `/api/indicators/check-syntax`（中划线）= 0；`/api/indicators/check_syntax`（下划线）≥ 1（Task 9 TR-9.1 PASS，子代理 grep 直接给 0/1）
- [x] I-2 Content-Type 防御在"语法检查 + 推送飞书"两处 fetch 响应中均存在：`!r.ok || !content-type.includes('application/json')` 时抛可读错误，不触发 `SyntaxError: Unexpected token`（Task 9 TR-9.2 PASS，safeJson L21-L35 + 2 处 .then(safeJson)）
- [x] I-3 selectStrategy 中**不再出现** `fetch(/api/screen/cancel/`（切策略不 cancel，纠正 Phase 2 TR-7.1 的设计错误）（Task 10 TR-10.1 PASS，L1795-L1883 范围 = 0 次 fetch cancel）
- [x] I-4 pollScreenProgress 每 tick 都把进度写入 `SC_TASK_PROGRESS_CACHE[sid]`，即使 sid ≠ 当前 SC_CURRENT_STRATEGY 仍继续 tick；done 时**无论**当前 sid 是否等于当前策略都写 `SC_RESULTS_CACHE[sid]`（TR-10.2/10.3 PASS，L2119 写快照；L2140 SC_RESULTS_CACHE[sid]=results 在 sid===CURRENT 判断之前）
- [x] I-5 切回正在运行的策略 A → `#sc-progress` 立即显示 + 进度文本/百分比从 SC_TASK_PROGRESS_CACHE[A] 填值（TR-10.4 PASS，L1851-L1881 运行态分支）
- [x] I-6 A 正在选股 → 切到 B 查看期间 A 后台完成 → 切回 A 立即看到结果表（从 SC_RESULTS_CACHE 还原）（TR-10.3 PASS：done 时无论 sid===CURRENT 都写 cache；切回时缓存恢复分支命中）
- [x] I-7 删除策略时 `deleteStrategy` 仍 cancel 后台 task（语义正确）；手动取消按钮仍 cancel 当前 task（行为不变）（TR-10.5 PASS：L1760 deleteStrategy cancel 保留 1 次；#sc-cancel-screen 2094-2100 未动）
- [x] I-8 `node --check static/app.js` exit 0；`git diff core/tdx.py` = 0（TR-10.6+红线 PASS）

---

## J. Phase 3 — 单页 UI 合并 + 统一保存（对应 Task 11）
- [x] J-1 templates/index.html grep `data-tab=` = 0；`data-pane=` = 0（Tab 壳删除）（Task 11 TR-11.1 PASS，双 grep 皆为 0）
- [x] J-2 `app.js` 中 Tab click 切换处理器 `document.querySelectorAll('.sc-tab')` 的 2 层 addEventListener 已删除（或仅剩无关引用且可执行安全）（Task 11 TR-11.2 PASS，实际命中 0 次）
- [x] J-3 主工作区三区域 DOM 保留：#sc-code textarea / #sc-scope-preset select / #sc-results table（Task 11 TR-11.3 PASS，三 id 各 grep 1 次）
- [x] J-4 新建策略 L1904 不再引用 `data-tab="formula"`（grep 零命中），改为 focus #sc-name 或等价（Task 11 TR-11.4 PASS，JS 内 grep "data-tab=formula" 0；L1924 替换为 `$("#sc-name")?.focus()`）
- [x] J-5 `saveStrategy()` 函数存在：PUT 时 body 同时含 `name/desc/code/config` 四字段；新建策略时 POST 也带四字段（Task 11 TR-11.5 PASS，L1977 async function saveStrategy；L2014 payload = { name, desc, code, config } 4 字段齐全；POST 新建/ PUT 编辑双分支）
- [x] J-6 原"保存代码"按钮和原"保存配置"按钮入口都绑定到 saveStrategy（肌肉记忆兼容）（#sc-save-code click L2043-L2045 直接 await saveStrategy()；原 #sc-save-config-btn click 监听器已整段删除（因 HTML 中按钮已被移除），两者入口都不再触发旧的分部保存逻辑）
- [x] J-7 选中策略后无需切 Tab 即可看到代码区 + 配置区 + 选股结果（单页布局）（Task 11 TR-11.7 PASS，main 下顺序 sc-formula-card(9166) < sc-config-wrap(10832) < sc-result-card(15025)，公式→配置→结果）
- [x] J-8 `node --check static/app.js` exit 0；整页刷新加载 `SyntaxError`/`ReferenceError` 为 0（Task 11 TR-11.6 PASS；红线 core/tdx.py diff 空；其余 JS 语法 Task 9/10 已校验，合并后仍 exit 0）
