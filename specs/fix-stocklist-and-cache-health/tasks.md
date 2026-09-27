# 任务清单：股票清单容错与缓存健康度治理

对应 `requirements.md` / `design.md`。8 个任务分 5 阶段。

## 阶段 1 · 清单容错（核心改动）

- [x] **1. 改造清单拉取：单页重试 + 失败不中断 + 完整性判定**
  - `core/screener.py` 新增常量 `_MIN_STOCK_COUNT = 2000`、`_PAGE_MAX_RETRY = 3`、`_LIST_VERSION = 2`
  - 把 `_fetch_sina_stock_list()` 中「新浪原始条目 → 标准结构」的解析段抽为模块级纯函数 `_normalize_stock_rows(raw_items)`
  - `_fetch_sina_stock_list()` 改为返回 `(stocks, ok)`：单页失败退避重试至多 3 次；仍失败则记 warning 并**继续后续页**；结束后 `ok = 无失败页 且 条数 ≥ _MIN_STOCK_COUNT`
  - 改造前先全仓 grep 确认 `_fetch_sina_stock_list` 调用点（预期仅 `load_stock_list` 一处）
  - _Requirement: AC-1.1、AC-1.2、AC-1.4、AC-1.7_

- [x] **2. 改造 `load_stock_list`：落库校验 + 降级回退**
  - 新增 `load_stock_list_meta(force=False) -> (stocks, meta)`；`meta` 含 `degraded / count / fetched_at / reason`
  - `load_stock_list(force=False)` 保持原签名，内部包装 `load_stock_list_meta` 只返回列表（不破坏调用方）
  - 落库规则：仅 `ok=True` 才写 `stock_list.json`（结构加 `version` / `complete` 字段）
  - 降级规则：拉取失败且有旧缓存 → **不覆盖**、返回旧缓存、`degraded=True`；无缓存 → 返回 `[]` 并记 error
  - 旧版缓存（无 `version`）按 `version=1`（可能不完整）处理，允许被下次成功拉取覆盖
  - _Requirement: AC-1.3、AC-1.5、AC-1.6_

## 阶段 2 · 可观测性

- [x] **3. `/api/screen/stock_list` 透出降级状态**
  - `app.py` 该路由改用 `load_stock_list_meta`，响应新增 `degraded` / `reason` / `count` 字段
  - 确认前端现有渲染不受影响（纯增量字段）
  - _Requirement: AC-1.8_

## 阶段 3 · 体检与清理工具

- [x] **4. 新增 `scripts/cache_health.py`（report + clean）**
  - `report`（默认，只读）：文件数、逻辑体积、行数分布、mtime 分布、数据新鲜度（最新交易日与逾期交易日数）、与清单的差集、复权孤儿数
  - `clean`（默认 dry-run）：以当前清单为基准列出待删文件与可释放空间；`--apply` 才执行
  - `clean --orphan-adjust`：连带纳入复权孤儿
  - 安全链：`load_stock_list_meta` 若 `degraded=True` → **拒绝清理**并提示先获取完整清单
  - 删除粒度为整文件，不做内容裁剪；删除失败逐条报告不中断
  - 复用 `scripts/diag_boards.py` 的 `sys.path` 定位写法（脚本在 scripts/ 下需指向项目根）
  - _Requirement: AC-2.1~2.3、AC-3.1~3.5、AC-4.1、AC-4.2_

## 阶段 4 · 测试

- [x] **5. 新增 `tests/test_screener_stocklist.py`**
  - monkeypatch `core.screener._sina_get` 构造分页响应，覆盖：重试后成功 / 重试耗尽（且仍请求后续页）/ 条数不足 / 不写残缺缓存 / 回退旧缓存 / 无缓存失败返回空 / 三市齐全
  - `_normalize_stock_rows` 纯函数用例（字段映射、万元→亿、市场前缀）
  - 旧版缓存（无 `version`）兼容读取用例
  - _Requirement: AC-5.2_

- [x] **6. 新增 `tests/test_cache_health.py`**
  - 以 `tmp_path` 构造临时 klines 目录与清单桩，**不触碰真实 `data/`**
  - 覆盖：report 只读（前后 mtime 不变）/ 统计正确 / 过期判定 / dry-run 不删 / 按清单删孤儿 / 降级拒绝清理 / 复权孤儿默认不删
  - _Requirement: AC-5.2_

## 阶段 5 · 验证与收尾

- [x] **7. 全量验证与真实环境核验**
  - `pytest` 全套通过（现有 205 + 新增），离线可跑
  - **有效性自检**：临时改坏重试逻辑（如把 `continue` 改回 `break`），确认对应用例变红，再回滚
  - 真实环境：`load_stock_list(force=True)` 拉一次完整清单，确认本地 `stock_list.json` 由 300 条修正为约 5,568 条（含 sh/sz/bj 三市）
  - `scripts/cache_health.py report` 在真实 `data/` 上跑一次，核对与设计预期一致
  - _Requirement: AC-5.1、AC-5.3_

- [x] **8. 更新文档并提交**
  - `ROADMAP.md` 第 5 项：更正「只增不减」的错误描述（附实测依据），改写为「清单容错 + 缓存健康度」
  - `README.md`：补 `scripts/cache_health.py` 用法
  - `.workbuddy/memory/`：记录本次发现与结论；`MEMORY.md` 若涉及长期事实则同步
  - 提交拆分：`fix(screener):` 清单容错 / `feat(scripts):` 体检清理工具 / `test:` 用例 / `docs:` 文档
  - 确认工作区干净、无临时文件入库
  - _Requirement: 全部_

---

## 验收对照

| 阶段 | 对应 AC | 通过标准 |
|---|---|---|
| 1 · 清单容错 | AC-1.1~1.7 | 用例覆盖 + 真实拉取条数达标 |
| 2 · 可观测性 | AC-1.8 | 路由返回 `degraded` 字段 |
| 3 · 工具 | AC-2.1~2.3、AC-3.1~3.5、AC-4.1~4.2 | 用例覆盖 + 真实 `report` 输出可读 |
| 4 · 测试 | AC-5.2 | 新增用例全绿 |
| 5 · 收尾 | AC-5.1、AC-5.3、全项 | 全套 pytest 通过 + 文档更新 + 提交规范 |

## 依赖与顺序

```
1 ──→ 2 ──→ 3 ──→ 7 ──→ 8
         └──→ 4 ──→ 6 ──┘
   └──→ 5 ──────────────┘
```

- 任务 1 是任务 2、4、5 的前提（返回类型与纯函数提取）
- 任务 4 的 `clean` 依赖任务 2 的 `load_stock_list_meta`（降级判定）
- 任务 6 依赖任务 4 的脚本可被 import
