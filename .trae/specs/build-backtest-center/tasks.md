# Tasks

- [ ] Task 1: 顶部一级导航栏改造
  - [ ] SubTask 1.1: 在 `templates/index.html` 将 topbar 改造为一级导航栏，含 Logo + 「策略选股」「回测中心」两个入口 + 用户区
  - [ ] SubTask 1.2: 在 `static/style.css` 实现导航栏深色主题、选中态蓝色下划线
  - [ ] SubTask 1.3: 在 `static/app.js` 实现导航栏切换逻辑，切换时刷新整个内容区

- [ ] Task 2: 回测中心页面 HTML 结构搭建
  - [ ] SubTask 2.1: 在 `templates/index.html` 新增 `#page-backtest` 页面容器
  - [ ] SubTask 2.2: 搭建左侧「我的回测方案」列表面板（搜索框 + 方案列表 + 新建按钮）
  - [ ] SubTask 2.3: 搭建右侧主工作区：顶部标题栏 + 配置区（参数栏 + 代码编辑器）+ 结果区
  - [ ] SubTask 2.4: 搭建回测结果区：指标卡片行 + 图表区 + 交易明细表 + 空状态

- [ ] Task 3: 后端回测方案 CRUD API
  - [ ] SubTask 3.1: 在 `app.py` 新增回测方案持久化（JSON 文件存储方案列表）
  - [ ] SubTask 3.2: 新增 `/api/backtest_plans` GET/POST 接口（方案列表查询、新建）
  - [ ] SubTask 3.3: 新增 `/api/backtest_plans/<id>` GET/PUT/DELETE 接口（方案详情、更新、删除）
  - [ ] SubTask 3.4: 新增 `/api/stock_search` 股票联想搜索接口

- [ ] Task 4: 后端 Python 代码回测引擎
  - [ ] SubTask 4.1: 在 `core/backtest.py` 新增 Python 代码模式回测引擎，沙箱执行用户代码（exec + 受限 globals）
  - [ ] SubTask 4.2: 实现生命周期调用：initialize(context) → before_trading_start(context) → handle_bar(context, bar)
  - [ ] SubTask 4.3: 实现 API 函数：数据获取（history_bars/get_price/attribute_history）、技术指标（MA/MACD/KDJ/RSI/BOLL/VOL）、交易下单（order/order_target/order_value/order_target_value/order_target_percent）、账户信息（context.portfolio）、其他（log/set_benchmark/set_slippage/set_commission）
  - [ ] SubTask 4.4: 新增 `/api/backtest/run` POST 接口，接收方案 ID + 代码 + 参数，返回回测结果

- [ ] Task 5: 前端代码编辑器集成
  - [ ] SubTask 5.1: 引入 CodeMirror 或 Monaco Editor 库（本地静态文件）
  - [ ] SubTask 5.2: 在 `static/app.js` 初始化编辑器，配置 Python 语法高亮、行号、自动补全、括号匹配
  - [ ] SubTask 5.3: 实现代码模板下拉选择（MACD/双均线/布林带/RSI/网格策略），选中填充示例代码
  - [ ] SubTask 5.4: 实现右侧「API 参考」可折叠面板，点击函数名插入代码片段
  - [ ] SubTask 5.5: 实现语法错误行内提示（编辑器实时检查 + 「开始回测」按钮置灰逻辑）

- [ ] Task 6: 前端回测中心交互逻辑
  - [ ] SubTask 6.1: 在 `static/app.js` 实现回测方案列表加载、新建、选中切换
  - [ ] SubTask 6.2: 实现参数栏（回测标的联想搜索、日期范围、资金/费率/滑点/复权、展开收起）
  - [ ] SubTask 6.3: 实现回测执行调用与进度显示（按钮变「回测中...」+ 进度条 + 控件置灰）
  - [ ] SubTask 6.4: 实现回测结果渲染：7 指标卡片、收益曲线图（策略 vs 基准）、回撤曲线图、交易明细表（可展开 + 导出 CSV）
  - [ ] SubTask 6.5: 实现回测日志 Tab（按级别着色、级别筛选、清空）
  - [ ] SubTask 6.6: 实现参数变更黄色提示条「参数已变更...重新回测」
  - [ ] SubTask 6.7: 实现策略选股页「回测」按钮跳转到回测中心并自动填入股票

# Task Dependencies
- Task 2 依赖 Task 1（导航栏先就位）
- Task 4 依赖 Task 3（方案存储先就位）
- Task 6 依赖 Task 2、Task 4、Task 5（HTML + 后端引擎 + 编辑器就位后才能写交互）
- Task 5 与 Task 3、Task 4 可并行
