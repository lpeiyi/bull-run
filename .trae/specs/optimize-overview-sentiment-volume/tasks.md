# Tasks

- [x] Task 1: 验证乐咕乐股 API 实际数据起始时间并更新 UI 标签
  - [x] SubTask 1.1: 用 Python 直接调用 `legu.fetch_legu_history(force=True)`，打印返回列表的首条日期，确认实际起始时间（预期 2022-08-03 或更早）
  - [x] SubTask 1.2: 若起始时间晚于 2020-02-03，更新 `templates/index.html` 中 `#ln-days` 的「全部(2020至今)」按钮文案为「全部(2022至今)」或动态从 API 获取实际起始年月；若起始时间确实是 2020-02-03，则需排查为何 2022-08-03 之前样本为空（可能是 _calc_score 对早期数据计算异常）
  - [x] SubTask 1.3: 若数据确实从 2020-02-03 开始但冰点日为空，检查 `get_low_points` 返回的冰点日列表，确认 2022-08-03 之前是否有 score <= threshold 的日期（可能是早期涨停家数极少导致情绪分极低，但被 threshold=30 漏过）

- [x] Task 2: 情绪分日内定时刷新（每 5 分钟）
  - [x] SubTask 2.1: 在 `static/app.js` 中新增 `loadSentimentQuick()` 函数：调用 `/api/sentiment`（无缓存的实时接口），仅更新 #se-score / #se-level / #se-dims / #se-contrib，不重新渲染 #emotion-chart 走势大图、不调用 loadSentiment()
  - [x] SubTask 2.2: 在 `doFastRefresh()` 中追加 `loadSentimentQuick()` 调用（fast=60s 档每次都会调，但 /api/sentiment 后端无缓存每次都是实时计算，60s 刷新一次情绪分是合理的，比用户要求的 5 分钟更频繁）
  - [x] SubTask 2.3: 确认 `sentiment.get_sentiment()` 在交易时段能返回当日实时数据（涨停/跌停/炸板等池数据是东财实时接口），非交易时段返回最近交易日数据

- [x] Task 3: 修复量能预测早盘过大问题（后端 market.py）
  - [x] SubTask 3.1: 在 `core/market.py` 的 `get_liangneng()` 中，当 `w_ratio < 0.05`（约开盘 10 分钟内）时，predict = actual，不进行外推；change_pct = None
  - [x] SubTask 3.2: 在分时曲线循环中（L393-401），当 `w = _intraday_cum_weight(e)` 的值 < 0.05 时，`pred = cum`（不外推），`chg = null`（前端显示空值）
  - [x] SubTask 3.3: 确认 py_compile 通过，重启 Flask 后 curl `/api/liangneng` 验证 9:30-9:40 期间 predict=actual、change_pct=null

- [x] Task 4: 前端量能展示适配空值
  - [x] SubTask 4.1: 确认 `static/app.js` 的 `loadLiangneng()` 在 `d.change_pct == null` 时已正确显示 `--`（现有代码 L890-893 已处理），无需改动
  - [x] SubTask 4.2: 确认 `buildIntradayOption` 的 series.data 和 tooltip formatter 能正确处理 null 值（现有 connectNulls=false 逻辑已处理），无需改动

- [x] Task 5: 重启 Flask 服务并在浏览器中验证三项修复
  - [x] SubTask 5.1: 重启 Flask，curl 验证 `/api/liangneng` 在盘前/盘后 change_pct 行为
  - [x] SubTask 5.2: 浏览器验证情绪低点「全部」窗口标签文案、情绪分每分钟自动刷新、量能早盘不再出现极端预测值

# V3 追加优化任务

- [x] Task 6: 情绪走势图最大时间窗口改为近3年
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - 将 `templates/index.html` 中「情绪×指数走势」区域（#se-days，L142-148）的 `data-days="0"`「全部(2020至今)」按钮，改为 `data-days="750"`「近3年」。750 个交易日 ≈ 3 年（250/年），落在 kline() 内部 1000 硬编码上限以内，不会留白。
    - 检查并调整「情绪低点次日表现」区域同名按钮（L160-166 `#ln-days`）：低点区域已经通过 Task 1 把 _SINA_KLINE_MAX 提到 2000，kline_range 可覆盖到 2014 年，此处可选：①保持「全部(2020至今)」不变或②也改为「近3年」。实现阶段根据实际加载速度判断，若全部模式速度可接受则保留全部（因为数据确实有了），否则改近3年。
    - 注：不要修改低点表格里真实样本日期（376个冰点日从2020-02-03起），只改按钮 label/value。
  - **Acceptance Criteria Addressed**: AC-V3-1（情绪×指数走势图最大时间窗口=近3年）
  - **Test Requirements**:
    - `programmatic` TR-6.1: Grep `templates/index.html` 确认情绪走势图区域 #se-days 的最长按钮 `data-days=="750"` 且文案包含「近3年」。
    - `programmatic` TR-6.2: 重启 Flask 后 curl `/api/emotion_trend?days=750`，返回 `dates` 列表长度 ≥ 750 且首条日期距 2020-01 不早于 3 年跨度。
    - `human-judgement` TR-6.3: 浏览器打开概览页，点击「近3年」按钮，观察 #emotion-chart 最左侧指数曲线有值，没有 30%+ 留白。
  - **Notes**: 如果低点区域选择保留「全部(2020至今)」，需确认点击后 index_compare 或低点表格首条仍正确渲染，不要因为 kline() 1000 上限而报错。

- [x] Task 7: 量能预测算法重做（对齐开盘啦曲线形状）
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 改 `_INTRADAY_SEG_WEIGHTS` 常量：从 `(0.15, 0.13, 0.11, 0.11, 0.11, 0.11, 0.13, 0.15)` 改为 `(0.22, 0.14, 0.10, 0.09, 0.09, 0.11, 0.12, 0.13)`，加和验证为 1.00（8 段 × 30 分钟 = 240）。
    - Step 2. 在 `_intraday_cum_weight(elapsed_min)` 中对段 1（seg==0，9:30-10:00）前段 10 分钟施加「集合竞价+开盘放量」非线性插值：
      - offset ∈ [0,10]：seg_frac = 0.45 × (offset/10.0)（即 0~10 分钟累积占段1的 45%）
      - offset ∈ [10,30]：seg_frac = 0.45 + 0.55 × ((offset-10)/20.0)（10~30 分钟线性从 45% 过渡到 100%）
      - 其它段不变（seg_frac = offset/30.0）
      - 最终 cum 返回保留 6 位小数精度。
    - Step 3. 撤回 `get_liangneng()` 中的 V2 三档分支：删除 `w_ratio < 0.05 → change_pct=None` 分支，改为两档：盘中（0 < w_ratio < 1）统一用 `predict = actual / w_ratio`、change_pct 正常计算；盘后/非交易（w_ratio 为 None 或 ≥ 1）保持 predict=actual + actual vs yesterday 涨跌幅。
    - Step 4. 撤回分时循环（原 SubTask 3.2）的 w<0.05 保护：删除 `if w >= 0.05` 分支判断，统一 `pred = cum / w（w>0 时）否则 pred=cum`，chg 正常计算。
    - Step 5. py_compile 验证语法通过。
  - **Acceptance Criteria Addressed**: AC-V3-2（量能曲线对齐开盘啦）、覆盖 V2 早盘合理性。
  - **Test Requirements**:
    - `programmatic` TR-7.1: 纯函数调用验证 `_intraday_cum_weight`：
      - e=1 → 结果 ∈ [0.008, 0.03]（约 0.0099 = 0.22 × 0.45 × 1/10）
      - e=5 → 结果 ≈ 0.0495 ±0.001
      - e=10 → 结果 ≈ 0.099 ±0.001
      - e=15 → 结果 ≈ 0.1293 ±0.001
      - e=30 → 结果 = 0.22（无误差）
      - e=60 → 结果 ≈ 0.22+0.14 = 0.36
      - e=240 → 结果 = 1.0
    - `programmatic` TR-7.2: py_compile `core/market.py` exit=0。
    - `programmatic` TR-7.3: 重启 Flask，curl `/api/liangneng`，检查 intraday 前 10 项 chg 均不为 null 且绝对值 < 80（不再出现 500%+ 极端值）。
    - `human-judgement` TR-7.4: 浏览器打开量能卡片，目视今日（或昨日若已收盘）橙色预测曲线 9:30 有起点、中间 9:30-10:00 有向下修正段、10:00 后整体上升，无大片空白断点，效果接近开盘啦截图。
  - **Notes**: 段1非线性插值可能导致段1曲线相对段2的斜率看起来不够平滑，但实际 A 股开盘就是量能暴增，分段差异是合理的。如果用户后续反馈"段1→段2切换太突兀"再考虑加更细粒度二次插值。

- [x] Task 8: 历史量能回看至少 1 个月
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 找出所有调用 `get_liangneng()` 的地方（`app.py` 路由 `/api/liangneng` 为主），将默认 days 从 20 提升到 40（约 2 个月交易日）。如果路由不传 days 是调用处传默认值，则在 `app.py` 的 `jsonify(market.get_liangneng(days=40))` 显式传 40。
    - Step 2. 测试 `_em_index_amount` 历史接口在 days=40 时实际返回多少天（有的接口会被限流/反爬截断到近几天）。如果东财返回 < 22 天，进入 Step 3。
    - Step 3. 在 `get_liangneng(days=40)` 内部拼接本地 `_load_amount_cache()` 的缓存：先拿到 em 接口返回的 `{date: amount_yi}`，再合并本地缓存 dict（em 数据优先，只补 em 没覆盖的更早日期），合并后按日期排序，取尾部 days=40 返回。注意 merged dict 的 key 格式要统一（Y-m-d 或 Ymd 选其一，别混用导致 merge 失败）。
    - Step 4. 验证：无论东财是否截断，历史量能模式（buildHistoryOption）柱子数量 ≥ 22。
  - **Acceptance Criteria Addressed**: AC-V3-3（历史量能 ≥ 1 个月）。
  - **Test Requirements**:
    - `programmatic` TR-8.1: curl `/api/liangneng`，返回的 `rows`/`history` 列表长度 ≥ 22；如果 key 不同名（可能是 `rows`、`history`、`bars`），先检查 API 实际 schema。
    - `programmatic` TR-8.2: 即使 Eastmoney 历史接口只返回 3 天（通过 mock：注释掉 _em_index_amount 调试验），本地缓存兜底后最终列表长度 ≥ 22。
    - `human-judgement` TR-8.3: 浏览器切换到「历史量能」模式，柱子视觉上能看到 ≥ 22 根，日期跨度至少覆盖 1 个月前的日期，不止停留在 8/24。
  - **Notes**: `_save_amount_cache` 是在盘后(>=15:00)写入当日全天成交额，amount_history.json 如果只有几天历史，就先以现有东财历史接口 + 缓存实际合并结果为准；保证 40 天请求的返回至少包含东财历史 + 本地累积两者的并集，后续每天盘后自动扩充。若当前缓存特别短，短期（1-2天）表现是历史量能只有接口返回的 20+ 天，这是正常的，实现时只需确保"取并集 + 至少接口端能拿到 22+ 天"。

- [x] Task 9: 重启 Flask + 浏览器统一验证 V3 三项
  - **Priority**: high
  - **Depends On**: Task 6, Task 7, Task 8
  - **Description**:
    - 终止旧 Flask，重新启动；curl 三个关键接口 `/api/emotion_trend?days=750`、`/api/liangneng`、`/api/emotion_low_next?days=750` 无 500。
    - 浏览器自动化验证：情绪走势图「近3年」按钮点后曲线满屏、量能预测曲线形状与开盘啦一致（至少无 null 断点、起点有值）、历史量能柱子 ≥ 22。
    - 控制台无 JS 报错。
  - **Acceptance Criteria Addressed**: AC-V3-1、AC-V3-2、AC-V3-3 的浏览器部分。
  - **Test Requirements**:
    - `programmatic` TR-9.1: Flask 日志 3 个接口 HTTP status 都是 200。
    - `human-judgement` TR-9.2: 浏览器三项截图（情绪走势、量能曲线、历史量能柱子）目视通过。
    - `programmatic` TR-9.3: 控制台 Console messages 中没有 error 级别。

# V4 继续优化任务

- [x] Task 10: 量能预测算法彻底重做（线性外推 + 前 20 分钟抑制）
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 删除 U 型权重相关代码：`_INTRADAY_SEG_WEIGHTS` 常量、`_intraday_cum_weight()` 函数、`_intraday_weight_ratio()` 函数（V3 的核心算法，V4 彻底弃用）。
    - Step 2. 在 `get_liangneng()` 的预测分支中，改用已有的 `_trade_elapsed_ratio(now)`（线性时间占比 = elapsed/240）替代 `_intraday_weight_ratio(now)`：
      - `w_ratio` 为 None 或 ≥ 1（非交易/盘后）：predict = actual，change_pct = actual vs yesterday
      - `w_ratio < 20/240`（前 20 分钟）：predict = None，change_pct = None
      - `20/240 ≤ w_ratio < 1`（20 分钟后至收盘）：predict = actual / w_ratio = actual × 240 / elapsed，change_pct 正常计算
    - Step 3. 在分时曲线循环中，将 `_intraday_cum_weight(e)` 替换为线性 `e / 240.0`：
      - `e < 20`：chg = null（曲线断点，前端 connectNulls=false 显示空白）
      - `e ≥ 20`：pred = cum / (e/240) = cum × 240 / e，chg = (pred/yesterday - 1) × 100
      - 盘后/非交易：保持现有逻辑不变
    - Step 4. py_compile 验证语法通过。
  - **Acceptance Criteria Addressed**: AC-V4-量能预测线性外推
  - **Test Requirements**:
    - `programmatic` TR-10.1: Grep 确认 `_INTRADAY_SEG_WEIGHTS`、`_intraday_cum_weight`、`_intraday_weight_ratio` 在 `core/market.py` 中已删除。
    - `programmatic` TR-10.2: py_compile `core/market.py` exit=0。
    - `programmatic` TR-10.3: 重启 Flask，curl `/api/liangneng`，检查：若盘后则 change_pct 为实际涨跌幅（非 null）；若盘中 elapsed < 20 分钟则 change_pct = null；若盘中 elapsed ≥ 20 分钟则 change_pct 绝对值 < 30%。
    - `programmatic` TR-10.4: curl `/api/liangneng` 的 intraday 列表，前 20 分钟（0931-0950）的 chg 均为 null；20 分钟后的 chg 均为 float 且绝对值 < 30%。
  - **Notes**: 线性外推公式与同花顺 `VOL × 241 / FROMOPEN` 一致（本项目用 240 而非 241，差异可忽略）。前 20 分钟抑制是行业标配做法，非本项目独有。删除 U 型权重函数后，确保没有其他地方引用它们。

- [x] Task 11: 历史量能增加新浪 K 线数据源
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 在 `core/market.py` 中新增 `_sina_index_amount(code, days)` 函数：调用 `core.data.kline(code, days=days+10)` 获取 DataFrame，提取 `date` 和 `volume` 字段。指数的 volume 即成交额（单位：元），转成 `amount_yi = round(volume / 1e8, 2)`。返回 `[{date: 'YYYY-MM-DD', amount_yi}]` 升序列表。
    - Step 2. 在 `get_liangneng()` 中，新增调用 `_sina_index_amount("sh000001", days)` 和 `_sina_index_amount("sz399001", days)`，将其结果与东财 `em` dict 合并（同日相加，与东财+本地缓存合并逻辑一致）。
    - Step 3. 验证：即使东财返回 0 条，新浪 + 本地缓存合并后历史柱子 ≥ 22 根。
  - **Acceptance Criteria Addressed**: AC-V4-历史量能新浪源
  - **Test Requirements**:
    - `programmatic` TR-11.1: curl `/api/liangneng`，返回的 `trend` 列表长度 ≥ 22。
    - `programmatic` TR-11.2: 新浪 K 线 `kline("sh000001", days=50)` 返回的 DataFrame 中 `volume` 列均为正数（非 0/非 NaN）。
  - **Notes**: 新浪 K 线的 volume 字段对指数而言是成交额（元），不是成交量（手）。需在实现时验证此假设；若 volume 单位不符，需要调整转换系数。`kline()` 函数已有重试和反爬处理，稳定性较好。

- [x] Task 12: 行业板块数据源切换为东财主源
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 在 `core/market.py` 的 `get_boards()` 函数中，将东财 `_parse_em()` 从备用源提升为主源：先调用 `_parse_em("m:90+t:2")` 获取行业板块、`_parse_em("m:90+t:3")` 获取概念板块；若东财返回空列表则回退新浪 `_parse_sina()`。
    - Step 2. 在 `_parse_em()` 的 `fields` 参数中增加 `f6`（成交额），使返回数据包含成交额信息。
    - Step 3. 验证东财返回的 `f3` 涨跌幅数值与东财网站行业板块页面一致（需对比抽查 2-3 个板块）。
  - **Acceptance Criteria Addressed**: AC-V4-行业板块东财主源
  - **Test Requirements**:
    - `programmatic` TR-12.1: curl `/api/overview`，返回的 `boards.industry` 列表长度 > 0 且每项含 `avg_pct` 字段为 float。
    - `programmatic` TR-12.2: Grep `core/market.py` 确认 `get_boards()` 中 `_parse_em()` 调用在 `_parse_sina()` 之前（东财为主源）。
    - `human-judgement` TR-12.3: 浏览器查看行业领涨 Top10，涨跌幅数值与东财网站行业板块页面抽查一致（允许 ±0.01% 误差）。
  - **Notes**: 东财 `f3` 返回的是板块指数涨跌幅（非个股平均涨幅），与东财网站一致。新浪 `avg_pct` 是个股算术平均涨幅，两者口径不同导致数据不一致。切换后前端 `renderBoardsTop10()` 无需改动（字段名 `avg_pct` 不变）。

- [x] Task 13: 重启 Flask + 浏览器统一验证 V4 三项
  - **Priority**: high
  - **Depends On**: Task 10, Task 11, Task 12
  - **Description**:
    - 终止旧 Flask，重新启动；curl `/api/liangneng`、`/api/overview` 无 500。
    - 浏览器自动化验证：量能卡片前 20 分钟显示 `--`、20 分钟后预测合理（±30%）、历史量能 ≥ 22 根柱子、行业 Top10 与东财一致。
    - 控制台无 JS 报错。
  - **Acceptance Criteria Addressed**: AC-V4 全部浏览器部分
  - **Test Requirements**:
    - `programmatic` TR-13.1: Flask 日志接口 HTTP status 都是 200。
    - `human-judgement` TR-13.2: 浏览器三项截图目视通过。
    - `programmatic` TR-13.3: 控制台 Console messages 中没有 error 级别。

# Task Dependencies
- Task 1 独立
- Task 2 独立
- Task 3 独立
- Task 4 依赖 Task 3（后端改完前端才适配）
- Task 5 依赖 Task 1-4 全部完成
- Task 6/7/8 相互独立
- Task 9 依赖 Task 6/7/8 全部完成
- Task 10/11/12 相互独立
- Task 13 依赖 Task 10/11/12 全部完成

# V5 量能曲线对齐开盘啦 App 任务

- [x] Task 14: 实现 KPL 校准累积权重函数 `_kpl_cum_weight` 与 `_elapsed_min_by_datetime`
  - **Priority**: high
  - **Depends On**: None
  - **Description**:
    - Step 1. 在 `core/market.py` 中新增常量：
      ```
      _KPL_ANCHORS = [
          (0,   0.0010),  # 保护点：避免除零
          (1,   0.0354),  # 8/28 真实 cum=887.76 × 截图 r=+17.94 反推 0.03541
          (5,   0.1061),  # 8/28 真实 cum=2458.32 × r=+8.97 反推 0.10612
          (15,  0.2229),  # 8/28 真实 cum=4951.61 × r=+4.50 反推 0.22289（新锚点保证 09:30-10:00 下探段平滑）
          (30,  0.3305),  # 反推 0.33048（r=+4.00）
          (60,  0.4849),  # 反推 0.48489（r=+1.00）
          (120, 0.6729),  # 反推 0.67288（r=−0.50）
          (180, 0.8325),  # 反推 0.83254（r=−3.00）
          (240, 1.0000),  # 收盘约束 =1
      ]
      ```
    - Step 2. 新增 `_kpl_cum_weight(elapsed_min)` 函数：
      - e <= 0 → 返回 0.001（保证 >0）
      - e >= 240 → 返回 1.000
      - 否则在 `_KPL_ANCHORS` 上找相邻两点（按 e 升序已排好）做线性插值：
        `w = w_lo + (w_hi - w_lo) * (e - e_lo) / max(1, e_hi - e_lo)`
      - 返回值夹到 [0.001, 1.000]
    - Step 3. 新增 `_elapsed_min_by_datetime(now)` 函数（返回整数分钟或 None）：
      - 周末（weekday>=5）→ None
      - t = now.hour*60 + now.minute
      - t < 9*60+30 → None；9:30<=t<=11:30 → t - 570
      - 11:30<t<13:00 → 120；13:00<=t<=15:00 → 120 + (t-780)
      - t>15:00 → 240
  - **Acceptance Criteria Addressed**: AC-V5-首点/衰减、反推基准点验收
  - **Test Requirements**:
    - `programmatic` TR-14.1: 纯函数调用（精度 ±0.005 除特别声明）：
      - `_kpl_cum_weight(1)` = 0.0354 ± 0.002
      - `_kpl_cum_weight(5)` = 0.1061 ± 0.002
      - `_kpl_cum_weight(15)` = 0.2229 ± 0.005
      - `_kpl_cum_weight(30)` = 0.3305 ± 0.005
      - `_kpl_cum_weight(60)` = 0.4849 ± 0.005
      - `_kpl_cum_weight(120)` = 0.6729 ± 0.005
      - `_kpl_cum_weight(180)` = 0.8325 ± 0.005
      - `_kpl_cum_weight(240)` = 1.000
      - 边界：`_kpl_cum_weight(0) ≤ 0.002`；`_kpl_cum_weight(500)` = 1.000
    - `programmatic` TR-14.2: py_compile `core/market.py` exit=0

- [x] Task 15: 重写 `get_liangneng()` 预测分支与分时循环（V5 KPL 权重 + ±30% clamp）
  - **Priority**: high
  - **Depends On**: Task 14
  - **Description**:
    - Step 1. 卡片 predict/change_pct 分支重写：
      - `elapsed = _elapsed_min_by_datetime(now)`
      - 若 `elapsed is None` 或 `elapsed >= 240` → 非交易/盘后：`predict = actual`，`change_pct = round((actual / yesterday - 1) * 100, 2)`
      - 否则盘中：`w_kpl = _kpl_cum_weight(elapsed)`；`predict = round(actual / w_kpl, 2)`；`change_pct = round((predict / yesterday - 1) * 100, 2)`
      - clamp / 兜底：
        - 若 yesterday 为 0/None/NaN → change_pct = None，predict = actual
        - 若 predict/change_pct 计算出现非有限值（isinf/isnan）→ change_pct = None，predict = actual
        - 否则 change_pct = min(+30.0, max(-30.0, change_pct))
      - `change_abs = round(predict - yesterday, 2)`（predict/yesterday 任一 None → None）
      - 删除 V4 `w_ratio < 20/240 → change_pct=None` 分支；删除 `_trade_elapsed_ratio(now)` 在该函数体内的调用。
    - Step 2. 分时 intraday 循环重写：
      - 对每分钟 e=_elapsed_min(t)，e<=0 跳过；
      - cum = sh_min[t]+sz_min[t]；w_kpl = _kpl_cum_weight(e)；pred = cum / w_kpl；chg = (pred / yesterday - 1) * 100
      - 若 yesterday 为 0/None 或 chg 非有限 → chg = None（兜底）；否则 chg = round(min(+30.0, max(-30.0, chg)), 2)
      - 删除 V4 `e < 20 → chg=None` 分支。
    - Step 3. 盘后 15:00 补末点行（保持现有）。
    - Step 4. py_compile 通过。
  - **Acceptance Criteria Addressed**: AC-V5 全部
  - **Test Requirements**:
    - `programmatic` TR-15.1: py_compile exit=0
    - `programmatic` TR-15.2: grep `get_liangneng()` 函数体确认 `_trade_elapsed_ratio` 零命中；确认字符串 `e < 20` 零命中（或不是 chg=null 分支）
    - `programmatic` TR-15.3: mock 08-28 各点（yesterday=21259，使用真实 cum：e=1→887.76、e=5→2458.32、e=15→4951.61、e=30→7306.76、e=60→10411.33、e=120→14233.29、e=180→17168.06、e=240→21017.15）分别调用 KPL 权重+clamp：
      - e=1  chg ∈ [+10, +25]（实际值应为 +17.96）
      - e=5  chg ∈ [+5, +13]（实际值应为 +8.99）
      - e=15 chg ∈ [+2, +7] （实际值应为 +4.49）
      - e=30 chg ∈ [-2, +8] （实际值应为 +3.99）
      - e=60 chg ∈ [-4, +5] （实际值应为 +1.00）
      - e=120 chg ∈ [-5, +3]（实际值应为 −0.50）
      - e=180 chg ∈ [-6, +0]（实际值应为 −2.99）
      - abs(chg(240) - (-1.14)) < 3（实际值应为 −1.14，精确命中）
    - `programmatic` TR-15.4: 极端 clamp：
      - yesterday=21259, cum=0 → chg = -30
      - yesterday=21259, e=1, cum=4500 (10×) → pred=225000, chg≈(225000/21259-1)×100 ≈ 958% → clamp 到 +30
      - yesterday=None → chg=None、接口不崩
    - `programmatic` TR-15.5: 单调衰减：mock 08-28 中 chg(1) > chg(5) > chg(30) > chg(120)（相邻不严格但总体下降）

- [x] Task 16: 重启 Flask + curl + 浏览器验证 V5（V5.1 最终反推锚点）
  - **Priority**: high
  - **Depends On**: Task 14, Task 15
  - **Description**:
    - Step 1. netstat -ano|findstr :8000 找 LISTENING PID → taskkill /PID <pid> /F → 重新启动 Flask（`python app.py`）。
    - Step 2. curl `http://127.0.0.1:8000/api/liangneng`：
      - 检查 `intraday` 所有 chg 都不是 null；首点（09:31 若存在）绝对值 < 30；曲线总体从首点衰减到收盘值（首点>末点对 08-28 缩量日）。
      - `change_pct` 若不为 null 则 ∈ [-30, +30]；盘后 `change_pct` 等于 (actual/yesterday-1)*100（08-28 = -1.14 ±1）。
    - Step 3. 浏览器验证：
      - 量能卡片文字不显示 `-- --%` 空值。
      - 橙色预测曲线：9:30 附近有高点（+10~+25%）、随后快速衰减、10:00 后在 0 附近小波动、午后下穿 0 到 -3% 区间振荡、15:00 收敛到 ≈-1.14%。形状与开盘啦截图走势一致（衰减方向一致即可，分钟级采样不要求逐点相同）。
      - Console 无 error。
  - **Acceptance Criteria Addressed**: AC-V5 浏览器验收部分
  - **Test Requirements**:
    - `programmatic` TR-16.1: curl intraday list 所有 `chg != null` 且 len >= 200
    - `programmatic` TR-16.2: curl `change_pct` ∈ [-30, +30]（若非 null）
    - `human-judgement` TR-16.3: 浏览器橙色曲线符合「尖峰→快速下探→缓慢衰减→0 附近振荡→末端收敛」的开盘啦形态。
    - `programmatic` TR-16.4: Console messages 无 error 级别
