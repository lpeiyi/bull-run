# 自选K线弹窗加KDJ副图 Spec（add-watchlist-kdj-subchart）

## Why
自选K线弹窗目前只有 K 线主图 + 成交量副图（双 grid 布局），缺少常用的 KDJ 超买超卖指标。加上 KDJ 后用户能在同一弹窗内判断短期买卖点，无需另开行情软件。

## What Changes
- **在 `renderWatchKline()` 中新增 KDJ 副图**：调整 grid 布局为三段（主图 K线+MA / 成交量 / KDJ），新增 grid[2]、xAxis[2]、yAxis[2]
- **前端计算 KDJ**：用 `d.kline`（开收高低）数据计算 9 日周期 KDJ（K/D/J 三条线），不修改后端
- **legend 追加 K/D/J**：legend.data 加 "K"、"D"、"J" 三项，颜色与 series 一致
- **tooltip 追加 K/D/J 显示**：hover 时除开/收/高/低 + 成交量 + MA 外，追加显示 K/D/J 数值（2 位小数）

## Impact
- Affected code: `static/app.js`（仅 `renderWatchKline()` 函数）
- Affected specs: `add-watchlist-kline-modal`（已完成的弹窗功能延伸）
- Non-affected: 后端 `app.py` / `core/*` 零改动（KDJ 前端计算）

## ADDED Requirements

### Requirement: KDJ 副图显示
`renderWatchKline()` SHALL 在 K 线弹窗中新增第三个 grid（gridIndex=2），显示 KDJ 指标的 K（白）、D（黄）、J（紫）三条 line series。

#### Scenario: 打开 K 线弹窗时显示 KDJ 副图
- **WHEN** 用户点击自选表「查看K线」按钮，Modal 打开并加载 `/api/index_kline` 返回数据
- **THEN** 主图下方依次显示「成交量副图」+「KDJ 副图」
- **AND** KDJ 副图有 K/D/J 三条线，颜色与 legend 一致
- **AND** legend 多出 K/D/J 三项可点击切换显示

#### Scenario: KDJ 计算使用 9 日周期标准算法
- **WHEN** 后端返回 `d.kline` 数组（每项 [开,收,低,高]）
- **THEN** 前端计算 RSV = (close - min(low_9)) / (max(high_9) - min(low_9)) * 100
- **AND** K = 2/3 * prevK + 1/3 * RSV（初始 prevK=50）
- **AND** D = 2/3 * prevD + 1/3 * K（初始 prevD=50）
- **AND** J = 3 * K - 2 * D
- **AND** 数组长度与 d.dates 一致

#### Scenario: tooltip 显示 KDJ 数值
- **WHEN** 鼠标 hover 在 K 线某一日
- **THEN** tooltip 除开/收/高/低 + 成交量 + MA 数值外，追加显示 `K：xx.xx　D：xx.xx　J：xx.xx`

#### Scenario: 档位切换后 KDJ 重新计算
- **WHEN** 用户切换 60/120/250 日档位
- **THEN** KDJ 随新数据重新计算并渲染，不残留旧值

### Requirement: 三 grid 布局不重叠
调整原双 grid 布局为三段，主图缩小占比，三段不重叠、留白合理。

#### Scenario: 布局比例
- **WHEN** K 线弹窗渲染
- **THEN** grid[0] 主图 top:30, height:50%（原 58% 缩小）
- **AND** grid[1] 成交量 top:66%, height:12%（原 74%/16% 调整）
- **AND** grid[2] KDJ top:82%, height:12%
- **AND** 三段间距合理、副图标签可读

## Constraints
- **后端零改动**：不修改 `app.py` / `core/*`，KDJ 完全前端计算
- **复用现有数据**：KDJ 用 `d.kline` 的 [开,收,低,高] 即可，无需新增字段
- **颜色规范**：K 白色 `#ffffff`、D 黄色 `#ffd166`、J 紫色 `#7c5cff`（与 MA5/MA20 区分；若冲突用备选 K=#f0e68c / D=#ff9800 / J=#9c27b0）
- **最小改动**：仅改 `renderWatchKline()` 函数内部 + 新增 `calcKDJ()` 辅助函数
