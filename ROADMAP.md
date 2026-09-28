# ROADMAP — 项目维护计划

本文件记录 bull-run 的**非功能性**改进事项（仓库治理、工程质量、稳定性）。
具体功能需求仍走 `.trae/specs/` 的 spec 工作流。

状态：✅ 已完成 · 🔜 进行中 · ⬜ 待办

## 总览

| # | 事项 | 状态 | 工作量 | 风险 |
|---|------|------|--------|------|
| 1 | 根目录整理 | ✅ | 小 | 低 |
| 2 | 提交规范化 | ✅ | 小 | 低 |
| 3 | 补充回归测试 | ✅ | 中 | 低 |
| 4 | 锁定依赖版本 | ✅ | 小 | 低 |
| 5 | 数据缓存治理 | ✅ | 中 | 中 |
| 6 | app.py 路由瘦身 | ✅ | 中 | 中 |
| 7 | 历史提交信息清理（可选） | ⬜ | 中 | 高 |
| 8 | 板块双源校准比对逻辑修正 | ✅ | 小 | 中 |

---

## 1. ✅ 根目录整理

**问题**：根目录散落 4 个调试脚本 + 3 张临时截图，其中部分已误入库。

**做法**
- 4 个脚本归入 `scripts/` 并去掉 `_` 前缀：`diag_boards.py`、`verify_boards.py`、`v51_curl.py`、`v51_mock.py`
- 3 张量能校准截图归入所属 spec：`.trae/specs/optimize-overview-sentiment-volume/reference/`
- `scripts/diag_boards.py` 修正 `sys.path`（脚本下移一级后需指向项目根，否则 import core 失败）
- 新增 `scripts/README.md`，说明各脚本用途与运行方式
- `.gitignore` 增加 `_tmp_*`，防止临时产物再次入库

**完成于**：`c1f5a11` · 未删除任何内容，只做归位

---

## 2. ✅ 提交规范化

**问题**：多条历史 commit message 是把 `git status` 输出整段当消息体，历史不可读。

**做法**：把此前积压的两组未提交工作按主题拆成 3 个提交，采用
`type(scope): 中文简述` + 结构化 body（问题 / 根因 / 改动 / 验证）。

**完成于**：`c1f5a11`（整理）· `e49814e`（行业双源校准）· `06d21c3`（自选拖拽排序）

**遗留**：历史里的旧 message 未清理，见第 7 项。

---

## 3. ✅ 补充回归测试

**问题**：项目无 `tests/` 目录，验证依赖一次性脚本，改完没法一键回归。

**做法**
- 引入 `pytest`（装入系统 Python 3.12.10，与 `start.bat` 同环境），建 `tests/` 与 `pytest.ini`
- `tests/conftest.py` 提供 autouse 的 socket 阻断夹具，**强制离线**；统一 K 线夹具
- 四个测试文件共 **196 个用例**（第 8 项实施后增至 **205** 个），覆盖 4 个模块：
  - `test_sentiment.py` — `_calc_score` 五维度与等级边界、`_is_dt_stock` 三档阈值
  - `test_indicators.py` — MA / MACD / KDJ / RSI / BOLL 数值与内部恒等式
  - `test_tdx.py` — 语法检查、公式求值、指标属性访问、可重复性
  - `test_market_boards.py` — 双源选源判定与清洗排序
- 结构提取：`_compare_and_pick` / `_clean_and_sort` 由 `get_boards()` 内的嵌套函数提到模块级（行为不变，属需求约束 C-3 允许的例外）

**顺带修掉的 2 个缺陷**（测试暴露，当场修复）
1. `core/market.py` 缺模块级 `import math`，`_clean_and_sort` 处理**浮点** `avg_pct` 时抛 `NameError`
   → `get_boards()` 必炸 → `/api/overview` 冷启动首次请求 500，行业板块整块不可用
   （离线时两源皆空、循环不执行，反而掩盖了该问题）
2. `core/tdx.py` 项提取不识别 `[...]` 下标后缀，导致 `KDJ.J > 80`、`MACD.DIF > 0`、`BOLL.UP > C`
   这类「指标属性 + 比较运算」表达式畸形，选股公式**静默失效**（`get_signal` 吞掉异常返回 False）

**验收**：`pytest` 一键跑通（现有 **205** 个用例）、全绿、0.5 秒内结束；已做「改坏即变红」有效性自检
**需求 / 设计 / 任务**：`specs/add-regression-tests/`
**完成于**：本次提交（`fix(market)` + `fix(tdx)` + `refactor(market)` + `test`）

---

## 4. ✅ 锁定依赖版本

**问题**：`requirements.txt` 只有下限约束（`requests>=2.28` 等），上游大版本变更可能直接导致启动失败；
且无法复现「上次能跑」的环境。

**实施中发现的关键点（与建议方案不同，且必须成套落地）**

原建议是「`pip freeze > requirements.lock.txt`，或改成 `~=` 兼容约束」。实测后改用**另一条路**：

1. **只锁 4 项直接运行依赖（`==`），不做全量 `pip freeze`**。
   全量锁会把 `pywin32` 等平台专属包与全部间接依赖一并固化，换机器/Python 版本时反而更易装不上，
   且 60+ 行无法人工审阅。项目实际的痛点是「上游大版本破坏性变更」，锁直接依赖已足够覆盖。
2. **pin 必须配「先探测、缺了才装」，二者不可拆**。
   这是本项最容易踩空的地方：`start.bat` 原本每次启动都无条件 `pip install -r requirements.txt`。
   在 `>=` 时代这没问题（约束已满足时 pip 判定无需操作、秒退）；
   **改成 `==` 后语义反转** —— 本机版本一旦与 pin 有偏差，每次启动都会尝试**联网**调整版本，
   断网时 `pip` 失败 → `exit /b 1` → 起不来。可靠性反而低于改造前。
   故 `start.bat` 改为先跑 `check_deps.py --missing`，齐备则直接启动（不再联网）。
3. **`--missing` 刻意只判「包在不在」，不管版本对不对**。
   若把版本不符也算失败，则本机版本高于 pin 时会反复触发联网降级安装 —— 正是上一条要避免的。
   版本一致性交给报告模式（人工执行）负责。

**做法**

| 文件 | 改动 |
|---|---|
| `requirements.txt` | 4 项改 `==`：`requests==2.34.2` / `flask==3.1.3` / `numpy==2.4.6` / `pandas==3.0.3`，取值来自本机跑通全套测试的环境 |
| `requirements-dev.txt`（新增） | `-r requirements.txt` + `pytest==9.1.1`，把测试框架挡在运行环境之外 |
| `scripts/check_deps.py`（新增） | 依赖核查，纯标准库。报告模式逐包比对；`--missing` 只判缺失（供启动脚本用） |
| `start.bat` | 「每次无条件安装」→「先探测、缺了才装」；注释改写为英文（cmd 按 GBK 解析，中文注释会变乱码被当命令执行） |
| `tests/test_check_deps.py`（新增 11 例） | 解析 / 比对 / 命令行 / **守门用例** |
| `tests/test_startup.py`（新增 4 例） | `start.bat` 纯 ASCII、无 BOM、引用文件存在、先探后装 |

**验收**

- `pytest` **267 用例全绿**（252 原有 + 15 新增），离线可跑
- `python -m pip check` → `No broken requirements found.`
- `python scripts/check_deps.py` → 4 项全 OK，实装版本与 pin 完全一致
- **有效性自检**：把 `requests==2.34.2` 改回 `>=` → 守门用例变红；删除 `start.bat` 的探测行 →
  启动契约用例变红；恢复后 `sha1sum` 与改坏前一致，两处均完成自检

**注意：验收边界（如实记录）**

ROADMAP 原验收写的是「**在一台干净机器上按锁定的版本能一次装好并启动**」。
本次**没有条件做这项验证**（手边无第二台干净机器），只完成了替代验证：
`pip check` 无冲突、4 项 pin 与本机实装版本逐一相符、`--missing` 退出码为 0。
**残留风险**：若目标机 Python 版本与 3.12.10 差异较大，个别 pin 可能无对应 wheel。
处置方案见 `specs/lock-dependency-versions/design.md` §6。

**需求 / 设计 / 任务**：`specs/lock-dependency-versions/`

---

## 5. ✅ 数据缓存治理

> 需求 / 设计 / 任务：`specs/fix-stocklist-and-cache-health/`

**原问题（实测已推翻）**：`data/screener/klines` 已有 3,660 个 CSV、约 72M，「只增不减」。

**调研实测（2026-09-27）**

| 原论断 | 实测结果 | 结论 |
|---|---|---|
| 缓存「只增不减」 | `get_cached_kline()` 用 `to_csv` **覆盖写**，不追加；单文件行数上限 400 | ❌ 不成立 |
| 存在可清理的废弃文件 | 与实时清单（5,568 只）比对：疑似废弃 **0 个** | ❌ 无治理对象 |
| 体积异常（72M） | 逻辑体积 60.2 MB；`du` 的 72M 含 NTFS 簇对齐开销 | ❌ 属应有体积 |
| 按 mtime 删除可省空间 | 可省 **0 MB**，且删除后需重新联网拉取 3,660 次 | ❌ 负收益 |

**真实问题（本次修复）**：清单拉取失败后**静默产出残缺结果** ——
`_fetch_sina_stock_list()` 单页异常即 `break`，无重试、无日志、无校验，
残缺结果照常写入缓存并享有 24 小时有效期。本地 `stock_list.json` 实测**只有 300 条且 100% 是北交所**，
而全市场应有 5,568 只（沪 2,319 / 深 2,902 / 北 347）→ 选股候选池漏掉 94.6% 的标的，界面上毫无提示。

**做法**
- `core/screener.py`：单页失败递增退避重试（≤3 次），失败记 warning 且不中断后续页；
  拉取结束统一校验（失败页数 = 0 且条数 ≥ `_MIN_STOCK_COUNT = 2000`）才落库；
  不完整时**不覆盖旧缓存**，回退旧缓存并标记 `degraded`。
- `app.py`：`/api/screen/stock_list` 透出 `degraded` / `reason` / `count` 字段。
- `scripts/cache_health.py`：`report` 只读体检 + `clean` 清理（默认 dry-run，
  以当前完整清单为基准；清单降级时**拒绝清理**；复权孤儿需 `--orphan-adjust` 才纳入）。

**注意**：清理以**整文件**为粒度 —— 文件缺失时 `get_cached_kline()` 会自动重拉，
因此**不会**造成回测 250 日失真。该约束只适用于「未来若引入按行裁剪，必须保留 ≥250 行」。

**验收**
- 252 个回归用例全绿（新增 47 个，离线可跑）
- 真实环境 `load_stock_list(force=True)` 由 300 条修正为 **5,568 条（三市齐全）**
- `cache_health.py report` 输出与设计预期一致；`clean` 预演判定「待删 0 个」

---

## 6. ✅ app.py 路由瘦身

> 需求 / 设计 / 任务：`specs/slim-app-routes/`

**原问题**：`app.py` 890 行，业务算法与 HTTP 装配混在同一文件里。

**两处原定前提，实测均需更正**

| 原表述 | 实测结果 | 影响 |
|---|---|---|
| 「部分路由内嵌 70~85 行业务逻辑」 | 最厚的一块是 **81 行的 `_enrich_sentiment`，它根本不是路由**，而是被两个路由共用的模块级辅助函数 | 只搬 ROADMAP 点名的 2 个路由解决不了问题；而且新路由会跨层回调 `app.py` 的私有函数，形成 **core 依赖 app 的反向耦合**，比不改更糟 → 5 块必须一起搬 |
| 「用 `scripts/` 里的校验脚本回归」 | `scripts/` 下**没有**情绪校验脚本（只有联网契约校验与缓存体检两类） | 验收手段改为 `tests/test_app_routes.py` 契约测试 |

**做法**：算法回 `core/`，`app.py` 只留「参数校验 → 调 core → jsonify」。
HTTP 响应缓存字典（`_OVERVIEW_CACHE` / `_IDX_CMP_CACHE` / `_LOW_NEXT_CACHE` 等）属应用层关注点，**不下沉**。

| 原位置（`app.py`） | 行数 | 去向 |
|---|---|---|
| `_enrich_sentiment` | 81 | `emotion_history.enrich_sentiment` |
| `api_emotion_trend` 主体（含指数叠加段） | 68 | `emotion_history.get_trend_view` / `build_index_overlay` |
| `api_emotion_low_next` 主体 | 47 | `emotion_history.get_low_next_view` |
| ↳ 其依赖的 `_idx_closes` + `INDEX_TREND` + `_IDX_CLOSE_CACHE` | 16 | 随同上移（数据缓存，非 HTTP 缓存） |
| `api_market_distribution` 统计段 | 58 | `market.build_distribution(stocks)` |
| `api_index_compare` 主体 | 54 | `market.get_index_compare(days)` |
| `_is_limit_stock` | 11 | 与 `sentiment._is_dt_stock` 合并为 `limit_threshold` / `is_limit_stock` |

合计下沉 **335 行**（按 design 的分块口径；`app.py` 实际净减 **298 行**：890 → 592）。

**关键取舍**
- **先立契约、后动刀**：`tests/test_app_routes.py` 先在**未重构**的 `app.py` 上跑绿，
  之后任何一次搬迁都不得让它变红 —— 这是「零行为变更」承诺的唯一依据
- **core 新函数直接返回响应 dict**：与既有风格一致（`market.get_boards()` 等），搬迁量最小、逐字段可比对
- **取数与统计分离**：`build_distribution(stocks)` / `get_index_compare(days)` 是纯函数，
  测试只需喂一个 list，不必打桩 `screener`、不必起 Flask
- **不做「顺手优化」**：平盘的严格不等式与 ±0.001 边界归属、9 区间从高到低的级联顺序、
  `up_count` 的 `(change_pct or 0)` 语义、日期交集为空时返回 `set()` 而非 `None`、
  单个指数失败静默跳过 —— 全部逐行保持原样
- **`_is_limit_stock` 合并保两个对外行为**：抽出共享的 `limit_threshold`，
  `_is_dt_stock` 退化为 `is_limit_stock(stock, -1)` 薄包装，调用方与既有用例都不用改

**验收**
- **350 个回归用例全绿**（重构前 267；新增 83 = 23 路由契约 + 24 涨跌停阈值等价 + 36 市场统计单测），离线可跑、约 5 秒
- **行数**：`app.py` 890 → **592** 行（限 610）；顶层函数 709 → **404** 行（限 450）
- `python -c "import app"` 通过，26 条路由数量不变（确认 `core/` 未新增反向依赖）
- **「改坏即变红」有效性自检 3 项**（逐项改坏 → 对应用例变红 → 回滚 → `sha1sum` 一致）：
  ① 平盘边界改闭区间 → 2 例变红；② 删单点复制 `scores * 2` → 1 例变红；③ 冰点收益取当日而非次日 → 2 例变红

**遗留（可选）**：`scripts/verify_emotion.py`（联网真机对照情绪序列）未做，
纯离线契约测试已覆盖字段与取值口径，真机对照作为独立任务择期补。

---

## 7. ⬜ 历史提交信息清理（可选，有风险）

**问题**：约 12 条历史 message 是 `git status` 原文，不可读。

**做法**：`git rebase -i --root` 逐条重写 message，或 `git filter-repo --message-callback`。

**风险**：高
- 会改写所有 commit hash，需要 `push --force`
- 若该仓库在其他机器克隆过且有未推送改动，会破坏其本地历史

**建议**：仅在你确认这是单人仓库、其他机器无未推送改动时执行。若图省事，
也可以不清理，从本次往后的提交保持规范即可。

---

## 8. ✅ 板块双源校准比对逻辑修正

**问题**（写第 3 项回归测试时发现）

经实测深挖，本项实际由**三个独立问题**叠加，比初判更严重：

### ① 东财排序参数写错 —— 榜单候选池从一开始就是错的（主因）

`_parse_em()` 用 `"fl": "f3"` 试图按涨跌幅排序，但 `fl` 是「返回哪些字段」的参数，
**不具备任何排序作用**。正确写法是 `fid=f3`（排序字段）+ `po=1`（降序）。

后果：东财行业板块共 **496 个**（`total=496`），而请求只取 `pz=100`；排序失效后返回的是
**按板块代码排序的前 100 个**，而非涨幅最高的 100 个 → 涨幅最高的板块（林业、其他医疗服务、
纺织鞋类制造等）全部被截断在候选池之外。

实测对比（2026-09-24 收盘后真实数据）：

| # | 修正前 `fl=f3` | 修正后 `fid=f3&po=1` |
|---|---|---|
| 1 | 风电设备 **+2.15%** | 林业Ⅲ **+5.83%** |
| 2 | 纺织制造 +1.31% | 其他医疗服务 +4.29% |
| 3 | 电视广播Ⅱ +0.77% | 其他家电Ⅲ +4.24% |

榜首 2.15% vs 5.83%，**相差 2.7 倍** —— 这正是"涨幅偏低约一半"的直接原因。

### ② 双源校准从未生效

`_compare_and_pick()` 依赖「两源存在同名板块、可交叉比对」的前提，实测不成立：
新浪返回 49 个大类、东财返回 496 个细分，**名称交集仅 6 个（重合率 12.2%）**；
即使两源都先降序取前 5，命中数仍为 **0** → `hits >= 3` 永假 → 校准是一段死代码。

### ③ 榜单出现同层级重复项

东财板块含Ⅰ/Ⅱ/Ⅲ 层级，修正排序后 Top10 中会出现「林业Ⅲ +5.83%」与「林业Ⅱ +5.83%」
等成对重复，白占榜单名额。

**做法（已实施）**

- `_parse_em()`：`fl=f3` → `fid=f3`，并补注释说明为何不能用 fl
- `_compare_and_pick()` → 替换为 `_pick_source()`：东财优先；东财为空或条数 <20 时回退新浪；
  两者皆空返回 `[]`。整段失效的交叉比对逻辑删除
- 新增 `_dedup_by_level()`：按「去掉末尾罗马数字后的基名」去重，保留涨幅更高的一条
- `get_boards()`：新浪改为**按需拉取**（仅东财不可靠时请求），正常路径网络请求由 4 次降为 2 次；
  编排体由约 70 行缩减至 12 行
- 解析函数 `_parse_sina` / `_parse_em` 提到模块级，使请求参数可被测试断言（防止再次写错）

**验收**

- `scripts/verify_boards.py` 三项判定全部 **PASS**：
  ① 榜单严格降序 ② 榜首与东财源一致 ③ 无同层级重复项
- `tests/test_market_boards.py` 用例由 10 个增至 19 个（净增 9 个），其中 `test_parse_em_uses_fid_sort_param`
  是本缺陷的回归防线（已做"改坏即变红"自检）
- 实施结果：Top10 首位「林业Ⅲ +5.83%」，与东财源完全一致；pytest **205 用例全绿**

**需求 / 设计 / 任务**：`specs/fix-boards-source-selection/`（Phase 1~3）

**注意**：本项**不影响**第 3 项测试的有效性 —— `test_market_boards.py` 用构造数据验证判定逻辑，
本项解决的是「判定在真实数据上能否正确触发」。
