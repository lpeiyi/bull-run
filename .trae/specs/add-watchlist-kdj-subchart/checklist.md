# Checklist

## Task 1: calcKDJ 函数

- [x] Checkpoint 1: `calcKDJ(kline, n=9)` 函数存在
  - [x] 1.1 `static/app.js` 中存在 `function calcKDJ(kline` 定义（L1714）
  - [x] 1.2 函数返回 `{ K, D, J }` 三个数组
  - [x] 1.3 K/D/J 数组长度与 kline 一致
  - [x] 1.4 算法正确：K=2/3*prevK+1/3*RSV，D=2/3*prevD+1/3*K，J=3*K-2*D
  - [x] 1.5 prevK/prevD 初始值均为 50
  - [x] 1.6 除零保护：highN === lowN 时 RSV 返回 50
  - [x] 1.7 函数内有中文注释说明算法步骤

## Task 2: renderWatchKline 加 KDJ 副图

- [x] Checkpoint 2: legend 追加 K/D/J
  - [x] 2.1 legend.data 数组包含 `"MA5","MA10","MA20","MA60","MA120","K","D","J"` 共 8 项（L1764）

- [x] Checkpoint 3: 三 grid 布局
  - [x] 3.1 grid 数组长度为 3
  - [x] 3.2 grid[0]: top=30, height="50%"（L1766）
  - [x] 3.3 grid[1]: top="66%", height="12%"（L1767）
  - [x] 3.4 grid[2]: top="82%", height="12%"（L1768）

- [x] Checkpoint 4: xAxis / yAxis 第三组
  - [x] 4.1 xAxis 数组长度为 3，第 3 项 gridIndex: 2（L1773）
  - [x] 4.2 yAxis 数组长度为 3，第 3 项 gridIndex: 2（L1778）

- [x] Checkpoint 5: series 追加 KDJ 三条 line
  - [x] 5.1 series 数组长度为 10（K线 + 5 MA + 成交量 + K + D + J）
  - [x] 5.2 K series: name="K", xAxisIndex=2, yAxisIndex=2, color="#ffffff"（L1790）
  - [x] 5.3 D series: name="D", xAxisIndex=2, yAxisIndex=2, color="#ffd166"（L1791）
  - [x] 5.4 J series: name="J", xAxisIndex=2, yAxisIndex=2, color="#7c5cff"（L1792）

- [x] Checkpoint 6: tooltip 追加 KDJ 显示
  - [x] 6.1 tooltip.formatter 中存在 K/D/J 分支判断（L1759）
  - [x] 6.2 显示格式为 `${p.seriesName}：${Number(p.value).toFixed(2)}`（2 位小数）

- [x] Checkpoint 7: 后端零改动
  - [x] 7.1 `git diff --name-only app.py core/` 输出为空，`app.py` 和 `core/` 未修改

- [x] Checkpoint 8: 整体功能
  - [x] 8.1 静态推断：打开 K 线弹窗后 KDJ 副图能显示，三段不重叠（grid 50% + 12% + 12% = 74%，加间距合理）
  - [x] 8.2 静态推断：切换档位后 KDJ 随新数据重新计算（renderWatchKline 内每次都调 `const kdj = calcKDJ(d.kline);` L1743）
  - [x] 8.3 静态推断：tooltip hover 能看到 K/D/J 数值（L1759 KDJ 分支）
