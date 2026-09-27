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

## git 推送（本机特有坑，已修，务必看这条）

**默认用自适应脚本推拉，不要直接敲 git push：**
```bash
"C:/Users/peiyilu/AppData/Local/Programs/Python/Python312/python.exe" \
  "C:/Users/peiyilu/.workbuddy/skills/windows-git-push-troubleshoot/scripts/git_net.py" \
  push origin main
```
它会自动挑通道（本机代理 8080 / 系统代理 / 直连）并重试，且显式带上正确的
代理与凭据参数，不受全局坏配置影响。

### 网络事实（2026-09-27 实测，别再搞错）
- **公司内网**：**必须开代理**才能访问 GitHub（老陆确认）。代理起时本机 8080 被占用
- **家里**：代理关闭；GitHub **直连时通时不通**——连续 5 次仅 1 次成功，
  其余在 TCP 建连阶段超时 15 秒。**不是配置问题，是线路本身不稳**
- gitee 直连稳定（3/3，1.5~1.9s）；SSH over 443 本机无公钥，不可用

### 两个坑（曾导致 push 卡死 12 分钟无输出）
1. `credential.helper = helper-selector`（WorkBuddy 自带 PortableGit 的**弹窗选择器**），
   无 GUI 后台调用时挂起 44 秒 —— 这是那次卡死的**真正主因，与网络无关**。
   且该键是**累加型**，`-c credential.helper=wincred` **覆盖不掉**，
   必须先 `-c credential.helper=` 置空重置再追加
2. 全局 `http.proxy/https.proxy = http://127.0.0.1:8080` —— 公司环境该端口有代理、
   家里没有。注意注册表里存的是 `proxy.xn.petrochina:8080`（公司服务器），
   与配置里的 `127.0.0.1:8080`（本机）不是一回事

### 已做的修复
- **本仓库** `.git/config`：`http.proxy`/`https.proxy` 置空 +
  `credential.helper` = 空值重置 + `wincred`（直读凭据管理器里已有的
  `git:https://github.com`，无弹窗）→ 裸命令在家里可用
- **全局 `~/.gitconfig` 未动**（公司需要代理，且全局改动须经老陆同意）：
  里面那两个坏配置仍在，其他仓库若卡顿同因
- 排障手法：`GIT_TRACE=1 GIT_CURL_VERBOSE=1 GIT_TERMINAL_PROMPT=0 timeout 45 git ... push --dry-run`
  输出到文件再看，能直接看到 401 → 调了哪个 helper → 卡在哪

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
- **205 个用例**，**离线可跑**（`tests/conftest.py` 用 autouse 夹具阻断 socket），约 0.5 秒
- 覆盖 `sentiment` / `indicators` / `tdx` / `market` 四个模块，
  需求见 `specs/add-regression-tests/` 与 `specs/fix-boards-source-selection/`
- **改 `core/` 里任何算法后必须先跑一遍**再交付
- `scripts/` 下的脚本管联网契约校验（接口是否还在、字段有没有变），与测试分工不同
- 交付前自查项：**"改坏即变红"有效性自检**——临时改坏一处被测逻辑，确认对应用例真的失败，
  再回滚。防止出现"测试全绿但其实没测到东西"的假安全

## 板块榜单口径（ROADMAP 第 8 项，已完成）
- 主源为**东财** `push2/clist/get`，`fs=m:90+t:2`(行业) / `t:3`(概念)
- **排序参数必须是 `fid=f3` + `po=1`**；写成 `fl=f3` 无效（`fl` 是字段列表参数，
  不具排序作用）。写错会让「496 个板块里按代码序取前 100 个」变成候选池，
  顶部板块被截断 → 榜单涨幅系统性偏低
- 东财板块含Ⅰ/Ⅱ/Ⅲ 层级，`_dedup_by_level()` 按「去末尾罗马数字后的基名」去重
- 新浪只在东财不可用或条数 <20（`_MIN_SOURCE_ROWS`）时兜底
- 旧的「双源按名称交叉比对」已废弃：两源分类体系不同，名称交集仅 12.2%，永远命中不了
- 验收脚本：`scripts/verify_boards.py`（三项判定：严格降序 / 榜首与东财源一致 / 无同层级重复）

## 已知遗留
- ROADMAP 第 4（锁依赖）/ 5（缓存治理）/ 6（app.py 瘦身）/ 7（历史 message 清理）待办
- 第 5 项：清理 K线缓存的窗口**必须 ≥250 交易日**，回测默认取 250 日，砍狠了回测失真
- 第 7 项风险高，须确认是单人仓库且其他机器无未推送改动
- 全局 `~/.gitconfig` 里那两个错误配置（`http.proxy=127.0.0.1:8080`）**仍未清理**，
  只在本仓库用局部配置覆盖了。其他仓库若有联网操作异常，大概率同因
