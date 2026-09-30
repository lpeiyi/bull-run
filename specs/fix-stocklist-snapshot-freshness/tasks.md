# 任务清单：全市场行情快照的时效与有效性治理

> 对应 `requirements.md` / `design.md`。12 个任务分 4 阶段。
> 参数已定（老陆 2026-09-30 确认）：有效性阈值 90% / 交易时段 TTL 120s / 非交易时段 TTL 12h /
> 并发度 6 / 新增启动预热 / 缓存 `version` 递增到 3。

## 阶段 1 · 时效与有效性（core 核心改动）

- [ ] **1. 新增常量与纯函数**
  - `core/screener.py` 新增常量：`_TTL_TRADING=120`、`_TTL_IDLE=12*3600`、`_VALID_PRICE_RATIO=0.90`、
    `_MIN_VALID_SAMPLE=100`、`_FETCH_WORKERS=6`、`_MAX_PAGE=60`、`_MIN_RETRY_INTERVAL=60`
  - 新增纯函数 `snapshot_valid_ratio(stocks)`、`snapshot_is_valid(stocks)`（样本 < 100 直接返回 `True`）
  - 新增纯函数 `_in_quote_window(now=None)`（交易日 09:15~11:30、13:00~15:00）、`_cache_ttl(now=None)`
  - 全部为纯函数，`now` 可注入，**不得**在函数内直接读系统时钟以外的外部状态
  - _Requirement: AC-1.1、AC-2.1、AC-2.2、AC-3.1_

- [ ] **2. 改造 `_fetch_sina_stock_list` 为分批并发**
  - 保持签名与返回 `(stocks, ok)` 不变；`_PAGE_SIZE = 100` 提为模块级常量
  - 按 `_FETCH_WORKERS` 分批，批内并发执行；每页内部保留原有的 3 次退避重试
  - **原样保留三条既有语义**：单页重试后成功 / 单页耗尽不中断后续页 / 整批全失败达
    `_MAX_CONSECUTIVE_FAIL` 即提前结束
  - 尾页判定：任一批内出现返回条数 < `_PAGE_SIZE` 的页 → 结束拉取
  - 上限保护：`_MAX_PAGE` 用尽时若最后一页仍满 100 条 → 记 warning（提示上限需上调）
  - 输出前按 `code` 升序排序，保证产物确定性（核查结论：全部消费方均不依赖顺序）
  - 改造前先 grep 确认 `_fetch_sina_stock_list` 调用点（预期仅 `load_stock_list_meta` 一处）
  - _Requirement: AC-3.1~3.4、AC-1.2_

- [ ] **3. 改造 `load_stock_list_meta`：TTL 分层 + 有效性闸门 + 防惊群**
  - 新增模块级 `_FETCH_LOCK = threading.Lock()` 与 `_LAST_ATTEMPT = {"ts": 0.0, "usable": False}`
  - 快路径改为 `_directly_usable(cached, now)`：`complete is True` **且** 有已知 `version`
    **且** `now - ts < _cache_ttl(now)` **且** 有效性三态判定通过
  - 慢路径加锁 → **双检**缓存 → 最小重试间隔抑制 → 拉取 → `valid = ok and snapshot_is_valid(stocks)`
  - `valid` 为真才写缓存；为假时走 `_fallback_or_empty`，**不得**覆盖已有有效缓存
  - 新增 `_meta_valid_or_unknown(stocks, meta)`：v3 看 `valid` 标记，v1/v2 无标记则**当场判定**
  - `meta` 新增 `valid` / `stale` 两个键；既有四个键（`degraded`/`count`/`fetched_at`/`reason`）语义不变
  - `force=1` 穿透新鲜度判断、双检、重试间隔抑制
  - `load_stock_list(force)` 签名与返回不变
  - _Requirement: AC-1.3~1.5、AC-2.3~2.5、AC-4.1~4.4_

- [ ] **4. 缓存文件升级为 v3**
  - `_LIST_VERSION` 由 2 改为 3；`_write_stock_list_cache` 增加 `"valid": True` 字段
  - 读取侧保持兼容：无 `version`（v1）/ `version=2` 的旧文件可正常读出，按 §3.6 三态处理
  - 旧文件在下次成功拉取后自然被覆盖为 v3
  - _Requirement: 约束 C-4、C-5_

- [ ] **5. 启动时预热清单**
  - `app.py` 的 `__main__` 块新增 `_warmup_stock_list()`：调用一次 `screener.load_stock_list(force=True)`，
    异常吞掉（与既有 `_warmup_emotion` 同风格），用 daemon 线程启动
  - 目的：把首次请求约 4 秒的拉取挪到页面打开之前
  - 注意：仅在进程启动且**行情窗口内**预热（窗口外拉取无意义，但也不报错，直接照常拉一次即可）
  - _Requirement: AC-3.1、需求 §7.5_

## 阶段 2 · 接口与前端

- [ ] **6. `/api/market_distribution` 透传状态**
  - `app.py` 该路由改用 `load_stock_list_meta(force=force)`，在 `build_distribution(stocks)` 的结果上
    追加 `stale` / `degraded` / `reason` / `snapshot_at`（`snapshot_at` 为格式化后的 `fetched_at`，无数据为 `""`）
  - **不改动** `build_distribution` 的任何既有字段，也不把状态注入逻辑下沉到 `core/`
  - 同步核查 `/api/screen/stock_list` 是否需要透出 `stale`（可选，属增量字段）
  - _Requirement: AC-5.3、AC-5.5、约束 C-4_

- [ ] **7. 前端：刷新入口 + 状态标注 + 口径标注**
  - `loadDistribution(force)` 支持 `force` → 拼 `?force=1`
  - `#ov-refresh` 点击时同时调 `loadOverview(true)` 与 `loadDistribution(true)`
  - `templates/index.html` 涨跌统计卡片标题增加 `<span class="hint mono" id="dist-status"></span>`
    并在提示文案中标注 `全市场实时快照`
  - `renderDistribution(d)` 末尾渲染 `#dist-status`：不可用 / 基于某日数据 / 数据时间（三级优先级见 design §3.8）
  - `d.degraded` 或 `d.total === 0` 时**不画柱**，显示既有空态样式 `boards-empty`
  - 情绪卡片 `#se-dims` 行前加固定说明 `口径：东财涨停池（收盘）`
  - **不新增定时器**：`doFastRefresh` 已每 60s 调 `loadDistribution()`
  - _Requirement: AC-5.1~5.5、AC-6.1~6.3_

## 阶段 3 · 测试

- [ ] **8. 同步调整既有用例（仅 2 个）**
  - `test_screener_stocklist.py::test_consecutive_failures_abort_early`：断言改为「总请求数不超过第一批的量」
    **且**「未拉满 `_MAX_PAGE`」，保留"断网不空转"的原意
  - `test_screener_stocklist.py::test_fresh_complete_cache_used_without_fetch`：保留原用例，
    另加一版 **v3 缓存**（带 `valid: true`）直用的用例
  - 明确写入注释：这两个用例的行为断言随并发化调整，**语义未变**
  - **其余用例一律不得修改**（含 `test_app_routes.py` 的 23 个路由契约）
  - _Requirement: AC-7.1_

- [ ] **9. 新增 `tests/test_screener_snapshot.py`**
  - 复用 `test_screener_stocklist.py` 的 `iso` 夹具风格（临时清单文件 + 假 `_sina_get` + `sleep` 置空）
  - 覆盖：有效性边界（0% / 89.9% / 90% / 100% / 空表 / 样本不足豁免）
  - 覆盖：TTL 分层（119s vs 121s、11.9h vs 12.1h、午休、周末）
  - 覆盖：无效快照不写缓存（比对缓存文件字节不变）
  - 覆盖：无效时回退可用旧缓存（标 `degraded` + `stale`）；旧缓存也是废数据 → 当场判无效 → 返回空
  - **覆盖「盘前场景」核心回归**：63.5% `price=0` 的桩 + 时间打桩 09:20 → 不返回废数据；
    时间推进到 10:00 且桩返回真实行情 → 拿到有效数据
  - 覆盖：single-flight（多线程并发 + 过期缓存 → 实际拉取批次只有一份）
  - 覆盖：最小重试间隔（60s 内第二次不发请求）
  - 覆盖：并发/串行等价性、按 `code` 排序的确定性
  - 全部离线（沿用 `tests/conftest.py` 的 socket 阻断夹具）
  - _Requirement: AC-7.2、AC-7.3_

## 阶段 4 · 验证与收尾

- [ ] **10. 有效性自检（改坏即变红）**
  - 自检 A：`_VALID_PRICE_RATIO` 由 `0.90` 改为 `0.0` → 「无效快照不污染」用例应变红
  - 自检 B：`_cache_ttl` 恒返回 `24 * 3600` → 「TTL 分层」用例应变红
  - 每次自检后回滚并核对 `sha1sum` 与改前一致
  - _Requirement: AC-7.4_

- [ ] **11. 全量回归 + 真实环境核验**
  - `"C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe" -m pytest` 全套通过（现有 369 + 新增），离线可跑
  - 真实环境（**盘中**执行，利用当前时间窗口）：
    - 记下当前 `stock_list.json` 的 `ts` 与统计值 → 等 TTL 过期后再请求 `/api/market_distribution`
    - 断言数据时点已更新、`price=0` 占比降到 1% 以下
    - 对比修复前后同一接口的 `zt_count`（预期从"启动快照"变为"当前实时"）
  - 真实环境（**盘前场景**）：无法实时复现，用 §5.2 的时间打桩用例替代，并在报告中说明这一限制
  - _Requirement: AC-7.1、AC-7.3_

- [ ] **12. 文档与记忆更新、提交**
  - `ROADMAP.md`：新增「第 9 项 · 快照时效与有效性」并标记完成（或并入 §已知遗留的处置说明）
  - `README.md`：补一句数据时效策略（120s / 12h 与有效性判据）
  - `specs/optimization-audit-20260930/findings.md`：在 P0-1 处标注"已由 `fix-stocklist-snapshot-freshness` 处置"，
    并更正"建议方向"中"短期拆两段缓存"的表述（实测已否决，见 design §4）
  - `.workbuddy/memory/`：记本次改动与实测数据；`MEMORY.md` 同步长期事实（TTL 策略、并发度、有效性阈值）
  - 提交拆分：`perf(screener):` 并发拉取 / `fix(screener):` 时效与有效性 / `feat(ui):` 前端标注 /
    `test:` 用例 / `docs:` 文档
  - 确认工作区干净、无临时文件入库
  - _Requirement: 全部_

---

## 验收对照

| 阶段 | 对应 AC | 通过标准 |
|---|---|---|
| 1 · core | AC-1.1~1.5、AC-2.1~2.5、AC-3.1~3.5、AC-4.1~4.4 | 纯函数可脱网单测；并发实测 ≤5s |
| 2 · 接口前端 | AC-5.1~5.5、AC-6.1~6.3 | 接口字段可查；页面状态与口径标注可见 |
| 3 · 测试 | AC-7.1~7.3 | 现有用例仅 2 个按语义调整；新增用例全绿；离线可跑 |
| 4 · 收尾 | AC-7.4、全项 | 两项自检均变红并回滚一致；真实环境数据变新；提交规范 |

## 依赖与顺序

```
1 ──→ 2 ──→ 3 ──→ 4 ──→ 6 ──→ 7 ──→ 11 ──→ 12
                  └──→ 9 ──→ 10 ──→ 11
        └──→ 8 ──────────────→ 11
5 ──────────────────────────────→ 11
```

- 任务 1 是 2、3、9 的前提（常量与纯函数）
- 任务 3 是 4、6 的前提（`meta` 新键与闸门逻辑）
- 任务 8 必须在任务 2 之后（并发化是改用例的原因）；**先跑一遍全套确认只有这 2 个变红**
- 任务 10 依赖任务 9 的用例存在
- 任务 5 独立，可与 2~4 并行

## 已知限制（交付时需在报告中标明）

1. **盘前场景无法真机复现**：验证时是盘中，无法把系统时间拨回 09:00 跑真实链路。
   以「时间打桩 + 真实形态桩数据」的离线用例作为替代证据，并在报告中写明。
2. **节假日不识别**：`_in_quote_window` 不挂休市日历，法定假日会有约 120 次无谓拉取（拉到的是昨日收盘快照，有效）。
3. **`_MAX_PAGE = 60` 的余量**：对应 6000 只。若标的数超过该上限，需上调常量（拉取时会记 warning 提示）。
