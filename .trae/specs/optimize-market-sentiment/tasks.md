# Tasks

- [ ] Task 1: 情绪趋势图加载缓存优化
  - [ ] SubTask 1.1: 在 `core/emotion_history.py` 增加历史情绪结果本地缓存（按交易日 key 缓存）
  - [ ] SubTask 1.2: 在 `app.py` 的 `/api/emotion_trend` 优先读缓存，仅 force=1 时重新计算
  - [ ] SubTask 1.3: 验证同一天内切换时间窗口可秒级返回

- [ ] Task 2: 情绪分维度贡献度可视化
  - [ ] SubTask 2.1: 在 `core/sentiment.py` 的 `get_sentiment` 返回值中增加各维度贡献度明细（涨停家数分/连板高度分/晋级率分/炸板率修正/跌停惩罚）
  - [ ] SubTask 2.2: 在 `templates/index.html` 情绪页情绪卡片中新增维度贡献度区域
  - [ ] SubTask 2.3: 在 `static/app.js` 实现水平条形图渲染各维度贡献度（正贡献蓝色、负贡献红色）
  - [ ] SubTask 2.4: 在 `static/style.css` 实现贡献度条形图样式

- [ ] Task 3: 情绪等级说明卡片
  - [ ] SubTask 3.1: 在 `templates/index.html` 情绪页新增情绪等级说明区域
  - [ ] SubTask 3.2: 在 `static/app.js` 根据当前情绪等级高亮对应说明并展示操作建议
  - [ ] SubTask 3.3: 在 `static/style.css` 实现等级说明卡片样式

- [ ] Task 4: 情绪低点次日表现图优化
  - [ ] SubTask 4.1: 在 `static/app.js` 的 `renderLowNext` 中增加「冰点次日平均涨幅」基准虚线标注
  - [ ] SubTask 4.2: 在 tooltip 中增加与平均涨幅的差值提示

# Task Dependencies
- Task 1、Task 2、Task 3、Task 4 互相独立，可并行
