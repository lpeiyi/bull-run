# 市场概览页三类问题修复 Spec（fix-overview-sentiment-kline-issues）

## Why
市场概览页存在三个问题：①短线情绪卡片当日数据来源用东财涨停池+新浪跌停，口径与开盘啦不一致（涨停 83 vs 52、跌停 0 vs 8、炸板率 6.7% vs 28%、最高 7板 vs 4板），导致情绪分算错为 71（正确约 50）；而历史情绪走乐咕 API 口径正确，两者割裂。②自选K线弹窗副图高度 12% 太窄，成交量和 KDJ 看着逼仄。③指数K线卡片成交量副图 Y 轴 `splitNumber:2` + `splitLine:{show:false}` 导致刻度显示不全。

## What Changes
- **修正当日情绪数据来源**：`get_sentiment()` 的涨停/跌停/炸板数从东财+新浪改为优先走乐咕 API（`legu.fetch_legu_history()` 取最后一日），东财仅补充连板高度和晋级率。保证当日与历史口径一致。
- **K线弹窗副图加高**：`renderWatchKline()` 的 grid 布局从主图 50% / 成交量 12% / KDJ 12% 调整为主图 46% / 成交量 15% / KDJ 15%，总高度利用更充分。
- **指数K线副图 Y 轴刻度修复**：`renderIndexKline()` 的成交量副图 yAxis 从 `splitNumber:2` 改为 `splitNumber:3`，并移除 `splitLine:{show:false}` 改为 `splitLine:{show:true}`（或保留 false 但增加 splitNumber），确保刻度数字不被截断。

## Impact
- Affected code:
  - `core/sentiment.py`：`get_sentiment()` 函数重构数据来源
  - `static/app.js`：`renderWatchKline()` grid 高度调整 + `renderIndexKline()` yAxis 调整
- Non-affected: `app.py`、`core/legu.py`、`core/emotion_history.py` 不改动

## ADDED Requirements

### Requirement: 当日情绪数据来源与历史一致
`get_sentiment()` SHALL 优先使用乐咕 API（`legu.fetch_legu_history()` 最后一日）获取涨停/跌停/炸板数和炸板率，保证与历史情绪序列（`get_emotion_trend()`）口径完全一致。东财涨停池仅用于补充连板高度（`max_height`）和晋级率（`promo_rate`）。

#### Scenario: 交易时段获取当日情绪
- **WHEN** 用户在交易时段查看情绪卡片
- **THEN** 涨停/跌停/炸板数来自乐咕 API（与开盘啦口径一致）
- **AND** 连板高度和晋级率来自东财涨停池（补充因子）
- **AND** 情绪分由 `_calc_score(zt_n, dt_n, max_height, promo_rate, break_rate)` 计算
- **AND** 五维度贡献明细正常显示

#### Scenario: 乐咕 API 失败时回退
- **WHEN** 乐咕 API 请求失败或当日数据为空
- **THEN** 回退到原东财+新浪逻辑（保证可用性）
- **AND** console 输出 warning 日志

#### Scenario: 当日与历史口径一致
- **WHEN** 对比当日情绪分和历史曲线最后一天
- **THEN** 两者涨停/跌停/炸板数一致（同一数据源）
- **AND** 情绪分计算公式一致

### Requirement: K线弹窗副图高度充足
`renderWatchKline()` 的三 grid 布局 SHALL 给成交量和 KDJ 副图足够高度，不逼仄。

#### Scenario: 副图可读
- **WHEN** 打开自选K线弹窗
- **THEN** 成交量副图高度约 15%（原 12%）
- **AND** KDJ 副图高度约 15%（原 12%）
- **AND** 主图仍占主导（约 46%）

### Requirement: 指数K线副图 Y 轴刻度完整
`renderIndexKline()` 的成交量副图 yAxis SHALL 显示完整的 Y 轴刻度，不被截断。

#### Scenario: Y 轴刻度可读
- **WHEN** 打开指数K线卡片
- **THEN** 成交量副图左侧 Y 轴显示 3 个刻度（上/中/下）
- **AND** 刻度数字完整显示（不被遮挡或截断）

## MODIFIED Requirements

### Requirement: get_sentiment 数据来源（原东财+新浪）
原 `get_sentiment()` 涨停数 `_zt_codes()` 走东财 `getTopicZTPool`、跌停数 `_dt_count()` 走新浪 `_dt_list_sina()` 或东财 `getTopicDTPool`、炸板数 `_zb_count()` 走东财 `getTopicZBPool`。修改为：涨停/跌停/炸板数优先走乐咕 `fetch_legu_history()` 最后一日，东财仅补充连板高度和晋级率。

## Constraints
- **乐咕 API 依赖**：`core/legu.py` 已实现 `fetch_legu_history()`，有当日缓存，不修改
- **后端改动范围**：仅改 `core/sentiment.py` 的 `get_sentiment()` 函数 + `static/app.js` 两个渲染函数
- **回退机制**：乐咕失败时回退原东财+新浪逻辑，保证可用性
- **不修改 app.py**：`app.py` 的 `/api/sentiment` 路由不改
