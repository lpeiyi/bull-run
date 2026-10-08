# 情绪分重复计算与耗时治理 — 设计（cut-sentiment-latency）

> Phase 2。上游为同目录 `requirements.md`（Phase 1，含实测数据与 4 项取舍的拍板结论）。
> 参数取值：请求去重=做 / 数据层 TTL=**30s** / 东财限流=**0.35s** / `_dt_count`=**改**。

## 0. 结论摘要

三层改动，自下而上：

| 层 | 改什么 | 收益 |
|---|---|---|
| **L1 东财访问层**（新增 `core/em_api.py`） | 限流收敛为**单一全局间隔** + 池结果 30s 进程内缓存 | 消掉 1 次重复请求（≈1.25s）；限流等待从 ≈4.0s 降到 ≈0.9s；**同时惠及 `market.py`** |
| **L2 情绪分取值层**（`core/sentiment.py`） | `_dt_list_sina()` / `_filter_zt_pool()` 改用**只读** `peek_stock_list()` | 情绪分不再被一次 4 秒的全市场拉取阻塞（消掉实测的 3.26s 冷热差） |
| **L3 数据层**（`core/screener.py`） | 新增 `peek_stock_list()`（只读、**绝不联网**） | 为 L2 提供"不阻塞"的读数入口；对既有行为零影响 |

**预期**（交易日热路径）：`get_sentiment()` 5.21s → **≈1.4s**；冷路径 8.47s → ≈1.5s（冷热差基本消失）。
长假后的首个交易日需回溯多个非交易日，上界约 2.5s。

---

## 1. L1 新增 `core/em_api.py`

### 1.1 为什么必须统一限流（**超出 requirements §5 字面范围，请确认**）

改前事实：`core/sentiment.py` 与 `core/market.py` 各有一份**逐字相同**的 `_em_get`，
**各自持有独立的 `_em_last`**。也就是说"1 秒/次"的限流从来不是全局的 ——
两个模块交替请求时，对东财的实际速率是设计值的 2 倍。

`/api/overview` 冷路径两边都用：`market.get_zt_pool` + `get_zb_pool` + `get_dt_pool`（3 次）
+ `get_sentiment()`（4 次）= **7 次东财请求**，按各自 1.2s 计 ≈ 8.4s —— 这是实测 11.36s 的主体。

**把限流收敛成单一全局间隔，既让"防封"这条约束第一次真正成立，又让 `market.py` 一并提速。**
本条超出 requirements §5（那里是按模块写的），但服务于同一条意图：**不重复为同一件事付费**。

- **若纳入**：`/api/overview` 冷路径预计 11.36s → ≈4s
- **若不纳入**：`/api/overview` 只能改善约一半，且两份限流器继续并存（防封承诺依旧不成立）

### 1.2 模块结构

```python
# core/em_api.py
"""东财 push2ex 接口统一访问层：全局限流 + 池结果进程内缓存。"""

EM_MIN_INTERVAL = 0.35        # 全局最小请求间隔（秒）—— 单点可调，回滚就改这一行
EM_JITTER = (0.05, 0.15)      # 间隔抖动区间
POOL_TTL = 30                 # 池结果缓存有效期（秒）
ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"

EM_BACKOFF_STREAK = 3         # 连续失败达此数 → 间隔临时翻倍（可选子项）
EM_BACKOFF_MAX = 2.0          # 退避上限（秒）
EM_RECOVER_STREAK = 10        # 连续成功达此数 → 恢复基准间隔

_SESSION = requests.Session()
_last = [0.0]                 # 上一次真实请求完成时刻（全局唯一一份）
_INTERVAL = [EM_MIN_INTERVAL] # 当前有效间隔（可被退避调高）
_LOCK = threading.Lock()
_CACHE = {}                   # {(endpoint, date, sort): (ts, pool)}

def get(url, params, timeout=10): ...           # 全局限流 + 真实请求
def pool(endpoint, date, sort="fbt:asc"): ...   # 限流 + 30s 缓存（对外主入口）
def clear_cache(): ...                          # 清缓存（测试 / 排障）
def cache_info(): ...                           # 返回缓存条目数与当前有效间隔（测试断言用）
```

### 1.3 关键决策

**（a）限流：锁内 sleep，全局单时间戳。**
`time.sleep` 必须在**释放锁之前**完成，否则多线程会同时睡、同时发，限流形同虚设。

```python
with _LOCK:
    wait = _INTERVAL[0] - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(*EM_JITTER))
    try:
        return _SESSION.get(url, params=params, timeout=timeout)
    finally:
        _last[0] = time.time()
```

锁内 sleep 会让东财请求严格串行 —— **这正是"限流"的定义**，也是既有行为（改前也是串行）。

**（b）缓存：命中判断放在锁内（double-check）。**
否则并发同 key 会各自发一次请求。锁内先查缓存，未命中才发请求并写缓存 ⇒ 同 key 并发只需 1 次（single-flight）。

**（c）失败不写缓存。**
`get()` 抛异常 ⇒ `pool()` 返回 `[]` 且**不写缓存**（AC-2.3）。
为区分"请求失败"与"成功但池为空"，缓存写入只发生在请求成功分支。

**（d）当日空池不写缓存** —— 见 §3（红线 AC-4.1 的实现）。

**（e）保留旧函数名做薄包装。**
```
sentiment._em_pool(endpoint, date, sort="fbt:asc")  →  em_api.pool(...)
market._em_pool(endpoint, date)                     →  em_api.pool(..., sort="fbt:asc")
```
好处：`core/emotion_history.py:32-33` 的 `sentiment._em_pool(...)` 调用点不用动；
模块内阅读路径、既有注释的含义都不变。

**（f）可选子项：失败自适应降速。**
连续 3 次请求失败 ⇒ 间隔翻倍（上限 2.0s）；连续 10 次成功 ⇒ 恢复基准。
把"防封"从静态常量变成带反馈的闭环。约 15 行，**建议做**（若嫌复杂可跳过，不影响其余验收）。

### 1.4 限流参数对比

| 项 | 改前 | 改后 |
|---|---|---|
| 基准间隔 | 1.0s | **0.35s** |
| 抖动 | 0.10 ~ 0.30s | 0.05 ~ 0.15s |
| 实测相邻请求实际间隔 | 1.26 ~ 1.41s | **≈ 0.40 ~ 0.50s** |
| 作用域 | 每模块一份（非全局） | **全局唯一** |
| 失败反馈 | 无 | 连续失败临时退避（可选） |

**风险与回滚**：这是**唯一有外部风险**的改动（可能触发东财限流/封禁）。
回滚成本 = 改 `EM_MIN_INTERVAL` 一个常量回 1.0，其余改动不受影响。
**建议上线后观察 1~2 个交易日**；若 403 或空响应率上升，立即回退。

---

## 2. L2 情绪分路径不再被全市场快照阻塞

### 2.1 调用点

| 位置 | 用途 | 现状 | 改后 |
|---|---|---|---|
| `_dt_list_sina()` | 跌停家数 | `load_stock_list()`：TTL（120s）过期即**拉 4 秒** | `peek_stock_list(max_age=_dt_peek_max_age())` |
| `_filter_zt_pool()` | ST/新股过滤（需 code→name） | 同上 | `peek_stock_list(max_age=_NAME_SNAPSHOT_MAX_AGE, require_valid=False)` |

两处顺序相邻，改前实际只阻塞一次（第二处命中刚写入的缓存），但**一次就是 4 秒**。

### 2.2 L3 只读入口

```python
def peek_stock_list(max_age=None, require_valid=True):
    """只读已落盘的全市场快照。**绝不发起网络请求。**

    max_age=None        → 用正式时效判据（行情窗口内 _TTL_TRADING / 窗口外 _TTL_IDLE）
    max_age=<秒>        → 放宽为该年龄内即算可用
    require_valid=False → 不要求 price>0 占比达标（取名称等慢变字段时用）
    返回 (stocks, ts)；不可用返回 (None, None)
    """
```
判据链：文件存在且可解析 → 条数 ≥ `_MIN_STOCK_COUNT` → `now - ts <= max_age` →（`require_valid` 时）过有效性闸门。

### 2.3 可接受陈旧度（**对 AC-3.2 的刻意细化，请确认**）

| 用途 | 时段 | 取值 | 理由 |
|---|---|---|---|
| 跌停家数 | 行情窗口内 | **10 分钟**（`_DT_SNAPSHOT_PEEK_MIN_AGE`） | 跌停数日内变化慢；**保住与涨跌统计图同一口径**（新浪全市场按档判定，AC-3.3） |
| 跌停家数 | 窗口外 | `_TTL_IDLE`（12h） | 窗口外本来就是收盘快照 |
| code→名称 | 任意 | **7 天**（`_NAME_SNAPSHOT_MAX_AGE`）+ `require_valid=False` | 名称慢变；盘前那份 63% 空值的快照**行是全的**，取名称完全够用 |

实现：
```python
def _dt_peek_max_age():
    from core.screener import _cache_ttl
    return max(_cache_ttl(), _DT_SNAPSHOT_PEEK_MIN_AGE)
```

**为什么要细化 AC-3.2**：按字面"快照过期即回退东财"做，情绪卡的跌停数会在快照超过 120 秒后
**一直走东财口径**，与同屏的涨跌统计图数字对不上 —— 那正是刚用一整个 spec 消除掉的
"同屏两数矛盾"（P0-2）。放宽到 10 分钟，既满足"不阻塞"的意图，又把口径不一致概率压到最低。

（交易时段前端每 60 秒调一次 `loadDistribution()`，它会顺带把快照刷进 120 秒内 ⇒ 实际几乎总能命中。）

### 2.4 降级行为（如实声明）

- 无可用快照（冷启动 / 长假后）⇒ 跌停数走 `getTopicDTPool`；ST 过滤被跳过。
- 两者都是**既有代码里已存在的降级分支**（`_dt_count` 的东财回退、`_filter_zt_pool` 的 `except → 返回原列表`），
  本轮**没有新增降级形态**，只是"进入降级"的条件从"拉取异常"放宽到"没有现成快照"。

---

## 3. 红线：`trade_date` 不得滞后（AC-4.1）

缓存键是 `(endpoint, date, sort)`，**date 参与键** ⇒ 跨交易日必然失效（AC-4.3 零代码）。

但还有一条更细的路径要堵：`_find_recent_trade_date()` 判断"今天是不是交易日"靠的是
**当日涨停池非空**，而"当日尚无涨停"是一个**会变的中间态**。若把它当"确定为空"缓存 30 秒：

> 09:25 探测 → 当日空 ⇒ 回退昨日 ⇒ `trade_date = 昨日`
> 09:25:20 首只涨停出现
> 09:25:25 再次调用 → 命中"当日空"缓存 ⇒ **仍返回昨日**

这就是"缓存让 `trade_date` 滞后"。**做法：`date == today` 的空池结果一律不写缓存。**
其它日期的空池（非交易日 / 历史无数据）是稳定事实，照常缓存。

代价：交易日开盘初期可能每次多 1 次请求（≈0.45s），窗口极短（首只涨停出现即结束）。

对应地，AC-1.1「同一三元组最多 1 次请求」的准确表述是：
**除"当日空池"外**，同一 `(endpoint, date, sort)` 在 TTL 内最多 1 次真实请求。

---

## 4. 可观测性

- 缓存命中记 `debug` 日志（含 key）。
- `/api/sentiment` 响应**不加任何字段**（AC-5.2）。若日后要暴露缓存指标，走独立诊断端点。
- 可选（**建议做**）：`scripts/verify_sentiment.py` —— 真机打印请求序列与分段耗时，
  作为交付证据；顺带补上 ROADMAP 第 6 项挂账的那个脚本。

---

## 5. 测试策略

**现有 414 例应当一例都不动。** 已确认：没有任何用例打桩 `_em_get` / `_em_pool` / `_em_last`，
`test_sentiment.py` 只测纯函数（`_calc_score` / `is_limit_stock` / `limit_threshold`），
路由契约测试用 `patch_sentiment` 打桩 `get_sentiment`。网络层此前是零覆盖。

### 5.1 新增 `tests/test_em_api.py`（离线）

1. TTL 内同 key 只请求 1 次（假 `requests.Session.get` 计数）
2. 超 TTL 后重新请求
3. **失败不写缓存**：第 1 次抛异常、第 2 次成功 ⇒ 计 2 次
4. **当日空池不缓存**（连续两次都真实请求）；**非当日空池缓存**（只 1 次）
5. 跨日期 key 不命中（AC-2.2）
6. **全局限流间隔**：假 `time.time` / `time.sleep`，断言相邻两次请求时间差 ≥ `EM_MIN_INTERVAL`
7. `clear_cache()` 后重新请求；`cache_info()` 反映条目数
8. **并发 single-flight**：多线程同 key ⇒ 真实请求数 == 1

### 5.2 新增 `tests/test_sentiment_cache.py`（离线）

1. `get_sentiment()` 期间东财请求序列**无重复三元组**（AC-1.2）
2. **红线**：当日空池不缓存 ⇒ 第二次调用仍会重新探测（AC-4.1）
3. `_dt_count` **不触发全市场拉取**：打桩 `screener.load_stock_list` 为"一调用即 AssertionError"
4. `_dt_count` 无快照时回退东财（断言等于东财池长度）
5. `_filter_zt_pool` 用只读快照；无快照时降级为"不过滤"（返回原列表）
6. `_filter_zt_pool` 在"盘前 63% 空值但行齐全"的快照下**仍能完成 ST 过滤**（`require_valid=False` 的意义）
7. 跨交易日失效：把 `date` 换成前一日 ⇒ 缓存不命中（时间打桩）

### 5.3 `tests/test_screener_snapshot.py` 追加（peek）

1. 缓存新鲜 ⇒ 返回 `(stocks, ts)`
2. 缓存超期 ⇒ `(None, None)`，**且不触发网络**（打桩 `_sina_get` 为 AssertionError）
3. `max_age` 放宽后可用
4. `require_valid=False` 时，盘前废快照（63% `price=0`）仍可读出（取名称用）
5. 条数 < `_MIN_STOCK_COUNT` ⇒ `(None, None)`

### 5.4 夹具

`tests/conftest.py` 追加 autouse 夹具重置 `em_api._CACHE` / `_last` / `_INTERVAL`，
避免用例间串味（与既有 `_reset_screener_state` 同理）。

### 5.5 「改坏即变红」自检（2 项）

| # | 改坏什么 | 预期变红 |
|---|---|---|
| A | `EM_MIN_INTERVAL` 0.35 → 0 | 限流间隔用例（§5.1-6） |
| B | `_dt_list_sina()` 的 `peek_stock_list` 换回 `load_stock_list` | "不触发拉取"用例（§5.2-3） |

两项均须**回滚后核对 `sha1sum` 与基线一致**（沿用第 9 项确立的"sha1 往返验证"手法，
因为本机疑似有外部进程会自动回滚 `core/screener.py`）。

---

## 6. 非目标

- 不缓存**合成后**的情绪结果；不改 `_calc_score` 权重、等级阈值、各字段取值来源
- 不改前端（**本轮零前端改动**）；不改任何接口的响应字段
- 不改 `/api/overview` 的 60 秒缓存策略（sentiment 继续实时）
- 不处理 `core/legu.py` 的整日缓存（独立问题，requirements §6 已记录）
- `sentiment._zt_codes()` 已无任何调用方（死代码）⇒ 本轮**仅清理它**（删除 + 断言无引用），
  不做其它"顺手优化"

---

## 7. 已知限制与风险

1. **东财限流下调是唯一的外部风险**（可能触发封禁）。回滚 = 改 1 个常量。
   上线后建议观察 1~2 个交易日；出现 403 / 空响应率上升立即回退到 1.0。
2. **今天是 2026-10-06（国庆假期，非交易日）** ⇒ 真机验证只能覆盖"非交易日"路径
   （`_find_recent_trade_date` 需回溯到 09-30，`_dt_count` 走东财分支）。
   **"盘中 5.2s → 1.4s"这个核心指标无法在本次交付时真机复现**，只能给
   「非交易日耗时对比 + 真实请求序列对比 + 离线用例」三条证据。**必须写进交付报告**，
   与第 9 项"盘前场景无法真机复现"的处置方式一致。
3. 锁内 sleep 使东财请求严格串行；若某次请求卡到 10 秒超时，会阻塞后续请求。
   **可接受**（改前同样串行），且超时后 `_last` 会更新，不影响后续节奏。
4. `POOL_TTL = 30s` 意味着池数据最多滞后 30 秒。对"涨停/炸板/跌停家数"无实质影响；
   **不适用于任何需要秒级一致性的场景**。
5. 情绪卡的跌停数在"连 10 分钟内的快照都没有"时改用东财口径，与涨跌统计图会短暂不同。
   该窗口仅出现在冷启动与长假后，且前端 60 秒轮询会很快把它刷回一致。

---

## 8. 执行顺序（对应 tasks.md）

1. L1 东财访问层（新增 `core/em_api.py` + 两处薄包装）
2. L3 只读入口（`screener.peek_stock_list`）
3. L2 情绪分取值层（两处调用点）
4. 测试（新增 2 个文件 + 追加 1 个文件 + 夹具）
5. 自检 + 真机核验 + 文档提交
