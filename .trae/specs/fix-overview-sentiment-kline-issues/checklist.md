# Checklist

## Task 1: get_sentiment 数据来源修正

- [x] Checkpoint 1: 乐咕 API 优先
  - [x] 1.1 `core/sentiment.py` 顶部存在 `from core import legu`（L20）
  - [x] 1.2 `get_sentiment()` 内调用 `legu.fetch_legu_history()` 取最后一行（L193-195）
  - [x] 1.3 涨停数 `zt_n` 来自乐咕 `last.get("zt_count", 0)`（L196）
  - [x] 1.4 跌停数 `dt_n` 来自乐咕 `last.get("dt_count", 0)`（L197）
  - [x] 1.5 炸板数 `zb_n` 来自乐咕 `last.get("zb_count", 0)`（L198）
  - [x] 1.6 炸板率 `break_rate` 来自乐咕 `last.get("break_rate", 0.0)`（L199）

- [x] Checkpoint 2: 东财补充连板高度和晋级率
  - [x] 2.1 `max_height` 仍来自东财 `_zt_codes(date)`（L206）
  - [x] 2.2 `promo_rate` 仍来自东财 `_promo_rate(date, zt_codes)`（L207）

- [x] Checkpoint 3: 回退机制
  - [x] 3.1 乐咕失败时（rows 为空或异常）回退原东财+新浪逻辑（L210-214）
  - [x] 3.2 回退时输出 `logging.warning` 日志（L203）
  - [x] 3.3 回退时返回结构不变（dict 字段完整）

- [x] Checkpoint 4: 返回值一致性
  - [x] 4.1 `trade_date` 来自乐咕返回的 `date`（YYYYMMDD 格式）（L200）
  - [x] 4.2 返回 dict 字段完整：`score, level, trade_date, zt_count, dt_count, zb_count, break_rate, promo_rate, max_height, contributions`（L218-222）

## Task 2: K线弹窗副图高度

- [x] Checkpoint 5: renderWatchKline grid 高度调整
  - [x] 5.1 grid[0] height 改为 "46%"（L1766）
  - [x] 5.2 grid[1] top 改为 "64%", height 改为 "15%"（L1767）
  - [x] 5.3 grid[2] top 改为 "81%", height 改为 "15%"（L1768）

## Task 3: 指数K线副图 Y 轴刻度

- [x] Checkpoint 6: renderIndexKline yAxis 刻度修复
  - [x] 6.1 yAxis[1]（成交量副图）的 `splitNumber` 改为 3（L855）
  - [x] 6.2 `splitLine` 保持 `show: false` 不变
  - [x] 6.3 其他属性（`gridIndex: 1`、`axisLabel`、`formatter: volFmt`）不变

## 整体验证

- [x] Checkpoint 7: 不修改 app.py 和 core/legu.py
  - [x] 7.1 `git diff --name-only app.py core/legu.py core/emotion_history.py` 输出为空
  - [x] 7.2 `core/sentiment.py` 仅 `get_sentiment()` 函数有改动（+顶部 import）
  - [x] 7.3 `static/app.js` 仅 `renderWatchKline` 和 `renderIndexKline` 两函数有改动
