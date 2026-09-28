# 任务清单：锁定依赖版本

对应 `requirements.md` / `design.md`。8 个任务分 5 阶段，**状态已全部勾选**（本次为一次连续实施）。

## 阶段 1 · 依赖声明

- [x] **1. `requirements.txt` 改为精确锁定**
  - 4 项运行依赖由 `>=` 下限约束改为 `==`：`requests==2.34.2`、`flask==3.1.3`、`numpy==2.4.6`、`pandas==3.0.3`
  - 版本取值来自本机**已跑通全套 `pytest`** 的解释器环境（AC-1.2）
  - 文件头补注释：说明锁定纪律（改动前须跑通 pytest）与核查命令
  - _Requirement: AC-1.1、AC-1.2_

- [x] **2. 新增 `requirements-dev.txt`**
  - `-r requirements.txt` 继承运行依赖 + `pytest==9.1.1`
  - 目的：把测试框架挡在运行环境之外，避免生产环境被塞入 pytest
  - _Requirement: AC-1.3_

## 阶段 2 · 探测层

- [x] **3. 新增 `scripts/check_deps.py`**
  - 纯标准库实现（`argparse` / `importlib.metadata` / `re` / `os` / `sys`），满足 C-1
  - `parse_requirements(path) -> (pins, skipped)`：只认 `<包>==<版本>`，其余形态进 `skipped` 并输出提示
  - `check(pins) -> [dict]`：产出 `name / expected / installed / status`（`ok` / `missing` / `mismatch`）
  - `main(argv)`：报告模式（退出码反映一致性）+ `--missing` 模式（**只判包在不在**）
  - 退出码约定见 design.md §4.3
  - 顶部 docstring 注明 ROADMAP 第 4 项背景与用法
  - _Requirement: AC-2.1~2.5_

## 阶段 3 · 执行层

- [x] **4. `start.bat` 改为「先探测、缺了才装」**
  - 新增 `"%PY%" scripts\check_deps.py --missing >nul 2>&1` 探测
  - `if not errorlevel 1 goto :start`：依赖齐备直接跳到启动段，**不联网**
  - 缺失时才走 `pip install -r requirements.txt`，并保留失败提示 + `exit /b 1`
  - 原 `--quiet` 去掉（首次安装时让用户看到进度）
  - 注释改写为**英文**：cmd 按 GBK 解析，中文注释会变乱码并被当命令执行（C-4）
  - 新增 `:start` 标签，`[2/2]` 提示语位置相应调整
  - _Requirement: AC-3.1~3.5_

## 阶段 4 · 测试

- [x] **5. 新增 `tests/test_check_deps.py`（11 例）**
  - 解析组：只取锁定行 / 非锁定行进 skipped / 文件不存在返回空
  - 比对组：`ok` / `mismatch` / `missing` 三态（monkeypatch `importlib.metadata.version`）
  - 命令行组：全部一致 / 版本不符 / `--missing` 检出缺失 / **`--missing` 忽略版本不符** / 非锁定行提示 / 空锁定视为失败
  - **守门用例** `test_project_requirements_fully_pinned`：直接读项目根 `requirements.txt`，断言无 `skipped`
  - _Requirement: AC-2.1~2.4、AC-4.2_

- [x] **6. 新增 `tests/test_startup.py`（4 例）**
  - `test_start_bat_is_pure_ascii`：无 >0x7F 字节
  - `test_start_bat_has_no_bom`：无 UTF-8 BOM
  - `test_start_bat_referenced_files_exist`：正则抽出 `scripts\*.py` 与 `-r *.txt` 引用，逐一断言存在
  - `test_start_bat_checks_before_installing`：断言含 `check_deps.py --missing` 与 `if not errorlevel 1 goto :start`
  - 说明：只读文件字节做契约断言，不真正运行 `start.bat`（会常驻 web 服务），属 C-3 离线约束下的合理取舍
  - _Requirement: AC-3.1、AC-3.2、AC-3.4、AC-3.5、AC-4.3_

## 阶段 5 · 验证与收尾

- [x] **7. 全量验证与有效性自检**
  - `pytest` 全套 **267 passed**（252 原有 + 15 新增），离线可跑，8.65s
  - **有效性自检 ①**：`requirements.txt` 的 `requests==2.34.2` 改回 `requests>=2.28` → `test_project_requirements_fully_pinned` 变红（`1 failed, 10 passed`），恢复后转绿
  - **有效性自检 ②**：删除 `start.bat` 的 `if not errorlevel 1 goto :start` → `test_start_bat_checks_before_installing` 变红（`1 failed, 3 passed`），恢复后转绿
  - **恢复校验**：两文件 `sha1sum` 汇总值前后一致（`fd7f2c23…`），确认自检未留痕
  - `python -m pip check` → `No broken requirements found.`
  - `python scripts/check_deps.py` → 4 项全 OK，退出码 0
  - `python scripts/check_deps.py --missing` → 退出码 0（启动不会触发安装）
  - _Requirement: AC-1.4、AC-4.1、AC-4.4_

- [x] **8. 更新文档并提交**
  - `specs/lock-dependency-versions/` 三件套落盘
  - `ROADMAP.md` 第 4 项标记 ✅，并如实记录验收边界（未在第二台干净机器验证）
  - `README.md`：快速开始补 `requirements-dev.txt`；开发与测试段补依赖核查命令
  - `scripts/README.md`：新增 `check_deps.py` 条目，并修正"这些脚本不参与启动流程"的表述
    （`check_deps.py` 已为 `start.bat` 所调用，原表述会与新事实矛盾）
  - `.workbuddy/memory/`：追加当日工作日志
  - 提交拆分（按主题）：`chore(deps)` 锁定与拆分 / `feat(scripts)` 核查工具 / `chore(start)` 启动链路 / `test` 用例 / `docs` 文档
  - _Requirement: 全部_

---

## 验收对照

| 阶段 | 对应 AC | 通过标准 |
|---|---|---|
| 1 · 依赖声明 | AC-1.1~1.3 | 4 项全 `==`；dev 文件继承并锁定 pytest |
| 2 · 探测层 | AC-2.1~2.5 | 两种模式退出码正确；无非锁定行；不联网 |
| 3 · 执行层 | AC-3.1~3.5 | 齐备则跳过安装；纯 ASCII 无 BOM；引用文件存在 |
| 4 · 测试 | AC-4.2、AC-4.3 | 两道守门用例存在且改坏即变红 |
| 5 · 收尾 | AC-1.4、AC-4.1、AC-4.4 | 267 用例全绿离线可跑；`pip check` 无冲突；文档同步 |

## 依赖与顺序

```
1 ──→ 2 ──┐
          ├──→ 5 ──→ 6 ──→ 7 ──→ 8
3 ────────┤
4 ────────┘
```

- 任务 1 是任务 5（守门用例读项目根 `requirements.txt`）的前提
- 任务 3 是任务 4（`start.bat` 调用）与任务 5 的前提
- 任务 4 是任务 6 的前提
- 任务 7 的**有效性自检**要求同时改坏任务 1 与任务 4 的产物，故须排在两者之后

## 未完成 / 遗留

- **真机干净环境验证未做**：ROADMAP 原验收要求"在一台干净机器上按锁定版本一次装好并启动"，
  本次无可用干净机器，仅完成替代验证（见 requirements.md §8 与 design.md §6）。
  若日后有第二台机器，应补做一次并回填结论。
