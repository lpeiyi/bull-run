# 实施计划：修正板块榜单的数据源选择逻辑

- **Spec 名称**：`fix-boards-source-selection`
- **状态**：Phase 3 — 任务
- **需求**：`requirements.md` · **设计**：`design.md`

---

## 阶段 1 · 核心改动（`core/market.py`）

- [x] **1. 提取解析函数到模块级，并修正东财排序参数**
  - 将 `_parse_sina(url)` 由 `get_boards()` 内移到模块级，函数体逐字不变
  - 将 `_parse_em(fs_code)` 由 `get_boards()` 内移到模块级，**仅改动请求参数**：`"fl": "f3"` → `"fid": "f3"`
  - 新增模块级常量 `SINA_HY_URL` / `SINA_CON_URL`，消除 `get_boards()` 内的硬编码 URL
  - _Requirement: AC-1.2_

- [x] **2. 用 `_pick_source` 替换 `_compare_and_pick`**
  - 新增模块级常量 `_MIN_SOURCE_ROWS = 20`
  - 实现 `_pick_source(em_rows, sina_rows, label)`：东财足量→东财；否则新浪有数据→新浪；否则沿用东财；皆空→`[]`
  - 删除 `_compare_and_pick` 及其交叉比对逻辑
  - 各分支打 warning 日志，便于线上排查
  - _Requirement: AC-2.1 / AC-2.2 / AC-2.3 / AC-2.4 / AC-2.5_

- [x] **3. 新增层级去重**
  - 实现 `_LEVEL_SUFFIX`、`_base_name(name)`、`_dedup_by_level(rows)`
  - `_dedup_by_level` 输入须已降序，按基名去重、保留靠前的一条；空名不参与判断但保留输出
  - _Requirement: AC-3.1_

- [x] **4. 重写 `get_boards()` 编排**
  - 先拉东财行业 / 概念；仅当对应东财结果不足 `_MIN_SOURCE_ROWS` 时才请求新浪
  - 新增 `_sina_or_empty(url)` 包裹新浪拉取，失败返回 `[]` 不抛异常
  - 结果管线：`_dedup_by_level(_clean_and_sort(_pick_source(...)))`
  - 保持返回结构 `{"industry": [...], "concept": [...]}` 与元素字段名不变
  - _Requirement: AC-1.1 / AC-1.4 / AC-4.1 / AC-4.3_

---

## 阶段 2 · 测试（`tests/test_market_boards.py`）

- [x] **5. 改写选源相关用例，新增参数与去重用例**
  - 移除针对 `_compare_and_pick` 的用例，改为 `_pick_source` 语义
  - 新增：`test_parse_em_uses_fid_sort_param`（monkeypatch `requests.get`，断言 `fid=="f3"`、`po==1`、不含 `fl`）—— **本次 bug 的回归防线**
  - 新增：`test_parse_em_parses_pct_and_fields`、`_pick_source` 四个分支用例、`_dedup_by_level` 两个用例、`test_get_boards_returns_sorted_deduped` 整体用例
  - 保留既有 `test_clean_and_sort_*` 用例
  - _Requirement: AC-5.1_

---

## 阶段 3 · 脚本验收口径（`scripts/verify_boards.py`）

- [x] **6. 更正 Step 3 判定标准**
  - 移除「比对新浪源第一名」（原假设两源可比，不成立）
  - 改为：① 结果严格降序；② 榜首与东财 `fid=f3` 源榜首一致（涨幅差 ≤0.01）；③ 无「去罗马数字后同名」重复项
  - _Requirement: AC-5.3_

---

## 阶段 4 · 验证闸门

- [x] **7. 全量验证与有效性自检**
  - `py_compile` 语法检查
  - `pytest` 全量通过（含既有 196 用例，AC-5.2）
  - 真实行情运行 `scripts/verify_boards.py`，Step 3 判定通过（AC-5.3）
  - **测试有效性自检**：临时把 `fid` 改回 `fl`，确认 `test_parse_em_uses_fid_sort_param` 变红后再还原
  - 抽取真实 Top10，人工核对降序与无重复
  - _Requirement: AC-5.2 / AC-5.3_

---

## 阶段 5 · 文档与提交

- [x] **8. 更新文档并提交**
  - `ROADMAP.md` 第 8 项标记完成，补实施结果（含"排序参数写错"的根因说明）
  - `.workbuddy/memory/` 追加执行记录；若发现环境或约定类新事实则更新 `MEMORY.md`
  - 按 `fix(market):` 提交生产改动；文档与 spec 单独提交
  - 确认工作区干净、无冗余文件入库
  - _Requirement: 全部_

---

## 验收对照

| 阶段 | 对应 AC | 通过标准 |
|---|---|---|
| 1 · 核心改动 | AC-1.1/1.2/1.4、AC-2.1~2.5、AC-3.1、AC-4.1 | 代码审查 + 用例覆盖 |
| 2 · 测试 | AC-5.1 | 新增用例全部通过 |
| 3 · 脚本 | AC-5.3 | 真实行情判定通过 |
| 4 · 验证 | AC-5.2/5.3、AC-1.3/4.2/4.3 | pytest 全绿 + 脚本通过 + 自检有效 |
| 5 · 收尾 | 全项 | 文档更新、提交规范、无冗余文件 |
