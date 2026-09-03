# Tasks

- [x] Task 1: 测试乐咕 API 返回数据 + 修正情绪数据口径
  - [ ] SubTask 1.1: 用 Python 直接调用 `legu.fetch_legu_history(force=True)`，打印 `rows[-1]` 的日期和数据，确认是当日还是前一日数据
  - [ ] SubTask 1.2: 如果乐咕口径与东财一致（涨停 83 而非 52），则在 `get_sentiment()` 中对东财涨停池 `_zt_codes(date)` 返回的代码列表做过滤：
    - 排除 ST/*ST 股票（代码名称包含 ST）
    - 排除上市不足 60 日的新股
    - 过滤后 `zt_n = len(filtered_codes)`
    - `max_height` 基于过滤后的涨停池重新计算
  - [ ] SubTask 1.3: 同样对跌停数做过滤（如果走东财回退逻辑时）
  - [ ] SubTask 1.4: 如果乐咕返回的是前一日数据且口径正确（52），则保持当前逻辑不变（因为前一日的乐咕数据与开盘啦一致）

- [x] Task 2: 调整 renderWatchKline 三 grid 布局消除重叠
  - [ ] SubTask 2.1: 修改 `static/app.js` 中 `renderWatchKline` 的 grid 数组：
    - grid[0]: `{ left: 52, right: 20, top: 30, height: "50%" }`（原 "46%"）
    - grid[1]: `{ left: 52, right: 20, top: "66%", height: "15%" }`（原 "64%"/"15%"）
    - grid[2]: `{ left: 52, right: 20, top: "83%", height: "20%" }`（原 "81%"/"15%"）
    - 即主图 50% + 成交量 15%（top 66%）+ KDJ 20%（top 83%），段间距 1% 和 2%

- [x] Task 3: 修复 renderIndexKline 副图 Y 轴刻度不全
  - [ ] SubTask 3.1: 修改 `static/app.js` 中 `renderIndexKline` 的 grid 数组，增大 left：
    - grid[0]: `{ left: 65, right: 20, top: 30, height: "58%" }`（原 left: 52）
    - grid[1]: `{ left: 65, right: 20, top: "74%", height: "16%" }`（原 left: 52）
  - [ ] SubTask 3.2: 确认 yAxis[1] 的 `splitNumber: 3` 保持不变

# Task Dependencies
- Task 1 独立（后端测试+修正）
- Task 2 独立（前端 grid 调整）
- Task 3 独立（前端 left 调整）
- 三者互相无依赖，可并行实施
