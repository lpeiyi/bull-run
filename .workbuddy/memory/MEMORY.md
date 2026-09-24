# bull-run 项目长期记忆

> 跨会话的项目约定与关键事实。日常流水记在 `YYYY-MM-DD.md`，本文件只留长期有用的。

## 项目定位
A股 / 基金ETF 短线盯盘工具（「牛来」）。Flask 单页应用 + `core/` 纯后端模块，
无数据库，JSON + CSV 落地。入口 `start.bat` → `app.py`，端口 8000。

## 环境（容易弄错，务必看这条）
- **运行解释器**：`C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe`
  （3.12.10，已装 pandas 3.0.3、pytest 9.1.1）
- 助手沙箱托管的 3.13 **没有 pandas**；跑测试或脚本一律用上面的系统解释器
- 项目**无 venv**，`start.bat` 直接指向系统解释器
- 沙箱代理 `127.0.0.1:5290` 连不了外网（装包报 502、访问行情源也会失败）；
  需要联网时须 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY` 并出沙箱执行

## 协作规范
- **spec 目录**：新需求走 `specs/<name>/`（requirements → design → tasks 三件套），
  与 Trae 遗留的 `.trae/specs/` 分开存放，后者保持原样不动
- **阶段确认**：每个 phase 产出后先给老陆看，确认再进下一步；执行前要拿到任务清单的点头
- **提交风格**：`type(scope): 中文简述` + 结构化 body（问题 / 根因 / 改动 / 验证）
- **缺陷策略**：测试或脚本暴露的缺陷**当场修**——独立提交、写明根因与依据、同步补测试用例；
  不采用"先记录后修"
- **同文件拆提交**：`git diff` → 按 hunk 分类生成补丁 → `git apply --cached` 只暂存目标 hunk
  （补丁文件用 LF 写入）

## 回归测试（ROADMAP 第 3 项，已完成）
- 运行：项目根执行 `"C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe" -m pytest`
- 196 个用例，**离线可跑**（`tests/conftest.py` 用 autouse 夹具阻断 socket），约 0.5 秒
- 覆盖 `sentiment` / `indicators` / `tdx` / `market` 四个模块，需求见 `specs/add-regression-tests/`
- **改 `core/` 里任何算法后必须先跑一遍**再交付
- `scripts/` 下的脚本管联网契约校验（接口是否还在、字段有没有变），与测试分工不同

## 已知遗留
- **ROADMAP 第 8 项**：板块双源校准 `_compare_and_pick` 实际从不触发
  （两源返回列表均非按 avg_pct 降序；且东财/新浪板块分类体系不同，前 5 名几乎不重名
  → hits 恒为 0 → 始终用东财）。需老陆确认判定口径后再动，会影响首页行业榜来源
- ROADMAP 第 4（锁依赖）/ 5（缓存治理）/ 6（app.py 瘦身）/ 7（历史 message 清理）待办
- 第 7 项风险高，须确认是单人仓库且其他机器无未推送改动
