# 任务清单：app.py 路由瘦身

对应 `requirements.md` / `design.md`。13 个任务分 5 阶段，**全部未开始**（待确认）。

> **执行铁律**：阶段 1（立契约）必须先完成并**在重构前的代码上跑绿**，
> 之后的任何一次搬迁都不得让这批用例变红。违反这条，本次「零行为变更」的承诺就没有依据。

## 阶段 1 · 立契约（测试护栏）

- [ ] **1. 建立 `tests/test_app_routes.py` 骨架与统一打桩夹具**
  - `import app as app_module` + `test_client` 夹具（可行性已实测：26 条路由、导入安全、离线可跑）
  - 实现 `patch_data_sources` 夹具：把 `kline` / `kline_range` 打到**所有可能持有引用的模块**上
    （`app` / `emotion_history` / `market` / `screener`），并记录调用序列供断言
  - 原因见 design §5.2：`from X import f` 会复制引用，重构后打桩目标会变，必须全覆盖
  - 数据构造用等差序列（可手算），沿用 `conftest.kline_factory` 的思路
  - _Requirement: AC-3.1、AC-3.5、AC-3.6_

- [ ] **2. 契约用例：`/api/market_distribution`**
  - 9 区间边界归类：喂 `7 / 5 / 2 / 0.001 / 0 / -0.001 / -2 / -5 / -7` 及其邻域值，断言落入预期区间
  - `zt_count / dt_count / up_count / down_count`（含 `change_pct=None` 不计入涨跌）
  - `total == len(stocks)`
  - _Requirement: AC-1.2、AC-1.5、AC-3.2_

- [ ] **3. 契约用例：`/api/emotion_trend`**
  - 13 个顶层字段齐全 + `latest` 的 14 个字段齐全（AC-1.3 的字段清单）
  - `latest` 被实时 `sentiment.get_sentiment()` 覆盖
  - 指数叠加：等差收盘 → 首值 100、后续值手算可比
  - `days<=0` → 传给 `kline` 的 `days == 1000`
  - 历史仅 1 点 → `history_scores` 长度 2 且两点相同
  - 异常分支：`kline` 抛异常 → `indexes == []` 且仍 200；`get_sentiment` 抛异常 → `latest` 回退 `trend[-1]`
  - _Requirement: AC-1.2、AC-1.3、AC-1.4、AC-3.2_

- [ ] **4. 契约用例：`/api/emotion_low_next`**
  - 冰点日次日收益手算（等差收盘，如 100 → 101 记 `+1.0`）
  - 冰点日无次日 → `ret is None` 且不计入 `n`（AC-1.6）
  - `n == 0` → `avg` 与 `win_rate` 均为 `None`（不是 0）
  - `threshold` 参数生效；同参数命中 600 秒缓存、异参数不命中
  - _Requirement: AC-1.2、AC-1.6、AC-3.2_

- [ ] **5. 契约用例：`/api/index_compare` 与 `/api/overview`**
  - `index_compare`：4 指数日期取交集；归一化首值 100；`days=45` 被规范化为 60；某指数失败时该系列缺失
  - `overview`：60 秒缓存命中（第二次不重复取板块）；`sentiment` 每次实时；`force=1` 绕过缓存；9 个字段齐全
  - **验收闸**：在**未改动的 app.py** 上跑绿 → 契约成立
  - _Requirement: AC-1.2、AC-1.3、AC-3.2、AC-3.3_

## 阶段 2 · 情绪模块下沉

- [ ] **6. `_enrich_sentiment` → `emotion_history.enrich_sentiment`**
  - 原样搬迁 81 行，逐条保留 design §4.3 列出的 7 个细节（`_to_score` 双层兜底、日期归一化、
    `<3` 时 `force` 重取、取最近 15 点、两级空序列兜底、单点复制成两点、返回前强制校验）
  - 去掉前导下划线；`app.py` 两个调用点（`/api/overview`、`/api/emotion_trend`）同步改名
  - 搬迁后跑阶段 1 的用例 + `tests/test_sentiment.py`
  - _Requirement: AC-2.1、AC-2.3、AC-2.5_

- [ ] **7. `api_emotion_trend` 主体 → `emotion_history.get_trend_view`**
  - 拆出 `build_index_overlay(dates, kline_days)`
  - 搬入 `INDEX_TREND` 常量（5 个指数，注意与 `index_compare` 的 4 个**不是同一列表**）
  - `latest` 覆盖段整体 `try/except`，失败静默保留 `trend[-1]`（不得改成抛错）
  - 路由收敛为：解析 `force` / `days` → `jsonify(emotion_history.get_trend_view(...))`
  - _Requirement: AC-1.3、AC-2.1、AC-2.2_

- [ ] **8. `api_emotion_low_next` 主体 → `emotion_history.get_low_next_view`**
  - 一并搬入 `_idx_closes` 与 `_IDX_CLOSE_CACHE`（design §3.5 的例外说明）
  - 保留取整口径：`ret` 2 位、`avg` 2 位、`win_rate` 1 位；`n == 0` 时 `avg`/`win_rate` 为 `None`
  - 600 秒缓存 `_LOW_NEXT_CACHE` **留在 app.py**，core 函数不接 `force`
  - _Requirement: AC-1.2、AC-1.6、AC-2.1、AC-2.2_

## 阶段 3 · 市场模块下沉

- [ ] **9. `api_market_distribution` 统计段 → `market.build_distribution(stocks)`**
  - **只下沉统计**，取数（`screener.load_stock_list`）留在路由（design §3.6）
  - 原样保留 9 区间级联顺序、`平盘` 的严格不等式与 `0.001` / `-0.001` 边界归属
  - `ranges` 的 `min`/`max` 仍仅作展示字段
  - _Requirement: AC-1.5、AC-2.1、AC-2.2、AC-2.5_

- [ ] **10. `api_index_compare` 主体 → `market.get_index_compare(days)`**
  - 固定 4 指数与名称（不得与 `INDEX_TREND` 混用）
  - 保留日期交集逻辑、`common_dates = set()`（非 `None`）的空集兜底、首值归一化、异常指数跳过
  - `days` 的合法化（15/30/60）**留在路由**；`_IDX_CMP_CACHE` 留在 app.py
  - _Requirement: AC-1.2、AC-2.1、AC-2.2、AC-2.5_

## 阶段 4 · 涨跌停阈值去重

- [ ] **11. 合并 `_is_limit_stock` 与 `_is_dt_stock`**
  - `core/sentiment.py` 新增 `limit_threshold(stock)` 与 `is_limit_stock(stock, sign)`
  - `_is_dt_stock` 改为 `return is_limit_stock(stock, -1)`，**签名与语义不变**
  - 删除 `app._is_limit_stock`，其调用方改调 `sentiment.is_limit_stock`
  - 补充用例：三档阈值、正负方向、`change_pct=None`；
    并断言 `_is_dt_stock(stock) == is_limit_stock(stock, -1)` 逐样本一致
  - 跑 `tests/test_sentiment.py` 确认既有跌停用例仍绿（AC-2.6 的双保险）
  - _Requirement: AC-2.3、AC-2.4、AC-2.6、AC-4.3_

## 阶段 5 · 验证与收尾

- [ ] **12. 全量验证与有效性自检**
  - `pytest` 全套通过（既有 267 + 新增），离线可跑，耗时仍在秒级
  - 目标行数核对：app.py 顶层函数 ≤ 450 行、总行数 ≤ 610 行（AC-2.2）
  - `python -c "import app"` 通过（确认 core 新增 import 未造成循环依赖）
  - **有效性自检**（design §5.5），逐项改坏 → 确认对应用例变红 → 回滚 → 核对哈希一致：
    ① `平盘` 区间的严格不等式改成 `<=`；② 删掉 `scores * 2`；③ 把 `_idx_closes` 的"次日"改成"当日"
  - _Requirement: AC-2.2、AC-4.1、AC-4.2_

- [ ] **13. 文档同步与提交**
  - `ROADMAP.md` 第 6 项标记完成，更正两处前提（§1.2 最厚块不是路由；§1.4 原定验收手段不存在）
  - `README.md`：项目结构补充 `tests/test_app_routes.py`；如涉及则说明 app.py 的职责边界
  - `scripts/README.md`：如新增 `scripts/verify_emotion.py` 则补条目（可选任务，见下）
  - `.workbuddy/memory/`：追加当日日志；`MEMORY.md` 视情况补"app.py 职责边界"与"契约测试"条目
  - 提交拆分（C-6）：`test(app)` 契约护栏 / `refactor(emotion)` 情绪下沉 /
    `refactor(market)` 市场下沉 / `refactor(sentiment)` 阈值去重 / `docs` 文档
  - _Requirement: 全部_

---

## 验收对照

| 阶段 | 对应 AC | 通过标准 |
|---|---|---|
| 1 · 立契约 | AC-3.1~3.3、AC-1.2/1.3/1.4/1.5/1.6 | 新增用例在**未改动**的代码上跑绿 |
| 2 · 情绪下沉 | AC-2.1~2.3、AC-2.5 | 契约用例保持绿 + app.py 该段逻辑清空 |
| 3 · 市场下沉 | AC-1.5、AC-2.1、AC-2.2 | 契约用例保持绿 + 行数达标 |
| 4 · 阈值去重 | AC-2.4、AC-2.6 | 新旧两个入口行为一致 + 既有用例绿 |
| 5 · 收尾 | AC-2.2、AC-4.1~4.3 | 全套绿 + 有效性自检 + 文档同步 |

## 依赖与顺序

```
1 ──→ 2 ──┐
  └─→ 3 ──┤
  └─→ 4 ──┼──→ 6 ──→ 7 ──→ 8 ──→ 9 ──→ 10 ──→ 11 ──→ 12 ──→ 13
  └─→ 5 ──┘
```

- 任务 1 是任务 2~5 的前提（夹具与骨架）
- 任务 2~5 全部完成并在**重构前**跑绿之后，任务 6 以后才开始（C-5 铁律）
- 任务 6 是任务 7 的前提（`get_trend_view` 内部要调用 `enrich_sentiment`）
- 任务 12 的有效性自检需要三个阶段的下沉都已完成
- 任务 11 与 9 都在 `market`/`sentiment` 里动刀，但互不依赖，可互换顺序

## 可选任务（需老陆确认）

- [ ] **A. 新增 `scripts/verify_emotion.py`（联网真机对照）**
  - 用途：补 ROADMAP 原本期望、但实际不存在的"情绪专区校验脚本"
  - 做法：直连真实数据源，拉取 `/api/emotion_trend`、`/api/emotion_low_next`、
    `/api/market_distribution`、`/api/index_compare`，输出关键数值（情绪分、冰点样本数、
    涨跌家数、指数归一化首值）供人工对照
  - 与契约测试的分工：契约测试管"结构不变"，此脚本管"真机数据看起来对"
  - _Requirement: AC-1.2 的补充手段_

## 未完成 / 遗留

- **"4 张卡片显示正常"不在本次因果链内**：本次不动前端，只能保证"响应字段未变"。
  若老陆要在界面上确认，需人工打开页面点一遍（或做可选任务 A）。
- **异常分支的理论风险**：契约用例覆盖不到的输入（如数据源返回意外结构）仍可能有行为偏差，
  详见 requirements.md §8。
