# 技术设计：修正板块榜单的数据源选择逻辑

- **Spec 名称**：`fix-boards-source-selection`
- **状态**：Phase 2 — 设计
- **日期**：2026-09-24
- **需求**：`specs/fix-boards-source-selection/requirements.md`

---

## 1. 概述与改动边界

本次改动集中在 `core/market.py` 的板块相关代码，共 4 处：

| # | 位置 | 改动性质 | 说明 |
|---|---|---|---|
| 1 | `_parse_em()` 请求参数 | **缺陷修复** | `fl=f3` → `fid=f3`，排序方才生效 |
| 2 | `_parse_sina()` / `_parse_em()` | 结构提取 | 由 `get_boards()` 内嵌套函数提到模块级（为可测性，C-2 允许的例外） |
| 3 | `_compare_and_pick()` | **替换** | 改为 `_pick_source()`，删除失效的交叉比对 |
| 4 | `get_boards()` | 重写编排 | 东财优先、按需拉新浪、增加去重 |

**不改动**：`/api/overview` 返回结构、前端任何文件、`get_liangneng()` 及其他板块无关功能、依赖清单。

---

## 2. 数据流对比

### 2.1 现状（缺陷版）

```
get_boards()
  ├─ _parse_em("m:90+t:2")   ← fl=f3（无效），返回「代码序前 100 条」
  ├─ _parse_em("m:90+t:3")
  ├─ _parse_sina(行业)        ← 总是拉取，但结果几乎总被丢弃
  ├─ _parse_sina(概念)
  ├─ _compare_and_pick(em, sina, label)
  │     └─ 按名称交叉比对 → hits 恒为 0 → 永远返回 em（死代码）
  └─ _clean_and_sort(...)     ← 只对「错误的 100 条」排序
```

结果：候选池 = 496 个板块中的「代码序前 100 个」→ 高涨幅板块被截断。

### 2.2 目标（修正版）

```
get_boards()
  ├─ em_ind = _parse_em("m:90+t:2")   ← fid=f3&po=1，返回「全量降序前 100 条」
  ├─ em_con = _parse_em("m:90+t:3")
  ├─ 若东财不可靠（空 or 条数 < 20）→ 才拉对应新浪源（省一次网络请求）
  ├─ _pick_source(em, sina, label)    ← 东财优先 / 回退新浪 / 双空返回 []
  ├─ _clean_and_sort(...)             ← 数值过滤 + 降序
  └─ _dedup_by_level(...)             ← 同一行业层级去重
```

---

## 3. 详细设计

### 3.1 修复排序参数（`_parse_em`）

```python
# 现状
params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fl": "f3",
          "fields": "f12,f14,f3,f6", "fs": fs_code}

# 修正后
params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fid": "f3",
          "fields": "f12,f14,f3,f6", "fs": fs_code}
```

要点：
- `fid`（sort field）= `"f3"`（涨跌幅）、`po`（order）= `1`（降序）—— 这是东财 `clist/get` 的标准排序写法。
- `fl` 参数与排序无关，直接移除。
- `pz=100` 保持不变：服务端按 `f3` 全局排序，第一页即为全市场涨幅最高的 100 条（实测第 100 条为 -0.18%，其后方为更低涨幅，佐证为全局排序而非局部排序）。榜单只取 Top10，100 条余量充足。
- `po=1` 原本就在，说明当初意图就是降序，只是字段名写错了。

### 3.2 主源选择（新增 `_pick_source`，替代 `_compare_and_pick`）

```python
_MIN_SOURCE_ROWS = 20  # 少于该条数视为源不可靠（正常应为 100 条）


def _pick_source(em_rows, sina_rows, label):
    """东财优先；东财不可靠时回退新浪；两者皆空返回 []。

    原 _compare_and_pick 依赖「两源同名板块可比」的前提，
    实测两源名称重合率仅 12.2%（49 个大类 vs 496 个细分），
    交叉比对命中数恒为 0，机制从未触发，故整体移除。
    """
    log = logging.getLogger(__name__)
    if em_rows and len(em_rows) >= _MIN_SOURCE_ROWS:
        return list(em_rows)
    if sina_rows:
        log.warning("[boards] %s: 东财源不可靠(em=%d 条)，回退新浪(%d 条)",
                    label, len(em_rows), len(sina_rows))
        return list(sina_rows)
    if em_rows:
        log.warning("[boards] %s: 两源均不足，沿用东财(%d 条)", label, len(em_rows))
        return list(em_rows)
    log.warning("[boards] %s: 东财与新浪均无数据", label)
    return []
```

设计取舍：
- **为何保留 20 条阈值**：东财正常返回 100 条；若因网络抖动只解析出个位数条，榜单会残缺。以 20 条作为「明显不完整」的下限，此时宁可切新浪。
- **为何新浪仅在必要时拉取**：原实现无条件拉取 4 个请求（东财×2 + 新浪×2），而新浪结果在机制失效后从未被使用。改为按需拉取后，正常路径的网络请求由 4 次降为 2 次。
- **兜底优先级**：东财足量 → 东财；否则新浪有数据 → 新浪；否则有多少用多少。

### 3.3 层级去重（新增 `_dedup_by_level`）

```python
_LEVEL_SUFFIX = ("Ⅲ", "Ⅱ", "Ⅰ")


def _base_name(name):
    """去掉名称末尾的罗马数字层级标记，用于识别同一行业的不同层级。"""
    n = name or ""
    while n and n[-1] in _LEVEL_SUFFIX:
        n = n[:-1]
    return n


def _dedup_by_level(rows):
    """输入须已排序；同一基名的板块只保留靠前（涨幅更高）的一个。"""
    seen, out = set(), []
    for x in rows:
        base = _base_name(x.get("name", ""))
        if base and base in seen:
            continue
        if base:
            seen.add(base)
        out.append(x)
    return out
```

要点：
- 东财板块含Ⅰ/Ⅱ/Ⅲ三级且命名不统一（部分带罗马数字、部分不带），无法靠固定后缀精确判层；**以「去掉末尾罗马数字后的基名」作为同一行业的判据**，通用且不依赖东财内部规则。
- 去重**在降序排序之后**执行，保证保留的是涨幅更高的那一条。
- 名称为空的行不参与去重判断，但保留输出（避免误删脏数据行，交由 `_clean_and_sort` 的 `avg_pct` 校验处理）。

### 3.4 编排重写（`get_boards`）

```python
SINA_HY_URL = "https://money.finance.sina.com.cn/q/view/newSinaHy.php"
SINA_CON_URL = "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class"


def _sina_or_empty(url):
    """新浪源拉取，失败返回 []（不抛异常）。"""
    try:
        return _parse_sina(url)
    except Exception:
        logging.getLogger(__name__).warning("[boards] 新浪源拉取失败: %s", url)
        return []


def get_boards():
    """行业 + 概念板块，按平均涨幅降序。东财为主源，新浪为备用源。"""
    em_ind = _parse_em("m:90+t:2")
    em_con = _parse_em("m:90+t:3")
    # 东财不可靠时才请求新浪，正常路径不发新浪请求
    sina_ind = _sina_or_empty(SINA_HY_URL) if len(em_ind) < _MIN_SOURCE_ROWS else []
    sina_con = _sina_or_empty(SINA_CON_URL) if len(em_con) < _MIN_SOURCE_ROWS else []

    def build(em, sina, label):
        return _dedup_by_level(_clean_and_sort(_pick_source(em, sina, label)))

    return {"industry": build(em_ind, sina_ind, "industry"),
            "concept": build(em_con, sina_con, "concept")}
```

`get_boards()` 由原约 70 行（含两个嵌套函数）缩减为约 12 行编排逻辑。

### 3.5 结构提取清单

为满足可测性（C-2 允许的例外），以下函数由 `get_boards()` 内部移到模块级，**函数体保持原样**（除 `_parse_em` 的参数修正）：

| 函数 | 原位置 | 现位置 | 函数体是否改动 |
|---|---|---|---|
| `_parse_sina` | `get_boards()` 内 | 模块级 | 否 |
| `_parse_em` | `get_boards()` 内 | 模块级 | **仅参数：`fl` → `fid`** |
| `_pick_source` | —（新增，替代 `_compare_and_pick`） | 模块级 | 新写 |
| `_dedup_by_level` / `_base_name` | —（新增） | 模块级 | 新写 |

---

## 4. 测试策略

### 4.1 新增/修改的用例（`tests/test_market_boards.py`）

| 用例 | 覆盖 AC | 构造方式 |
|---|---|---|
| `test_parse_em_uses_fid_sort_param` | AC-1.2 | monkeypatch `requests.get`，捕获 params，断言 `fid=="f3"`、`po==1`、不含 `fl`。**这是本次 bug 的回归防线** |
| `test_parse_em_parses_pct_and_fields` | AC-1.3 | mock 返回固定 JSON，断言 `avg_pct` 换算与字段映射 |
| `test_pick_source_prefers_em` | AC-2.1 | 传 100 条东财 + 100 条新浪，断言取东财 |
| `test_pick_source_falls_back_to_sina` | AC-2.2 | 东财 `[]`、新浪有数据 → 断言取新浪 |
| `test_pick_source_insufficient_rows_falls_back` | AC-2.4 | 东财 5 条、新浪有数据 → 断言取新浪 |
| `test_pick_source_both_empty` | AC-2.3 | 两者皆空 → 断言返回 `[]` 且不抛异常 |
| `test_pick_source_em_only_partial_kept` | AC-2.4 | 东财 5 条、新浪空 → 断言沿用东财 5 条 |
| `test_dedup_by_level_removes_duplicate_levels` | AC-3.1 | 构造"林业Ⅲ/林业Ⅱ"同值 → 断言只留一条 |
| `test_dedup_by_level_keeps_higher_first` | AC-3.1 | 降序输入含重复基名 → 断言保留涨幅高者 |
| `test_get_boards_returns_sorted_deduped` | AC-1.1 / AC-4.1 | monkeypatch `_parse_em`/`_sina_or_empty`，断言结果降序、字段齐全 |

既有 `test_clean_and_sort_*` 用例保留不动。

### 4.2 需同步移除的用例

原针对 `_compare_and_pick` 的用例（若有）改为 `_pick_source` 语义；该函数已不存在，直接替换。

### 4.3 脚本验收（`scripts/verify_boards.py`）

Step 3 的判定口径由「比对新浪源第一名」改为：

1. `get_boards()["industry"]` 的 `avg_pct` 严格降序；
2. `industry[0]` 与东财 `m:90+t:2`（`fid=f3&po=1`）返回的第一条名称一致、涨幅差 ≤0.01；
3. 榜单中无「去罗马数字后同名」的重复项。

> 原口径「比对新浪第一名」本身基于错误假设（新浪 49 个大类与东财 496 个细分不可比），故一并更正。

---

## 5. 风险与回滚

| 风险 | 等级 | 应对 |
|---|---|---|
| 榜单内容变化（用户可见） | 中 | 已在需求 §1.1 用真实数据说明变化；前端与接口不变，仅数据更准 |
| 东财接口日后改版 | 低 | 保留新浪兜底 + `_MIN_SOURCE_ROWS` 阈值 + 失败日志 |
| 去重误删合法板块 | 低 | 仅在「去掉末尾罗马数字后同名」时触发；空名不参与判断 |
| 结构提取引入行为变化 | 低 | 提取前后函数体逐字比对；`py_compile` + 全量 pytest + `verify_boards.py` 三重验证 |

**回滚**：改动集中在 `core/market.py` 单文件，`git revert` 对应提交即可完全恢复；测试与脚本改动独立，无连带影响。

---

## 6. 需求追溯矩阵

| AC | 设计落点 | 测试落点 |
|---|---|---|
| AC-1.1 严格降序 | §3.3 `_clean_and_sort`（既有） | `test_get_boards_returns_sorted_deduped` |
| AC-1.2 候选池完整 | §3.1 `fid=f3` 参数修正 | `test_parse_em_uses_fid_sort_param` |
| AC-1.3 榜首一致 | §3.1 + §3.4 | `verify_boards.py` Step 3 |
| AC-1.4 概念同步 | §3.4 `build()` 复用 | 同上（`concept` 分支） |
| AC-2.1 东财优先 | §3.2 `_pick_source` | `test_pick_source_prefers_em` |
| AC-2.2 回退新浪 | §3.2 + §3.4 | `test_pick_source_falls_back_to_sina` |
| AC-2.3 双空返回 [] | §3.2 | `test_pick_source_both_empty` |
| AC-2.4 条数不足回退 | §3.2 `_MIN_SOURCE_ROWS` | `test_pick_source_insufficient_rows_falls_back` |
| AC-2.5 移除交叉比对 | §3.2 整体替换 | 代码审查 + 旧用例移除 |
| AC-3.1 层级去重 | §3.3 `_dedup_by_level` | `test_dedup_by_level_*` |
| AC-4.1 接口不变 | §3.4 返回结构 | `test_get_boards_returns_sorted_deduped` |
| AC-4.2 无新依赖 | 全程使用 `requests` | `requirements.txt` 无变化 |
| AC-5.1 测试覆盖 | §4.1 | — |
| AC-5.2 全套全绿 | — | `pytest` 全量 |
| AC-5.3 脚本口径更正 | §4.3 | `scripts/verify_boards.py` |

---

## 7. 已确认事项

需求文档 §6 的三项决策（东财单主源 / 移除交叉比对 / 按基名去重）在设计中全部落实，无需额外确认。
