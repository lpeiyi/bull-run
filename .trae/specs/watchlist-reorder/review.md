# Review Gate - watchlist-reorder — **PASS Cycle1（18/18 全过）**

## AC-1 三条排序指令生效
- [x] CP-1.1 watchUp：i<=0 return；否则交换 i-1 与 i；await saveConfig()；loadWatch() → PASS L1708-1715
- [x] CP-1.2 watchDown：i<0 或 i>=len-1 return；否则交换 i 与 i+1；saveConfig；loadWatch → PASS L1718-1724
- [x] CP-1.3 watchTop：i<=0 return；否则 splice(i,1)+unshift；saveConfig；loadWatch → PASS L1727-1734
- [x] CP-1.4 操作前后 CONFIG.watchlist 长度不变，元素不变 → PASS（交换/移动都是稳定元素重排）

## AC-2 按钮渲染 + disabled 边界
- [x] CP-2.1 按钮顺序 w-kline → w-top → w-up → w-down → w-del 齐全 → PASS L1619-L1624
- [x] CP-2.2 i=0 行 w-up/w-top 有 disabled 属性 → PASS L1620/L1621 first? disabled
- [x] CP-2.3 i=len-1 行 w-down 有 disabled → PASS L1622 last? disabled
- [x] CP-2.4 len≤1 时三按钮都 disabled → PASS（first 同时 last，3 条均命中）

## AC-3 持久化/刷新闭环
- [x] CP-3.1 三函数都 `await saveConfig()` 再 `loadWatch()` → PASS
- [x] CP-3.2 CONFIG.watchlist 排序落地持久化 → PASS

## AC-4 不回归
- [x] CP-4.1 查看K线/删除 事件绑定保持；delWatch/openWatchKline/addWatch 不变 → PASS
- [x] CP-4.2 行情 6 列模板变量未变 → PASS L1626-L1630
- [x] CP-4.3 空列表 colspan="7" + 「暂无自选标的」 → PASS L1611

## AC-5 列宽铺满
- [x] CP-5.1 7 个 th width：24+10+10+11+13+11+21=100% → PASS
- [x] CP-5.2 名称 24%(≥22%)，操作 21%(≥19%) → PASS
- [x] CP-5.3 列数仍为 7（colspan=7）→ PASS

## 代码边界
- [x] CP-B.1 写入文件 = {static/app.js, static/style.css, templates/index.html} 3 → PASS
- [x] CP-B.2 py_compile app.py exit 0 → PASS

---

## Review History
### Cycle 1 首次独立审查 → PASS（18/18）
- 审查者：general-purpose 独立 agent
- 结果：pass
- Notes：
  - 空列表文本「暂无自选标的，请在上方添加」= CP 要求超集，无回归
  - 数据缺失行 L1625 colspan=4 + 2 列 + op = 7 列 结构一致
