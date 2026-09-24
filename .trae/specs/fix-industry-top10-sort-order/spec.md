# 行业领涨领跌 Top10 修复 Spec

## Why

用户现场验证（2026-09-04）：农林牧渔板块真实涨幅 +3.61% 排第一、传媒板块 +2.32% 排第二，但系统显示领涨 Top1 为"酿酒行业 1.79%"、农林牧渔被误压至第 3（0.30%），**整体数值严重偏低**。2026-09-04 21:49 诊断脚本 `_diag_boards.py` Python 直调 `market.get_boards()` 确认后端返回的 49 个行业最大涨幅仅 1.79%，与真实行情差 2 倍以上。

**精确根因**：

1. `_parse_em()` 东财 push2 `f3` 口径错误：`f3/100` 算出来的是"板块指数涨跌幅"，不是板块"成分股平均涨幅 avg\_pct"（用户期望口径、东财网页/新浪均使用），导致数值系统性偏低。
2. 兜底条件漏洞：L197 `if not ind:` 仅当东财返回**空数组**时才切新浪，但实际上东财返回了 49 个"有记录但数值错"的行，新浪兜底永远不触发。
3. 自选标的 CSS/JS 改动（限 `.tbl td` 作用域 / `renderWatch` 局部函数）**与本 Bug 无关**——行业卡片不含 `.tbl` 祖先、非 table 结构，纯粹是时序巧合。

## What Changes

- **后端根因修复（核心）**：`core/market.py get_boards()` 双源拉取 + 自动兜底切换：

  - 同时调用 `_parse_em(东财)` 和 `_parse_sina(新浪)` 两个 industry / concept 源

  - 以**新浪源为校准基准**：若东财 `ind` 的第一名 avg\_pct 与新浪第一名相差 0.5 个百分点以上（或东财第一名缺失/非数字），则切**新浪为主源**；如果新浪源为空或东财与新浪偏差在阈值内，保留东财。

  - 概念板块 concept 同等逻辑。

- **东财口径修正（保留使用）**：如果保留东财主源，使用东财板块成分接口（`_parse_em_stocks_avg(f12)` 取成分股算平均涨幅）或改用 `f186(涨跌幅)` / 其他字段替代 `f3/100`（若无法调通则切新浪）。

- **兜底阈值显式化**：增加 `_compare_and_pick(em_rows, sina_rows, label)` 函数做名值交叉比对（name 匹配后验证 avg\_pct 差距），非黑盒"空就换"。

- **前端渲染**（仍做但不再是核心修复）：

  - `renderBoardsTop10` 领涨 slice 之前前端二次显式 sort(降序 null 兜底).slice(0,10)

  - 领跌 sort key 增加 `?? 1e9` null 兜底排末尾

  - name / avg\_pct 渲染 `|| "--"` / `?? 0`

- **视觉层兜底**：`.boards-bar-row` 固定 `height: 38px; box-sizing:border-box`，防止行高参差导致用户视觉误判数据错位。

## Impact

- Affected code:

  - `core/market.py`：新增 `_parse_em_stocks_avg()` 或直接 `_compare_and_pick()`；修改 `get_boards()` 为"双源拉取 + 名值交叉比对切换主源"

  - `static/app.js`：`renderBoardsTop10()` 前端二次排序 + null 兜底

  - `static/style.css`：`.boards-bar-row` 固定行高 38px

- 影响 specs：自选标的 reorder spec 完全不回归（改的 CSS 全部限 `.tbl td`）

## ADDED Requirements

### AC-1 后端数据正确性（根因修复）——必须与现场锚点匹配

#### AC-1.1 (rule) 双源拉取 + 名值比对切换

`get_boards()` 必须**同时拉取东财和新浪两个 source**（不是"空再兜底"），调用 `_compare_and_pick(em_rows, sina_rows, label)`：

- label = "industry" / "concept"

- 逻辑：sina 有数据且 sina 第一名涨幅存在 → 取 sina 前 5 名与 em 中同 name 的行做比对，若任意 3 个 name 匹配上且 avg\_pct 平均偏差 > 0.5 百分点，则选 sina 作为最终 rows；否则选 em。

- 若 sina 为空选 em；若 em 为空选 sina；两者都空返回空数组。

#### AC-1.2 (rule) 返回结果与现场锚点对得上（最终验证基准）

**以用户给定 2026-09-04 锚点为验收**：切换后 `get_boards()["industry"][0]` = `{ name: "农林牧渔", avg_pct: 3.61 }` 附近（±0.3 容差），第 2 名 avg\_pct ≈ 2.32。若当天真实行情变更到非 3.61/2.32，则以**新浪源返回第一名值为基准**，验收条件为"新浪首名 avg\_pct 与最终返回首名一致"。

#### AC-1.3 (rule) sort 前空值过滤

最终 rows（不论选 sina 还是 em）在 sort 前做 `row = [x for x in rows if isinstance(x.get("avg_pct"), (int, float))]`（NaN 也过滤，加 `import math` + `not math.isnan`），排序后返回。

#### AC-1.4 (rule) 东财 push2 加 fl=f3（即使切 sina 也保留，作为当 sina 失败时的保险）

`_parse_em(fs_code)` params 增加 `'fl': 'f3'`，当需使用东财时，其返回顺序一定是按涨跌幅降序。

### AC-2 前端双保险排序（不依赖后端顺序）

#### AC-2.1 (rule) 领涨 Top10 前端再显式 sort 一次

`renderBoardsTop10` 的 boards\_up 改为：`industry.slice().sort((a, b) => (b.avg_pct ?? -1e9) - (a.avg_pct ?? -1e9)).slice(0, 10)`。不修改原 industry 引用。

#### AC-2.2 (rule) 领跌 Top10 增加 null 兜底

boards\_down 的 sort 改为：`[...industry].sort((a, b) => (a.avg_pct ?? 1e9) - (b.avg_pct ?? 1e9)).slice(0, 10)`。null 的行排末尾。

#### AC-2.3 (rule) 渲染 name / avg\_pct 双兜底

map 循环里 name = `x.name || "--"`，avg\_pct = `x.avg_pct ?? 0`。任何字段缺失不破坏 DOM。

### AC-3 视觉层对齐（防止用户视觉误判为数据顺序错）

#### AC-3.1 (rule) boards-bar-row 固定高度

`.boards-bar-row` CSS 增加 `height: 38px; box-sizing: border-box`，配合已有的 padding 上下 6px = 内容 26px，所有行等高。

#### AC-3.2 (rule) 自选标的改动作用域不过界（反证）

自选标的新增 CSS（`.tbl td .btn.sm`、`.tbl td .w-grip`、`.tbl tr.dragging` 等）都必须以 `.tbl` 为前缀，行业卡片 `.boards-top10` 的任何后代元素不匹配这些规则。现场 Grep 验证。

### AC-4 不回归

#### AC-4.1 (rule) 自选标的功能不受影响

拖拽排序（三条杠）、移首按钮、查看K线、删除、列宽铺满全部不变。

#### AC-4.2 (rule) 其他 API / 页面不受影响

双源比对仅在 `get_boards()` 内生效，不改动 `/api/overview` 路由签名、`_OVERVIEW_CACHE` 结构、其他 API。

#### AC-4.3 (rule) 进程内缓存兼容性

`/api/overview` 的 `_OVERVIEW_CACHE` 60s 缓存不变，boards 字段仍来自 `market.get_boards()` 返回，修复后每次缓存重建都会拿到经过双源校准的 boards。

## Non-Goals

- 不更换 boards 的 UI 结构（rank/name/pct/bar 四列顺序保留）

- 不修改 boards-down / boards-up 归一化基准 maxAbs 的公式

- 不引入新的第三方数据源（仅在已有的 sina + em 两源间比对切换）

