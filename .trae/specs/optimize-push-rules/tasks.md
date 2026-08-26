# Tasks

- [ ] Task 1: 后端组合条件规则支持
  - [ ] SubTask 1.1: 在 `core/rules.py` 的 `check_rules` 支持组合条件评估（conditions 数组 + and/or 逻辑）
  - [ ] SubTask 1.2: 在 `app.py` 的 `/api/config` 支持新规则结构（conditions + logic + channel）
  - [ ] SubTask 1.3: 实现旧规则自动兼容转换（单条件 → conditions 数组，logic 默认 and，channel 默认 feishu）

- [ ] Task 2: 多渠道推送支持
  - [ ] SubTask 2.1: 在 `core/notifier.py` 新增 `send_dingtalk` 和 `send_wecom` 函数
  - [ ] SubTask 2.2: 在 `core/rules.py` 的触发推送中根据 channel 字段选择发送函数
  - [ ] SubTask 2.3: 在 `app.py` 的 webhook 配置支持飞书/钉钉/企业微信三个字段

- [ ] Task 3: 推送历史记录
  - [ ] SubTask 3.1: 在 `core/rules.py` 增加推送历史记录写入（JSON 文件，保留最近 100 条）
  - [ ] SubTask 3.2: 在 `app.py` 新增 `/api/rules/history` GET 接口返回推送历史
  - [ ] SubTask 3.3: 在 `templates/index.html` 推送规则页新增推送历史卡片
  - [ ] SubTask 3.4: 在 `static/app.js` 实现推送历史列表渲染

- [ ] Task 4: 规则列表内联编辑
  - [ ] SubTask 4.1: 在 `templates/index.html` 规则列表表格增加「最后触发时间」列
  - [ ] SubTask 4.2: 在 `static/app.js` 实现点击规则行展开内联编辑表单
  - [ ] SubTask 4.3: 在 `static/app.js` 实现内联编辑保存逻辑
  - [ ] SubTask 4.4: 在 `static/style.css` 实现内联编辑表单样式

- [ ] Task 5: 添加规则表单支持组合条件
  - [ ] SubTask 5.1: 在 `templates/index.html` 添加规则表单支持多子条件添加与 and/or 选择
  - [ ] SubTask 5.2: 在 `static/app.js` 实现子条件动态增删和逻辑选择
  - [ ] SubTask 5.3: 在 `static/style.css` 实现组合条件表单样式

# Task Dependencies
- Task 4、Task 5 依赖 Task 1（后端先支持新结构）
- Task 2、Task 3 与 Task 1 可并行
