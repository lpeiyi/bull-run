- [x] Checkpoint 1: HTML DOM 结构
  - [x] 1.1 页面存在 `id="wk-modal"` 节点（`.modal-bg` + `.modal`）
  - [x] 1.2 Modal 内存在 `id="watch-kline-chart"` ECharts 容器
  - [x] 1.3 Modal 内存在 `#wk-range` seg，包含 60/120/250 三个按钮，60 日默认 on
  - [x] 1.4 Modal 内存在关闭控件（X 按钮或可点击关闭区域）

- [x] Checkpoint 2: 自选表格「查看K线」按钮
  - [x] 2.1 每行操作列 td 有「查看K线」按钮（`.w-kline`），在「删除」按钮（`.w-del`）左侧
  - [x] 2.2 每个 `.w-kline` 按钮带有 `data-code` 和 `data-name` 属性
  - [x] 2.3 两按钮之间有合理间距，不重叠

- [x] Checkpoint 3: Modal 打开/关闭行为
  - [x] 3.1 点击「查看K线」打开 modal（`#wk-modal.on`）
  - [x] 3.2 点击空白遮罩层（非 .modal 内容区）关闭 modal
  - [x] 3.3 点击右上角 X 关闭 modal
  - [x] 3.4 按 ESC 键关闭 modal
  - [x] 3.5 Modal 标题栏显示「标的名称（代码）」

- [x] Checkpoint 4: K线图渲染与接口调用
  - [x] 4.1 打开 Modal 后触发 `/api/index_kline?code=XXX&days=60` 请求（默认 60 日）
  - [x] 4.2 Modal 内显示蜡烛图（红涨绿跌颜色正确）
  - [x] 4.3 显示 MA5/MA10/MA20/MA60/MA120 五条均线（legend 可见、颜色与指数K线一致）
  - [x] 4.4 下方副图显示成交量柱子（红涨绿跌）
  - [x] 4.5 tooltip hover 显示开/收/高/低 + 成交量 + 各均线数值

- [x] Checkpoint 5: 时间档位切换
  - [x] 5.1 点击 120 日按钮 → on class 切换到 120 日 → 发起 `days=120` 请求 → 图表刷新为 120 根
  - [x] 5.2 点击 250 日按钮 → 同上，`days=250`
  - [x] 5.3 再点回 60 日 → 正确回到 60 日档位

- [x] Checkpoint 6: 切换标的无残留
  - [x] 6.1 打开 A 的 K线 → 关闭 → 打开 B 的 K线，标题、代码、蜡烛数据正确为 B 的
  - [x] 6.2 全过程 console 无 error / uncaught TypeError

- [x] Checkpoint 7: 后端零改动
  - [x] 7.1 `app.py` 和 `core/` 目录下所有文件 git diff 为空（或手动确认未修改）
