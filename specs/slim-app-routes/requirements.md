# 需求：app.py 路由瘦身

> 对应 ROADMAP 第 6 项「app.py 路由瘦身」。
> 调研中发现该项的两处前提需要更正：**最厚的逻辑块不是路由**（§1.2），
> 且**原定的验收手段不存在**（§1.4）。

## 1. 背景与问题

### 1.1 现状：六块逻辑占了 41% 的篇幅

`app.py` 共 **890** 行、**26 个路由**。按顶层函数统计（含装饰器），**709 行**落在函数体内，
其中 6 块明显偏厚：

| 行数 | 位置 | 类型 | 名称 | 实际在干什么 |
|---|---|---|---|---|
| 81 | L84 | **辅助**（非路由） | `_enrich_sentiment` | 历史序列 + 实时情绪 → 前端要的 `scores/labels/prev_score` |
| 68 | L331 | 路由 | `api_emotion_trend` | 指数叠加归一化 + `latest` 实时覆盖 |
| 58 | L261 | 路由 | `api_market_distribution` | 9 个涨跌幅区间的级联统计 |
| 54 | L811 | 辅助（后台线程） | `background_screener` | 定时选股推送 |
| 54 | L525 | 路由 | `api_index_compare` | 多指数归一化对比 |
| 47 | L416 | 路由 | `api_emotion_low_next` | 冰点日次日收益统计 |

合计 **362 行，占 app.py 的 41%**。

### 1.2 更正一：最厚的那块根本不是路由

ROADMAP 原文说「部分路由内嵌 70~85 行业务逻辑」。实测：
**81 行、最厚的一块是 `_enrich_sentiment`，它是个被两个路由共用的辅助函数**
（`/api/overview` 与 `/api/emotion_trend` 都调它）。若只按字面去搬"路由"，
这块最大的问题会被漏掉。

更本质的判据不是行数，而是**代码性质**：

- `api_market_distribution` 里有 9 个区间的级联判断，含 `0.001` / `-0.001` 这种**刻意的边界设计**
  （保证"平盘"与 `0~2%`、`-2~0%` 互斥且不重叠）；
- `api_emotion_low_next` 里有"冰点日 → 次一交易日 → 收益率 → 均值/胜率"的统计；
- `api_index_compare` 里有"取多指数日期的交集 → 按首值归一化到 100"的计算。

这些**全是算法与统计，与 HTTP 毫无关系**，却因为它们写在路由函数里而
**完全无法离线测试** —— 这才是真正的问题。

### 1.3 后果：没有护栏，谁也不敢碰 app.py

`tests/` 目前覆盖 `core/` 的 4 个模块 + `screener` + `cache_health` + `check_deps` + `start.bat`，
共 **267 个用例**；**对 `app.py` 的覆盖是零**（实测 `grep -rln "test_client\|import app" tests/` 无结果）。

于是本次改动撞上一个先有鸡还是先有蛋的问题：
**要重构 app.py，且承诺不改任何行为；但没有任何测试能证明"行为没变"。**

### 1.4 更正二：ROADMAP 写的验收手段不存在

ROADMAP 第 6 项原文：「验收：情绪专区 4 张卡片功能与数据不变（**用 `scripts/` 里的校验脚本回归**）」。

实测 `scripts/` 现有全部脚本：

| 脚本 | 实际校验对象 |
|---|---|
| `check_deps.py` | Python 依赖版本 |
| `verify_boards.py` | 板块榜 |
| `diag_boards.py` | 板块数据诊断 |
| `cache_health.py` | K 线缓存 |
| `v51_curl.py` | **量能接口** `/api/liangneng` |
| `v51_mock.py` | 量能权重函数 |

**没有任何一个校验情绪专区**。`v51_curl.py` 名字里带 `curl` 容易误认，但它只打 `/api/liangneng`。

→ 这条验收路径**不存在**，必须另建手段（见 §2.1 第 3 项与 §7.3）。

## 2. 范围

### 2.1 本次要做

1. **把 5 块纯计算逻辑从 `app.py` 下沉到 `core/`**（§1.1 中除 `background_screener` 外的 5 项，约 308 行）。
2. **消除一处重复实现**：`app._is_limit_stock` 与 `core/sentiment.py::_is_dt_stock` 判定口径完全相同
   （app 里的注释自己就写了「与 `sentiment._is_dt_stock` 口径一致」），实测两者阈值
   均为 `9.8 / 19.5 / 29.5`（bj 优先）→ 合并为一处。
3. **补上测试护栏**（§1.3）：新增 app 接口契约测试，且**必须先对重构前的代码跑通**。
4. `app.py` 回归「参数校验 → 调用 core → `jsonify`」的装配职责。

### 2.2 本次不做

- **不改任何响应结构、字段名、字段顺序与数值口径**（前端零改动）。
- 不重构后台线程（`background_monitor` / `background_screener`）—— 它们属应用生命周期，不是路由装配。
- 不引入 Flask 蓝图（blueprint）、不换框架、不动静态资源。
- 不重构 CRUD 类路由（`/api/indicators/*`、`/api/config`）—— 本就薄，且含文件 IO，属另一关注点。
- 不改 `core/` 中已有算法的实现（只**新增**函数 + **复用**既有函数）。

## 3. 用户故事

- **US-1**：作为维护者，我希望改情绪卡片相关的计算时能跑测试确认没弄坏，而不是只能手工点页面看。
- **US-2**：作为维护者，我希望打开 app.py 一眼看清"有哪些接口、各自要什么参数"，
  不必在 80 行统计逻辑里翻找。
- **US-3**：作为使用者，我希望这次重构后，情绪专区 4 张卡片、涨跌分布、指数对比的
  **数字和以前一模一样**。
- **US-4**：作为维护者，我希望同一套涨跌停阈值判定只有一份实现，不再有两处各自演化。

## 4. 验收标准（EARS）

### 4.1 行为不变（US-3）

- **AC-1.1** the 重构 shall 不改变任何路由的 URL、HTTP 方法、响应状态码与 JSON 字段名。
- **AC-1.2** When 以相同输入调用任一被重构的接口，the 响应 shall 与重构前逐字段一致
  （含数组长度、`None` 出现的位置、数字精度与取整方式）。
- **AC-1.3** the `/api/emotion_trend` 的 `latest` shall 仍携带 `score / level / date / trade_date /
  zt_count / dt_count / zb_count / break_rate / promo_rate / max_height / contributions /
  history_scores / history_labels / prev_score` 全部字段。
- **AC-1.4** While 历史序列只有一个数据点，the `history_scores` shall 仍复制为两个相同点
  （ECharts 单点不画线的既有修复，不得回退）。
- **AC-1.5** When 涨跌幅恰好等于区间边界值（`0.001` / `-0.001` / `2` / `5` / `7` / `-2` / `-5` / `-7`），
  the 分布统计 shall 归入与重构前相同的区间。
- **AC-1.6** When 指数在冰点日的**次一交易日**不存在（如停牌或已是最后一个交易日），
  the 次日收益 shall 记为 `None` 且不计入均值与胜率的分母。

### 4.2 代码搬家的完整性（US-1、US-2）

- **AC-2.1** the `app.py` shall 不再包含涨跌幅区间统计、指数归一化、冰点次日收益这三类算法代码。
- **AC-2.2** the `app.py` 顶层函数行数 shall 由 709 行降至 **450 行以下**，总行数由 890 行降至 **610 行以下**。
- **AC-2.3** When 同一段逻辑被两个及以上调用方使用，the 实现 shall 在 `core/` 中只有一份。
- **AC-2.4** the 涨跌停阈值判定 shall 只有一份实现（`app._is_limit_stock` 与 `sentiment._is_dt_stock` 合并）。
- **AC-2.5** the 被下沉的函数 shall 只依赖传入参数与 `core` 内模块，
  不得出现 `from flask import ...`、`request`、`jsonify`。
- **AC-2.6** While 合并 `_is_dt_stock` 与 `_is_limit_stock`，the 两者原有的**对外行为** shall 各自保持不变
  （一个是"是否跌停"的布尔判断，一个是"按 sign 判涨停/跌停"）。

### 4.3 可测试性（US-1）

- **AC-3.1** the 测试套件 shall 新增 `tests/test_app_routes.py`，使用 Flask `test_client`，
  且**离线可跑**（网络入口全部 monkeypatch）。
- **AC-3.2** the 新增用例 shall 至少覆盖 `/api/emotion_trend`、`/api/emotion_low_next`、
  `/api/market_distribution`、`/api/index_compare`、`/api/overview` 五个接口。
- **AC-3.3** the 新增用例 shall 在**重构前**的 `app.py` 上全部通过（先立契约，后动刀）。
- **AC-3.4** While 重构进行中，the 上述契约用例 shall 持续保持绿色；任一变红即视为行为被破坏。
- **AC-3.5** the 新增用例 shall 对关键数值使用**可手算的 mock 数据**（等差序列构造），
  不得采用"先跑一遍再把输出抄成期望值"的自证式断言。
- **AC-3.6** the `tests/conftest.py` 的 socket 阻断夹具 shall 继续生效，全套测试离线可跑。

### 4.4 不退化（US-1）

- **AC-4.1** While 改动前 267 个用例存在，the 重构 shall 不使其中任何一个失败。
- **AC-4.2** When 执行 `pytest`，the 全套 shall 通过且仍在秒级完成。
- **AC-4.3** When 改动涉及 `core/` 中已有模块（如 `sentiment.py` 新增公开函数），
  the 既有对应用例 shall 同步补齐（沿用"改 `core/` 必跑测试"的既有纪律）。

## 5. 约束

- **C-1 零行为变更**：本次是纯搬迁 + 去重，不夹带任何功能修改、字段重命名或"顺手优化"。
  若搬迁中暴露缺陷，按既有约定**当场修、独立提交、写明根因**，不混在同一次提交里。
- **C-2 离线可测**：新增测试不得发起真实网络请求（沿用 `conftest.py` 的 socket 阻断夹具）。
- **C-3 前端零改动**：`static/`、`templates/` 一行都不动。
- **C-4 环境一致**：系统 Python 3.12.10 + 项目既有 pytest。
- **C-5 先立契约后动刀**：契约测试必须在重构**之前**写入并跑绿，否则该护栏无效。
- **C-6 提交拆分**：按「测试护栏 / 情绪模块下沉 / 市场模块下沉 / 文档」分开提交，便于单独回滚。

## 6. 非目标

- 不引入 flask-restful / 蓝图 / 依赖注入等架构改造。
- 不重构后台线程（`background_monitor` / `background_screener`）。
- 不动 `/api/indicators/*` 的 CRUD 逻辑（含文件 IO）。
- 不清理模块级 HTTP 缓存字典（`_OVERVIEW_CACHE` / `_LN_CACHE` / `_GOLD_CACHE` /
  `_KLINE_CACHE` / `_IDX_CMP_CACHE` / `_LOW_NEXT_CACHE`）—— 它们属应用层关注点，留在 app.py。
- 不做接口性能优化、加日志、改错误码等顺手活。

## 7. 待确认事项（附推荐值）

1. **下沉范围** —— 建议**把 §1.1 的 5 块一起做**（约 308 行），而非只做 ROADMAP 点名的 2 个路由。
   理由：`api_emotion_trend` 内部就调用 `_enrich_sentiment`，只搬路由不搬共用函数等于没搬干净；
   且这 5 块属同一类问题（算法写在 HTTP 层）。
   备选：严格只做 ROADMAP 点名的 `api_emotion_trend` + `api_emotion_low_next`（约 115 行）。
2. **核心函数的返回形态** —— 建议 `core` 新函数**直接返回响应 dict**
   （与现有 `market.get_boards()` / `gold.get_gold_overview()` 的风格一致），路由只做 `jsonify(...)`。
   备选：返回中间数据结构、由路由组装 —— 更"纯"，但搬迁量翻倍且更易引入偏差。
3. **验收手段** —— ROADMAP 说的那份脚本不存在（§1.4）。建议**新增 `tests/test_app_routes.py`
   接口契约测试**（离线、可反复跑、能"改坏即变红"）。可选再补一个联网的 `scripts/verify_emotion.py`
   做真机数据对照（非必须）。
4. **HTTP 缓存字典是否下沉** —— 建议**留在 app.py**。

## 8. 验收边界（诚实说明）

- 本次**无法证明"绝对零行为变更"**，只能证明：**在被契约测试覆盖的输入范围内**，响应逐字段一致。
  未覆盖的分支（如数据源返回意外结构、`kline` 拉取失败）仍存在理论上的偏差风险；
  缓解手段是尽量让契约用例覆盖异常分支（数据源返回空 / 抛异常 / 字段缺失）。
- 契约用例的 mock 数据是**人造的**，不能替代真机验证。若需要真机确认，
  建议重构前后各启动一次服务、对同一批接口抓取响应做比对（可作为可选任务，见 tasks.md）。
- 本次**不动**前端的实际渲染，故"4 张卡片显示正常"这一点只能靠"响应字段未变"来间接保证，
  不在本次的因果链内。
