# 设计：app.py 路由瘦身

> 对应 `requirements.md`。本次是**纯搬迁 + 去重**，唯一的新增产物是测试护栏（§5）。

## 1. 目标结构

改动前：算法与 HTTP 装配混在同一个文件里。

```
app.py (890 行)
├── 装配职责（参数校验 / jsonify / HTTP 缓存）   ← 应该只有这些
├── ✗ _enrich_sentiment          81 行  情绪序列组装
├── ✗ api_emotion_trend 里的叠加  60 行  指数归一化
├── ✗ api_market_distribution    54 行  9 区间统计
├── ✗ api_index_compare          50 行  多指数归一化
├── ✗ api_emotion_low_next       40 行  冰点次日收益统计
└── ✗ _is_limit_stock            11 行  涨跌停阈值（与 sentiment 重复）
```

改动后：**算法回 core，app.py 只留装配**。

```
app.py (≈610 行)          参数校验 → 调 core → jsonify（+ 模块级 HTTP 缓存字典）
   │
   ├─→ core/emotion_history.py   情绪历史视图  ：enrich_sentiment / build_index_overlay
   │                                              get_trend_view / get_low_next_view
   ├─→ core/market.py            市场统计      ：build_distribution / get_index_compare
   └─→ core/sentiment.py         涨跌停阈值    ：limit_threshold / is_limit_stock
```

依赖方向均为 `app → core`，`core` 内部**不新增反向依赖**（`market → sentiment` 已有先例，
见 market.py L112 的 `from core.sentiment import _dt_list_sina`）。

## 2. 下沉清单

| # | 原位置（app.py） | 行数 | 目标模块 | 新函数 | 归属理由 |
|---|---|---|---|---|---|
| 1 | `_enrich_sentiment` L84–164 | 81 | `core/emotion_history` | `enrich_sentiment(s)` | 本质是"历史序列 + 实时分"的组装，而历史序列归 emotion_history |
| 2 | `api_emotion_trend` L331–398 | 68 | `core/emotion_history` | `get_trend_view(days, force)` | 指数叠加与 `latest` 覆盖属情绪视图 |
| 2b | ↳ 其中指数叠加段 L341–355 | 15 | `core/emotion_history` | `build_index_overlay(dates, kline_days)` | 被 2 调用（trend 视图内部）；独立后便于单测 |
| 3 | `api_emotion_low_next` L416–462 | 47 | `core/emotion_history` | `get_low_next_view(threshold, days)` | 冰点日统计，同属情绪历史 |
| 3b | ↳ `_idx_closes` L405–413 + `_IDX_CLOSE_CACHE` | 9 | `core/emotion_history` | `_idx_closes(code)` | 数据获取 + 模块级缓存，可整体搬迁 |
| 3c | ↳ `INDEX_TREND` 常量 L322–328 | 7 | `core/emotion_history` | `INDEX_TREND` | 只服务于上述两个视图 |
| 4 | `api_market_distribution` L261–318 | 58 | `core/market` | `build_distribution(stocks)` | 全市场涨跌幅统计，属市场模块 |
| 5 | `api_index_compare` L525–578 | 54 | `core/market` | `get_index_compare(days)` | 指数对比，属市场模块 |
| 6 | `_is_limit_stock` L248–258 | 11 | `core/sentiment` | `is_limit_stock(stock, sign)` | 与 `_is_dt_stock` 同一口径，应合并 |

**合计下沉 328 行**（含常量与辅助），app.py 顶层函数行数 709 → 约 413。

## 3. 关键设计决策

### 3.1 为什么"只做 ROADMAP 点名的 2 个路由"不够

`api_emotion_trend`（68 行）内部第一件事就是调 `_enrich_sentiment`，而后者 **81 行、被两个路由共用**。
如果只搬路由、把 `_enrich_sentiment` 留在 app.py，结果是：

- app.py 仍然藏着一块最大的情绪算法（81 行），问题没解决；
- 路由变薄，但"算法在 HTTP 层"的本质没变；
- 而且新路由要跨层回调 app.py 里的私有函数，形成**core 依赖 app** 的反向耦合，比不改更糟。

所以 §2 的 5 块必须一起搬。

### 3.2 core 新函数直接返回"响应 dict"

与既有风格一致（`market.get_boards()`、`gold.get_gold_overview()`、`screener.backtest_indicator()`
都直接返回可 `jsonify` 的结构），路由侧只剩一行调用。

| 方案 | 优点 | 缺点 |
|---|---|---|
| **返回响应 dict（采用）** | 搬迁量小、结构与搬迁前逐字段一致、易核对 | core 承担了"视图形状"职责 |
| 返回中间数据结构，路由组装 | 层次更"纯" | 搬迁量翻倍；组装代码留在 app.py，仍不符合 AC-2.1；两处结构拼接更易引入偏差 |

本次的第一诉求是**零行为变更**，方案一在这点上风险最低。

### 3.3 `_enrich_sentiment` 为什么放 `emotion_history.py`

它做的事情是：取近 20 日历史序列 → 兜底当天 → 补 `scores/labels/prev_score` → 单点复制成两点。
其中"取历史序列"（`get_emotion_trend`）本来就在 `emotion_history.py`，搬过去后
从跨模块调用变成**同模块内部调用**，反而更自然（`get_emotion_trend(20)` 不再需要前缀）。

命名：去掉前导下划线改为 `enrich_sentiment`（它已成为跨模块公开接口）。

### 3.4 `_is_limit_stock` 的合并方式：保两个对外行为

两者判定口径实测**完全一致**（`bj` 29.5%、`300`/`688` 19.5%、其余 9.8%），但**对外形态不同**：

| 现有函数 | 形态 | 调用方 |
|---|---|---|
| `sentiment._is_dt_stock(stock)` | 只判跌停，返回 bool | `sentiment` 内部、既有测试 |
| `app._is_limit_stock(stock, sign)` | 按 `sign` 判涨停/跌停 | `/api/market_distribution` |

**不能直接改任一方的签名**（会破坏调用方）。做法：抽出共享的阈值函数，两侧都变成薄包装。

```python
# core/sentiment.py 新增
def limit_threshold(stock):
    """该股涨跌停幅度（正数百分比）：bj 29.5 / 300|688 19.5 / 其余 9.8"""
    if stock.get("market", "") == "bj":
        return 29.5
    pure_code = stock.get("pure_code", "")
    if pure_code.startswith("300") or pure_code.startswith("688"):
        return 19.5
    return 9.8

def is_limit_stock(stock, sign):
    """按 sign 判涨停(+1)/跌停(-1)；change_pct 缺失返回 False（与原有行为一致）"""
    pct = stock.get("change_pct")
    if pct is None:
        return False
    t = limit_threshold(stock)
    return pct >= t if sign > 0 else pct <= -t

def _is_dt_stock(stock):          # 保留原签名与语义，改为薄包装
    return is_limit_stock(stock, -1)
```

`_is_dt_stock` 的**对外行为逐分支等价**已核对：
原实现是 `if bj → pct<=-29.5; if 300|688 → pct<=-19.5; else pct<=-9.8`，
新实现先算同一个阈值再取负比较 —— 包括"`change_pct is None` 返回 False"这一条也一致。

### 3.5 HTTP 缓存字典留在 app.py

`_OVERVIEW_CACHE` / `_LN_CACHE` / `_GOLD_CACHE` / `_KLINE_CACHE` / `_IDX_CMP_CACHE` / `_LOW_NEXT_CACHE`
是 **HTTP 层的响应缓存**（TTL 60/120/300/600 秒），与算法无关，属应用层关注点。

因此：

- **不下沉**，路由自行判断缓存命中后再调 core；
- 相应地，core 的新函数**不接收 `force` 参数**（除 `get_trend_view` —— 它的 `force` 是传给
  `emotion_history.get_emotion_trend` 的**数据缓存**刷新开关，属 core 内部语义，与 HTTP 无关）。

唯一的例外是 `_IDX_CLOSE_CACHE`（`{code: {日期: 收盘}}`）：它是**指数字典的数据缓存**，
不含 TTL、不属 HTTP 语义，随 `_idx_closes` 一起搬到 `emotion_history.py`。

### 3.6 数据获取与统计分离

`api_market_distribution` 的第一行是取数（`screener.load_stock_list(force=force)`），
其余 54 行是统计。设计上**只下沉统计**：

```python
# app.py
stocks = screener.load_stock_list(force=force)      # 取数留在路由（含 force 语义）
return jsonify(market.build_distribution(stocks))   # 统计在 core
```

好处：`build_distribution(stocks)` 变成**纯函数**，测试只需喂一个 list，不必 mock `screener`；
也避免 `market` 为了一行取数去依赖 `screener`。

## 4. 各新函数的设计要点

### 4.1 `core/sentiment.py`

见 §3.4。**新增 2 个函数**（`limit_threshold` / `is_limit_stock`），
`_is_dt_stock` 改为薄包装。既有测试（`tests/test_sentiment.py` 里针对 `_is_dt_stock` 的用例）
**必须保持通过** —— 这与 AC-2.6 是一致的双重保险。

### 4.2 `core/market.py`

```python
def build_distribution(stocks):
    """全市场涨跌幅分布统计。返回
    {"ranges": [...9 项...], "total": int, "zt_count": int,
     "dt_count": int, "up_count": int, "down_count": int}"""
```

**必须原样保留的分支**（这些是刻意的设计，不是随手写的）：

1. 9 个区间的级联判断顺序 —— 从高到低 `>=7 / >=5 / >=2 / >=0.001 / >-0.001 / >=-2 / >=-5 / >=-7 / else`，
   保证每只股票**只计入一个区间**；
2. `平盘` 用严格不等式 `-0.001 < pct < 0.001`，边界 `0.001` 归 `0~2%`、`-0.001` 归 `-2~0%`；
3. `ranges` 里 `min`/`max` 字段**仅作展示**，归类不用它们（注释已写明）；
4. `up_count` / `down_count` 用 `(s.get("change_pct") or 0)` 比较 —— 注意 `None` 走 `or 0`
   后**不计入**上涨也不计入下跌。

```python
def get_index_compare(days):
    """4 指数近 days 日归一化叠加。返回 {"dates": [...], "series": [{"name","values"}]}"""
```

**必须原样保留**：

1. 目标指数与名称是**固定 4 个**（`sh000001/sz399001/sz399006/sh000300`）——注意与
   `INDEX_TREND`（5 个）**不是同一个列表**，不能混用；
2. `days` 只接受 `15/30/60`，非法值由**路由**规范化（保持现有行为：路由里判断，core 只接收合法值）；
3. 取日期**交集**：逐个指数把 `{YYYYMMDD: close}` 的 key 求交，任一指数为空则跳过它；
   全空时 `common_dates = set()`（**不是** `None`）；
4. 归一化以**该系列首个非零值**为基数 → 首值恒为 `100`，缺失日给 `None`；
5. 某指数 `kline` 抛异常 → 该系列直接不出现（`continue`），不影响其它指数、不返回 500。

### 4.3 `core/emotion_history.py`

```python
INDEX_TREND = [...]                         # 从 app.py 搬来（5 个指数）
_IDX_CLOSE_CACHE = {}
def _idx_closes(code): ...                  # 搬来（kline_range 全量 + 缓存）
def enrich_sentiment(s): ...                # 搬来（原 app._enrich_sentiment）
def build_index_overlay(dates, kline_days): ...   # 新拆分出的纯计算段
def get_trend_view(days=15, force=False): ...     # 组装完整响应
def get_low_next_view(threshold=30, days=0): ...  # 组装完整响应
```

**`enrich_sentiment` 必须原样保留的细节**：

1. `_to_score` 的双层兜底：非数字 → `50`；可转 float → 取整，越界（<0 或 >100）→ `50`；
2. 日期归一化 `YYYYMMDD → YYYY-MM-DD`；
3. 历史序列 `len < 3` 时用 `force=True` 重取一次；
4. 取最近 **15** 个点（`scores[-15:]`）；
5. 历史序列为空时的两级兜底（有 `score` 则用实时分，无则用 `50`）；
6. **单点复制成两点**（`scores * 2`）—— ECharts 单点不画线的既有修复（AC-1.4）；
7. 返回前对 `scores` 再做一次 `_to_score` 强制校验。

> 观察（**本次不动**）：`prev_score` 的分支
> `if last_date == today_date: ... else: ...` 两个分支代码完全相同，属冗余。
> 本次按 C-1「不夹带」原则**原样搬迁**；若老陆确认，可作为独立的清理提交。

**`get_trend_view` 的顺序**（不能调换）：先取历史序列 → 生成 `dates` → 拉指数叠加 →
组装 `latest`（再被实时 `sentiment.get_sentiment()` 覆盖）→ 最后一次性组装响应。
其中 `latest` 覆盖段整体包在 `try/except` 里，**失败时静默保留 `trend[-1]`**（不得改成抛错）。

`get_low_next_view` 的统计口径：`ret = (次日收盘 / 当日收盘 - 1) * 100` 保留 2 位；
`avg` 保留 2 位、`win_rate` 保留 1 位；`n == 0` 时 `avg` 与 `win_rate` 均为 `None`（**不是 0**）。

## 5. 测试策略（本次最需要想清楚的部分）

### 5.1 契约测试的基本形态

新增 `tests/test_app_routes.py`，用 Flask 自带的 `test_client`，**不启动真实服务**：

```python
import app as app_module

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
```

可行性已实测：`import app` 成功、`url_map` 有 26 条路由、模块级无网络调用、
启动逻辑都在 `if __name__ == "__main__"` 内 → 导入安全、离线可用。

### 5.2 ⚠️ 关键坑：`from X import f` 造出的"引用副本"

app.py 顶部有几处 `from ... import ...`：

```python
from core.data import real_quotes, kline, kline_range
from core.notifier import send_feishu
from core.tdx import check_tdx_syntax
```

这类写法在 `app` 模块里**复制了一份函数引用**。因此：

- `monkeypatch.setattr(app_module, "kline", fake)` ✅ 有效
- `monkeypatch.setattr(core.data, "kline", fake)` ❌ **无效**（app 里绑的还是原函数）

而本次重构会把这些调用**从 app.py 移到 core 里**，于是打桩目标也要跟着变：

| 阶段 | `kline` 的调用点 | 需要打桩的目标 |
|---|---|---|
| 重构前 | `app.kline` | `app` 模块属性 |
| 重构后 | `emotion_history.kline`、`market.kline` | 这两个模块属性 |

**若不处理，契约测试在重构后会"因为没打上桩而真的去联网"**（被 conftest 的 socket 阻断夹具拦下报错），
更糟的情况是被 mock 之外的分支掩盖成假绿。

→ 对策：做一个**统一打桩夹具**，把所有可能的挂载点一次性替换：

```python
@pytest.fixture
def patch_data_sources(monkeypatch):
    """把 kline / kline_range 打桩到所有可能持有引用的模块上。
    重构前后挂载点不同，故全覆盖；并断言桩确实被调用，避免假绿。"""
    calls = []
    def _fake_kline(code, days=250, adjust="qfq"):
        calls.append(("kline", code, days))
        return _make_df(...)
    def _fake_kline_range(code, start=None, end=None, adjust="qfq"):
        calls.append(("kline_range", code, start))
        return _make_df(...)
    for mod in (app_module, emotion_history, market, screener):
        if hasattr(mod, "kline"):
            monkeypatch.setattr(mod, "kline", _fake_kline)
        if hasattr(mod, "kline_range"):
            monkeypatch.setattr(mod, "kline_range", _fake_kline_range)
    return calls
```

用例里对需要触发取数的接口**断言 `calls` 非空** —— 否则"桩没被调用"会让用例失去意义。

### 5.3 用例清单

| 接口 | 用例 | 锚定的 AC |
|---|---|---|
| `/api/market_distribution` | 9 区间边界归类（喂 `7 / 5 / 2 / 0.001 / 0 / -0.001 / -2 / -5 / -7` 等构造值） | AC-1.5 |
| | `zt/dt/up/down` 家数（含 `change_pct=None` 不计入涨跌） | AC-1.2 |
| | `total == len(stocks)` | AC-1.2 |
| | `degraded` 清单下仍能正常返回结构 | AC-1.2 |
| `/api/emotion_trend` | 响应字段齐全（`dates/labels/scores/zt_count/dt_count/break_rate/promo_rate/max_height/levels/contributions/indexes/latest`） | AC-1.3 |
| | `latest` 被实时 `get_sentiment` 覆盖，且 14 个字段齐全 | AC-1.3 |
| | 指数叠加：等差收盘 → 首值 = 100、后续可手算 | AC-1.2 |
| | `days<=0` → 传给 `kline` 的 `days == 1000` | AC-1.2 |
| | 历史序列只有 1 点 → `history_scores` 长度 2 且两点相同 | AC-1.4 |
| | `kline` 抛异常 → `indexes == []`，接口仍 200 | AC-1.2 |
| | `get_sentiment` 抛异常 → `latest` 回退为 `trend[-1]`，接口仍 200 | AC-1.2 |
| `/api/emotion_low_next` | 冰点日次日收益：等差收盘可手算（如 100→101 记 +1.0） | AC-1.2 |
| | 冰点日无次日 → `ret is None` 且不计入 `n` | AC-1.6 |
| | `n == 0` → `avg` 与 `win_rate` 均为 `None` | AC-1.2 |
| | `threshold` 参数生效（改阈值 → 冰点日数量变化） | AC-1.2 |
| | 同参数命中 600 秒缓存、不同参数不命中 | AC-1.2 |
| `/api/index_compare` | 4 指数日期取交集 | AC-1.2 |
| | 归一化首值 = 100 | AC-1.2 |
| | `days=45` → 按 60 处理（规范化在路由） | AC-1.2 |
| | 某指数失败 → 该系列缺失、其余正常 | AC-1.2 |
| `/api/overview` | 60 秒缓存：第二次请求不重复取板块数据 | AC-1.2 |
| | `sentiment` 每次实时（即使命中缓存也重新计算） | AC-1.2 |
| | `force=1` 绕过缓存 | AC-1.2 |
| | 结构含 `trade_date/index_order/indexes/sentiment/ladder/zt_pool/zb_pool/dt_pool/boards` | AC-1.3 |
| `core/sentiment.py` | `limit_threshold` 三档阈值 + `is_limit_stock` 正负方向 + `change_pct=None` | AC-2.6 |
| | `_is_dt_stock` 与 `is_limit_stock(stock, -1)` 结果一致（旧行为保持） | AC-2.6 |

**数据构造原则**（AC-3.5）：用等差序列（如收盘 `100, 101, 102...`），
使归一化、收益率、均值都有闭式解，期望值可手算 —— 沿用项目既有 `kline_factory` 的思路。

### 5.4 执行顺序（这是本次的成败关键）

```
① 写 tests/test_app_routes.py  →  在【重构前】的 app.py 上跑绿   ← 先立契约
② 重构 app.py + core（分批）   →  每一步都跑 ① 的用例          ← 契约保持绿 = 行为未变
③ 每次搬迁后再跑全套 267 + 新增
```

若 ① 在重构前就跑不绿，说明用例写错了（而不是代码有问题）—— 这一步同时也是对用例本身的校准。

### 5.5 有效性自检

按既有规矩，至少做两次"改坏即变红"：

| 改坏方式 | 预期变红 |
|---|---|
| 把 `平盘` 区间的 `-0.001 < pct < 0.001` 改成 `<=` | 分布边界用例 |
| 把 `enrich_sentiment` 的单点复制 `scores * 2` 删掉 | `history_scores` 长度用例 |
| 把 `_idx_closes` 的"次日"改成"当日" | 冰点次日收益用例 |

每处改坏后确认对应用例变红，再回滚并核对文件哈希一致。

## 6. 风险与处置

| 风险 | 触发条件 | 处置 |
|---|---|---|
| 打桩没生效 → **测试假绿** | 重构后调用点移入 core，patch 目标未同步 | §5.2 的统一夹具 + 断言桩被调用 |
| 契约用例先绿后红被误判为"重构引入 bug" | 用例锚定过细（如断言了 mock 数据的全部数值） | 用例只锚定**结构与可手算的关键数值**（AC-3.5） |
| 搬迁时漏抄异常兜底分支 | 手工搬运 300 余行 | 逐函数对照搬迁；契约用例专门覆盖"数据源抛异常""返回空"分支 |
| 顺手改了行为 | 觉得某处代码冗余/不好看 | C-1：只搬家不改逻辑；`prev_score` 的冗余分支已识别但**本次不动**（§4.3） |
| core 新增 import 造成循环依赖 | `market → sentiment` 等 | 该依赖已有先例（market.py L112）；实施后立刻 `python -c "import app"` 验证 |
| `_is_dt_stock` 改薄包装后既有用例变红 | 等价性判断有误 | 先跑 `tests/test_sentiment.py` 确认既有用例仍绿（AC-2.6 的双保险） |
| 改动夹带 → 出问题难定位 | 一次提交里混合多处改动 | C-6：按「测试护栏 / 情绪下沉 / 市场下沉 / 文档」拆提交，可单独回滚 |

## 7. 对现有功能的影响

| 面 | 影响 |
|---|---|
| HTTP 契约 | **无**。URL、方法、状态码、字段名、数值口径全不变 |
| 前端 | **无**。`static/`、`templates/` 零改动 |
| 数据文件 | **无**。`config.json` / `indicators.json` / `data/` 均不涉及 |
| 启动 | **无**。`start.bat` → `app.py` 链路不变 |
| 测试 | **新增** `tests/test_app_routes.py`；既有 267 个用例须全绿 |
| 可维护性 | app.py 顶层函数 709 → 约 413 行；算法落地 `core/`，可离线单测 |
