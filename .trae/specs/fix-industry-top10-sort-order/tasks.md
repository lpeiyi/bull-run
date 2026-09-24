# Tasks - 行业领涨领跌 Top10 数据修复（双源校准）

## Task 1: 后端核心修复——双源拉取 + 名值比对切换
- **Priority**: high
- **Depends On**: None
- [ ] Task 1:
  - SubTask 1.1: `_parse_em(fs_code)` L170 params 增加 `'fl': 'f3'`（按涨跌幅字段降序）
  - SubTask 1.2: 新增 `_compare_and_pick(em_rows, sina_rows, label)` 函数：前 5 名 name 交叉匹配，平均 avg_pct 偏差 > 0.5pp 选 sina，否则选 sina；sina 空选 em；两者都空返回 []
  - SubTask 1.3: 重写 `get_boards()`：同时调用 em+sina（industry & concept 各 4 次调用），再经 `_compare_and_pick()` 挑最终 ind/con
  - SubTask 1.4: 最终 ind/con 排序前空值过滤（isinstance + 非 NaN）
  - SubTask 1.5: 顶部 import math

## Task 2: 前端二次排序双保险 + null 兜底
- **Priority**: high
- **Depends On**: None
- [ ] Task 2:
  - SubTask 2.1: renderBoardsTop10 L633 boards_up = industry.slice().sort(b.avg_pct??-1e9 降序).slice(0,10)
  - SubTask 2.2: L635 boards_down = [...industry].sort(a.avg_pct??1e9 升序).slice(0,10)
  - SubTask 2.3: L647/L661 name 改为 x.name||"--"，avg_pct 改为 x.avg_pct??0

## Task 3: 视觉层对齐 + 自选作用域验证
- **Priority**: medium
- **Depends On**: None
- [ ] Task 3:
  - SubTask 3.1: .boards-bar-row CSS 加 height:38px + box-sizing:border-box
  - SubTask 3.2: Grep 验证自选标的新增 CSS 全部带 .tbl 前缀，行业 .boards-top10 无后代匹配

## Task 4: 端到端验证（锚点对齐）
- **Priority**: high
- **Depends On**: Task 1, 2, 3
- [ ] Task 4:
  - SubTask 4.1: `python -m py_compile core/market.py app.py`
  - SubTask 4.2: Python 直调 get_boards()，打印 industry 前 3 名 avg_pct，若新浪返回对得上锚点（±0.3 容差），则最终返回第一必须与之对齐
  - SubTask 4.3: 自选标的 5 项功能（查看K线/拖拽/移首/删除/列宽）代码不变，Grep 验证
  - SubTask 4.4: Grep app.py 确认 boards 字段来源仍为 market.get_boards()

# Task Dependencies
- Task 1, 2, 3 可并行
- Task 4 依赖 1+2+3
