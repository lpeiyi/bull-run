# 设计：历史提交信息清理

> 上游：`requirements.md`（Phase 1，已产出）。
> 本阶段回答两个问题：**用什么工具**、**具体改成什么**。
> 全部技术判断都附实测证据，不引用记忆或惯例。

## 1. 范围复核（与 requirements 对齐）

| 项 | 值 |
|---|---|
| 待改写提交 | **10 条**（从最早算序号 2~11） |
| 不改的提交 | 序号 1 `e43718fdcd828ec24b602344ea718c59dc8f10dd`（initial commit，默认风格、语义清晰）+ 序号 12 起已规范的全部 |
| 核查时总提交数 | 51 |
| 唯一不可协商项 | C-1：只动 message，tree / blob / 作者 / 时间戳一律不动 |

待改写的 10 条（**完整 hash，改用原 sha 匹配，不用短 hash**）：

| 序号 | 旧 commit | 日期 |
|---|---|---|
| 2 | `a62ea8106769a39412445bf1a4124cdec3ba239b` | 2026-08-23 |
| 3 | `191ca6692…` → 见 `message_map.json` | 2026-08-24 |
| 4 | `62761aa7d…` | 2026-08-25 |
| 5 | `4515c6d18…` | 2026-08-26 |
| 6 | `68652110d…` | 2026-08-27 |
| 7 | `3e3b627e7…` | 2026-08-27 |
| 8 | `922fd7fe9…` | 2026-08-29 |
| 9 | `600bce502…` | 2026-09-02 |
| 10 | `f70548fd2…` | 2026-09-02 |
| 11 | `41ee77919…` | 2026-09-03 |

> 上表短 hash 仅为便于对照；**可执行的映射以 `message_map.json` 里的 40 位全 hash 为唯一来源**。

## 2. 工具选型

### 2.1 候选对比

| 方案 | 本机可用性 | 关键问题 | 结论 |
|---|---|---|---|
| `git filter-branch --msg-filter` | ✅ 内置（git 2.55.0） | 已废弃、打印告警；但只跑 51 条，代价可忽略 | **选定** |
| `git filter-repo` | ❌ 命令与 Python 模块都未安装 | 需联网安装（沙箱不通外网）；且要求 *fresh clone*，会自动移除 `origin` 远端 —— 对一个已推送的仓库是额外的风险面 | 弃用 |
| `git rebase -i --root` | ✅ 内置 | 目标提交在历史最底部（序号 2~11），交互式 rebase 需逐条 `edit` 并手工 amend；非交互化要写 `GIT_SEQUENCE_EDITOR` 加 10 次 `git commit --amend`，**比 filter-branch 多 10 个出错点** | 弃用 |

弃用 `filter-repo` 的补充理由：它对本任务没有实质增益（我们不需要删文件、不需要重映射路径），却引入一次联网安装和一次「必须重新 clone」的强制动作。

### 2.2 实测证据（写进设计前已跑过探针）

在临时仓库上构造了 5 条提交（1 条 initial + 2 条 `git status` 原文 + 2 条干净消息，
其中 1 条**行尾带空格**、1 条**无结尾换行**，并在构造时用 `--cleanup=verbatim` 固化消息字节），
执行 `git filter-branch -f --msg-filter '"<python>" "<msgmap.py>"' -- HEAD`，结果：

| 问题 | 实测结果 |
|---|---|
| **Q1** `--msg-filter` 中能否读到**原提交** sha | ✅ 可以。`GIT_COMMIT` 被导出，且值就是重写前的原 sha（探针日志逐条 `hit=True/False` 判定正确） |
| **Q2** 未改动的 message 是否逐字节不变 | ✅ 是。行尾空格 `'…消息   \n\nbody 也有空格 \n'` 与无结尾换行 `'docs(y): 无结尾换行的消息'` 在重写后**完全一致**（这两条 hash 已变，说明确实被重建过） |
| **Q3** tree / 作者 / 时间戳是否保留 | ✅ 逐条 `tree` 哈希、`%an %ae %at %cn %ce %ct` 全部相同 |
| **Q4** 是否自动建立回滚锚点 | ✅ `refs/original/refs/heads/main` 自动指向重写前 HEAD（AC-3.2 白捡） |

按 Q2 的机制：`--msg-filter` 脚本 `sys.stdin.buffer.read()` 得到**原始消息字节**，
原样透传时不经过任何 normalize（无 `strip`、无加末尾换行），因此 AC-1.2 是**结构上成立**的，
不只是"这次碰巧没变"。这是本次最核心的技术前提。

### 2.3 一个可验证的预测

序号 1 的 initial commit：消息不变、tree 不变、无父提交、作者与时间戳均保留
→ **它的 hash 在重写后应当保持 `e43718f…` 完全不变。**

这条是免费的自检：如果重写后发现 initial commit 的 hash 也变了，说明有**计划外的改动**混进来了。

### 2.4 选定命令

```bash
git filter-branch -f \
  --msg-filter '"<PYTHON312>" "specs/clean-history-messages/apply_message_map.py"' \
  -- HEAD
```

说明：
- `-f` 必需（`refs/original/` 已存在时 filter-branch 会拒绝，重跑时必须带）；
- `-- HEAD` 只重写当前分支可达提交 —— 仓库仅 `main` 一个分支、无标签，
  故**不需要** `--tag-name-filter`，也**不使用** `--all`（避免波及 `refs/original`）；
- 探针已验证：命令串用 `"<带空格的 python 路径>" "<脚本路径>"` 形式在 Git Bash 下可正常执行；
- 脚本按 `GIT_COMMIT` 查 `message_map.json`：命中则输出新消息，未命中则**字节透传**。

## 3. 交付物

| 文件 | 位置 | 是否入库 | 职责 |
|---|---|---|---|
| `message_map.json` | `specs/clean-history-messages/` | ✅ 入库 | **唯一可执行映射**：40 位旧 sha → 完整新 message（含逐字节保留的原文件清单）。也是本次改写的留痕 |
| `apply_message_map.py` | `specs/clean-history-messages/` | ✅ 入库 | filter-branch 的入口，约 20 行：读 `GIT_COMMIT` → 查表 → 命中输出新消息 / 未命中透传 |
| `verify_history_rewrite.py` | `scripts/` | ✅ 入库 | 可复用校验器：`--dump` 落基线、`--verify` 逐条比对，退出码 0/1 |
| `test_verify_history_rewrite.py` | `tests/` | ✅ 入库 | 校验器纯比较逻辑的单测 |
| 基线 JSON + bundle 备份 | 仓库**外**的备份目录 | ❌ 不入库 | 回滚依据，见 §8 |

**为什么校验器放 `scripts/` 而前两个放 `specs/`**：`scripts/` 的既有约定是
「联网契约校验 + 缓存体检运维」。`verify_history_rewrite.py` 对这个约定是**可辩护的扩展** ——
它校验的不是业务逻辑而是仓库自身状态，且**对任何未来的历史重写都复用**
（与 `cache_health.py` 同属"仓库运维"）。而 `message_map.json` / `apply_message_map.py`
是本次一次性的执行载体，按其来源归档在 spec 目录下更合体例。
若老陆认为 `scripts/` 不该新增此类工具，可整体挪到 `specs/clean-history-messages/tools/`。

## 4. 改写规则（满足 AC-1.3 的形态）

新 message 由上到下三段：

```
<type>(<scope>): 中文简述          ← 满足 AC-1.1

- 要点 1（读 diff 后人工撰写，说明"做了什么/为什么"）
- 要点 2

原始文件清单（git status 原文）：
	modified:   xxx.py              ← 以下各行与旧 message 的清单行逐字节相同
	new file:   yyy.py
```

- 第二段的概括是本次的**人工判断产物**，是 requirements §8 里明确"不能保证写得绝对对"的部分，
  因此**必须经老陆过目后才执行重写**；
- 第三段由生成脚本从旧消息中**原样搬运**（含行首 `\t`、含被 git 八进制转义的中文文件名），
  不做任何整理 —— 这是 AC-1.3「信息零丢失」的实现方式；
- 旧消息的第一行 `Changes to be committed:` 不保留（它正是被替换掉的 subject；AC-1.4 要求它彻底消失）。

## 5. 消息映射表（**需老陆逐条过目**）

> 下表为便于阅读只列 subject + 概括；**文件清单段**统一为"原清单逐字节搬运"，
> 各条的完整成品文本见 `message_map.json`（会一并提供给老陆核对每一个字节）。

**#2 `a62ea81`** → `feat(kline): 指数K线补充 MA60/MA120 均线`
- 取数窗口由 `days+35` 改为 `days+150`，保证 120 日均线从可视区起点就有值
- `/api/index_kline` 返回体新增 `ma60` / `ma120`
- `core/data.py` 订正代理环境变量注释：清掉本地 proxy 变量后回落到系统注册表里的公司代理，而非"不使用代理"
- `static/app.js` 同步小改（3 行）

**#3 `191ca66`** → `feat(screener): 新增智能选股引擎与通达信公式解释器`
- 新增 `core/tdx.py`：通达信公式解释器，支持 MA/EMA/SMA/REF/LLV/HHV/CROSS/RSI/MACD/KDJ/BOLL 与 CODELIKE/NAMELIKE/CAPITAL，基于 pandas 向量化
- 新增 `core/screener.py`：全市场清单 + K 线缓存 + 选股过滤 + 异步任务 + 回测
- `app.py` 新增指标 CRUD（`/api/indicators`）、语法检查、选股启动/状态/取消/回测路由
- 前端新增智能选股页；`indicators.json` 预置指标

**#4 `62761aa`** → `docs(readme): 补充五个页面说明与数据来源表`
- 页面总览由"四个页面"改为"五个页面"，补市场概览与智能选股的逐项说明
- 新增数据来源表（接口 / 时效）与项目结构说明

**#5 `4515c6d`** → `feat(overview): 新增黄金行情、涨跌幅分布与指数归一化对比`
- 新增 `core/gold.py`：伦敦金 / 纽约金 / 沪金主连实时行情 + 黄金 ETF 518880 历史
- 新增 `/api/gold`、`/api/market_distribution`（9 区间 + 涨停/跌停/上涨/下跌家数）、`/api/index_compare`（4 指数归一化叠加，分档缓存 600s）
- `app._enrich_sentiment`：为情绪分补近 15 日序列与上一交易日分值
- `market.get_dt_pool` 当日改用新浪全市场清单（东财兜底）；分时量能改按 U 型分布外推
- `sentiment` 新增 `_is_dt_stock` / `_dt_list_sina`
- 首页前端重构：情绪迷你图与因子条、板块 Top10、指数对比、涨跌幅分布图、自选管理、黄金卡片

**#6 `6865211`** → `feat(overview): 情绪贡献度明细与黄金历史多源兜底`
- `sentiment._calc_score` 新增返回五维度 `contributions`，随 `/api/emotion_trend` 下发
- `_enrich_sentiment` 重写：日期归一化、score 强约束 0~100、单点复制为两点让 ECharts 画出水平短线；情绪序列与趋势取数全链路异常兜底
- `core/gold.py`：品种改为伦敦金 / 纽约金 / Au99.99，历史改走「真实 XAUUSD → 518880×系数 → ETF 直出」三级兜底，并回传 `source`
- `market.get_boards` 增东财备用源；补 15:00 收盘点限盘后执行
- `app` 关闭模板缓存（`TEMPLATES_AUTO_RELOAD`），避免磁盘模板已改仍读旧字节码

**#7 `3e3b627`** → `fix(web): innerHTML 渲染前转义用户可控字符串`
- `app.js` 新增 `escapeHtml()`，对 `& < > " '` 做实体化，防止 XSS 与渲染错位

**#8 `922fd7f`** → `feat(liangneng): 量能预测改用开盘啦校准权重，板块改东财主源`
- 分时量能权重由「30 分钟 U 型分段」改为 `_KPL_ANCHORS` 9 锚点线性插值，锚点按 08-28 真实分时数据反推；日线预测与分时曲线共用，全程连续
- 预测值 ±30% 硬 clamp，并对 `inf` / `nan` / 除零做兜底
- 板块主源切换为东财（取 `f6` 成交额），新浪降为兜底
- 新浪指数成交量按缓存「成交额 / 成交量」比率折算成交额，补齐东财缺失日期；回看窗口至少 40 日，不足 22 根时告警
- 同步 README；附 `_v51_curl.py` / `_v51_mock.py` 校准脚本与 3 张对照截图

**#9 `600bce5`** → `feat(screen): 选股策略管理重做，结果补齐所属行业`
- `core/screener.py` 新增东财行业映射 `_industry_map()`（落 `data/industry_map.json`，24h 缓存）；选股结果 `industry` 为空时按 `pure_code` 补齐
- 选股页前端重做：策略列表与搜索、保存/删除、语法检查、进度条、结果表，回测入口调整
- `indicators.json` 清理 **12 条**同名重复策略（均叫「日k勾到大负值」），`config` 增 `timer` 定时推送字段
- 移除历史对照截图 `行业领涨领跌top10.png`

**#10 `f70548f`** → `feat(watchlist): 自选看板新增 K 线弹窗与 KDJ 副图`
- 新增 `openWatchKline` / `closeWatchKline` / `loadWatchKline` / `calcKDJ` / `renderWatchKline`
- 弹窗骨架 `wk-modal` + 图表容器，支持周期切换

**#11 `41ee779`** → `fix(sentiment): 情绪分改走乐咕口径，概览与趋势卡片强制实时`
- `sentiment.get_sentiment` 优先取乐咕 API 的涨停/跌停/炸板数与炸板率（仅当乐咕末日 == 当日才采用），否则回退东财 + 新浪
- 新增 `_filter_zt_pool`：涨停池剔除 ST/*ST 与上市不足 60 日的新股，对齐开盘啦口径；连板高度按过滤后重算
- `/api/overview` 的情绪分不再走 60 秒缓存，改为仅替换缓存中的 `sentiment` 字段
- `/api/emotion_trend` 的 `latest` 强制用实时情绪覆盖，避免 `trend[-1]` 仍是昨日
- 前端情绪卡片补分数 / 等级 / 维度 / 日期渲染

> 10 条覆盖的 scope 取值：`kline` `screener` `readme` `overview`×2 `web` `liangneng` `screen` `watchlist` `sentiment`，
> 全部落在 AC-1.1 正则允许的小写集合内。

## 6. 校验方案

`scripts/verify_history_rewrite.py`，两种模式：

```bash
# ① 重写前：把当前 HEAD 的逐条档案落成基线文件（写到仓库外的备份目录）
python scripts/verify_history_rewrite.py --dump <备份目录>/baseline.json

# ② 重写后：与基线逐条比对，并按 message_map.json 判定每条消息是否符合预期
python scripts/verify_history_rewrite.py --verify <备份目录>/baseline.json \
       --map specs/clean-history-messages/message_map.json
```

每条记录采集 `sha / tree / author / author_email / author_ts / committer /
committer_email / committer_ts / message(原始字节)`。

判定规则（**逐条**，不是只比 HEAD）：

| 检查 | 对应 AC | 不做会怎样 |
|---|---|---|
| 条数相同 | — | 掩盖"提交被吞/被复制" |
| `tree` 相同 | AC-2.2 | 掩盖文件内容被改 |
| `author/email/ts`、`committer/email/ts` 相同 | AC-2.3 | 掩盖元数据被改 |
| 未在 map 中的提交：message **字节**相同 | AC-1.2 | 掩盖"顺手统一风格" |
| 在 map 中的提交：message 等于 map 里的成品 | AC-1.1 / AC-1.3 | 掩盖改写没生效/写错 |
| 全部 subject 不以 `Changes to be committed:` 等开头 | AC-1.4 | 掩盖漏改 |

另外三项独立复核（不依赖脚本）：
- `git diff <旧HEAD> <新HEAD>` 为空（AC-2.1）
- `git status --porcelain` 为空（AC-2.4）
- 全量 `pytest`：**350 例**全绿（AC-2.5）
- `sha1sum app.py core/*.py static/*.js templates/index.html`：重写前后一致（人肉兜底）

**校验器自身也要有牙齿**：`tests/test_verify_history_rewrite.py` 断言 6 类失配必须被报出
（tree 不同 / 作者不同 / 时间戳不同 / 条数不等 / 未映射消息被改 / 已映射消息与 map 不符），
并断言"完全一致时返回空违规列表"。按项目惯例，还要做一次「改坏即变红」自检。

## 7. 执行流程（按序，含失败处置）

| 步 | 动作 | 验证点 / 失败处置 |
|---|---|---|
| 1 | 确认工作区干净、`HEAD == origin/main`、未推送 0 条 | 不满足则停 |
| 2 | 记录旧 HEAD 全 hash；`git bundle create <备份>/pre-rewrite.bundle --all` | `git bundle verify` 必须通过（AC-3.1）；失败则停 |
| 3 | `verify_history_rewrite.py --dump <备份>/baseline.json` | 基线条数 == `git rev-list --count HEAD`（51） |
| 4 | **老陆过目 §5 映射表 + `message_map.json`** | 未确认则停（AC-4.1 已满足，此处是 §8 的"概括需人审"） |
| 5 | 离线预演：直接对基线 JSON 打印 old→new 对照（不碰仓库） | 逐条确认 10 条命中、其余 41 条原样 |
| 6 | 执行 §2.4 的 `filter-branch` | 退出码 0；出现 `Cannot rewrite` 则先查 `refs/original` 是否存在，加 `-f` 重试 |
| 7 | `--verify` 跑校验 + 三项独立复核 + `pytest` | **任一不成立 → 立即回滚（AC-3.3），绝不 force-push** |
| 8 | 核对预测：`git rev-parse HEAD~50` 应仍是 `e43718f…` | 不符 → 说明有非预期改动，回滚 |
| 9 | `git log --oneline --reverse \| head -14` 人工看可读性 | 不合适 → 改 map 重跑（第 6 步可重复） |
| 10 | force-push：`git_net.py push origin main --force-with-lease=refs/heads/main:<旧HEAD>` | AC-4.2。已实测 `git_net.py` 透传任意参数（`args = sys.argv[1:]` 追加到 git 命令后） |
| 11 | 核对远端：`git log origin/main -1` == 本地 HEAD | 不符则排查 |
| 12 | 收尾：`rm -rf .git/refs/original` + `git reflog expire --expire=now --all` + `git gc --prune=now` | **仅在 §7 步 11 通过且 bundle 已验证可恢复后执行**；见 §9 备注 |
| 13 | 文档同步：ROADMAP 第 7 项标 ✅ 并补事实更正、MEMORY/日志追加 | — |

## 8. 回滚方案（两级，均在动手前就位）

- **一级（仓库内，一条命令）**：`git reset --hard refs/original/refs/heads/main`
  —— filter-branch 自动建立，指向重写前 HEAD（探针 Q4 已证实）。步 12 之前一直有效。
- **二级（仓库外，抗灾难）**：从 bundle 恢复
  `git clone <备份>/pre-rewrite.bundle restored && cd restored && git remote set-url origin <原地址>`
  bundle 含全部 refs 与对象，`git bundle verify` 通过才算数。
- **远端回滚**：改写结果已 force-push 但事后反悔 → 从 bundle 重建旧历史后再次
  `--force-with-lease` 推回。这也是 AC-4.3 要求"先验证旧 hash 可取回"的原因。

## 9. 风险与缓解

| # | 风险 | 级别 | 缓解 |
|---|---|---|---|
| 1 | 内容被误改（违背 C-1） | 高 | 逐条 tree 哈希校验（AC-2.2）+ `git diff 旧HEAD 新HEAD` 为空 + 文件 sha1sum 对照 |
| 2 | 41 条未改消息被顺手改动 | 中 | 字节级比对（AC-1.2）；`--msg-filter` 透传机制在结构上保证（§2.2 Q2） |
| 3 | 重写中断 / 半成品状态 | 中 | filter-branch 非事务性；bundle + `refs/original` 双保险；中断后 `git reset --hard refs/original/refs/heads/main` 重来 |
| 4 | force-push 覆盖远端核查之后的新提交 | 中 | `--force-with-lease`（AC-4.2），若远端已前进则推送被拒而非覆盖 |
| 5 | 推送线路不稳 | 低 | 走 `git_net.py` 多通道重试（实测首轮即成功） |
| 6 | 改写后 `git log` 反而更难读 | 低 | 步 9 人工过目；概括由人撰写、清单原文保留，只会更可读 |
| 7 | 概括与真实意图有偏差 | 中 | 已在 requirements §8 显式声明为"不保证"；缓解手段 = 步 4/5 先给老陆过目 |
| 8 | Windows 下 `.git` 对象文件只读导致清理失败 | 低 | 探针时已实际遇到 `PermissionError: WinError 5`（清理临时仓库时）；步 12 的 gc 若失败**不影响任何 AC**，可跳过 |
| 9 | 仓库为 **public** | 低 | 改写只动 message 文本，不涉及任何凭据；旧对象可达性本就是 requirements §6.4 的非目标 |

**关于步 12（`gc --prune=now`）要不要做**：它能让**本地**旧对象真正消失，
但代价是失去一级回滚锚点。建议做，前提是步 12 之前先做一次
「从 bundle 恢复到临时目录并 `git log` 通过」的演练。若老陆想保留本地回滚能力，
**跳过步 12 也无妨** —— 旧的 10 条消息只存在于本地 `refs/original` 里，不影响任何 AC。

## 10. AC 对照表

| AC | 由什么满足 |
|---|---|
| AC-1.1 10 条 subject 合规 | `message_map.json` 成品文本（§5）；步 6 执行、步 7 校验 |
| AC-1.2 其余 message 逐字节不变 | `--msg-filter` 字节透传（§2.2 Q2）；校验器逐条字节比对 |
| AC-1.3 原文件清单原样保留 | 生成时从旧消息搬运清单行（§4 第三段） |
| AC-1.4 不再有 `Changes to be committed:` 等 subject | 校验器全量扫描 subject |
| AC-2.1 `git diff 旧新 HEAD` 为空 | 步 7 独立复核 |
| AC-2.2 逐条 tree 相同 | 校验器（§6） |
| AC-2.3 作者/提交者/时间戳一致 | 校验器（§6） |
| AC-2.4 工作区干净 | 步 7 |
| AC-2.5 全量测试通过 | 步 7（350 例） |
| AC-3.1 bundle 备份且 `verify` 通过 | 步 2 |
| AC-3.2 本地引用指向旧 HEAD | filter-branch 自动建立 `refs/original/refs/heads/main`（探针 Q4） |
| AC-3.3 校验不通过不得推送 | 步 7 的硬门禁 |
| AC-4.1 老陆确认前不执行 | 老陆本轮已确认「其他机器无旧克隆、无未推送改动」✅ |
| AC-4.2 用 `--force-with-lease` | 步 10 |
| AC-4.3 记录旧 HEAD 且验证可取回 | 步 2（bundle verify）+ 步 5 的旧 hash 记录 |

## 11. 需老陆拍板

1. **§5 的 10 条概括措辞**是否准确？尤其 #2（我判断为"补 MA60/MA120"）、
   #8（判断为"量能预测改开盘啦校准"）—— 这两条是我读 diff 后下的结论，
   原文里没有自述，欢迎纠偏。
2. **`scripts/verify_history_rewrite.py` 放 `scripts/` 还是 spec 目录**？（§3 给了推荐与理由）
3. **步 12 的 gc 要不要做**？（做 = 本地旧对象也消失；不做 = 保留本地回滚能力，不影响任何 AC）
