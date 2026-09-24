# 实施计划 — 补充回归测试

> 上游：`requirements.md`（34 条 AC）、`design.md`（技术方案）。
> 依赖关系：**任务 3 必须先于任务 8**（`market` 测试依赖结构提取）；任务 4~7 相互独立，可任意顺序。
> 状态标记：`[ ]` 未开始 / `[~]` 进行中 / `[x]` 已完成。

## 阶段 0 · 环境准备

- [ ] **1. 安装 pytest 并建立测试入口**
  - 用系统 Python 3.12.10 安装：`"C:/Users/peiyilu/AppData/Local/Programs/Python/Python312/python.exe" -m pip install pytest`
  - 确认版本 ≥ 7.0（`pytest.ini` 的 `pythonpath` 配置项需要），记录实际版本
  - 新建 `tests/` 目录
  - 新增根目录 `pytest.ini`（`testpaths = tests`、`pythonpath = .`）
  - 将 `.pytest_cache/` 加入 `.gitignore`（若有 `__pycache__` 遗漏一并补）
  - _Requirement: AC-1.1, C-4, C-6_

## 阶段 1 · 测试基础设施

- [ ] **2. 编写 `tests/conftest.py`**
  - autouse 夹具 `_no_network`：patch `socket.socket.connect`、`socket.socket.connect_ex`、`socket.create_connection`，被调用即抛 `AssertionError`
  - 工厂夹具 `kline_factory(n=60, base=10.0, step=0.1)`：返回含 `date/open/high/low/close/volume` 的等差 K 线 DataFrame
  - 自检：写一个临时用例断言夹具可用（如 `len(df) == n`），确认后并入正式用例或删除
  - _Requirement: AC-1.2, C-1_

## 阶段 2 · 结构性提取（唯一生产代码改动）

- [ ] **3. 将 `_compare_and_pick` / `_clean_and_sort` 提取到 `core/market.py` 模块级**
  - 前置确认：模块顶部已有 `import math`、`import logging`，缺则补（配套改动，非行为变更）
  - **记录行为基线**：提取前运行 `scripts/verify_boards.py` 与 `scripts/diag_boards.py`，保存输出
  - 两个函数**原样**搬到模块级（置于 `get_boards()` 之前），函数体一行不改
  - `get_boards()` 内两处调用改为指向模块级函数，删除嵌套定义
  - `_parse_sina` / `_parse_em` **保持不动**（不提取）
  - 提取后重跑两个脚本，输出与基线一致
  - `python -m py_compile core/market.py` 通过
  - _Requirement: C-2（例外一）, C-3, AC-6.1 ~ AC-6.6_

## 阶段 3 · 测试用例编写

- [ ] **4. `tests/test_sentiment.py` — 情绪分算法**
  - AC-2.1 ~ AC-2.3：涨停贡献 `base` 的下界（18 家 = 0）、上界（≥150 家 = 90）、`zt_n=0` 时 `score=0`
  - AC-2.4 ~ AC-2.7：`连板高度 / 晋级率 / 炸板率 / 跌停惩罚` 四维度各一组参数化断言，直取 `contributions` 对应键
  - AC-2.9：等级五档边界，按 `design.md` §5.1 的参考输入表参数化
  - AC-2.8：高低两端极端输入 → `score ∈ [0,100]` 且为 `int`
  - AC-2.10：键集合等于五个固定键；`round(sum(contributions.values())) == score`（未钳制时）
  - _Requirement: AC-2.1 ~ AC-2.10_

- [ ] **5. `tests/test_sentiment.py` — 跌停判定**
  - AC-3.1：北交所 `-29.5 / -29.4` 边界（`market="bj"`）
  - AC-3.2：创业板 `300` / 科创板 `688` 的 `-19.5 / -19.4` 边界
  - AC-3.3：主板 `-9.8 / -9.79` 边界
  - AC-3.4：`change_pct` 键缺失、显式 `None` 两种情形均返回 `False` 且不抛异常
  - 全部以**字典**构造入参（如 `{"change_pct": -9.8, "pure_code": "600000", "market": "sh"}`）
  - _Requirement: AC-3.1 ~ AC-3.4_

- [ ] **6. `tests/test_indicators.py`**
  - AC-4.1：`ma(close, n)` 前 n−1 位为 `NaN`、第 n 位等于前 n 个值的算术平均
  - AC-4.2 / 4.3 / 4.6：`macd` 恒等式、`kdj` 的 `j` 恒等式、`boll` 上下轨对称——用 `numpy.testing.assert_allclose(..., rtol=1e-9, atol=1e-9)`
  - AC-4.4：构造 `high == low` 区间，断言 k/d/j 无 `NaN`、无 `inf`、不抛异常
  - AC-4.5：严格递增 close → `rsi` 末值 > 90；严格递减 → < 10
  - 注意与 `tdx.KDJ` 的实现差异（分母兜底方式不同），期望值不可互用
  - _Requirement: AC-4.1 ~ AC-4.6_

- [ ] **7. `tests/test_tdx.py`**
  - AC-5.1：参数化若干非法公式（`"选股: 1 + "`、`"选股: (C"`、`""` 等），断言 `check_tdx_syntax` 返回 `ok=False` 且错误信息非空、不抛异常
  - AC-5.2：合法布尔公式（如 `"选股: C > MA(C,5);"`）→ 解包 `(results, signal)`；断言输出变量序列 `len == len(df)` 且 `dtype == bool`
  - AC-5.3：`"选股: KDJ.J > 80;"` 不报错且能取到输出
  - AC-5.4：同 code + 同 df 连调两次，两次结果完全一致
  - _Requirement: AC-5.1 ~ AC-5.4_

- [ ] **8. `tests/test_market_boards.py`**
  - AC-6.1 / 6.2 / 6.5：单源为空、双源为空的三个分支
  - AC-6.3：构造两源前 5 名中 ≥3 条同名且平均偏差 > 0.5pp（样本见 `design.md` §5.4）→ 期望切新浪
  - AC-6.4：同样 ≥3 条命中但偏差 ≤ 0.5pp → 期望保持东财
  - AC-6.6：`_clean_and_sort` 输入含 `"x"` / `None` / `float("nan")` 的行 → 被剔除且按 `avg_pct` 严格降序
  - 断言用 `==` 比对内容（函数返回 `list(...)` 副本，非同一对象）
  - _Requirement: AC-6.1 ~ AC-6.6_

## 阶段 4 · 验证与缺陷处理（关键闸门）

- [ ] **9. 全量跑通、校验与缺陷修复**
  - 项目根执行 `"C:/.../Python312/python.exe" -m pytest -v`：确认 34 条 AC 全部有用例覆盖、全绿、60 秒内结束
  - **校验手算参考表**（`design.md` §5.1 AC-2.9 表）：逐行核对实际 score 与等级
  - **校验非法公式样本**（§5.3）：确认每个样本确实走到 `check_tdx_syntax` 的失败分支，否则替换样本
  - **缺陷处理**（按 C-2 例外条款，当场修复）：
    - 甄别"手算有误"还是"实现缺陷"——手算过程可复核，二者不得混淆
    - 确属实现缺陷 → 当场修复，作为**独立提交**（写明问题、根因、修复依据），并补充/更新对应用例
  - **测试有效性自检**：临时改坏一处被测逻辑（如 `_calc_score` 的某档阈值），确认对应用例确实变红，然后回滚
  - _Requirement: AC-1.1 ~ AC-1.4, C-2_

## 阶段 5 · 收尾

- [ ] **10. 文档更新与提交**
  - `ROADMAP.md` 第 3 项状态改为「已完成」
  - 根 `README.md` 补一节「运行测试」（含解释器绝对路径命令）
  - 追加 `.workbuddy/memory/` 当日日志
  - 提交：建议拆为两个提交——① `test: 新增核心模块回归测试套件`（tests/ + pytest.ini）；② `refactor(market): 提取板块选源/清洗函数到模块级以便测试`（core/market.py）——若提取与测试强耦合也可合一，但提交信息须分段说明
  - 确认无 `__pycache__` / `.pytest_cache` / `data/` 误入库
  - _Requirement: 全项_

---

## 验收对照

| 阶段 | 覆盖 AC | 通过判定 |
|---|---|---|
| 0 · 环境 | AC-1.1, C-4, C-6 | `pytest --version` 正常、`pytest.ini` 生效 |
| 1 · 基础设施 | AC-1.2, C-1 | 离线夹具生效、夹具可生成 DataFrame |
| 2 · 结构提取 | C-2, C-3, AC-6.x | 提取前后 `verify_boards.py` 输出一致 |
| 3 · 用例 | AC-2 ~ AC-6 | 每个测试文件单独跑全绿 |
| 4 · 验证 | AC-1.1 ~ 1.4 | 全量 `pytest` 一次通过、<60s、坏码能变红 |
| 5 · 收尾 | 全项 | 文档更新、提交入库、无冗余文件 |
