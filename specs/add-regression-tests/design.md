# 补充回归测试 — 技术设计

> 上游：`requirements.md`（34 条验收标准 / 6 条约束 / 5 项非目标）。本文件只回答「怎么测」。任务拆分见 `tasks.md`。

## 1. 方案总览

四个被测模块里，三个（`sentiment` / `indicators` / `tdx`）是纯函数或可构造纯输入的，可直接 import 测试；只有 `market.py` 的选源逻辑当前被包在 `get_boards()` 函数体内部，需要一次**最小结构提取**才能独立测试。

因此整体方案是：

```
tests/  ──import──▶  core.sentiment   （纯函数，直接测）
                     core.indicators  （纯函数，直接测）
                     core.tdx         （固定 DataFrame 输入，直接测）
                     core.market._compare_and_pick   ┐ 需先做结构提取
                     core.market._clean_and_sort     ┘（唯一改动的生产代码）
```

结构性改动**只有一处**，且限定为「把两个嵌套函数原样提到模块级」。除此之外不动任何生产代码（约束 C-2）。

## 2. 目录与文件布局

```
bull-run/
├── pytest.ini                      # 新增：testpaths + pythonpath
├── tests/                          # 新增
│   ├── conftest.py                 # 共享夹具 + 离线强制
│   ├── test_sentiment.py           # AC-2.1 ~ 2.10、AC-3.1 ~ 3.4
│   ├── test_indicators.py          # AC-4.1 ~ 4.6
│   ├── test_tdx.py                 # AC-5.1 ~ 5.4
│   └── test_market_boards.py       # AC-6.1 ~ 6.6
└── core/market.py                  # 唯一被改动的生产文件（见 §6）
```

**为什么加 `pytest.ini` 而不是 `pyproject.toml`**：项目当前没有 `pyproject.toml`，为测试引入一个会顺带声明打包元数据，容易引起歧义。`pytest.ini` 只做一件事——告诉 pytest「测试在 `tests/`，项目根要进 `sys.path`」，边界最干净。

```ini
[pytest]
testpaths = tests
pythonpath = .
```

`pythonpath = .` 是必需的：测试文件用 `import core.sentiment`，而 `tests/` 下不放 `__init__.py`（避免包名冲突），此时项目根必须显式在 `sys.path` 中。

## 3. 运行环境与执行方式

### 3.1 关键发现：两个 Python 是分裂的

排查环境时发现一个必须先解决的问题：

| 解释器 | 用途 | pandas | pytest |
|---|---|---|---|
| `C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe`（3.12.10） | **`start.bat` 指定的运行环境**，已装 pandas 3.0.3 | ✅ 3.0.3 | ❌ 未安装 |
| `C:\Users\peiyilu\.workbuddy\binaries\python\versions\3.13.12\python.exe`（3.13.12） | 助手沙箱托管版本 | ❌ 未安装 | ❌ 未安装 |

也就是说：**能跑 app 的那个 Python 没 pytest；有 pytest 可能性的那个没 pandas。** 项目也没有 venv。

按约束 C-6（测试须在项目当前使用的 Python 版本下通过），测试**必须**跑在 3.12.10 那个解释器上，因此需要给它装上 pytest。这一步只加 `pytest` 一个包（约束 C-4），不动 `requirements.txt` 之外的东西。

### 3.2 执行方式

```bash
# 一次性准备
"C:/Users/peiyilu/AppData/Local/Programs/Python/Python312/python.exe" -m pip install pytest

# 日常运行（项目根目录）
"C:/Users/peiyilu/AppData/Local/Programs/Python/Python312/python.exe" -m pytest
```

### 3.3 装 pytest 到哪个环境：两个选项

给系统 Python 装 pytest 会轻度污染用户全局环境。两条路：

| | 方案 A：装入系统 Python 3.12（**推荐**） | 方案 B：新建项目 venv `.venv` |
|---|---|---|
| 做法 | 直接 `pip install pytest` | `.venv` 内装 `requirements.txt` + pytest |
| 符合 C-6 | ✅ 与 app 完全同环境 | ✅ 但需保证 requirements 装全 |
| 改动面 | 零（不碰 `start.bat`） | 需改 `start.bat` 指向 venv |
| 代价 | 全局多一个 pytest | 多一层环境，pandas 版本可能与现在不同 |
| 风险 | 低 | 新环境可能装不到 pandas 3.0.3 同版本 |

**已采用方案 A（2026-09-24 确认）**：pytest 装入系统 Python 3.12.10，不新建 venv，不改 `start.bat`。

## 4. 通用测试策略

### 4.1 离线强制（对应 AC-1.2 / C-1）

不满足于「我们没写网络调用」，而是**让网络在物理上不可用**——在 `conftest.py` 里用 autouse 夹具阻断 socket 连接：

```python
import socket
import pytest

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """任何真实网络连接都直接失败，保证测试离线可跑（AC-1.2）。"""
    def _blocked(*args, **kwargs):
        raise AssertionError("测试期间禁止真实网络访问：请检查被测代码是否新增了外部请求")
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
```

好处：将来谁不小心让某个纯函数偷偷发起请求，测试会**当场炸出来**，而不是在离线环境里静默失败。四个被测模块均不在 import 期发请求，故此夹具不误伤。

### 4.2 夹具设计（`conftest.py`）

行情 DataFrame 用工厂夹具生成，避免每个用例重复拼装：

```python
@pytest.fixture
def kline_factory():
    """生成等差数列性质的 K 线 DataFrame：open/high/low/close 线性递增。"""
    def _make(n=60, base=10.0, step=0.1):
        ...
        return pd.DataFrame({...})   # 含 date/open/high/low/close/volume
    return _make
```

等差序列的好处：均线、极值、布林带都有闭式解，期望值可手算，不依赖「跑一遍再抄结果」这种自证式断言。

**指标测试统一用 `core/indicators.py` 与 `core/tdx.py` 各自的输入形态**：
- `indicators.ma/ema/macd/boll/rsi` 收 **Series**（`df["close"]`）
- `indicators.kdj` 收 **(high, low, close) 三个 Series**
- `tdx.evaluate_tdx` 收 **DataFrame + 公式字符串**

这两套接口长得像但不能混用，测试里要写清。

### 4.3 断言风格（对应 AC-1.3）

统一写成 `assert actual == expected`，让 pytest 在失败时自动打印期望值/实际值。避免写 `assert cond`（只给一个 False，看不出差多少）。

浮点比较一律用 `numpy.testing.assert_allclose`，**同时给 `rtol` 与 `atol`**——因为 AC-4.2/4.3/4.6 里的恒等式在数值较大时，绝对 1e-9 会误报。

## 5. 分模块测试设计

### 5.1 `core/sentiment.py`（AC-2.x、AC-3.x）

#### 接口澄清（重要）

`_calc_score` 的签名是**位置参数五元组**，返回**三元组**：

```python
_calc_score(zt_n, dt_n, max_height, promo_rate, break_rate)
    -> (score, level, contributions)
```

`_is_dt_stock` 收的是**一个 dict**，不是散开的参数：

```python
_is_dt_stock({"change_pct": -9.8, "pure_code": "600000", "market": "sh"}) -> bool
```

需求文档 AC-3.x 写的「`market = "bj"` 且 `change_pct = -29.5`」指的是这个 dict 的字段。测试必须按 dict 构造，不能传两个位置参数。

#### AC-2.x 参数表设计

涨停贡献 `base` 是对数映射 `90·(ln(zt_n) − ln18)/(ln150 − ln18)`，钳制到 [0, 90]。由于 `base` 是连续量，直接命中某个整数 score 需要凑输入。设计阶段已按公式手算出下表参考输入（全部满足 `height=0`〔max_height<4〕、`zb=0`〔break_rate≤40〕、`dt=0`〔dt_n≤30〕）：

| 目标 score | 输入 `(zt_n, dt_n, max_height, promo_rate, break_rate)` | 预期 level | 覆盖 AC |
|---|---|---|---|
| 25 | `(33, 0, 3, 7.0, 0.0)` | 冰点 | AC-2.9 |
| 26 | `(33, 0, 3, 10.0, 0.0)` | 偏冷 | AC-2.9 |
| 45 | `(52, 0, 3, 10.0, 0.0)` | 偏冷 | AC-2.9 |
| 46 | `(53, 0, 3, 10.0, 0.0)` | 正常 | AC-2.9 |
| 65 | `(83, 0, 3, 10.0, 0.0)` | 正常 | AC-2.9 |
| 66 | `(85, 0, 3, 10.0, 0.0)` | 偏热 | AC-2.9 |
| 80 | `(118, 0, 3, 10.0, 0.0)` | 偏热 | AC-2.9 |
| 81 | `(120, 0, 3, 10.0, 0.0)` | 过热 | AC-2.9 |

> ⚠️ **以上是设计阶段手算值，不是实测值。** Phase 4 首跑时若某行不符，须先甄别：若是**手算有误**，校准后回填本表；若确属**实现缺陷**，按 C-2 例外条款当场修复（独立提交 + 补充用例），不停留在"记录"。二者不得混淆——甄别依据是手算过程可复核。

其余维度各用一条断言直取 `contributions` 的对应键，不绕总分：

| AC | 断言方式 |
|---|---|
| AC-2.1 | `_calc_score(0, 0, 0, 0.0, 0.0)` → `score == 0` 且 `contributions["涨停家数"] == 0.0` |
| AC-2.2 | `zt_n=18` → `contributions["涨停家数"] == 0.0` |
| AC-2.3 | `zt_n=150` 与 `zt_n=200` 均 → `contributions["涨停家数"] == 90.0` |
| AC-2.4 | 参数化 `max_height ∈ {3,4,5,6,7,8}` → `contributions["连板高度"] == {0,1,2,3,4,5}` |
| AC-2.5 | 参数化 `promo_rate ∈ {16,15,10,7,5}` → `contributions["晋级率"] == {2,1,0,-1,-2}` |
| AC-2.6 | `break_rate ∈ {40.0, 40.1}` → `contributions["炸板率"] == {0, -2}` |
| AC-2.7 | `dt_n ∈ {30, 50}` → `contributions["跌停惩罚"] == {0.0, -0.8}` |
| AC-2.8 | 高/低两极端输入 → `0 <= score <= 100` 且 `isinstance(score, int)` |
| AC-2.10 | `set(contributions) == {五个键}` 且 `round(sum(contributions.values())) == score` |

> ✅ **AC-2.10 措辞已修订（2026-09-24）**：原写「向上取整」与实现 `int(round(...))`（四舍五入）不符，`requirements.md` 已改为「四舍五入取整」。测试按 `round()` 断言。

#### AC-3.x 跌停判定

参数化构造 stock dict：

| AC | 输入 | 期望 |
|---|---|---|
| AC-3.1 | `{"change_pct": -29.5, "pure_code": "830001", "market": "bj"}` | `True` |
| AC-3.1 | `{"change_pct": -29.4, "pure_code": "830001", "market": "bj"}` | `False` |
| AC-3.2 | `{"change_pct": -19.5, "pure_code": "300001", "market": "sz"}` | `True` |
| AC-3.2 | `{"change_pct": -19.4, "pure_code": "300001", "market": "sz"}` | `False` |
| AC-3.2 | `{"change_pct": -19.5, "pure_code": "688001", "market": "sh"}` | `True` |
| AC-3.3 | `{"change_pct": -9.8, "pure_code": "600000", "market": "sh"}` | `True` |
| AC-3.3 | `{"change_pct": -9.79, "pure_code": "600000", "market": "sh"}` | `False` |
| AC-3.4 | `{"pure_code": "600000", "market": "sh"}`（无 `change_pct`） | `False`，不抛异常 |
| AC-3.4 | `{"change_pct": None, "pure_code": "600000", "market": "sh"}` | `False`，不抛异常 |

注意 `_is_dt_stock` 用 `stock.get(...)`，**缺失键与显式 None 走同一条路径**（`pct is None` → False），两条都测。

### 5.2 `core/indicators.py`（AC-4.x）

| AC | 构造与断言 |
|---|---|
| AC-4.1 | `close = pd.Series(range(1, 21), dtype=float)`；`ma(close, 5)` 的第 4 号索引（第 5 个）== (1+2+3+4+5)/5 == 3.0；前 4 个为 NaN |
| AC-4.2 | `res = macd(close)`；`assert_allclose(res["macd"], 2 * (res["dif"] - res["dea"]), rtol=1e-12, atol=1e-12)` |
| AC-4.3 | `res = kdj(high, low, close)`；`assert_allclose(res["j"], 3 * res["k"] - 2 * res["d"], rtol=1e-12, atol=1e-12)` |
| AC-4.4 | 构造 `high == low` 的区间（`high_n - low_n == 0`）；断言 k/d/j 无 NaN、无 inf、不抛异常。实现用 `.replace(0, 1e-9)` 兜底，预期结果有限 |
| AC-4.5 | 严格递增 close → `rsi(close).iloc[-1] > 90`；严格递减 → `< 10` |
| AC-4.6 | `res = boll(close)`；`assert_allclose(res["upper"] + res["lower"], 2 * res["mid"], rtol=1e-9, atol=1e-9)` |

> ⚠️ **同类不同实现，别混**：`indicators.kdj` 用 `.replace(0, 1e-9)`（分母置极小值），而 `tdx.KDJ` 用 `.replace(0, np.nan)` + `fillna(50)`（分母置 NaN 再补 50）。两者在「高低价相等」时的结果**不同**，测试要分别针对各自模块写，不能互相套期望值。

### 5.3 `core/tdx.py`（AC-5.x）

| AC | 构造与断言 |
|---|---|
| AC-5.1 | 参数化若干非法公式（如 `"选股: 1 + "`、`"选股: (C"`、`""`）→ `check_tdx_syntax` 返回 `ok is False` 且 `msg` 非空字符串，不抛异常 |
| AC-5.2 | 合法布尔公式（如 `"选股: C > MA(C,5);"`）→ `results, signal = evaluate_tdx(code, df)`；断言输出变量对应序列 `len(...) == len(df)` 且 `dtype == bool` |
| AC-5.3 | `"选股: KDJ.J > 80;"` → 不抛异常，且存在输出序列。该语法经 `_expand_attr_access` 展开为 `KDJ(HIGH,LOW,CLOSE,9,3,3)[2]` |
| AC-5.4 | 同 code + 同 df 连调两次，`assert_series_equal(r1, r2)`（含 index/values） |

> ✅ **AC-5.2 措辞已修订（2026-09-24）**：原写「返回布尔序列」，`requirements.md` 已改写为「返回二元组 `(结果字典, 信号)`，输出变量对应序列与输入等长、布尔公式时为布尔类型」。测试按此结构取 `results_dict[输出变量名]`。另：只有**布尔型**公式的输出才是 bool 序列，取值型公式（如 `X: MA(C,5)`）输出是浮点——被测公式要选布尔型。

> ⚠️ **非法样本需实测确认**：`check_tdx_syntax` 捕获的是 `parse_tdx` + `evaluate_tdx` 抛出的异常。某些"看起来非法"的公式可能恰好被容错跑通。Phase 4 首跑时逐一确认每个样本确实走到失败分支；若不成立，替换样本而不是改实现。

### 5.4 `core/market.py`（AC-6.x）

提取后（见 §6）两个函数均为纯函数，无需 mock：

| AC | 输入 | 期望 |
|---|---|---|
| AC-6.1 | `_compare_and_pick([], sina_nonempty, "industry")` | 返回 `sina_nonempty` 的副本 |
| AC-6.2 | `_compare_and_pick(em_nonempty, [], "industry")` | 返回 `em_nonempty` 的副本 |
| AC-6.3 | 两源前 5 名含 ≥3 个同名，且对应 `avg_pct` 平均偏差 > 0.5 | 返回 `sina_nonempty` |
| AC-6.4 | 两源前 5 名含 ≥3 个同名，平均偏差 ≤ 0.5 | 返回 `em_nonempty` |
| AC-6.5 | `_compare_and_pick([], [], "industry")` | `== []`，不抛异常 |
| AC-6.6 | `_clean_and_sort` 输入含 `avg_pct` 为 `"x"` / `None` / `float("nan")` 的行 + 若干正常行 | 脏行被剔除；结果按 `avg_pct` 严格降序 |

构造 AC-6.3 的样本时要**同时满足**「命中（hits）≥3」和「平均偏差 > 0.5」两个条件——这是最容易构造失败的地方：只放 2 个同名板块会因 hits<3 而回退东财。设计给出的样板：

```
em_rows   = [{"name":"农林牧渔","avg_pct":1.8}, {"name":"酿酒行业","avg_pct":1.7},
             {"name":"医药制造","avg_pct":1.6}, {"name":"半导体","avg_pct":1.5},
             {"name":"汽车行业","avg_pct":1.4}]
sina_rows = [{"name":"农林牧渔","avg_pct":3.6}, {"name":"酿酒行业","avg_pct":3.4},
             {"name":"医药制造","avg_pct":3.2}, {"name":"半导体","avg_pct":3.0},
             {"name":"汽车行业","avg_pct":2.8}]
# hits=5, 平均偏差 ≈ 1.8pp > 0.5 → 期望返回 sina_rows
```

AC-6.4 同样 5 条命中，但把偏差压到 ≤0.5（如两源 `avg_pct` 差 0.2）→ 期望返回 `em_rows`。

**注意**：`_compare_and_pick` 返回 `list(...)` 副本，测试断言应比对**内容相等**而非对象同一性（`==` 而非 `is`）。

## 6. 唯一的结构性改动：`core/market.py` 函数提取

当前 `_compare_and_pick`（原 208–235 行）与 `_clean_and_sort`（原 237–245 行）定义在 `get_boards()` 函数体内部，外部无法 import。二者均为**不依赖任何闭包变量的纯函数**（只用到参数与模块级 `math` / `logging`），是理想的提取对象。

**改动内容**：

1. 将两个函数**原样**移到 `core/market.py` 模块级（放在 `get_boards()` 定义之前）。
2. `get_boards()` 内部的两处调用改为调用模块级同名函数，删除嵌套定义。
3. **不**提取 `_parse_sina` / `_parse_em`——它们依赖 `requests` 且测试不需要，原地保留（最小改动原则）。

**行为不变性的保证**（约束 C-2 允许的唯一例外）：

- 函数体一行不改，只是从嵌套作用域搬到模块作用域；
- 二者原本就不引用 `get_boards()` 的局部变量（已确认只使用入参、模块级 `math`、模块级 `logging`）；
- 提取后 `get_boards()` 的输入输出、顺序、字段完全一致。

**验证方式**：提取前后各跑一次 `scripts/verify_boards.py`（联网验收脚本，对照新浪源 Top1）与 `scripts/diag_boards.py`，输出一致即认为行为未变。若你希望更保险，可在提取前先手工记录一次 `get_boards()` 的真实输出（如盘后无网络则用离线桩数据）作为对照基线。

**风险**：低。若 `math` / `logging` 未在模块级导入，需补 import —— 从现有代码看 `_clean_and_sort` 用了 `math.isnan`、`_compare_and_pick` 用了 `logging.getLogger`，需在 Phase 4 部署前确认模块顶部已有 `import math` / `import logging`，缺则补（这属于提取的必要配套，非行为变更）。

## 7. 需求追溯矩阵

| 验收标准 | 测试文件 | 测试函数（建议名） |
|---|---|---|
| AC-1.1 一键运行 | —— | pytest 天然满足；`pytest.ini` 定义 `testpaths` |
| AC-1.2 离线可跑 | `conftest.py` | `_no_network`（autouse 夹具） |
| AC-1.3 失败可视化 | 全局 | 统一使用 `assert actual == expected` |
| AC-1.4 60 秒内 | —— | 纯计算测试，设计目标 <5s（不做计时断言，避免不稳定） |
| AC-2.1 ~ 2.10 | `test_sentiment.py` | `test_calc_score_*`（参数化） |
| AC-3.1 ~ 3.4 | `test_sentiment.py` | `test_is_dt_stock_*`（参数化） |
| AC-4.1 ~ 4.6 | `test_indicators.py` | `test_ma_*` / `test_macd_*` / `test_kdj_*` / `test_rsi_*` / `test_boll_*` |
| AC-5.1 ~ 5.4 | `test_tdx.py` | `test_syntax_*` / `test_evaluate_*` |
| AC-6.1 ~ 6.6 | `test_market_boards.py` | `test_compare_and_pick_*` / `test_clean_and_sort_*` |

34 条 AC 全部有归属，无遗漏。

## 8. 风险与取舍

| 项 | 说明 | 应对 |
|---|---|---|
| pandas 3.0.3 较新 | 被测代码使用了 `.replace` / `rolling` / `ewm` 等；pandas 3.0 若有弃用警告 | 警告不视为失败；若某断言因 pandas 行为变化而不符，按「疑似缺陷」记录上报，不擅自改生产代码 |
| 环境分裂 | app 用 3.12、沙箱用 3.13，二者依赖不同 | 测试固定用 3.12.10 解释器（§3.2 给出绝对路径命令） |
| 手算期望值可能偏差 | §5.1 的 score 参考表为设计阶段手算 | 首跑校验，不符则记缺陷、校准回填 |
| 结构提取 | 动了生产文件 `core/market.py` | 限定为原样搬家 + 调用点替换，前后跑 `verify_boards.py` 对照 |
| 不引入覆盖率 | 非目标 | 不装 `pytest-cov`，不设门禁 |

## 9. 已确认事项（2026-09-24）

1. **pytest 安装位置** —— 采用**方案 A**：装入系统 Python 3.12.10，不新建 venv，不改 `start.bat`（见 §3.3）。
2. **`requirements.md` 措辞修正** —— 已完成：AC-2.10「向上取整」→「四舍五入取整」；AC-5.2 改为「返回二元组，输出变量序列等长/布尔」。另补充：`_is_dt_stock` 入参为字典的说明、C-2 例外条款（含缺陷修复）、C-6 明确解释器版本、非目标相应调整、§6 改为「已确认事项」。
3. **缺陷处理** —— **当场修复**（不等同于"记录"）：修复须作为独立提交，提交信息写明问题、根因与修复依据，并同步补充或更新对应测试用例。Phase 4 因此包含「缺陷甄别与修复」环节（见 `tasks.md`）。

> 遗留待办：**AC-2.9 手算参考表与非法公式样本**的有效性需在 Phase 4 实测校验（§5.1、§5.3），偏差按上述第 3 条甄别处理。
