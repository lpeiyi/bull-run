# Tasks（Task 17 增量追加：2026-08-26）

## 文档定位
本文件原 Task 1~16（自选看板合并 / 呼吸灯 / 量能预测改进 / 跌停更正 / 涨跌统计柱状图 / 双色进度条 / 量能X轴 / 情绪卡信息补充 / 自选增删改查 / overview-grid 1列3卡 / 情绪因子整宽卡 / 行业Top10 / 黄金卡 / 指数对比曲线）已在前序工作中按主 spec 实施完毕，相关勾选与验证已写入主 tasks.md。本文件仅补充 **Task 17 的 5 个子任务（17.1~17.5）+ 依赖关系更新**，作为增量工作流唯一入口。

- [x] Task 17: 概览页 5 项细节修正（双色进度条斜杠分隔/指数对比近15/30/60切换/情绪卡去重复+空图与渐变修复/行业Top10样式对齐参考图/黄金折线口径与Y轴精度）
  - [x] SubTask 17.1: 涨跌双色进度条分隔改为灰色斜向分割条（/ 形状）+ 两侧留白（style.css + renderDistSummary）
    - 移除原 .up.with-gap 的 margin-right 留白实现；新增 `.dist-divider` 元素与样式：形状为「灰色斜杠 /」，倾斜角度 ~45°~60°，主体厚度 2~4px，颜色 #666~#8a96b5 级别；可通过伪元素（skewY(-45°) 或 linearGradient 135° 方向 stop、或 clip-path 斜切）实现；divider 外层左右各 ~1px 留白（可通过 inline-flex 把红段/.dist-divider/绿段 隔开，中间 div 再带左右 padding 或 margin），层次固定为：红段 - 留白 - 斜杠 - 留白 - 绿段
    - static/app.js renderDistSummary：仅当 up>0 且 down>0 时，在 .up 与 .down 两个 .dist-seg 之间插入 <div class="dist-divider"></div>；单边为 0 时不插入，不再产生多余空隙
    - .dist-bar 使用相对定位 / inline-flex 保证斜杠尺寸与进度条高度一致，不挤压红/绿段宽度百分比（红段与绿段的 width 仍是上涨/下跌占比的精确百分比）
    - 依赖：Task 7 / Task 11
    - 关联 Acceptance Criterion: 斜杠分隔仅在红绿段同时出现时出现；斜杠两侧留白、无多余视觉毛边
    - 测试要求：
      - programmatic: .dist-bar DOM 结构中，仅当 up>0 且 down>0 时出现恰好 1 个 .dist-divider，单边为 0 时不出现 .dist-divider
      - human-judgement: 肉眼可见红/绿两色之间的灰色「斜杠 /」形分割条，角度 ~45°~60°；斜杠两侧各有极细留白与红绿段分开，不再是纯水平直条或纯留白间隙
  - [x] SubTask 17.2: 指数走势对比卡新增近 15/30/60 日切换档位（HTML + app.js + app.py /api/index_compare 分档缓存）
    - templates/index.html：在「指数走势对比」卡片的标题下方新增工具栏档位，风格与 #ik-range 一致，3 个 seg-btn（近15日 / 近30日 / 近60日），默认高亮「近60日」；hint 副标题随当前档位显示对应日期数（例如「近30日 归一化累计涨幅（起始日=100）」）
    - static/app.js：改造 loadIndexCompare(days=60) 接受参数并请求 /api/index_compare?days=N；绑定档位按钮点击事件，切换高亮并刷新图表；已绑定的 resize 保持不变
    - app.py：/api/index_compare 增加 days query 参数，校验合法值 ∈ {15,30,60}，缺省 60；_IDX_CMP_CACHE 由单条对象改为按 days 分档缓存（例如用 dict key "15"/"30"/"60" 分别存 ts+data，或原单条结构扩展为 Map），600s TTL 独立；取日期交集后取末尾 N 天返回
    - 依赖：Task 16
    - 关联 AC：切换 15/30/60 档，返回日期点数与按钮档位一致；缓存独立、切换不串数
    - 测试要求：
      - programmatic: 分别请求 /api/index_compare?days=15 / 30 / 60，dates 长度分别为 15 / 30 / 60，无多余或缺失；按钮点击后 hint 副标题同步
      - human-judgement: 切换档位后折线数据平滑更新，legend/tooltip 仍正常；窗口 resize 自适应
  - [x] SubTask 17.3: ~~（已替换）原概览页情绪 sent-card 简化与迷你图修复，已由 Task 19 情绪页优化整体取代~~
  - [x] SubTask 17.4: 行业领涨领跌 Top10 卡样式升级对齐附件 行业领涨领跌top10.png
    - templates/index.html：该卡内部结构升级为左右两栏各自带独立小标题（左栏头「领涨 TOP10」红色、右栏头「领跌 TOP10」绿色）；两栏之间加一条竖向分隔线（border-right / 或外层 flex 的 gap + 中间子 div 垂直边框）
    - static/style.css：重写 .boards-top10 / .boards-bar-row.up / .boards-bar-row.down / .rank / .name / .pct / .bar.up / .bar.down 结构：第 1/2/3 名序号徽章更醒目（金/银/铜或红黄渐变 + 对应字体色加深），第 4~10 名普通深色徽章；行结构 flex 明确，使用 flex:0 0 固定的 rank/name/pct 宽与 bar-track flex:1，禁止换行错位；≤900px 响应式下两栏保持竖排
    - static/app.js renderBoardsTop10：DOM 顺序对齐参考图（领涨：序号→名称→涨幅值→右向红条；领跌：左向绿条→跌幅值→名称→序号）；归一化宽度算法保留 maxAbsPct 统一刻度；领涨涨幅值前缀保持 +、领跌保持 -（或根据 avg_pct 自动加前缀，参考原实现 fmt(avg_pct)）；空态降级保留 boards-empty
    - 参考图片路径：d:/job/Repository/bull-run/行业领涨领跌top10.png；若图片格式无法机器解析，按「左右独立标题+竖分隔线+前三名徽章强化+行列不换行」四点即可
    - 依赖：Task 14
    - 测试要求：
      - programmatic: 控制台无报错；#boards-up / #boards-down 各行数 ≤10；首行 bar 宽度为 100%（对应 maxAbsPct）
      - human-judgement: 左右分隔线存在；每栏有独立「领涨 / 领跌 TOP10」小标题；前三名徽章样式更醒目；单条行内 4 元素（序号/名称/涨跌值/条）不换行错位
  - [x] SubTask 17.5: 综合黄金行情卡修复 — 历史折线 Y 轴与 Tooltip 口径（黄金ETF 518880 代理）
    - templates/index.html：黄金卡标题下 hint/或折线上方小字，由「近30日伦敦金价格迷你折线图」更正为「近30日黄金ETF 518880 走势（代理国内金价）」，避免误导为伦敦金 XAUUSD（当前 data 实际来源是国内黄金 ETF 518880 的收盘）
    - static/app.js renderGoldHistory：tooltip.formatter 文案改为「<日期><br>黄金ETF 518880 收盘：<价格>」，价格保留 3~4 位小数；yAxis axisLabel formatter 同步保留小数；grid.left 增加到 64+ 像素保证数字不被裁切；如有 Y 轴 name 可标为「收盘价（元）」
    - 数值一致性：/api/gold 返回的 history_xau[i].close 数值（当前是 round(float,4)）需与悬停 tooltip 展示完全一致；若后端精度不足可提高到 4 位以上，必要时在 core/gold.py 补 round(float,4) 再输出
    - 依赖：Task 15
    - 测试要求：
      - programmatic: 悬停任一数据点，tooltip 价格 == d.history_xau[i].close（精确到 ≤4 位小数）；Y 轴刻度范围 ≈ [floor(min*0.995), ceil(max*1.005)]，不会出现 0 / 1e6 这类离谱刻度
      - human-judgement: 肉眼观察 Y 轴刻度与折线数值匹配，不再感觉「刻度不对」；Tooltip 文案明确标注为黄金ETF 代理，而非伦敦金美元报价

# Task Dependencies Updates（仅对 Task 17 有效）
- Task 17.1 依赖 Task 7 / Task 11（双色进度条已存在）
- Task 17.2 依赖 Task 16（指数对比卡已存在）
- Task 17.3 依赖 Task 13（sent-card 三列 + 迷你图已实现，但需修正 bug）
- Task 17.4 依赖 Task 14（行业 Top10 卡已存在，但要对齐参考图）
- Task 17.5 依赖 Task 15（黄金卡已存在，但口径与精度需修正）
- Task 17.1/17.2/17.3/17.4/17.5 互相之间无直接依赖，可并行委派

---

# Tasks（Task 18 增量追加：2026-08-26 — 验证回归修复）

## 文档定位
Task 17 实施后进行 Verification，发现 2 项回归问题。本节追加 Task 18 的 2 个子任务用于修复，作为验证回归修复入口。

- [x] Task 18: 验证回归修复（/api/gold force 参数 / 行业 Top10 grid 布局错位）
  - [x] SubTask 18.1: /api/gold 接口补充 force=1 强制刷新支持（app.py）
    - 现状：app.py:168-177 的 `/api/gold` 路由函数体内**未读取 force 查询参数**，导致 `?force=1` 无法强制跳过 300s 缓存，前端无法拉取最新黄金行情。其他接口（/api/overview、/api/index_compare、/api/market_distribution、/api/emotion_trend）均已实现 force 参数，唯独 /api/gold 缺失
    - 修复：参照 `/api/overview` 实现，在 `/api/gold` 路由内补两行：
      1. 在函数体首行 `now = time.time()` 后新增 `force = request.args.get("force") == "1"`
      2. 将缓存判断条件由 `if _GOLD_CACHE["data"] and now - _GOLD_CACHE["ts"] < 300:` 改为 `if not force and _GOLD_CACHE["data"] and now - _GOLD_CACHE["ts"] < 300:`
    - 依赖：Task 15（黄金卡已存在）
    - 关联 Acceptance Criterion: `?force=1` 能跳过缓存返回最新数据；不传 force 时仍按 300s 缓存
    - 测试要求：
      - programmatic: 连续两次 curl `/api/gold?force=1`，第二次返回的 `history_xau` 末尾 close 值与第一次不同（或缓存未过期情况下 msg 字段一致但能证明 force 跳过了缓存判断分支）；py_compile app.py 通过
      - human-judgement: 浏览器或前端调用 /api/gold?force=1 能立即看到最新行情
  - [x] SubTask 18.2: 行业领涨领跌 Top10 卡 .boards-top10 grid 布局修复（style.css）
    - 现状：style.css:425-431 的 `.boards-top10 { display:grid; grid-template-columns: 1fr 1px 1fr; gap:16px; align-items:start; position:relative; }` 配合仅有 2 个正常流子元素 `.boards-col` 时，按 CSS Grid 自动排布规则会把第 2 个 `.boards-col`（领跌栏）放入 1px 中间分隔列，导致右栏被压缩到 1px、右侧大块空白，分隔线位置连带错位（.boards-top10::before 的 left:50% 落不到两等栏正中）
    - 修复（任选其一，推荐方案 1 最简）：
      1. 将 `grid-template-columns` 由 `1fr 1px 1fr` 改为 `1fr 1fr`（分隔线完全交给 `::before`，避免空 1px 列与子元素自动流入）
      2. 或保留 3 列模板，显式定位：`.boards-col:nth-child(1){grid-column:1} .boards-col:nth-child(2){grid-column:3}`
    - 同时保留 `.boards-top10::before` 的 `left:50%; transform:translateX(-50%)` 实现竖分隔线居中
    - 依赖：Task 17.4（行业 Top10 样式已对齐参考图）
    - 关联 Acceptance Criterion: 左右两栏宽度相等（各 1fr）；竖分隔线落于两栏正中；领跌栏不再被压缩为 1px
    - 测试要求：
      - programmatic: 浏览器 DevTools 检查 `.boards-top10` 的 computed grid-template-columns；两个 `.boards-col` 的 offsetWidth 接近相等（差 ≤1px）
      - human-judgement: 肉眼可见左右两栏对称，领跌栏内容完整可见，右侧无大块空白；竖分隔线位于两栏正中

---

# Tasks（Task 19 增量追加：2026-08-26 — 市场情绪页优化，原 optimize-market-sentiment 融入）

## 文档定位
原 `optimize-market-sentiment` spec 已剔除，其全部 4 项需求融入本 spec 作为 Task 19（含 SubTask 19.1~19.4），替换原 SubTask 17.3 的概览页情绪卡修复（17.3 已标替换删除）。

- [x] Task 19: 市场情绪页优化（趋势图缓存 / 维度贡献度 / 等级说明 / 低点次日基准线）
  - [x] SubTask 19.1: 情绪趋势图加载缓存优化
    - 在 `core/emotion_history.py` 增加历史情绪结果本地缓存（按交易日 key 缓存）
    - 在 `app.py` 的 `/api/emotion_trend` 优先读缓存，仅 force=1 时重新计算
    - 验证同一天内切换时间窗口可秒级返回
  - [x] SubTask 19.2: 情绪分维度贡献度可视化
    - 在 `core/sentiment.py` 的 `get_sentiment` 返回值中增加各维度贡献度明细（涨停家数分/连板高度分/晋级率分/炸板率修正/跌停惩罚）
    - 在 `templates/index.html` 情绪页情绪卡片中新增维度贡献度区域
    - 在 `static/app.js` 实现水平条形图渲染各维度贡献度（正贡献蓝色、负贡献红色）
    - 在 `static/style.css` 实现贡献度条形图样式
  - [x] SubTask 19.3: 情绪等级说明卡片
    - 在 `templates/index.html` 情绪页新增情绪等级说明区域
    - 在 `static/app.js` 根据当前情绪等级高亮对应说明并展示操作建议
    - 在 `static/style.css` 实现等级说明卡片样式
  - [x] SubTask 19.4: 情绪低点次日表现图优化
    - 在 `static/app.js` 的 `renderLowNext` 中增加「冰点次日平均涨幅」基准虚线标注
    - 在 tooltip 中增加与平均涨幅的差值提示

# Task Dependencies Updates（Task 19）
- SubTask 19.1、19.2、19.3、19.4 互相独立，可并行

