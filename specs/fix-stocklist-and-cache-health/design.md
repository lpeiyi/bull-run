# 设计：股票清单容错与缓存健康度治理

对应 `requirements.md`。技术方案、结构改动与测试策略。

## 1. 现状数据流

```
load_stock_list(force=False)
  ├─ 读 data/screener/stock_list.json，ts < 24h → 直接返回
  └─ 过期/不存在
       └─ _fetch_sina_stock_list()          ← 循环 _sina_get("hs_a", page, 100)
            └─ except: break                ← ★ 问题点：单页失败即整体中断
       └─ 无条件写回 stock_list.json        ← ★ 问题点：残缺结果也写
       └─ return stocks
```

消费方：`run_screen()`、`start_screen_async()`、`/api/screen/stock_list`。
三者都只看返回值，**无法感知清单是否完整**。

```
get_cached_kline(code, days, adjust)
  ├─ data/screener/klines/{code}_{adjust}.csv 存在 且 max(date) == today → 读并 tail(days)
  └─ 否则 → kline(code, max(days+150,300)) → df.to_csv(path)   ← 覆盖写，非追加
       ↑ adjust 参与文件名 → 切换复权即产生新文件，旧文件成孤儿
```

## 2. 设计目标

| 目标 | 对应 AC | 手段 |
|---|---|---|
| 单页失败不致命 | AC-1.1/1.2 | 单页重试 + 失败页计数 + 继续后续页 |
| 残缺结果不落地 | AC-1.3/1.4/1.6 | 完成后统一校验（失败页数=0 且条数≥下限）才写缓存 |
| 失败可降级、可感知 | AC-1.5/1.8 | 回退旧缓存 + meta 标记 degraded + API 透出 |
| 缓存可见 | AC-2.1~2.3 | 只读体检脚本 |
| 清理可控安全 | AC-3.1~3.5 | dry-run 默认 + 以清单为基准 + 降级时拒绝 |
| 孤儿可识别 | AC-4.1/4.2 | 复权后缀比对 |

## 3. 详细设计

### 3.1 `core/screener.py`：清单拉取改造

**新增模块级常量**

```python
_MIN_STOCK_COUNT = 2000      # 合理性下限：低于此判为失败（可调）
_PAGE_MAX_RETRY  = 3         # 单页重试上限
_LIST_VERSION    = 2         # 缓存文件结构版本
```

**`_fetch_sina_stock_list()` 改为返回 `(stocks, ok)`**

```python
def _fetch_sina_stock_list():
    """拉取全市场清单。

    返回 (stocks, ok)：
      ok=True  —— 所有页均成功且条数达下限
      ok=False —— 存在失败页或条数不足，stocks 仅供诊断，不得落库
    """
    node, page_size, max_page = "hs_a", 100, 200
    all_data, failed_pages = [], []

    for page in range(1, max_page + 1):
        diff, last_err = None, None
        for attempt in range(_PAGE_MAX_RETRY):
            try:
                diff = _sina_get(node, page, page_size)
                break
            except Exception as e:
                last_err = e
                if attempt < _PAGE_MAX_RETRY - 1:
                    time.sleep(1.5 * (attempt + 1))    # 递增退避
        if diff is None:
            failed_pages.append(page)                   # AC-1.1/1.2：记录但不中断
            logging.getLogger(__name__).warning(
                "[stocklist] 第 %d 页重试 %d 次仍失败：%s", page, _PAGE_MAX_RETRY, last_err)
            continue
        if not diff:
            break                                       # 正常翻到末页
        all_data.extend(diff)
        if len(diff) < page_size:
            break

    out = _normalize_stock_rows(all_data)               # 原解析逻辑抽为纯函数
    ok = (not failed_pages) and (len(out) >= _MIN_STOCK_COUNT)
    if not ok:
        logging.getLogger(__name__).error(
            "[stocklist] 拉取不完整：失败页=%s 解析后条数=%d（下限 %d）",
            failed_pages or "无", len(out), _MIN_STOCK_COUNT)
    return out, ok
```

**结构提取（为可测试性，属 C-2 允许的例外）**

原 `_fetch_sina_stock_list` 中「把新浪原始 dict 列表转成标准结构」的那段（约 40 行）抽为模块级纯函数：

```python
def _normalize_stock_rows(raw_items):
    """新浪原始条目 → 标准结构 [{code, pure_code, name, market, ...}]（纯函数，无网络）"""
```

理由：AC-1.7（三市齐全）与解析正确性需要能脱网测试；同时让 `_fetch_sina_stock_list` 只负责「分页 + 容错」一件事。

**`load_stock_list()` 改造 —— 保持原签名，新增 meta 版本**

```python
def load_stock_list(force=False):
    """兼容原签名：只返回列表。"""
    stocks, _meta = load_stock_list_meta(force)
    return stocks


def load_stock_list_meta(force=False):
    """返回 (stocks, meta)。

    meta = {
      "degraded": bool,      # True=使用降级缓存，非本次实时结果
      "count": int,
      "fetched_at": float,
      "reason": str,         # degraded 时的原因说明
    }
    """
```

判定顺序：

| 情形 | 行为 | 依据 |
|---|---|---|
| 缓存未过期且结构合法 | 直接用缓存，`degraded=False` | 原有 24h 语义 |
| 拉取成功（ok=True） | 写缓存（含 `complete: true`）并返回 | AC-1.7 |
| 拉取失败 + 有旧缓存 | **不覆盖**缓存，返回旧缓存，`degraded=True` + reason | AC-1.3/1.5 |
| 拉取失败 + 无缓存 | 返回 `[]`，`degraded=True`，记 error 日志 | AC-1.6 |

缓存文件结构（向后兼容，新增字段不破坏旧读取）：

```json
{ "ts": 1788750766.35, "version": 2, "complete": true, "stocks": [ ... ] }
```

> 旧文件无 `version`/`complete` 字段 → 读时按 `version=1` 处理，视为「可能不完整」，允许被下一次成功拉取覆盖。这正好让老陆当前那份 300 条残缺缓存**在首次成功拉取后被自动修正**。

### 3.2 `app.py`：/api/screen/stock_list 透出降级状态

```python
@app.route("/api/screen/stock_list")
def api_screen_stock_list():
    force = request.args.get("force") == "1"
    stocks, meta = screener.load_stock_list_meta(force=force)
    return jsonify({"stocks": stocks, "count": len(stocks),
                    "degraded": meta["degraded"],
                    "reason": meta.get("reason", "")})
```

前端若不需要可忽略新字段（纯增量，不破坏现有渲染）。

### 3.3 `scripts/cache_health.py`：体检与清理

单文件、双子命令，与既有 `scripts/` 工具风格一致（无第三方依赖，仅用 stdlib + 项目模块）。

```
用法：
  python scripts/cache_health.py report          # 体检（只读，默认）
  python scripts/cache_health.py clean           # 清理预演（dry-run，默认）
  python scripts/cache_health.py clean --apply   # 真正执行删除
  python scripts/cache_health.py clean --apply --orphan-adjust   # 连带删复权孤儿
```

**`report` 输出**（AC-2.1~2.3）

```
=== K线缓存体检 ===
文件数        3,660
逻辑体积      60.2 MB   （均 16.8 KB）
行数分布      最少 6 / 中位 400 / 最大 400；< 250 行的 124 个
mtime 分布    2026-08-29: 3,660
数据新鲜度    最新交易日 2026-08-28（已过期，逾期 20 个交易日）
与清单比对    清单 5,568 / 缓存 3,660 / 交集 3,660
              仅缓存有（疑似废弃）  0
              仅清单有（未缓存）    1,908
复权孤儿      无（当前仅 qfq）
```

**`clean` 判定链**（AC-3.1~3.5）

```
1. 读清单（load_stock_list_meta）
   └─ meta.degraded == True → 拒绝执行，提示「请先获取完整清单」   ← AC-3.5
2. 枚举 klines/*.csv → 解析出 (code, adjust)
3. 待删集合 A：code ∉ 清单标的集合
   待删集合 B（仅 --orphan-adjust）：adjust ∉ 当前配置复权类型
4. 打印将删清单 + 预计释放空间                                    ← AC-3.1
5. 若 --apply：逐个删除，失败逐条报告不中断                       ← AC-3.4
```

**关键安全设计**

- 删除粒度为**整文件**，不做内容裁剪 → 不触发 250 日失真（§1.4 / AC-3.3）。
- 默认 dry-run；`--apply` 必须显式给出。
- 清单降级时**拒绝清理**（防止以残缺基准误删有效缓存）。
- 删除前不备份（缓存可重拉，备份反而占空间），但输出完整待删清单便于事后核对。

### 3.4 复权孤儿识别（AC-4.1/4.2）

从配置读取当前复权类型（`config.json` 的选股/回测默认值，缺省 `qfq`）。文件名后缀与该值不一致者计为「孤儿」。

**注意**：`report` 只**报告**孤儿数量；`clean` 默认**不删**孤儿，需 `--orphan-adjust` 显式开启。理由见 requirements §7.4 —— 用户可能为多复权对比刻意保留。

## 4. 测试策略

沿用 `tests/conftest.py` 的 autouse socket 阻断夹具，全部离线。

### 4.1 清单容错（`tests/test_screener_stocklist.py`）

网络调用以 monkeypatch 替换 `core.screener._sina_get`。

| 用例 | 构造 | 断言 | AC |
|---|---|---|---|
| 单页失败后重试成功 | 第 1 页前 2 次抛异常、第 3 次成功 | ok=True，最终条数完整 | 1.1 |
| 单页重试耗尽 | 第 2 页恒抛异常 | failed_pages 含 2，ok=False，**但仍请求了第 3 页** | 1.2 |
| 条数不足判失败 | 只返回 1 页 100 条 | ok=False | 1.4 |
| 成功不写残缺 | ok=False 时检查 `stock_list.json` | 文件 mtime/内容未变 | 1.3 |
| 失败回退旧缓存 | 预置合法缓存 + 拉取失败 | 返回旧缓存，degraded=True | 1.5 |
| 无缓存且失败 | 无缓存 + 拉取失败 | 返回 []，degraded=True | 1.6 |
| 三市齐全 | 构造 bj/sh/sz 各若干 | 三市计数均 > 0 | 1.7 |
| `_normalize_stock_rows` | 已知新浪原始 dict | 字段映射正确（万元→亿、市场前缀） | 纯函数 |
| 兼容旧缓存 | 无 version 字段的旧文件 | 可正常读出，不抛异常 | 兼容性 |

### 4.2 缓存体检与清理（`tests/test_cache_health.py`）

用 `tmp_path` 构造临时 klines 目录 + 清单桩，不触碰真实 `data/`。

| 用例 | 断言 | AC |
|---|---|---|
| `report` 不改文件 | 前后文件 mtime 集合一致 | 2.2 |
| 体检统计正确 | 文件数/体积/行数分布与构造值一致 | 2.1 |
| 过期判定 | max(date) < today → 计入过期 | 2.3 |
| dry-run 不删 | 未加 `--apply` → 文件仍在 | 3.1 |
| 按清单删孤儿 | 不在清单的 code → 被删；在清单的 → 保留 | 3.2 |
| 降级拒绝清理 | meta.degraded=True → 抛/返回拒绝，0 删除 | 3.5 |
| 孤儿复权默认不删 | 非 `--orphan-adjust` → 孤儿保留 | 4.1/4.2 |

### 4.3 回归

- 现有 205 用例须全绿（AC-5.1）。
- `_fetch_sina_stock_list` 返回值从 `list` 变为 `tuple` —— **须确认无其他调用方**（当前仅 `load_stock_list` 调用，改造时一并处理）。

## 5. 需求追溯矩阵

| AC | 实现位置 | 测试 |
|---|---|---|
| 1.1 / 1.2 | `_fetch_sina_stock_list` 单页重试循环 | test_screener_stocklist 1~2 |
| 1.3 / 1.4 / 1.6 | `load_stock_list_meta` 落库判定 | 同上 3~6 |
| 1.5 | 回退旧缓存分支 | 同上 5 |
| 1.7 | `_normalize_stock_rows` | 同上 7 |
| 1.8 | `app.py` 路由 | 人工核验 / 可选路由测试 |
| 2.1~2.3 | `cache_health.py report` | test_cache_health 1~3 |
| 3.1~3.5 | `cache_health.py clean` | test_cache_health 4~6 |
| 4.1 / 4.2 | 复权后缀比对 | test_cache_health 7 |
| 5.1~5.3 | 全套 pytest | 整体 |

## 6. 已确认事项

| # | 决策 | 取值 | 理由 |
|---|---|---|---|
| 1 | 合理性下限 `_MIN_STOCK_COUNT` | **2000** | 当前 5,568 只，容忍度宽；不因新股上市频繁调整 |
| 2 | 残缺清单处置 | **丢弃 + 回退旧缓存** | 比"并集合并"简单且不会把残缺结果固化 |
| 3 | 清理入口形态 | **`scripts/cache_health.py`** | 与 `scripts/` 既有工具一致，可手动/定时 |
| 4 | 复权孤儿 | **只检测，默认不删** | 用户可能刻意保留多复权对比数据 |

以上为调研后给出的推荐值，任一可推翻。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 改 `_fetch_sina_stock_list` 返回类型破坏调用方 | 全仓 grep 确认调用点仅 1 处；`load_stock_list` 签名保持不变 |
| 重试加剧反爬封禁 | 退避 1.5s×n，上限 3 次；原 `kline()` 已有类似退避先例 |
| 清理误删 | 以完整清单为基准 + 默认 dry-run + 降级时拒绝执行 |
| 旧缓存无 `complete` 字段被误判为完整 | 旧文件一律按 `version=1`（可能不完整）处理，首次成功拉取即修正 |
