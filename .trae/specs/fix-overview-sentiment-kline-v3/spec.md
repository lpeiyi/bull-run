# 市场概览页问题根治 v3 Spec（fix-overview-sentiment-kline-v3）

## Problem

- **问题一（情绪数据未修正）**：Python 直接调 `get_sentiment()` 已返回正确（涨停 52、跌停 8、炸板率 22.4%、最高 4 板、情绪分 47 级"正常"），但 Flask 进程仍跑旧代码或 `_OVERVIEW_CACHE` 还缓存旧值，所以前端仍显示 83/0/6.7%。
- **问题二（KDJ 150 刻度与成交量 x 轴重叠）**：grid 混合用像素 `top: 30` + 百分比 `height: "50%"`，且 KDJ 副图 `top: "83%"` + `height: "20%"` = 103% 超出容器，`containLabel: false`（默认）不预留 Y 轴 label 空间，导致重叠。
- **问题三（指数K线 Y 轴刻度）**：已修复（grid left 52→65），无需再改。

## What Changes

### 问题一：Flask 侧彻底生效
- **清 `_OVERVIEW_CACHE`**：`app.py` 的 `_OVERVIEW_CACHE = {"ts": 0.0, "data": None}` 会缓存概览数据（含情绪），即使代码重启，若缓存在 60s 内仍可能返回旧值。修改缓存有效期或在 `/api/sentiment` 入口强制走实时数据（不经 `_OVERVIEW_CACHE`）。
- **Flask 重启提示**：本次改完后告诉用户必须 **重启 Flask 进程**（即关闭 `start.bat` 再双击启动），否则 Python 解释器不会重新加载模块。

### 问题二：三 grid 绝对定位，彻底消除重叠
- **百分比统一 + 绝对像素总控**：所有 grid 的 `top` 和 `height` 全部改为百分比，`top: 30` 像素改为 `top: "5%"`，容器总高 480px，legend 占约 30px 即约 6%，所以 5% 合适。
- **加 `containLabel: true`**：option 顶层加 `containLabel: true`，让 ECharts 自动为 X/Y 轴 label 预留空间，避免刻度文字重叠。
- **grid 不超出容器**：所有副图 `top + height <= 95%`（底部保留 5% 缓冲）。
- **段间距足够**：主图 bottom ≈ 5% + 45% = 50%，成交量 top 54% height 14% bottom 68%，KDJ top 72% height 22% bottom 94%。三段之间 4% / 4% 的段间距 + containLabel 兜底，永不重叠。
- **Modal 总高自适应**：如果总高度不够，把 `#watch-kline-chart` 高度从 480px 提到 560px，给三 grid 留足空间。

## Impact
- Affected code: `app.py`（概览缓存） + `static/app.js`（grid 布局） + `static/style.css`（chart 高度）
- Non-affected: `core/sentiment.py`（代码已正确）、`core/legu.py`（代码已正确）

## 根因记录（供用户理解）

### 问题一根因实测数据（2026-09-02 19:34 UTC+8）
```
乐咕 rows[-1] date=20260902  zt=52  dt=8  zb=15  break_rate=22.4
东财 getTopicZTPool 原始数: 52   过滤后: 52   过滤掉: 0 set()
炸板数: 15   跌停数: 7   最高连板: 4   晋级率: 15.7   炸板率: 22.4
sentiment.get_sentiment() 直接调用: score=47, zt=52, dt=8 ✓
```
`get_sentiment()` 的 Python 代码逻辑已正确。前端显示错误的原因是：Flask 运行时加载的是**旧版本**的 `sentiment.py` 字节码，或者 `_OVERVIEW_CACHE` 返回 60s 内的旧值。需要改 app.py 缓存 + 强制重启 Flask。

### 问题二根因
grid[0] 用 `top: 30`（像素绝对定位）+ `height: "50%"`（百分比）混合计算，ECharts 内部坐标系统一化时会错位；KDJ 副图 `83% + 20% = 103%` 超出容器边界，Y 轴 label 被压到与成交量 x 轴同一水平线；`containLabel: false`（默认）又不预留 label 空间，三重因素叠加导致重叠。

## 约束
- **不改 core/sentiment.py**（代码逻辑已经正确）
- **Flask 必须重启**，这是本次生效的**硬性前置条件**
- 前端 renderWatchKline 的 `containLabel: true` 会自动协调 grid 内边距，可能导致各 grid 的 left/top/height 相对移动，但保证不重叠、不截断
