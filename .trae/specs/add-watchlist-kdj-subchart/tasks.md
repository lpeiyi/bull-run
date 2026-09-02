# Tasks

- [x] Task 1: 新增 `calcKDJ(kline, n=9)` 辅助函数
  - [ ] SubTask 1.1: 在 `static/app.js` 中 `renderWatchKline` 函数之前（约 L1711 前）新增 `calcKDJ(kline, n = 9)` 函数
  - [ ] SubTask 1.2: 算法实现：
    - 遍历 kline 数组（每项 [开,收,低,高]）
    - 对每个 i，取最近 n 日（不足 n 日则取 0~i）的 high 最大值和 low 最小值
    - RSV = (close - lowN) / (highN - lowN) * 100，除零时返回 50
    - K = 2/3 * prevK + 1/3 * RSV（prevK 初始 50）
    - D = 2/3 * prevD + 1/3 * K（prevD 初始 50）
    - J = 3 * K - 2 * D
    - 返回 `{ K: [...], D: [...], J: [...] }`，长度与 kline 一致
  - [ ] SubTask 1.3: 函数体内追加简明中文注释说明算法步骤

- [x] Task 2: 修改 `renderWatchKline()` 加入 KDJ 副图
  - [ ] SubTask 2.1: 在 `renderWatchKline` 函数体开头（`if (!wkChart) return;` 之后）调用 `const kdj = calcKDJ(d.kline);`，得到 K/D/J 三组数据
  - [ ] SubTask 2.2: legend.data 追加 `"K"`, `"D"`, `"J"` 三项
  - [ ] SubTask 2.3: grid 数组从 2 段改为 3 段：
    - grid[0]: `{ left: 52, right: 20, top: 30, height: "50%" }`
    - grid[1]: `{ left: 52, right: 20, top: "66%", height: "12%" }`
    - grid[2]: `{ left: 52, right: 20, top: "82%", height: "12%" }`
  - [ ] SubTask 2.4: xAxis 数组追加第 3 个元素 `{ type: "category", data: labels, gridIndex: 2, boundaryGap: true, axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9" } }`
  - [ ] SubTask 2.5: yAxis 数组追加第 3 个元素 `{ type: "value", gridIndex: 2, scale: true, splitNumber: 2, axisLabel: { color: "#8ba0c9" }, splitLine: { show: false } }`
  - [ ] SubTask 2.6: series 数组追加 3 条 line series：
    - `{ name: "K", type: "line", data: kdj.K, xAxisIndex: 2, yAxisIndex: 2, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#ffffff" } }`
    - `{ name: "D", type: "line", data: kdj.D, xAxisIndex: 2, yAxisIndex: 2, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#ffd166" } }`
    - `{ name: "J", type: "line", data: kdj.J, xAxisIndex: 2, yAxisIndex: 2, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#7c5cff" } }`
  - [ ] SubTask 2.7: tooltip.formatter 追加 KDJ 显示逻辑：
    - 在 MA 分支之后追加 `else if (p.seriesName === "K" || p.seriesName === "D" || p.seriesName === "J") { if (p.value != null) s += `${p.marker}${p.seriesName}：${Number(p.value).toFixed(2)}<br>`; }`

# Task Dependencies
- Task 2 依赖 Task 1（需要 calcKDJ 函数存在才能调用）
- SubTask 2.1-2.7 串行实施（同一函数内修改）
