# 设计：全市场行情快照的时效与有效性治理

> 对应 `requirements.md`。核心判断：**24 小时缓存的性能前提已不存在**（实测串行 13s → 并发 6 线程 4.12s），
> 因此不需要"拆缓存文件"这类结构性改造，只需「并发化 + TTL 分层 + 有效性闸门」。

## 1. 整体思路

一句话：**把"行情快照"当成快消品来管，而不是把它和"标的名单"一起腌 24 小时。**

```
                      ┌─ 缓存新鲜？ ──是──→ 直用
请求 load_stock_list ─┤
                      └─ 否 ─→ 加锁（防惊群）
                                 └─ 并发拉取（4s）
                                      ├─ 不完整（有失败页/条数不足）→ 回退可用旧缓存 / 返回空
                                      └─ 完整 → 有效？（price>0 占比 ≥ 90%）
                                                 ├─ 有效 → 写缓存(v3) → 返回
                                                 └─ 无效 → 不写缓存 → 回退可用旧缓存 / 返回空
```

两条独立闸门，各管一件事：

| 闸门 | 管什么 | 判据 |
|---|---|---|
| **新鲜度**（TTL 分层） | 数据是不是"当前这一刻的" | 行情窗口内 120s，窗口外 12h |
| **有效性**（price 占比） | 这份快照是不是"真的行情" | `price > 0` 占比 ≥ 90% |

两者不得合并：盘前 09:00 的快照在写入那一刻是"新鲜的"，但它是**无效**的；收盘后的快照在 12 小时后仍新鲜**且**有效。

## 2. 模块边界

| 层 | 文件 | 职责 |
|---|---|---|
| 数据/缓存 | `core/screener.py` | 并发拉取、有效性判定、TTL 分层、single-flight、缓存读写 |
| 装配 | `app.py` | 解析 `force` 参数、把 `meta` 状态透传给前端 |
| 前端 | `static/app.js`、`templates/index.html` | 刷新入口、状态标注、口径标注 |

**新增逻辑全部落在 `core/screener.py`**，且以纯函数为主（`_in_quote_window`、`_cache_ttl`、`snapshot_is_valid`），
保证可脱网单测。`app.py` 只做透传，不下沉统计逻辑（沿用 ROADMAP 第 6 项的职责边界）。

## 3. 详细设计

### 3.1 新增模块级常量

```python
_LIST_VERSION       = 3        # 由 2 递增：标识「含有效性判定」语义
_TTL_TRADING        = 120      # 行情窗口内缓存有效期（秒）
_TTL_IDLE           = 12 * 3600  # 行情窗口外缓存有效期（秒）
_VALID_PRICE_RATIO  = 0.90     # 有效快照判据：price > 0 占比下限
_MIN_VALID_SAMPLE   = 100      # 样本不足此数时跳过有效性判定
_FETCH_WORKERS      = 6        # 并发分页线程数
_MAX_PAGE           = 60       # 页数上限（60 × 100 = 6000 只，覆盖当前 5571）
_MIN_RETRY_INTERVAL = 60       # 拉取失败/判定无效后的最小重试间隔（秒）
```

数值取值依据（均来自 2026-09-30 实测，见 `requirements.md` §1.6）：

- `_FETCH_WORKERS = 6`：并发 4/6/8 线程实测 6.08s / 4.12s / 2.17s，均 5571 条、失败页 0。取 6 是"够快且留余量"。
- `_VALID_PRICE_RATIO = 0.90`：盘前实测 36.5%、盘中 99.9%，90% 两侧余量都很大。
- `_MAX_PAGE = 60`：现状 56 页。若某次拉取的第 60 页仍满 100 条，记 warning（提示上限需上调）。
- `_MIN_VALID_SAMPLE = 100`：对**非全市场样本**（测试桩、残缺缓存）不做统计判定 —— 见 §5.3。

### 3.2 快照有效性判定（纯函数）

```python
def snapshot_valid_ratio(stocks) -> float:
    """price > 0 的标的占比。空列表返回 0.0。"""

def snapshot_is_valid(stocks) -> bool:
    """快照是否有效。样本少于 _MIN_VALID_SAMPLE 时返回 True（跳过判定）。"""
    if len(stocks) < _MIN_VALID_SAMPLE:
        return True
    return snapshot_valid_ratio(stocks) >= _VALID_PRICE_RATIO
```

**为什么判据用 `price > 0`**：盘前新浪会把绝大多数标的的 `trade` 重置为 0（实测 63.5%），
而 `change_pct` 仍残留着上一交易日的值（23.4% 非零）——**只看 `change_pct` 会把废快照误判为有效**，
必须看 `price`。

### 3.3 行情窗口与 TTL 分层

```python
def _in_quote_window(now=None) -> bool:
    """是否处于行情有效窗口：交易日 09:15~11:30、13:00~15:00（不含午休）。"""

def _cache_ttl(now=None) -> float:
    return _TTL_TRADING if _in_quote_window(now) else _TTL_IDLE
```

时段划分的理由：

| 时段 | 窗口 | TTL | 理由 |
|---|---|---|---|
| 09:15~11:30、13:00~15:00 | 是 | 120s | 集合竞价起快照开始变化 |
| 11:30~13:00（午休） | 否 | 12h | 市场停顿，无需重拉；13:00 后 `now - ts > 120s` 自然失效 |
| 15:00~次日 09:15 | 否 | 12h | 收盘价快照全天复用，且是盘前唯一有效数据 |
| 周末 / 节假日 | 否 | 12h | 同上 |

**AC-2.3（跨时段失效）的满足方式**：不需要专门的"跨时段"代码。昨晚 20:00 写入的缓存 `ts`，
到次日 10:00 时 `now - ts = 14h > 120s`，在窗口内自然判定为过期。**用 TTL 覆盖时段边界，而不是引入时段对比逻辑**。

**已知取舍**：不引入节假日日历，因此周中的法定假日会被当作行情窗口，每 120 秒做一次无谓拉取（拉到的是昨日收盘快照，有效但不变化）。代价是当天约 120 次多余请求；换来的是不维护一份会过期的日历。若日后需要，可在 `_in_quote_window` 内挂一张可选的休市表。

### 3.4 并发分页拉取

改造 `_fetch_sina_stock_list()`，**签名与返回保持不变**（`(stocks, ok)`），只把"串行 for 循环"换成"分批并发"：

```python
def _fetch_sina_stock_list():
    all_data, failed_pages = [], []
    for start in range(1, _MAX_PAGE + 1, _FETCH_WORKERS):
        pages = list(range(start, min(start + _FETCH_WORKERS, _MAX_PAGE + 1)))
        results = _fetch_pages_concurrent(pages)   # [(page, diff, err), ...]

        batch_failed = 0
        reached_end = False
        for page, diff, err in results:
            if err is not None:
                failed_pages.append(page); batch_failed += 1; continue
            all_data.extend(diff)
            if len(diff) < _PAGE_SIZE:      # 尾页
                reached_end = True

        if batch_failed == len(pages):      # 整批全失败
            consecutive_fail += len(pages)
            if consecutive_fail >= _MAX_CONSECUTIVE_FAIL:
                break
        else:
            consecutive_fail = 0

        if reached_end:
            break

    out = _normalize_stock_rows(all_data)
    ok = (not failed_pages) and (len(out) >= _MIN_STOCK_COUNT)
    return out, ok
```

`_fetch_pages_concurrent` 内部对**每一页**保留既有容错：重试至多 `_PAGE_MAX_RETRY` 次、退避 `1.5s/3.0s`。

**三个既有语义必须原样保留**（它们是 `specs/fix-stocklist-and-cache-health/` 的验收内容）：

1. **单页失败重试后成功**（AC-1.1）
2. **单页重试耗尽 → 记失败页、不中断、继续后续页**（AC-1.2）
3. **连续失败达 `_MAX_CONSECUTIVE_FAIL` → 提前结束，不空转拉满上限**（避免断网时空转）

**顺序无关**：`_normalize_stock_rows` 的输出顺序不再等于 `sort=symbol` 顺序。核查过全部消费方
（`build_distribution` 只做计数、`sentiment._dt_list_sina` 只做过滤、`_filter_zt_pool` 只建 dict、`run_screen` 逐只遍历），
**没有任何一处依赖清单顺序**。拉取后按 `code` 排序一次，让产物保持确定性（便于测试与 diff）。

### 3.5 缓存读取决策与 single-flight

```python
_FETCH_LOCK = threading.Lock()
_LAST_ATTEMPT = {"ts": 0.0, "usable": False}   # 最近一次拉取尝试的结果

def load_stock_list_meta(force=False):
    now = time.time()
    cached = _read_stock_list_cache()

    # ① 快路径：新鲜且（完整 + 有效）→ 直用
    if not force and _directly_usable(cached, now):
        return cached[0], _ok_meta(cached, now)

    # ② 慢路径：加锁，防惊群
    with _FETCH_LOCK:
        cached = _read_stock_list_cache()          # 双检：等锁期间可能已被别人刷新
        if not force and _directly_usable(cached, now):
            return cached[0], _ok_meta(cached, now)

        # ③ 抑制短时间内的重复无效尝试（AC-4.3）
        if not force and now - _LAST_ATTEMPT["ts"] < _MIN_RETRY_INTERVAL \
                and not _LAST_ATTEMPT["usable"]:
            return _fallback_or_empty(cached, now)

        stocks, ok = _fetch_sina_stock_list()
        valid = ok and snapshot_is_valid(stocks)
        _LAST_ATTEMPT.update(ts=time.time(), usable=valid)

        if valid:
            _write_stock_list_cache(stocks, now)
            return stocks, _ok_meta(...)

        return _fallback_or_empty(cached, now, reason=...)
```

要点：

- **single-flight（AC-4.1）**：`_FETCH_LOCK` 保证同一时刻只有一次真实拉取；等锁的线程在**双检**后直接复用结果，不会各自再拉一次。
- **最小重试间隔（AC-4.3）**：盘前连续无效时，60 秒内不再重试，避免空转。
- **`force=1` 穿透一切**：跳过新鲜度判断、跳过双检、跳过重试间隔抑制（AC-2.4）。

`_directly_usable(cached, now)` 的判定：

```python
def _directly_usable(cached, now):
    if cached is None:
        return False
    stocks, meta = cached
    if meta.get("complete") is not True:       # 沿用既有语义：不完整不直用
        return False
    if not _has_known_version(meta):           # 无 version 的 v1 → 沿用既有行为（重拉）
        return False
    if now - meta.get("ts", 0) >= _cache_ttl(now):
        return False
    return _meta_valid_or_unknown(stocks, meta)   # 见 §3.6
```

### 3.6 有效性标记与 v2 旧缓存的兼容

缓存写入时增加 `valid` 字段：

```json
{"ts": 1759190431.2, "version": 3, "complete": true, "valid": true, "stocks": [...]}
```

读取时按三态处理 `valid`：

| 缓存状态 | `valid` | 直用 / 回退 | 理由 |
|---|---|---|---|
| v3 有效快照 | `true` | 允许 | 写入时已通过闸门 |
| v3（理论上不会出现无效写入） | `false` | 拒绝 | 防御性分支 |
| **v2 旧缓存** | 字段缺失 | **当场判定**（见下） | 兼容既有文件 |

```python
def _meta_valid_or_unknown(stocks, meta):
    """v3 缓存看标记；v2 无标记则当场判定（样本不足时豁免）。"""
    v = meta.get("valid")
    if v is True:
        return True
    if v is False:
        return False
    return snapshot_is_valid(stocks)     # v1/v2：现场判定
```

**为什么 v2 要"当场判定"而不是"一律放行"**：升级后如果一律放行，那份 09:00 写的废缓存（`price=0` 占 63.5%）
在下一次回退时又会被当成可用数据返回 —— 问题原地复活。当场判定（O(n) 纯计算，零成本）能让它被识别为无效。

**`_MIN_VALID_SAMPLE` 豁免的意义**：`snapshot_is_valid` 在样本 < 100 时返回 `True`。
理由是非全市场样本（残缺缓存、测试桩）上算占比没有统计意义，不该用它否决一份可能正常的缓存。
这个豁免同时让 `tests/test_screener_stocklist.py` 里用 1 条桩数据构造的既有用例保持原有语义。

### 3.7 meta 与接口契约扩展

`load_stock_list_meta()` 的 `meta` **只增不改**（C-4）：

| 键 | 状态 | 含义 |
|---|---|---|
| `degraded` / `count` / `fetched_at` / `reason` | 保持 | 沿用既有语义 |
| `valid` | **新增** | 返回的这份数据是否通过有效性判定 |
| `stale` | **新增** | 数据是否**非当前时段**（来自旧快照） |

`stale` 的判定：`now - fetched_at >= _cache_ttl(now)`（即这份数据已经超出它本该有的寿命）。

`/api/market_distribution` 响应增加状态字段（**不改动 `build_distribution` 的统计字段**）：

```python
stocks, meta = screener.load_stock_list_meta(force=force)
body = market.build_distribution(stocks)
body["stale"]       = meta.get("stale", False)
body["degraded"]    = meta.get("degraded", False)
body["reason"]      = meta.get("reason", "")
body["snapshot_at"] = _fmt_ts(meta.get("fetched_at"))   # "2026-09-30 10:20:31"，无数据时为 ""
return jsonify(body)
```

`snapshot_at` 是给前端做"数据时点"标注用的（AC-5.3）。**这也是 `build_distribution` 保持在 `core/`
纯函数、装配留在路由的直接好处** —— 状态字段的注入不需要碰统计逻辑。

### 3.8 前端改动

**改动 1 · 刷新入口（AC-5.1）**

`#ov-refresh` 的点击处理由 `loadOverview(true)` 改为同时触发分布图强制刷新：

```js
$("#ov-refresh").addEventListener("click", () => {
  loadOverview(true);
  loadDistribution(true);      // 新增：让分布图也真正刷新
});
```

`loadDistribution(force)` 相应地拼接 `?force=1`。

**改动 2 · 自动刷新（AC-5.2）**

`doFastRefresh()` 已每 60 秒调用 `loadDistribution()`（`static/app.js:743`），**不需要新增定时器**。
后端 TTL 为 120s，会出现"每两次请求刷新一次数据"的节奏，属预期；这样既保证数据最多滞后 2 分钟，
又不把请求压到 60 秒一发。`doNonTradeFastRefresh` 不调分布图（非窗口内数据不变）。

**改动 3 · 状态标注（AC-5.3 / AC-5.5 / AC-5.4）**

`templates/index.html` 的涨跌统计卡片标题处增加状态元素：

```html
<h3>涨跌统计
  <span class="hint">全市场涨跌幅分布 · 实时快照</span>
  <span class="hint mono" id="dist-status"></span>
</h3>
```

`renderDistribution(d)` 末尾按优先级渲染 `#dist-status`：

| 条件 | 文案 |
|---|---|
| `d.degraded` 或 `d.total === 0` | `数据不可用（{reason}）` + 图表区显示空态，**不画柱** |
| `d.stale === true` | `基于 {snapshot_at} 数据` |
| 其他 | `数据时间 {snapshot_at}` |

空态复用既有样式类 `boards-empty`（`renderIndexCompare` 已在用），保持视觉一致。

**改动 4 · 口径标注（AC-6.x）**

- 分布图：标题旁标注 `全市场实时快照`（上表已含），并在 tooltip 中保持"只数（占比）"不变。
- 情绪卡片：在 `#se-dims` 那一行前增加固定说明 `口径：东财涨停池（收盘）`，与分布图形成区分。

两处**不追求数字一致**：分布图是"实时触板（`change_pct` 达分档阈值即计），含未封板的"，
情绪卡是"东财涨停池收录的收盘封板"。`requirements.md` §1.4 已说明它们是两个口径。

## 4. 被否决的方案（附实测依据）

| 方案 | 否决理由 |
|---|---|
| **拆成两个缓存文件**（名单长 TTL + 行情短 TTL） | 两者来自**同一次拉取**，拆开不省任何请求；收益不抵复杂度。并发化后整体 TTL 缩短已达成同一目标 |
| 东财 `clist` 批量通道 | `pz` 被硬限 100 条（实测 500/1000/3000/6000 一律返回 100），拿全市场仍需 60 页 |
| 腾讯 `real_quotes` 作实时通道 | 每批 60 只，全市场外推 **~69 秒**，不可用 |
| 新浪 `num` 放大 | 实测 200/500/1000/3000 一律返回 100 条 |
| TTL 直接降到 60s | 前端已按 60s 轮询，会变成"每 60s 一次全量拉取"（一天 240 次）；120s 让轮询与数据更新解耦，请求量减半 |
| 改用「按行裁剪 K 线缓存」式的分级失效 | 与本问题无关；`requirements.md` §2.2 已划出范围 |

## 5. 对既有测试的影响

### 5.1 必须同步调整的用例（2 个）

| 用例 | 为什么必须改 | 保留的语义 |
|---|---|---|
| `test_screener_stocklist.py::test_consecutive_failures_abort_early` | 断言了精确的调用页集合与次数（`{1,2,3}` / `9` 次）。分批并发后第一批会发 `_FETCH_WORKERS` 页 | 改为断言"**总请求数不超过第一批的量**，且**未拉满 `_MAX_PAGE`**"，即"断网时不空转" |
| `test_screener_stocklist.py::test_fresh_complete_cache_used_without_fetch` | 构造的是 v2 缓存。TTL 语义不变，断言仍成立；但应补一版 v3 缓存用例 | 原用例保留，另加 v3 用例 |

> 其余 367 个用例（含 `test_app_routes.py` 的 23 个路由契约）**不得修改**。
> `test_app_routes.py` 里桩掉 `screener.load_stock_list` 的方式不受影响。

### 5.2 新增用例（`tests/test_screener_snapshot.py`）

| 分组 | 用例要点 |
|---|---|
| 有效性判定（纯函数） | 占比 0% / 89.9% / 90% / 100% 的边界；空列表；样本 < 100 时豁免 |
| TTL 分层 | 窗口内 119s 新鲜、121s 过期；窗口外 11.9h 新鲜、12.1h 过期；午休算窗口外；周末算窗口外 |
| 无效快照不污染 | 拉取完整但 `price` 占比 < 90% → 不写缓存、原缓存字节不变 |
| 无效快照回退 | 有**可用**旧缓存 → 回退并标 `degraded` + `stale`；旧缓存也是 v2 废数据 → 当场判定无效 → 返回空 |
| **盘前场景回归**（本 spec 的核心用例） | 用 09:00 的真实形态桩（63.5% `price=0`、`change_pct` 残留非零）+ 系统时间打桩为 09:20 → 断言 **不返回废数据**；时间推进到 10:00 且桩返回真实行情 → 断言拿到有效数据 |
| single-flight | 多线程并发调用 + 过期缓存 → `_sina_get` 实际调用批次只有一份 |
| 最小重试间隔 | 60s 内连续两次无效拉取 → 第二次不再发请求 |
| 并发等价性 | 同一批原始数据下，并发实现与串行实现产出的集合完全一致 |
| 顺序确定性 | 三个市场的条目乱序输入 → 输出按 `code` 升序稳定 |

### 5.3 有效性自检（AC-7.4）

交付前临时改坏两处，确认对应用例真的变红，再回滚并核对 `sha1sum`：

1. 把 `_VALID_PRICE_RATIO` 从 `0.90` 改成 `0.0` → 「无效快照不污染」用例应变红。
2. 把 `_cache_ttl` 的返回值改为恒 `24 * 3600` → 「TTL 分层」用例应变红。

## 6. 风险与回退

| 风险 | 缓解 |
|---|---|
| 并发拉取触发新浪限流（456/501） | 并发度仅 6（实测余量足）；单页保留 3 次退避重试；`_FETCH_WORKERS` 是模块级常量，可单点降到 2~3 |
| 盘中每 120s 拉一次被对方视为爬虫 | TTL 是常量，可调到 300；且请求集中在 4 秒内（而非持续） |
| 首屏首次请求需等约 4 秒 | 在启动线程里**新增**清单预热（`requirements.md` §7.5），把 4 秒挪到页面打开之前 |
| 有效性阈值误判（阈值过高导致真实行情被判无效） | 盘中实测 99.9%，90% 阈值余量充足；且判无效时仍回退可用旧缓存并标注状态，不会白屏 |
| 并发导致清单顺序变化 | 拉取后按 `code` 排序，产物确定性可回归 |
| 出了问题时难以退回旧行为 | 全部开关都是模块级常量；`git revert` 单个提交即可回到串行 + 24h 缓存 |

## 7. 与需求的映射

| 需求 | 设计落点 |
|---|---|
| AC-1.1~1.5 有效性判定 | §3.2 `snapshot_is_valid`、§3.5 `_fallback_or_empty` |
| AC-2.1~2.5 时效 | §3.3 `_in_quote_window` / `_cache_ttl`、§3.5 `_directly_usable` |
| AC-3.1~3.5 并发化 | §3.4 分批并发、§3.1 `_FETCH_WORKERS` / `_MAX_PAGE` |
| AC-4.1~4.4 防惊群与降级 | §3.5 `_FETCH_LOCK` / `_LAST_ATTEMPT` |
| AC-5.1~5.5 前端 | §3.8 改动 1/2/3 |
| AC-6.1~6.3 口径标注 | §3.8 改动 4 |
| AC-7.1~7.4 回归与自检 | §5.1 / §5.2 / §5.3 |
| C-1~C-9 约束 | §2 模块边界、§3.1 常量、§4 否决方案 |
