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
- **350 个用例**，**离线可跑**（`tests/conftest.py` 用 autouse 夹具阻断 socket），约 5 秒
- 覆盖 `sentiment` / `indicators` / `tdx` / `market`(统计) / `screener`(清单容错) /
  `scripts/cache_health.py` / `scripts/check_deps.py`、`start.bat` 启动链路契约、
  以及 **`app.py` 路由契约**（`tests/test_app_routes.py`）
- 需求见 `specs/add-regression-tests/`、`specs/fix-boards-source-selection/`、
  `specs/fix-stocklist-and-cache-health/`、`specs/lock-dependency-versions/`、
  `specs/slim-app-routes/`
- **改 `core/` 里任何算法后必须先跑一遍**再交付
- `scripts/` 下的脚本两类：**联网契约校验**（接口是否还在、字段有没有变）与**缓存体检运维**，
  与测试的分工不同
- 交付前自查项：**"改坏即变红"有效性自检**——临时改坏一处被测逻辑，确认对应用例真的失败，
  再回滚并核对 `sha1sum` 一致。防止出现"测试全绿但其实没测到东西"的假安全
- 测网络分页逻辑的通用手法：把唯一的网络出入口（如 `screener._sina_get`）换成内存假接口，
  假接口**除返回分页数据外还要记录请求过的页序列**，否则断言不了"失败后仍继续拉后续页"；
  记得同时把 `time.sleep` 置空，免得真等退避

## app.py 职责边界（ROADMAP 第 6 项，已完成）
- `app.py` **只做装配**：解析请求参数 → 调 `core/` → `jsonify`，
  外加 **HTTP 响应缓存字典**（`_OVERVIEW_CACHE` / `_IDX_CMP_CACHE` / `_LOW_NEXT_CACHE` 等，
  带 TTL，属应用层关注点，**不下沉**）
- **算法一律在 `core/`**。判断标准：能否脱离 Flask 与网络单独测试——能，就属于 `core/`
- 现状：890 → **592 行**（顶层函数 709 → 404），26 条路由不变
- 下沉后的公开入口：
  `emotion_history.enrich_sentiment / build_index_overlay / get_trend_view / get_low_next_view`
  `market.build_distribution(stocks) / get_index_compare(days)`
  `sentiment.limit_threshold / is_limit_stock`
- **`core` 内部不得反向依赖 `app`**；`market → sentiment` 已有先例（函数内局部导入）
- **零行为变更的铁律：先立契约、后动刀**。`tests/test_app_routes.py` 用 Flask `test_client`
  锁定各接口响应字段与取值口径，必须**先在未重构的代码上跑绿**，之后每次搬迁都不得让它变红
- **打桩陷阱**：`from X import f` 是引用副本 → `monkeypatch.setattr(core.data, "kline", fake)`
  对 `app.py` **无效**。统一夹具对**所有可能挂载点**同时打桩：
  `(app_module, core_data, emotion_history, market, screener)`。
  **调用点搬家后打桩目标会变**，这是重构期最容易造成"假绿"的地方
- 搬迁纪律：脚本写入前先 `assert 旧函数名 not in 新内容`（连**注释**里的旧名也算残留）；
  搬迁后**重扫导入**，删掉变成死引用的（如 `kline_range`）
- 刻意保留、不得"顺手优化"的口径：平盘严格不等式与 ±0.001 边界归属、9 区间级联顺序、
  `up_count` 的 `(change_pct or 0)`、日期交集为空返回 `set()` 而非 `None`、
  `INDEX_COMPARE`(4 指数) 与 `INDEX_TREND`(5 指数) **是两个列表不得合并**


## 板块榜单口径（ROADMAP 第 8 项，已完成）
- 主源为**东财** `push2/clist/get`，`fs=m:90+t:2`(行业) / `t:3`(概念)
- **排序参数必须是 `fid=f3` + `po=1`**；写成 `fl=f3` 无效（`fl` 是字段列表参数，
  不具排序作用）。写错会让「496 个板块里按代码序取前 100 个」变成候选池，
  顶部板块被截断 → 榜单涨幅系统性偏低
- 东财板块含Ⅰ/Ⅱ/Ⅲ 层级，`_dedup_by_level()` 按「去末尾罗马数字后的基名」去重
- 新浪只在东财不可用或条数 <20（`_MIN_SOURCE_ROWS`）时兜底
- 旧的「双源按名称交叉比对」已废弃：两源分类体系不同，名称交集仅 12.2%，永远命中不了
- 验收脚本：`scripts/verify_boards.py`（三项判定：严格降序 / 榜首与东财源一致 / 无同层级重复）

## 数据缓存机制（ROADMAP 第 5 项，已完成）
- `data/screener/klines/{code}_{adjust}.csv` 由 `get_cached_kline()` 写：
  **`df.to_csv(path)` 覆盖写、不追加**；单文件行数中位 400、上限 400
  （`kline(code, max(days+150,300))`）→ **单文件大小恒定，不随时间增长**
- 因此缓存体积 = 标的数 × 16.8KB，属**应有体积**，不是泄漏。
  实测：3,660 文件 / 逻辑 60.2MB；与实时清单比对**疑似废弃 0 个**
- **「只增不减」的原判断不成立**（ROADMAP 第 5 项已据此改写）
- 「清理窗口必须 ≥250 交易日」只在**按行裁剪**时成立；**整文件删除不会失真**
  （文件缺失会被 `get_cached_kline` 自动重拉）。当前代码不做裁剪
- 缓存过期判据：文件内 `max(date) == 今天` 才复用，否则整表重拉
- **复权类型参与文件名** → 切换到 hfq/bfq 会另生成一整套文件，旧套成孤儿（当前仅 qfq，未发生）
- 体检/清理工具：`scripts/cache_health.py report|clean [--apply] [--orphan-adjust]`
  （默认只读 / dry-run；清单降级时拒绝清理）

## 股票清单口径（ROADMAP 第 5 项，已完成）
- 清单接口：新浪 `Market_Center.getHQNodeData`，`node=hs_a&sort=symbol&asc=1&num=100` 分页，
  返回顺序 **`bj < sh < sz`**（所以「拉到一半断掉」的表现是**全是北交所**）
- 全市场应有 **5,568 只**（沪 2,319 / 深 2,902 / 北 347）；清单缓存 24 小时
- 缓存文件 `data/screener/stock_list.json` 结构：
  `{"ts", "version":2, "complete":true, "stocks":[...]}`；
  **只有 `complete is True` 才走 24h 直用**，无 `version` 的旧文件一律重拉修正
- 容错参数：`_MIN_STOCK_COUNT=2000`（低于即判失败）、`_PAGE_MAX_RETRY=3`、
  `_MAX_CONSECUTIVE_FAIL=3`（连续 3 页失败即判网络不可用，提前结束）
- 落库规则：**仅完整结果才写**；拉取失败则回退旧缓存并标 `degraded=True`，绝不覆盖
- `/api/screen/stock_list` 返回 `degraded` / `reason`；`?force=1` 强制重拉
- 消费方（`run_screen` / `start_screen_async` / `sentiment` / `app.py`）全部只吃列表，
  故 `load_stock_list()` 签名保持不变，需要 meta 的走 `load_stock_list_meta()`

## 依赖管理（ROADMAP 第 4 项，已完成）
- `requirements.txt` 是**精确锁定**（`==`）的，只有 4 项直接依赖，**不是**下限约束：
  `requests==2.34.2` / `flask==3.1.3` / `numpy==2.4.6` / `pandas==3.0.3`
- 开发/测试依赖另在 `requirements-dev.txt`（`-r requirements.txt` + `pytest==9.1.1`）
- 核查手段：`python scripts/check_deps.py`（逐包比对，不一致退出码 1）/
  `python scripts/check_deps.py --missing`（只判「包在不在」，供 `start.bat` 调用）
- `start.bat` 已是「**先探测、缺了才装**」：依赖齐备直接启动、**断网也能起**；
  只在真缺包时才联网安装。（配套原因：`==` 之后若无条件 pip install，
  本机版本与 pin 有偏差时每次启动都要联网，断网反而起不来）
- **改 pin 的纪律**：先改文件 → 装 → 跑通 `pytest` → 才提交，三步缺一不可
- 两道守门用例别删：`test_check_deps.py::test_project_requirements_fully_pinned`
  （往 `requirements.txt` 写回 `>=` 会直接变红）、
  `test_startup.py::test_start_bat_checks_before_installing`（探测逻辑被删会变红）
- **别用记事本改 `start.bat`**：cmd 按 GBK 解析，中文注释/BOM 会让首行失效并报「找不到路径」。
  注释一律英文，`test_startup.py` 里三道用例守着

## 已知遗留
- ROADMAP 只剩第 7 项（历史 message 清理）待办；第 6 项已完成
- 第 6 项的可选收尾 `scripts/verify_emotion.py`（联网真机对照情绪序列）未做，
  纯离线契约测试已覆盖字段与取值口径
- 第 4 项「干净机器上按锁定版本一次装好并启动」**未验证**（无第二台机器），
  只做了 `pip check` / 逐项比对 / `--missing` 退出码等替代验证；日后有机器应补做
- 第 7 项风险高，须确认是单人仓库且其他机器无未推送改动
- 全局 `~/.gitconfig` 里那两个错误配置（`http.proxy=127.0.0.1:8080`）**仍未清理**，
  只在本仓库用局部配置覆盖了。其他仓库若有联网操作异常，大概率同因
