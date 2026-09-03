# Tasks

- [x] Task 1: 修正 `get_sentiment()` 当日数据来源为乐咕 API
  - [ ] SubTask 1.1: 在 `core/sentiment.py` 顶部导入 `from core import legu`（或 `from core.legu import fetch_legu_history`）
  - [ ] SubTask 1.2: 在 `get_sentiment()` 函数内，原 `zt_codes, max_height = _zt_codes(date)` / `zb_n = _zb_count(date)` / `dt_n = _dt_count(date)` 三行改为：
    - 优先调用 `legu.fetch_legu_history()` 取最后一行（`rows[-1]`），从中取 `zt_count` / `dt_count` / `zb_count` / `break_rate`
    - 东财仅取连板高度和晋级率：`zt_codes, max_height = _zt_codes(date)` / `promo_rate = _promo_rate(date, zt_codes)`
    - 如果乐咕返回空或失败（`rows` 为空或 `rows[-1]` 无数据），回退原逻辑（东财取涨停/炸板 + 新浪取跌停）
  - [ ] SubTask 1.3: 确保回退逻辑用 try/except 包裹，乐咕失败时 `import logging; logging.warning("乐咕 API 失败，回退东财+新浪")` 后执行原逻辑
  - [ ] SubTask 1.4: 返回 dict 的 `trade_date` 字段仍用乐咕返回的 `date`（YYYYMMDD 格式），保证与历史一致

- [x] Task 2: 调整 `renderWatchKline()` 三 grid 布局高度
  - [ ] SubTask 2.1: 修改 `static/app.js` 中 `renderWatchKline` 函数的 grid 数组：
    - grid[0]: `{ left: 52, right: 20, top: 30, height: "46%" }`（原 "50%"）
    - grid[1]: `{ left: 52, right: 20, top: "64%", height: "15%" }`（原 "66%"/"12%"）
    - grid[2]: `{ left: 52, right: 20, top: "81%", height: "15%" }`（原 "82%"/"12%"）

- [x] Task 3: 修复 `renderIndexKline()` 成交量副图 Y 轴刻度不全
  - [ ] SubTask 3.1: 修改 `static/app.js` 中 `renderIndexKline` 函数的 yAxis 第 2 个元素（成交量副图）：
    - 原: `{ type: "value", gridIndex: 1, splitNumber: 2, axisLabel: { color: "#8ba0c9", formatter: volFmt }, splitLine: { show: false } }`
    - 改: `{ type: "value", gridIndex: 1, splitNumber: 3, axisLabel: { color: "#8ba0c9", formatter: volFmt }, splitLine: { show: false } }`
    - 即 `splitNumber` 从 2 改为 3，刻度更密集，确保上/中/下三个刻度都能显示

# Task Dependencies
- Task 1 独立（后端 sentiment.py）
- Task 2 独立（前端 app.js renderWatchKline）
- Task 3 独立（前端 app.js renderIndexKline）
- 三者互相无依赖，可并行实施
