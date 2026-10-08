# 情绪分重复计算与耗时治理（cut-sentiment-latency）

> 来源：`specs/optimization-audit-20260930/findings.md` 的 **P1-2**（情绪分是唯一瓶颈点）。
> 本轮为 Phase 1（requirements），产出后待确认再进 design / tasks。

## 1. 问题

`core/sentiment.get_sentiment()` **每次调用都要重新跑一遍完整的 4 次东财请求 + 1 次新浪全市场**，
且**一屏之内会被调用 3~4 次**。它是当前唯一的单点热点，把它修掉，`/api/overview`、
`/api/sentiment`、`/api/emotion_trend` 三个接口同时受益。

### 1.1 实测（2026-09-30 盘中 14:35~14:40，本机直调）

| 项 | 实测值 |
|---|---|
| `get_sentiment()` 首次（冷） | **8.47s** |
| `get_sentiment()` 紧接着再调（热） | **5.21s** |
| 内部东财请求次数 | **4 次** |
| 其中**参数完全相同**的重复请求 | **2 次**（`getTopicZTPool date=20260930 sort=fbt:asc`） |
| 东财单请求的**真实网络耗时** | **0.12~0.13s**（连接复用后） |
| 东财单请求经 `_em_get` 后的耗时 | **1.26~1.41s** |
| `_em_get` 限流等待合计 | 约 **4.0s / 5.21s ≈ 77%** |
| `legu.fetch_legu_history()` | 0.01s（命中整日缓存），末条 = `20260929` |

**结论一：耗时的大头不是网络，是 `time.sleep`。** 真实网络 0.12s，被 1 秒固定间隔的
串行限流抬到 1.3s。4 次调用 ≈ 4.0s 纯等待 + 0.5s 网络。

**结论二：5.21s 里有约 1.25s 是白付的。** 4 次请求中第 1、2 次参数完全相同：

```
getTopicZTPool  date=20260930  sort=fbt:asc   ← _find_recent_trade_date() 用它"探测交易日"
getTopicZTPool  date=20260930  sort=fbt:asc   ← get_sentiment() 主体为拿涨停池又拉了一次
```

`_find_recent_trade_date()` 只要"池子非空"这个信息，拿到之后就把它**丢掉**了。

**结论三（新发现，与 P0-1 相关）：冷热差 3.26s 来自全市场清单拉取。**
8.47s − 5.21s = 3.26s —— 正是 `_dt_count()` → `_dt_list_sina()` → `load_stock_list()`
在 120 秒 TTL 过期后触发的一次全市场拉取（P0-1 改造后约 3.3~4.1s）。
**P0-1 把它从"24 小时陈旧但 0.02s"变成了"120 秒新鲜但可能阻塞 4 秒"** ——
情绪分路径因此被一个它并不真正需要的重量级资源绑住。

### 1.2 一屏之内的调用方

| 调用方 | 位置 | 说明 |
|---|---|---|
| `/api/overview` | `app.py:108` | **每次实时**，`sentiment` 不走 60s 缓存 |
| `/api/sentiment` | `app.py:141` | 无缓存 |
| `/api/emotion_trend` | `core/emotion_history.py:286` | `latest` **强制实时**（v4 修复引入） |
| 前端 `loadSentiment()` | `static/app.js:1188,1219` | 先 `/api/emotion_trend`，再用 `/api/sentiment` 兜底 → 同一屏 2 次 |
| 前端 `loadSentimentQuick()` | `static/app.js:1243` | 日内定时 → `/api/sentiment` |
| 推送规则 | `core/rules.py:29` | 后台定时 |

首屏因此串行付出 3~4 × 5.2s，这是审计中「首屏 23.57s」的主要构成。

## 2. 必须先说清楚的一条红线（历史事故）

**本项目已经因为"缓存整个情绪结果"出过一次事故**，见 `.trae/specs/diagnose-sentiment-data-path-v4/`：

> `core/emotion_history.get_emotion_trend()` 当时用「整日缓存」（`generated == today` 即读缓存），
> 导致 `latest` 卡在**前一日**（涨停 83/跌停 0/炸板率 6.7%），与正确的 52/8/22.4% 完全不符，
> 而前端只读 `latest` → 页面显示错误数据一整天。

现行代码里留着一行明确的疤（`app.py:100-103`）：

```python
# 缓存策略：其它字段保留 60 秒缓存，但 sentiment（情绪分）必须**每次实时**计算，
# 避免缓存卡住旧值（如涨停83/跌停0）导致用户看到错误数据。
```

**因此本项的非目标之一就是：不得缓存"合成后的情绪结果"。** 这不是保守，是明确的事故教训。
本项要动的是**更下层**——"同一秒内对同一个 URL 发两遍"这件事本身。

红线验收（AC-4.1）：**进程内任何新增缓存都不得使返回的 `trade_date` 滞后于当前真实交易日。**

## 3. 范围

### 做

1. **消除重复请求** —— `_find_recent_trade_date()` 的探测结果供主体复用，不再拉第二次同一个池子。
2. **同参数请求去重（短 TTL 数据层缓存）** —— 在 `_em_pool(endpoint, date, sort)` 这一层
   做进程内缓存，使"一屏 3 次调用"只付 1 次真实请求。**key 含 `date`，跨交易日天然失效。**
3. **情绪分路径不再被全市场快照阻塞** —— `_dt_count()` 改为"有快照就用，没有就回退东财跌停池"，
   不主动触发一次 4 秒的全市场拉取。
4. **可选：东财限流策略调整** —— 4 秒纯等待是最大的一块，但涉及"是否会被东财封 IP"的风险判断。

### 不做（非目标）

- **不改情绪分算法与口径**：`_calc_score` 的权重、等级阈值、`zt/dt/zb/break_rate/promo/max_height`
  的取值来源一律不动。本轮只改"多久拿一次数据"，不改"拿到数据怎么算"。
- **不缓存合成结果**（见 §2）。
- **不改前端接口契约**：`/api/overview`、`/api/sentiment`、`/api/emotion_trend` 的响应字段不变。
- **不改 `/api/overview` 的 60 秒缓存策略**（其它字段继续 60s，sentiment 继续实时）。
- **不处理乐咕的整日缓存**：`legu.fetch_legu_history()` 的 `generated == today` 也是同类隐患
  （盘中 + 盘后同一进程内 `legu_ok` 恒为 False，永远走东财+新浪回退路径），
  但它是**独立问题**，本轮只记录，见 §6。

## 4. EARS 验收标准

### AC-1 请求去重（无重复同参请求）

- **AC-1.1** When `get_sentiment()` 执行完毕, the sentiment 模块 shall 对同一
  `(endpoint, date, sort)` 三元组最多发起 **1 次**真实请求。
- **AC-1.2** While `_find_recent_trade_date()` 已探测到可用交易日, when `get_sentiment()`
  需要该日的 `getTopicZTPool`, the sentiment 模块 shall 复用探测阶段的请求结果，
  不再发起第二次同参数请求。
- **AC-1.3** `_find_recent_trade_date()` 对**返回值的语义**保持不变：仍返回
  `YYYYMMDD` 字符串或 `None`；仍按"从今天往前最多 8 天、跳过周末、池子非空即命中"的规则。
- **AC-1.4** If 交易日探测失败（8 天全空）, then `get_sentiment()` shall 保持现有行为 ——
  返回 `{"score": None, "error": "未探测到最近交易日", "trade_date": None}`。

### AC-2 数据层短 TTL 缓存（待确认，见 §5 第 2 项）

- **AC-2.1** While 距上一次成功请求同一 `(endpoint, date, sort)` 未超过 TTL,
  when 再次请求, the sentiment 模块 shall 直接使用缓存，不发起网络请求。
- **AC-2.2** While `date` 与缓存 key 中的 `date` 不同, the sentiment 模块 shall
  视为缓存未命中并发起真实请求（跨交易日天然失效，无需额外代码）。
- **AC-2.3** If 请求失败, then the sentiment 模块 shall **不写入**该 key 的缓存，
  也不把失败结果缓存为"空池子"。
- **AC-2.4** When 前端在同一屏内先后触发 `/api/overview`、`/api/emotion_trend`、
  `/api/sentiment`, the 系统 shall 只发起 1 次真实东财请求序列。
- **AC-2.5** 缓存**不得**改变任何接口的响应字段与取值口径（对比改造前后同一时刻的响应，
  除因行情自身变化导致的数值差异外应完全一致）。

### AC-3 情绪分路径不被全市场快照阻塞（待确认，见 §5 第 3 项）

- **AC-3.1** While `data/screener/stock_list.json` 的缓存处于有效期内,
  when 计算 `_dt_count()`, the sentiment 模块 shall 使用该缓存，不发起网络请求。
- **AC-3.2** While 快照缓存已过期或不可用, when 计算 `_dt_count()`,
  the sentiment 模块 shall **不主动触发全市场拉取**，而是回退到东财跌停池
  （`_em_pool("getTopicDTPool", date)`）。
- **AC-3.3** When 快照有效可用, the sentiment 模块 shall 保持现有跌停口径
  （新浪全市场按分档阈值判定），与 `market.build_distribution` 的跌停数口径一致。

### AC-4 缓存安全边界（红线）

- **AC-4.1** While 进程持续运行, when 调用 `get_sentiment()`, the 返回的 `trade_date`
  shall 等于当前真实最近交易日，**不得**因缓存而滞后。
- **AC-4.2** The sentiment 模块 shall **不缓存** `_calc_score` 的合成结果，
  也不缓存 `get_sentiment()` 的返回字典。
- **AC-4.3** If 系统跨过交易日边界（如从 23:59 到 00:01，或从周五到周一）,
  then 所有数据层缓存 shall 自动失效，无需人工清理或重启。

### AC-5 可观测性

- **AC-5.1** When 东财请求命中缓存, the sentiment 模块 shall 记录 debug 级日志（命中 key）。
- **AC-5.2** The `/api/sentiment` 接口 shall 保持现有响应字段不变
  （不因本轮改动新增或删除字段）。

### AC-6 回归与自检

- **AC-6.1** `pytest` 全量用例（当前 414）shall 全部通过，且**离线可跑**。
- **AC-6.2** 本项 shall 至少包含 1 项「改坏即变红」自检：临时让请求去重失效
  （恢复成重复请求），对应断言用例应变红；回滚后 `sha1sum` 与改前一致。
- **AC-6.3** 改造后 shall 提供**改造前后的同机耗时对比**（同一时段、同一台机器），
  而不是只给一个改造后的数字。

## 5. 待确认的关键取舍（3 项）

| # | 项 | 选项 | 建议 | 理由 |
|---|---|---|---|---|
| 1 | **请求去重** | 做 / 不做 | **做** | 零风险、零副作用，省 1.25s。唯一需要动的是 `_find_recent_trade_date()` 的返回值传递方式 |
| 2 | **数据层短 TTL 缓存 TTL** | `10s` / `30s` / `60s` / 不做 | **30s** | 前端本就 60s 轮询，30s 让"同一屏的 3 次调用"必然落在同一窗口内，同时把数据滞后上限压在 30s。**若你觉得与"必须每次实时"的原则冲突，可以选 10s 或不做的保守方案** |
| 3 | **东财限流间隔（当前 1s）** | 保持 1s / 降到 0.3~0.5s / 只对连续同 endpoint 限流 | **降到 0.35s** | 真实网络仅 0.12s，1s 限流贡献了 77% 的耗时。但这**直接关系到会不会被东财封 IP**，风险由你判断。若求稳，保持 1s 也能靠第 1、2 项把 5.21s 压到约 2.7s |
| 4 | **`_dt_count` 不阻塞快照** | 改 / 不改 | **改** | 让情绪分不再绑上一个 4 秒的无关资源；代价是快照过期时跌停数改用东财口径，与分布图口径会短暂不同（可标注） |

## 6. 关联发现（本轮不处理，仅记录）

- `core/legu.py:64` 的 `generated == today` 也是**整日缓存**，与 v4 事故同一模式。
  后果：同一进程内盘中拉过一次之后，即使收盘后乐咕已发布当日数据，
  `legu_ok` 仍恒为 False，永远走东财+新浪回退路径。
  用户可见影响小（两条路径的数值接近），但"乐咕优先"的设计意图实际上从未生效。
  **建议单独立项或在下一轮一并处理。**

## 7. 验收所需证据

1. 改造前后 `get_sentiment()` 冷/热耗时对比（同机同时段）
2. 改造前后东财请求**次数与参数序列**对比（用 `_em_get` 打桩记录，即本轮实测所用手法）
3. 同一屏 3 个接口的合并请求数：改造后应为 1 次真实请求序列
4. 跨交易日失效的离线用例（时间打桩）
5. 「改坏即变红」自检回滚前后 `sha1sum` 一致
