# bull-run 项目长期记忆

> 跨会话的重要事实与坑。日常流水记在 `YYYY-MM-DD.md`；各事项的历史细节在 `ROADMAP.md` 与 `specs/`。
> 本文件只留「不看会犯错」的东西。

## 项目定位
A股 / 基金ETF 短线盯盘工具（「牛来」）。Flask 单页应用 + `core/` 纯后端算法模块，
无数据库，JSON + CSV 落地。入口 `start.bat` → `app.py`，端口 8000。
3 个 tab：市场概览 / 智能选股（通达信公式 + 回测 + 定时推送飞书）/ 推送规则。

## 环境（最容易弄错）
- **运行解释器**：`C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe`
  （3.12.10，已装 pandas 3.0.3、pytest 9.1.1）
- 助手沙箱托管的 3.13 **没有 pandas** → 跑测试/脚本一律用上面的系统解释器
- 项目**无 venv**
- 沙箱代理 `127.0.0.1:5290` 连不了外网；需联网时 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY` 并出沙箱执行

## git（本机特有坑）
**推拉一律用自适应脚本，别直接敲 git push：**
```
"...\Python312\python.exe" "C:/Users/peiyilu/.workbuddy/skills/windows-git-push-troubleshoot/scripts/git_net.py" push origin main
```
它自动挑通道（本机 8080 / 系统代理 / 直连）并重试。

- 公司内网**必须开代理**才能访问 GitHub；家里代理关闭、直连**时通时不通**（线路本身不稳，非配置问题）
- 曾两次卡死的**真凶**：`credential.helper=helper-selector`（PortableGit 的弹窗选择器，无 GUI 时挂起 44s）。
  它是**累加型**，`-c credential.helper=wincred` 覆盖不掉，必须**先置空再追加**
- 全局 `~/.gitconfig` 有 `http.proxy=127.0.0.1:8080`（公司端口、家里没有）；**仅本仓库**用局部配置覆盖，全局未动
- **别用沙箱内 `git fetch` 核实推送**（连不上会误报失败）；用 `git log origin/main..HEAD` 是否为 0
- `gh` CLI 与 `git filter-repo` **本机未装**；内置 `git filter-branch` 可用
- 排障：`GIT_TRACE=1 GIT_CURL_VERBOSE=1 GIT_TERMINAL_PROMPT=0 timeout 45 git ... push --dry-run` 输出到文件看

## 协作规范
- 新需求走 `specs/<name>/`（requirements → design → tasks）；`.trae/specs/` 是 Trae 遗留，原样不动
- **每个 phase 产出后先给老陆看**，确认再进下一步；执行前要拿到任务清单的点头
- 提交风格 `type(scope): 中文简述` + 结构化 body（问题 / 根因 / 改动 / 验证）
- 缺陷**当场修**（独立提交、写根因、补用例），不"先记录后修"
- 同文件拆提交：`git diff` → 按 hunk 生成补丁 → `git apply --cached`（补丁用 LF）

## 测试通则（改 core/ 必跑）
- `"...\Python312\python.exe" -m pytest` → 目前 **445 例**，**离线可跑**（conftest 用 autouse 夹具阻断 socket），约 7~20s
- 交付前必做 **「改坏即变红」自检**：改坏一处被测逻辑 → 确认对应用例真变红 → 回滚 → 核对 `sha1sum` 与基线一致
- **自检要在「单进程」里做**（突变→subprocess 跑 pytest→还原→比哈希写在一个脚本里），
  否则本机那个自动回滚会让"还原"在你操作之前就发生，自检结论不可信
- **警惕「恒真断言」**：若断言写成 `gap >= 常量` 而同一条用例又把该常量改成 0，就退化成 `0 >= 0` 永远绿。
  限流/阈值类用例必须用**字面量下限**钉住（2026-10-08 真踩过：`EM_MIN_INTERVAL` 的两条用例原本捕获不到该类缺陷）
- 打桩测网络分页：把唯一出入口（如 `screener._sina_get`）换成内存假接口，假接口**除返回分页数据外还要记录请求过的页序列**，并把 `time.sleep` 置空
- **构造桩数据当心撞码**：`code = "%%06d" % (600000+i)` 生成的号段里再手动改某一行的 `pure_code`，
  会与内置行撞码并被字典推导的后者覆盖（表现为"看起来没生效"）。样例股票取生成号段之外
- **本机疑似有外部进程会自动回滚 `core/screener.py`**（2026-09-30 两次自检时突变被自动还原）。
  故自检改用 **sha1 往返验证**（记基线 → 突变 → 跑 → 还原 → 比哈希），并在提交前后各核一次

## 架构铁律
- `app.py` **只装配**：解析参数 → 调 `core/` → `jsonify`，外加 HTTP 响应缓存字典（`_OVERVIEW_CACHE` 等，**不下沉**）
- **算法一律在 `core/`**。判据：能否脱离 Flask 与网络单独测试
- `core` **不得反向依赖 `app`**；`market → sentiment` 有先例（函数内局部导入）
- 重构遵 **「先立契约、后动刀」**：`tests/test_app_routes.py` 锁响应字段与口径，先在未重构代码上跑绿
- **打桩陷阱**：`from X import f` 是引用副本 → 对 `app.py` 打桩无效；须对**所有挂载点**同时打桩
  `(app_module, core_data, emotion_history, market, screener)`。**调用点搬家后打桩目标会变**，这是"假绿"高发处
- 搬迁前 `assert 旧函数名 not in 新内容`（注释里的旧名也算残留）；搬迁后重扫导入删死引用
- **刻意保留、不得"顺手优化"**：平盘严格不等式与 ±0.001 边界归属、9 区间级联顺序、
  `up_count` 的 `(change_pct or 0)`、日期交集为空返回 `set()` 而非 `None`、
  `INDEX_COMPARE`(4 指数) 与 `INDEX_TREND`(5 指数) **是两个列表不得合并**

## 各模块易踩的坑（一句话版）
- **板块榜**：东财 `push2/clist/get`，`fs=m:90+t:2`(行业) / `t:3`(概念)；排序**必须 `fid=f3`+`po=1`**，
  写 `fl=f3` 无效（那是字段列表参数）→ 会退化成"按代码序取前 100"，榜首被截断。
  新浪仅在东财不可用或条数 <20 时兜底；`_dedup_by_level()` 去掉Ⅰ/Ⅱ/Ⅲ 同层重复
- **K线缓存**：`get_cached_kline()` 用 `to_csv` **覆盖写**，单文件行数上限 400 → 体积 = 标的数 × 16.8KB，
  属应有体积**不是泄漏**；过期判据 `max(date) == 今天`；**整文件删除不会失真**（缺了会自动重拉），
  所以「≥250 交易日」只在按行裁剪时才成立。体检/清理：`scripts/cache_health.py report|clean [--apply]`
- **股票清单**：新浪 `getHQNodeData` 分页，返回顺序 **`bj < sh < sz`**（"拉到一半断"的表现是**全是北交所**）；
  全市场 **5,568** 只（沪 2319 / 深 2902 / 北 347）；容错 `_MIN_STOCK_COUNT=2000`、`_PAGE_MAX_RETRY=3`、
  `_MAX_CONSECUTIVE_FAIL=3`；**仅完整结果才落库**，失败回退旧缓存并标 `degraded`
- **快照时效（第 9 项）**：`data/screener/stock_list.json` 装的是**含实时行情的全市场快照**，不是"慢变清单"。
  两条**独立、不得合并**的闸门：**新鲜度**（行情窗口内 120s / 窗口外 12h）+ **有效性**
  （`price > 0` 占比 ≥ 90%，`_MIN_VALID_SAMPLE=100` 以下豁免）。
  **判据只看 `price` 不看 `change_pct`**（盘前 change_pct 仍残留上一日值）。
  行情窗口 = 交易日 `09:15~11:30 + 13:00~15:00`（**刻意排除午休**）；**不挂休市日历**。
  拉取**分批并发**（`_FETCH_WORKERS=6`，每页 100 条，全市场约 4s；改造前串行 13s）。
  分批而非一次甩 60 页，才能保住"连续失败早停"语义。缓存 `version=3`；v1/v2 **当场算占比**判定，不一律放行。
  `_FETCH_LOCK` 锁内双检防惊群 + `_MIN_RETRY_INTERVAL=60s`。**盘前场景无法真机复现 → 用离线时间打桩用例**
- **东财池访问（第 10 项）**：全部收敛到 `core/em_api.py`（`sentiment._em_pool` / `market._em_pool` 保留旧名做薄包装）。
  改造前 `sentiment` 与 `market` **各持一份独立限流器**，"1 秒/次防封"实际是 2 倍速率 —— 现在 `_LOCK` 内 sleep+请求，**全局单间隔**。
  `EM_MIN_INTERVAL=0.35`（顶部带注释的**唯一外部风险常量**，回滚=改回 `1.0`）+ 失败自适应降速。
  池结果 30s 进程内缓存，key `(endpoint, date, sort)`；**当日空池一律不写缓存**（会变的中间态，否则 `trade_date` 滞后）。
  **绝不缓存 `get_sentiment()` 的合成结果**（v4 事故形态，红线）。
  读数入口 `screener.peek_stock_list(max_age, require_valid)`：**只读、绝不联网**，供情绪分这类"有就用没有就降级"的路径使用；
  取证脚本 `scripts/verify_sentiment.py`（联网打印真实请求序列与间隔）
- **依赖**：`requirements.txt` 精确锁定（`==`，4 项）；dev 依赖在 `requirements-dev.txt`。
  `start.bat` 已是"**先探测、缺了才装**"（断网也能起）。改 pin 纪律：先改文件 → 装 → 跑 pytest → 才提交。
  **别用记事本改 `start.bat`**（cmd 按 GBK 解析，中文注释/BOM 会让首行失效）；注释一律英文
- **历史重写**：`git filter-branch --msg-filter` 内可读 `GIT_COMMIT`(原 sha)；未命中消息**字节透传**。
  三坑：① 脚本必须用**绝对路径**（工作目录是 `.git-rewrite/t`）② `.git-rewrite/` 落在**仓库根**且不自动清理
  ③ 约 **4s/条**，53 条要 3 分半 → **必须后台跑**。回滚锚点 `refs/original/refs/heads/main` 刻意保留。
  校验器 `scripts/verify_history_rewrite.py --dump/--verify`；备份在**仓库外** `D:/job/Repository/bull-run-history-backup-20260928/`

## 已知遗留（截至 2026-10-08）
- **P0-1 已修**（`specs/fix-stocklist-snapshot-freshness/`）；**P0-2 已按「标注而非强行统一」处置**
- **P1-2 已修**（`specs/cut-sentiment-latency/`，ROADMAP 第 10 项）：`get_sentiment()` 真机 **冷 2.27s / 热 0.06s**
  （改造前 5.21s / 8.47s），一次调用 3 次东财请求、无重复三元组
- **P1-3**：非交易时段「领涨/领跌 Top10」显示同一榜单、数值全 `+0.00%` → **未修**（下一个候选）
- **P1-1 剩余**：`loadSentiment` / `emotion_trend` 仍串在 `await loadOverview` 之后 → **未修**
- **P2**：`emotion_trend?days=0` 367KB、`low_next` 108KB（`low_dates` 与 `items[].date` 重复）、favicon 404 → **未修**
- **`core/legu.py` 的 `generated == today` 是整日缓存**，与 v4 事故（`emotion_history` 整日缓存导致 `latest` 卡前一日）同模式
  → 同进程内 `legu_ok` 恒为 False，"乐咕优先"从未真正生效（一直在走东财+新浪回退）。影响小，待立项
- **`start.bat` 起的是旧进程时不会自动生效新代码** —— 改完 `core/` 要让运行中的服务重启（8000 端口）
- ROADMAP **1~10 全部 ✅**
- 挂账验证：情绪专区 4 卡片**人工页面确认**未做；第 4 项「干净机器一次装好并启动」未验证（无第二台机器）；
  第 10 项 `EM_MIN_INTERVAL=0.35` **需观察 1~2 个交易日**是否触发东财限流
- 全局 `~/.gitconfig` 的 `http.proxy=127.0.0.1:8080` 仍未清理（仅本仓库局部覆盖）
