# Tasks
- [x] Task 1: 将 prevIdx 从 `length-2` 改为 `length-1`，修正注释
  - 文件: `static/app.js` L1167-1171
  - 改 `const prevIdx = t.dates.length - 2;` → `const prevIdx = t.dates.length - 1;`
  - 改注释：说明趋势数组最后一条 = 昨日完整收盘（不含今日），`latest` 是独立字段已被 v4 覆盖为今日实时
  - 保留 `if (prevIdx >= 0)` 守卫用于空数组 fallback

# Task Dependencies
- 无
