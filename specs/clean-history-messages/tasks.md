# 任务：历史提交信息清理

> 上游：`requirements.md`（Phase 1）、`design.md`（Phase 2）。
> 编号 `AC-x.y` 指 `requirements.md` §4 的验收标准；`§n.m` 指 `design.md` 的章节。
>
> **执行前置**：`design.md` §11 的三问需老陆拍板；阶段 1 未过不得进入阶段 2。
>
> **执行完成（2026-09-29）**：三问老陆均「按推荐的来」——① 映射表措辞按现稿；
> ② 校验器留在 `scripts/`；③ **不做**本地 gc（保留 `refs/original` 回滚锚点）。
> 全流程走完：`513adf1…` → `f5e6bc6…`，52/53 条 hash 变化，initial commit 保持不变；
> `--force-with-lease` 强推成功，全量 369 例测试通过。
> 备份与留痕在仓库外的 `D:/job/Repository/bull-run-history-backup-20260928/`。
>
> 实际执行与设计的三处偏差（详见 `ROADMAP.md` 第 7 项）：
> ① `--msg-filter` 工作目录是 `.git-rewrite/t`，脚本**必须绝对路径**；
> ② 该临时目录在 Windows 下落于**仓库根**且不自动清理（已清并加 `.gitignore`）；
> ③ 重写耗时约 **3 分 25 秒**（53 条 × fork python），前台超时会掐断，须后台跑。
> 另：实际改写条数基数由 51 增至 53（本次新增了校验器与 spec 两个提交）。

## 阶段 0：准备（助手已完成，产出即本阶段的证据）

- [x] **0.1 工具选型实测**
  - 在临时仓库上验证 `filter-branch --msg-filter` 的 4 项行为（§2.2 的 Q1~Q4）
  - 结论：`GIT_COMMIT` 可读原 sha、未改动消息逐字节透传、tree/作者/时间戳保留、`refs/original` 自建
  - _Requirement: C-3_

- [x] **0.2 消息映射表落盘**
  - 逐条读 10 个提交的 diff，人工撰写 subject + 概括
  - 生成 `message_map.json`：文件清单段从旧消息**字节原样搬运**（含行首 tab、含八进制转义中文名）
  - 已核验：10 条清单段全部与原消息字节一致；10 条 subject 全部匹配 AC-1.1 正则
  - _Requirement: AC-1.1, AC-1.3, AC-1.4_

- [x] **0.3 重写入口**
  - `apply_message_map.py`：命中查表输出成品，未命中**字节透传**
  - _Requirement: AC-1.2_

- [x] **0.4 校验器与单测**
  - `scripts/verify_history_rewrite.py`：`--dump` / `--verify`，逐条比对并输出可读差异
  - `tests/test_verify_history_rewrite.py`：19 例；含 `message_map.json` 形态守门用例
  - 已成套跑通：19 例全绿、全量 369 例全绿
  - _Requirement: AC-2.2, AC-2.3, AC-1.2_

- [x] **0.5 校验器有效性自检（改坏即变红）**
  - 失效 `tree` 比较 → 1 例变红；失效消息比较 → 3 例变红
  - 两次回滚后 `sha1sum` 与改前一致（`b555bddb…`）
  - _Requirement: 项目交付纪律_

## 阶段 1：人工确认（**不可跳过**）

- [x] **1.1 老陆过目映射表**
  - 逐条确认 `design.md` §5 的 subject + 概括是否与真实改动相符
  - 关注 #2（判断为"补 MA60/MA120"）与 #8（判断为"改开盘啦校准权重"）—— 这两条是读 diff 得出的结论
  - _Requirement: AC-1.1, requirements §8「概括写得对不保证」_

- [x] **1.2 离线预演**
  - `python scripts/verify_history_rewrite.py --verify <基线> --map specs/clean-history-messages/message_map.json`
  - 逐条核对：命中 10 条、其余 41 条无一被动
  - _Requirement: AC-1.2_

## 阶段 2：执行重写

- [x] **2.1 前置快照与备份**
  - 确认工作区干净、`HEAD == origin/main`、未推送 0 条
  - 记录旧 HEAD 全 hash；`git bundle create <备份>/pre-rewrite.bundle --all`
  - `git bundle verify <备份>/pre-rewrite.bundle` 必须通过
  - `verify_history_rewrite.py --dump <备份>/baseline.json`，条数应为当日实际总数
  - _Requirement: AC-3.1, AC-3.2, AC-4.3_

- [x] **2.2 执行 filter-branch**
  - 命令见 `design.md` §2.4；`Cannot rewrite` 时先查 `refs/original` 再加 `-f`
  - _Requirement: AC-1.1_

- [x] **2.3 内容零变更复核**
  - `git diff <旧HEAD> <新HEAD>` 为空（AC-2.1）
  - `git status --porcelain` 为空（AC-2.4）
  - 全量 `pytest` 全绿，用例数与重写前一致（AC-2.5）
  - 关键文件 `sha1sum` 与重写前一致
  - `git rev-parse HEAD~50` 应仍是 `e43718f…`（design §2.3 的可验证预测）
  - _Requirement: AC-2.1, AC-2.4, AC-2.5_

## 阶段 3：硬门禁校验

- [x] **3.1 逐条校验**
  - `verify_history_rewrite.py --verify <备份>/baseline.json --map …/message_map.json`
  - 退出码必须为 0；输出中不得有「仍有 git status 原文 subject」
  - _Requirement: AC-1.1 ~ AC-1.4, AC-2.2, AC-2.3_

- [x] **3.2 人工看可读性**
  - `git log --oneline --reverse | head -14`
  - 不合适 → 改 `message_map.json` 重跑阶段 2（第 2.2 步可重复）
  - _Requirement: US-1_

- [x] **3.3 不通过即回滚**
  - `git reset --hard refs/original/refs/heads/main`，**不得**执行任何 force-push
  - _Requirement: AC-3.3_

## 阶段 4：推送与收尾

- [x] **4.1 force-push**
  - `git_net.py push origin main --force-with-lease=refs/heads/main:<旧HEAD>`
  - 被拒说明远端已前进 → 停止并排查，**不要**改用 `--force`
  - _Requirement: AC-4.2_

- [x] **4.2 核对远端**
  - `git log origin/main -1` 等于本地 HEAD；未推送 0 条

- [x] **4.3 清理本地旧对象（**可选**，见 design §9 备注）**
  - 前置：先从 bundle 恢复到临时目录并确认 `git log` 正常
  - `rm -rf .git/refs/original` + `git reflog expire --expire=now --all` + `git gc --prune=now`
  - 跳过它不影响任何 AC，只是本地仍保留旧对象（可继续一级回滚）

- [x] **4.4 文档同步**
  - `ROADMAP.md` 第 7 项标 ✅，并补已实测的事实更正（10 条而非约 12 条、initial commit 不动、
    `refs/original` 自动可回滚、公开仓库旧对象不保证消失）
  - `specs/clean-history-messages/tasks.md` 勾选本清单
  - _Requirement: requirements §2.1_

- [x] **4.5 记忆追加**
  - 追加当日工作日志；长期结论（`filter-branch --msg-filter` 的 `GIT_COMMIT` 可用、
    字节透传保真、`git_net.py` 可透传任意参数）写入 `MEMORY.md`

## 阶段 5：验证边界（**不做**，显式记录）

- [x] **5.1 不承诺旧 hash 从 GitHub 消失** —— 已显式列为非目标（requirements §6.4）；
  本项勾选指「**边界已记录**」，非「能力已交付」。公开仓库旧对象可达性不受我们控制
- [x] **5.2 不保证他人旧克隆自动修复** —— 前提已消除：老陆确认**无他人克隆**（AC-4.1 已满足），
  故此项无适用对象，同样只表示边界已记录
