# Implementation Plan — cut-sentiment-latency

> Phase 3。需求见 `requirements.md`，设计见 `design.md`。
> 参数已拍板：请求去重=做 / 池缓存 TTL=**30s** / 东财限流=**0.35s** / `_dt_count`=**改**。
> 完成后逐项勾选，并在交付报告里附「改造前后同机耗时对比」与「请求序列对比」。

## 阶段 1 — L1 东财访问层

- [x] 1. 新增 `core/em_api.py`：全局限流 + 池结果 30s 进程内缓存
  - 常量：`EM_MIN_INTERVAL=0.35` / `EM_JITTER=(0.05,0.15)` / `POOL_TTL=30` / `ZTB_UT`
  - `get(url, params, timeout=10)`：**锁内**完成 sleep 与请求，全局单份 `_last`
  - `pool(endpoint, date, sort="fbt:asc")`：锁内 double-check 缓存 → 未命中才请求 → 成功才写缓存
  - **当日空池不写缓存**（红线 AC-4.1）；其它日期的空池照常缓存
  - `clear_cache()` / `cache_info()`（供测试与排障）
  - _Requirement: AC-1.1 / AC-2.1 / AC-2.2 / AC-2.3 / AC-4.1 / AC-4.3_

- [x] 2. 失败自适应降速（**可选，建议做**，约 15 行）
  - 连续 `EM_BACKOFF_STREAK=3` 次失败 ⇒ 有效间隔翻倍，上限 `EM_BACKOFF_MAX=2.0s`
  - 连续 `EM_RECOVER_STREAK=10` 次成功 ⇒ 恢复 `EM_MIN_INTERVAL`
  - `cache_info()` 回报当前有效间隔，便于断言与排障
  - _Requirement: AC-5.1（可观测性）· design §1.3(f)_

- [x] 3. `sentiment.py` / `market.py` 收敛为薄包装，删除各自重复的限流实现
  - `sentiment._em_pool(endpoint, date, sort="fbt:asc")` → `em_api.pool(...)`（**保留旧名**）
  - `market._em_pool(endpoint, date)` → `em_api.pool(..., sort="fbt:asc")`（**保留旧名**）
  - 删除两处 `_em_get` / `_em_last` / `EM_SESSION`；`market` 的 `timeout=12` 与 `sentiment` 的 `10` 取值差异需显式取一个并在注释里说明
  - 确认 `core/emotion_history.py:32-33` 的 `sentiment._em_pool(...)` 调用点**不用改**
  - 写入前先 `assert "_em_last" not in 新内容`；写完重扫导入，删掉变成死引用的 `random` / `requests` 等
  - _Requirement: AC-1.1 / AC-2.4 · design §1.3(e)_

## 阶段 2 — L3 只读入口

- [x] 4. `core/screener.py` 新增 `peek_stock_list(max_age=None, require_valid=True)`
  - 判据链：文件可解析 → 条数 ≥ `_MIN_STOCK_COUNT` → `now - ts <= max_age` →（`require_valid` 时）过有效性闸门
  - `max_age=None` 时用 `_cache_ttl()`（行情窗口内 `_TTL_TRADING` / 窗口外 `_TTL_IDLE`）
  - **绝不发起网络请求**；不可用返回 `(None, None)`
  - 复用既有 `_read_stock_list_cache()` / `_meta_valid_or_unknown()`，不复制判据逻辑
  - 对既有 `load_stock_list_meta()` 的行为**零影响**
  - _Requirement: AC-3.2 · design §2.2_

## 阶段 3 — L2 情绪分取值层

- [x] 5. `core/sentiment.py` 两处调用点改为只读快照
  - `_dt_list_sina()` → `peek_stock_list(max_age=_dt_peek_max_age())`；返回 `None` 时调用方回退东财（现有分支不变）
  - `_dt_peek_max_age() = max(_cache_ttl(), _DT_SNAPSHOT_PEEK_MIN_AGE=600)`（窗口内 10 分钟、窗口外 12 小时）
  - `_filter_zt_pool()` → `peek_stock_list(max_age=_NAME_SNAPSHOT_MAX_AGE=7*24*3600, require_valid=False)`；无快照时保持"返回原列表"的既有降级
  - 更新两处**已过时**的注释（现写"load_stock_list 有 24 小时缓存"，P0-1 后已不成立）
  - _Requirement: AC-3.1 / AC-3.2 / AC-3.3 / AC-4.1_

- [x] 6. 清理死代码 `sentiment._zt_codes()`
  - 全仓 `assert 无引用` 后再删（连同其可能带出的死导入）
  - 不做其它"顺手优化"
  - _Requirement: design §6（非目标边界）_

## 阶段 4 — 测试

- [x] 7. 新增 `tests/test_em_api.py`（离线，假 `requests.Session.get` 计数）
  - TTL 内同 key 只 1 次请求；超 TTL 重新请求
  - 失败不写缓存（第 1 次抛异常、第 2 次成功 ⇒ 计 2 次）
  - **当日空池不缓存**（连续两次都真实请求）；**非当日空池缓存**（仅 1 次）
  - 跨日期 key 不命中
  - 限流间隔：假 `time.time` / `time.sleep`，断言相邻两次请求间隔 ≥ `EM_MIN_INTERVAL`
  - `clear_cache()` 后重新请求；`cache_info()` 条目数正确
  - 并发 single-flight：多线程同 key ⇒ 真实请求数 == 1
  - （可选子项若做了）失败退避与恢复
  - _Requirement: AC-1.1 / AC-2.1 / AC-2.2 / AC-2.3 / AC-5.1 / design §5.1_

- [x] 8. 新增 `tests/test_sentiment_cache.py`（离线）
  - `get_sentiment()` 期间东财请求序列**无重复三元组**（AC-1.2）
  - **红线**：当日空池不缓存 ⇒ 第二次调用仍会重新探测（AC-4.1）
  - `_dt_count` **不触发全市场拉取**（打桩 `load_stock_list` 为"一调用即 AssertionError"）
  - `_dt_count` 无快照时回退东财（断言等于东财池长度）
  - `_filter_zt_pool` 无快照时降级为"不过滤"
  - `_filter_zt_pool` 在"盘前 63% 空值但行齐全"的快照下**仍能完成 ST 过滤**
  - 跨交易日失效（时间打桩）
  - _Requirement: AC-1.2 / AC-3.x / AC-4.1 / AC-4.3 · design §5.2_

- [x] 9. `tests/test_screener_snapshot.py` 追加 peek 用例 + `conftest.py` 追加夹具
  - peek：新鲜可用 / 超期不可用且**不触发网络** / `max_age` 放宽后可用 /
    `require_valid=False` 时盘前废快照可读 / 条数不足返回 `(None, None)`
  - `conftest.py` 新增 autouse 夹具重置 `em_api._CACHE` / `_last` / `_INTERVAL`
  - **既有 414 例一例不动**（已确认无任何用例打桩 `_em_*`）
  - _Requirement: design §5.3 / §5.4_

## 阶段 5 — 自检、核验与收尾

- [x] 10. 两项「改坏即变红」自检（回滚后核对 `sha1sum` 与基线一致）
  - A：`EM_MIN_INTERVAL` 0.35 → 0 ⇒ 限流间隔用例变红
  - B：`_dt_list_sina()` 换回 `load_stock_list` ⇒ "不触发拉取"用例变红
  - 用 **sha1 往返验证**（记基线 → 突变 → 跑 → 还原 → 比哈希），并在提交前后各核一次
    —— 本机疑似有外部进程会自动回滚 `core/screener.py`
  - _Requirement: AC-6.2_

- [x] 11. 全量回归 + 真机核验
  - `pytest` 全绿（当前 414 + 新增），**离线可跑**
  - 真机：请求序列对比（改造前后各打一次桩记录 `(endpoint,date,sort)` 序列）+ 分段耗时对比
  - **如实记录限制**：2026-10-06 为国庆假期非交易日 ⇒ 只能覆盖"非交易日"路径，
    「盘中 5.2s → 1.4s」无法真机复现，以离线用例 + 请求序列 + 非交易日耗时三条证据替代
  - 观察服务日志确认无 403 / 空响应率异常
  - _Requirement: AC-6.1 / AC-6.3 / AC-5.2_

- [x] 12. （可选，建议做）新增 `scripts/verify_sentiment.py`
  - 联网打印一次 `get_sentiment()` 的真实请求序列与分段耗时，作为可复跑的交付证据
  - 顺带补上 ROADMAP 第 6 项挂账的同名脚本（原计划是 `verify_emotion.py`）
  - _Requirement: AC-6.3 · design §4_

- [x] 13. 文档与提交
  - `README.md`：「数据来源与时效」表补东财池 30s 进程内缓存与限流说明
  - `ROADMAP.md`：新增第 10 项并归档
  - `specs/optimization-audit-20260930/findings.md`：P1-2 标为已处置、更新下一步
  - `.workbuddy/memory/`：当日日志 + `MEMORY.md`（含"东财限流是全局单点常量、回滚方式"这条长期事实）
  - 按规范拆分提交（`perf(core)` / `refactor(core)` / `test` / `docs`），推送用自适应脚本
  - _Requirement: 协作规范（每个 phase 产出先给老陆看）_

---

## 依赖顺序

```
1 → 2（可选，依赖 1）→ 3（依赖 1）
4（独立）
3, 4 → 5 → 6
1, 3, 4, 5 → 7, 8, 9
7, 8, 9 → 10 → 11 → 12 → 13
```

## 待老陆确认的两点（写在最前，避免执行后才发现）

1. **是否纳入统一限流**（design §1.1）：会改动 `core/market.py`，超出 requirements §5 的字面范围，
   但能让 `/api/overview` 从 11.36s 降到 ≈4s，且"防封"承诺第一次真正成立。**建议纳入**。
2. **是否接受 AC-3.2 的细化**（design §2.3）：跌停数优先用 10 分钟内的只读快照（口径与分布图一致），
   而不是快照一超 120 秒就切东财口径。**建议按细化执行**，否则会出现同屏两数不一致。
