# 追加优化 Spec（fix-overview-sentiment-kline-issues-v2）

## Why
fix-overview-sentiment-kline-issues 第一轮修复后三个问题仍未完全解决：①情绪数据来源修正未生效（涨停仍 83 而非 52），需定位根因。②K线弹窗三段 grid 间距过小（2%），KDJ 的 Y 轴 150 刻度与成交量 x 轴时间标签、Y 轴 0 值重叠。③指数K线副图 Y 轴 `splitNumber:3` 已改但 `left:52` 像素不够，刻度数字被截断。

## What Changes
- **问题一**：先测试乐咕 API `fetch_legu_history()` 返回的 `rows[-1]` 是当日还是前一日数据；如果乐咕口径与东财一致（都含 ST/新股），则在 `get_sentiment()` 中对东财涨停池做过滤（排除 ST/*ST/新股），对齐开盘啦口径
- **问题二**：调整三 grid 布局为主图 50% / 成交量 15% / KDJ 20%，增大段间距消除重叠
- **问题三**：增大 `renderIndexKline` 的 grid left 从 52 到 65 像素，确保刻度数字完整显示

## Impact
- Affected code: `core/sentiment.py`（问题一过滤逻辑）+ `static/app.js`（问题二 grid + 问题三 left）
- Non-affected: `app.py`、`core/legu.py`、`core/emotion_history.py`

## ADDED Requirements

### Requirement: 情绪数据对齐开盘啦口径
`get_sentiment()` SHALL 在获取涨停池数据后过滤掉 ST/*ST 股票和上市不足 60 日的新股，使涨停数对齐开盘啦口径（约 52 而非 83）。

#### Scenario: 涨停数过滤后对齐开盘啦
- **WHEN** 用户在交易时段查看情绪卡片
- **THEN** 涨停数排除 ST/*ST 和新股后约 52（原 83）
- **AND** 跌停数同样过滤
- **AND** 情绪分降至约 50（原 71）

### Requirement: K线弹窗三段 grid 不重叠
`renderWatchKline()` 的三 grid 布局 SHALL 增大段间距，KDJ Y 轴刻度不与成交量 x 轴重叠。

#### Scenario: 布局调整
- **WHEN** 打开 K 线弹窗
- **THEN** 主图 50% / 成交量 15% / KDJ 20%
- **AND** 三段间距充足，KDJ 的 150 刻度不与成交量 x 轴时间标签重叠

### Requirement: 指数K线副图 Y 轴刻度完整
`renderIndexKline()` 的成交量副图 SHALL 有足够 left 留白，刻度数字不被截断。

#### Scenario: 刻度完整显示
- **WHEN** 打开指数K线卡片
- **THEN** 成交量副图左侧 Y 轴刻度数字完整显示（如"12.34亿"不被截断）
- **AND** grid left 从 52 增大到 65 像素

## Constraints
- **最小改动**：问题一在 `get_sentiment()` 内追加过滤逻辑；问题二调 grid 参数；问题三调 left 参数
- **不修改 app.py / core/legu.py / core/emotion_history.py**
