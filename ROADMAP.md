# ROADMAP — 项目维护计划

本文件记录 bull-run 的**非功能性**改进事项（仓库治理、工程质量、稳定性）。
具体功能需求仍走 `.trae/specs/` 的 spec 工作流。

状态：✅ 已完成 · 🔜 进行中 · ⬜ 待办

## 总览

| # | 事项 | 状态 | 工作量 | 风险 |
|---|------|------|--------|------|
| 1 | 根目录整理 | ✅ | 小 | 低 |
| 2 | 提交规范化 | ✅ | 小 | 低 |
| 3 | 补充回归测试 | ⬜ | 中 | 低 |
| 4 | 锁定依赖版本 | ⬜ | 小 | 低 |
| 5 | 数据缓存治理 | ⬜ | 小 | 中 |
| 6 | app.py 路由瘦身 | ⬜ | 中 | 中 |
| 7 | 历史提交信息清理（可选） | ⬜ | 中 | 高 |

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

## 3. ⬜ 补充回归测试

**问题**：项目无 `tests/` 目录，验证依赖一次性脚本，改完没法一键回归。

**做法（建议）**
- 引入 `pytest`，建 `tests/` 目录
- 优先覆盖**纯函数、无网络**的部分：
  - `core/sentiment.py` — 五维度打分与等级映射
  - `core/tdx.py` — 公式解析（用固定行情 DataFrame 作输入）
  - `core/indicators.py` — MA / MACD / KDJ / RSI / BOLL
  - `core/market.py` — `_compare_and_pick` 双源切换判定（mock 掉网络请求）
- 网络模块（`data.py` / `legu.py` / `gold.py`）不写单测，保持 `scripts/` 里的契约校验脚本

**验收**：`pytest` 一键跑通，覆盖上述 4 个模块的核心分支。

---

## 4. ⬜ 锁定依赖版本

**问题**：`requirements.txt` 只有下限约束（`requests>=2.28` 等），上游大版本变更可能直接导致启动失败。

**做法（建议）**
- 在当前可用环境导出精确版本：`pip freeze > requirements.lock.txt`
- 或把 `requirements.txt` 改为兼容版本约束（`requests~=2.32`）

**验收**：在一台干净机器上按锁定的版本能一次装好并启动。

---

## 5. ⬜ 数据缓存治理

**问题**：`data/screener/klines` 已有 3,660 个 CSV、约 72M，只增不减。

**做法（建议）**
- 在 `core/screener.py` 或启动流程中加清理：按 `mtime` 删除超过 N 个交易日的 `klines/*.csv`
- 或在 `scripts/` 新增 `clean_cache.py`，手动 / 定时执行

**注意**：回测默认取 250 日历史，清理窗口必须 **≥250 个交易日**，否则回测会因数据缺失而失真。

**验收**：清理后任意标的上一次回测仍能取满 250 日。

---

## 6. ⬜ app.py 路由瘦身

**问题**：`app.py` 884 行，部分路由内嵌 70~85 行业务逻辑，路由层偏厚。

**做法（建议）**
- 把 `/api/emotion_trend`、`/api/emotion_low_next` 的计算逻辑下沉到 `core/emotion_history.py`
- 路由只保留：参数校验 → 调用 core → 返回 JSON

**验收**：情绪专区 4 张卡片功能与数据不变（用 `scripts/` 里的校验脚本回归）。

---

## 7. ⬜ 历史提交信息清理（可选，有风险）

**问题**：约 12 条历史 message 是 `git status` 原文，不可读。

**做法**：`git rebase -i --root` 逐条重写 message，或 `git filter-repo --message-callback`。

**风险**：高
- 会改写所有 commit hash，需要 `push --force`
- 若该仓库在其他机器克隆过且有未推送改动，会破坏其本地历史

**建议**：仅在你确认这是单人仓库、其他机器无未推送改动时执行。若图省事，
也可以不清理，从本次往后的提交保持规范即可。
