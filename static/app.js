// ── 工具 ──────────────────────────────
const $ = (s) => document.querySelector(s);
const fmt = (v, d = 2) => (v == null ? "--" : Number(v).toFixed(d));

function colorClass(v) {
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

// ── Tab 切换 ───────────────────────────
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    document.querySelectorAll(".page").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    $("#page-" + t.dataset.page).classList.add("on");
    $("#ov-refresh").style.display = t.dataset.page === "overview" ? "" : "none";
    // 切换到概览页则加载并启动自动刷新；切到其他页则停止自动刷新
    if (t.dataset.page === "overview") {
      loadOverview();
    } else {
      stopOvAutoRefresh();
    }
    if (t.dataset.page === "screener") loadScreener();
    if (t.dataset.page === "rules") loadScreenRules();
  });
});

// ── 交易时段判断 ──────────────────────────
// 返回当前交易状态文字：休市/未开市/集合竞价/持续交易/午间休市/收盘竞价/已收盘
function getTradeSession() {
  const d = new Date();
  const day = d.getDay(); // 0=周日 6=周六
  if (day === 0 || day === 6) return "休市";
  const hm = d.getHours() * 60 + d.getMinutes();
  if (hm < 540) return "未开市";                  // 9:00 前
  if (hm >= 555 && hm < 565) return "集合竞价";    // 9:15-9:25
  if (hm >= 570 && hm < 690) return "持续交易";    // 9:30-11:30
  if (hm >= 690 && hm < 780) return "午间休市";    // 11:30-13:00
  if (hm >= 780 && hm < 897) return "持续交易";    // 13:00-14:57 下午持续交易
  if (hm >= 897 && hm < 900) return "收盘竞价";    // 14:57-15:00
  if (hm >= 900) return "已收盘";                  // 15:00 后
  return "休市";                                   // 其他（9:00-9:15、9:25-9:30）
}

// 是否处于实际交易时段（集合竞价/持续交易/收盘竞价）
function isTradeSession() {
  const s = getTradeSession();
  return s === "集合竞价" || s === "持续交易" || s === "收盘竞价";
}

// Task 12：是否处于黄金交易时段
// 简化判断：非周末（周一至周五）均视为黄金交易时段（伦敦金近 24 小时交易，
// AU99.99 夜盘 20:00-02:30，纽约黄金有夜间盘）；周末返回 false
function isGoldTradeSession() {
  const dow = new Date().getDay();
  return dow !== 0 && dow !== 6;
}

// 根据交易时段更新呼吸灯：交易时段绿色脉冲，非交易时段灰色
function updateLiveIndicator() {
  const ind = $("#live-indicator");
  const txt = $("#live-indicator .live-text");
  if (!ind || !txt) return;
  const session = getTradeSession();
  if (isTradeSession()) ind.classList.add("on");
  else ind.classList.remove("on");
  txt.textContent = session;
}

// Task 15：记录上次刷新时间戳，用于渲染相对时间（xx前刷新）
// 放在 tick() 首次调用之前声明，避免 temporal dead zone
let lastRefreshTs = 0;

// Task 15：渲染相对刷新时间，随 tick() 每秒累加更新
// 规则：未刷新/刚刚刷新/N秒前/N分N秒前/N小时N分N秒前
function renderRefreshAgo() {
  let agoText;
  if (lastRefreshTs === 0) {
    agoText = "未刷新";
  } else {
    const diff = Date.now() - lastRefreshTs;
    if (diff < 5000) {
      agoText = "刚刚刷新";
    } else if (diff < 60000) {
      agoText = `${Math.floor(diff / 1000)}秒前刷新`;
    } else if (diff < 3600000) {
      const m = Math.floor(diff / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      agoText = `${m}分${s}秒前刷新`;
    } else {
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      agoText = `${h}小时${m}分${s}秒前刷新`;
    }
  }
  const el = $("#data-time");
  if (el) el.textContent = agoText;
}

// 刷新成功后更新数据时间：记录刷新时间戳并渲染相对时间
function updateDataTime() {
  lastRefreshTs = Date.now();
  renderRefreshAgo();
}

// ── 时钟 ──────────────────────────────
function tick() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  $("#clock").textContent = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  updateLiveIndicator();
  renderRefreshAgo();  // Task 15：相对刷新时间随时钟每秒更新
}
setInterval(tick, 1000); tick();

// ═══ 市场概览（首页） ═══════════════════
async function loadOverview(force, skipSide = false) {
  try {
    const o = await fetch("/api/overview" + (force ? "?force=1" : "")).then((x) => x.json());
    renderIndexStrip(o);
    // 修复 #4：提前渲染行业 Top10，避免后续 sentiment 异常导致其被跳过
    renderBoardsTop10(o.boards || { industry: [], concept: [] }); // Task 14：行业领涨领跌 Top10
    // SubTask 12.3：5 张旧表格卡（炸板/跌停/板块/涨停梯队/热门概念）已从 overview-grid 移除，
    // 故注释以下 3 行调用；保留函数定义，供其他 Tab 或未来恢复使用。
    // renderZt(o.zt_pool || [], o.ladder || []);
    // renderZbDt(o.zb_pool || [], o.dt_pool || []);
    // renderBoards(o.boards || { industry: [], concept: [] });
    // 修改2：sent-card 已从概览页移除，renderOverviewSentiment 调用已删除（函数定义保留）
  } catch (e) {
    console.error("概览加载失败", e);
  }
  // Task 8 修复 A：updateDataTime 移至 try/catch 之外，保证 #data-time 始终更新，
  // 避免 renderOverviewSentiment 抛异常时 catch 捕获后 #data-time 停留 DATA: --
  // Task 14 修复 B：startOvAutoRefresh 同样移出 try 块，保证 fetch 失败或渲染异常时定时器仍启动
  updateDataTime();
  startOvAutoRefresh();  // 启动交易时段指数自动刷新
  if (!skipSide) {
    loadIndexKline();
    loadLiangneng();
    loadDistribution();     // 涨跌统计柱状图
    loadWatch();            // 自选标的实时行情（迁移自原自选看板页）
    loadGold();             // Task 15：综合黄金行情首次加载
    loadIndexCompare();     // Task 16：指数走势对比曲线
    loadSentiment();     // 情绪专区随概览页加载（原情绪tab融入）
    loadLowNext();       // 情绪低点次日表现随概览页加载
  }
}

function renderIndexStrip(o) {
  $("#ov-indexes").innerHTML = o.index_order.map((c) => {
    const q = o.indexes[c];
    if (!q) return "";
    const cls = q.change_pct > 0 ? "upx" : q.change_pct < 0 ? "downx" : "";
    return `<div class="idx-card ${cls}">
      <div class="nm">${q.name}</div>
      <div class="px mono ${colorClass(q.change_pct)}">${fmt(q.price)}</div>
      <div class="chg ${colorClass(q.change_pct)}">${q.change_pct > 0 ? "+" : ""}${fmt(q.change_pct)}%</div>
    </div>`;
  }).join("");
}

function renderOverviewSentiment(s, date) {
  $("#ov-date").textContent = date || "";
  const score = s.score == null ? null : s.score;
  const sc = $("#ov-score");
  sc.textContent = score == null ? "--" : score;
  sc.style.color = score <= 45 ? "var(--green)" : score >= 80 ? "var(--red)" : "var(--cyan)";
  $("#ov-level").textContent = "情绪：" + (s.level || "--");

  // 仪表盘：按分数填充宽度，随等级变色
  const g = $("#ov-gauge");
  if (score == null) { g.style.width = "0%"; g.style.background = "#1c2942"; }
  else {
    g.style.width = Math.max(2, Math.min(100, score)) + "%";
    g.style.background = score <= 45 ? "var(--green)" : score >= 80 ? "var(--red)" : score <= 65 ? "var(--cyan)" : "var(--amber)";
  }

  const stats = [
    ["涨停家数", s.zt_count == null ? "--" : s.zt_count],
    ["跌停家数", s.dt_count == null ? "--" : s.dt_count],
    ["炸板家数", s.zb_count == null ? "--" : s.zb_count],
    ["炸板率", s.break_rate == null ? "--" : s.break_rate + "%"],
    ["晋级率", s.promo_rate == null ? "--" : s.promo_rate + "%"],
    ["最高连板", s.max_height == null ? "--" : s.max_height + "板"],
  ];
  $("#ov-dims").innerHTML = stats.map(([l, v]) =>
    `<div class="ss"><span class="ss-lbl">${l}</span><span class="ss-val mono">${v}</span></div>`).join("");

  const tips = {
    "冰点": "情绪冰点，恐慌集中释放，次日往往现反弹，可留意低吸机会",
    "偏冷": "情绪偏冷，赚钱效应弱，宜防守观望、控仓等待",
    "正常": "情绪中性，结构性行情，跟随主线题材",
    "偏热": "情绪偏热，赚钱效应强，注意高位接力风险",
    "过热": "情绪过热，连板高位拥挤，警惕退潮回落",
  };
  const t = $("#ov-tip");
  t.textContent = tips[s.level] || "情绪数据暂无";
  t.className = "tip " + (s.level === "冰点" || s.level === "偏冷" ? "cold" : s.level === "过热" || s.level === "偏热" ? "hot" : "neutral");

  // 情绪卡片信息补充：迷你走势图 + 较昨日变化方向 + 6因子徽章
  renderSentimentMini(s);
  // SubTask 17.3：sent-card 去重复，隐藏右列后停用以下渲染（函数定义保留）
  // renderSentimentChange(s);
  // if (s) renderSentimentFactors(s);
}

// ── 情绪迷你走势图：已升级为大尺寸15日XY渐变图，带坐标轴和冷暖渐变背景 ──
// 函数名保持不变（最小化 renderOverviewSentiment 适配），内部改渲染到 #ov-sent-big，找不到回退 #ov-sent-mini
let ovSentMiniChart = null;
let _sentMiniRetry = 0;    // 0 尺寸重试计数器（每次调用 renderSentimentMini 入口重置）
let sentLatest = null;     // Task 17：情绪数据全局缓存，供 Tab 切换 Fallback 重建 / resize 用
// ── 情绪迷你走势图：已升级为大尺寸15日XY渐变图 + 多层兜底永不空白 ──
// 六层兜底：入口重置计数器 → scores 二次清洗 → rAF 6 次 + ResizeObserver 强制尺寸 →
//           echarts try/catch → 6 次失败走 SVG polyline Fallback → Tab 切换重建
function renderSentimentMini(s) {
  // --- Task 17 加固层 1：每次调用先重置计数器，防止跨次调用累积
  _sentMiniRetry = 0;
  // --- Task 17 加固层 1.5：缓存最新数据，供 Tab 切换 / Fallback 重建复用
  if (s) sentLatest = s;

  const useScores = s ? (s.history_scores || []) : sentLatest ? (sentLatest.history_scores || []) : [];
  const useLabels = s ? (s.history_labels || []) : sentLatest ? (sentLatest.history_labels || []) : [];
  // --- Task 17 加固层 2：scores 二次清洗 Number（兜底 50），杜绝字符串/NaN/超范围
  let scores = useScores.map((v) => {
    const n = Number(v);
    return Number.isFinite(n) && n >= 0 && n <= 100 ? n : 50;
  });
  let labels = useLabels.slice(0, scores.length);
  // 兜底：极端场景 scores 空，给两个 50 让 Fallback 至少能画一条线
  if (scores.length === 0) { scores = [50, 50]; labels = ["--", "--"]; }

  // 优先用新容器 #ov-sent-big，找不到回退旧 #ov-sent-mini
  const box = document.getElementById("ov-sent-big") || document.getElementById("ov-sent-mini");
  if (!box) return;

  // --- Task 17 加固层 0：每次调用先清除旧 Fallback DOM，然后再走 ECharts 流程
  const oldFb = box.querySelector(":scope > .sent-fallback");
  if (oldFb) { try { oldFb.remove(); } catch (_) {} }

  if (!scores.length) {
    // 无历史数据时空态提示
    if (ovSentMiniChart) { try { ovSentMiniChart.dispose(); } catch (_) {} ovSentMiniChart = null; }
    box.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#5a6a8a;font-size:12px">暂无历史情绪数据</div>';
    return;
  }

  // 兜底显式宽度，避免父级 flex 未布局时宽度为 0
  if (!box.style.width) box.style.width = "100%";

  // --- Task 17 加固层 3：rAF 重试上限从 3 提至 6；关键次数强制 getBoundingClientRect + 一次性 ResizeObserver
  if (box.offsetWidth === 0 || box.offsetHeight === 0) {
    if (_sentMiniRetry < 6) {
      _sentMiniRetry++;
      // 第 1/3/6 次：强制 getBoundingClientRect 触发重排；如浏览器支持，附加一次性 ResizeObserver
      if (_sentMiniRetry === 1 || _sentMiniRetry === 3 || _sentMiniRetry === 6) {
        try { void box.getBoundingClientRect(); } catch (_) {}
        if ("ResizeObserver" in window) {
          try {
            const ro = new ResizeObserver(() => {
              try { ro.disconnect(); } catch (_) {}
              // 尺寸就绪后，立即重新用缓存数据渲染（非 rAF 递归）
              if (sentLatest) renderSentimentMini(sentLatest);
            });
            ro.observe(box);
          } catch (_) {}
        }
      }
      requestAnimationFrame(() => renderSentimentMini(null));
    } else {
      // --- Task 17 加固层 4：6 次后仍 0 尺寸 → 立刻走 SVG Fallback，绝不空白
      _sentMiniRetry = 0;
      renderSentFallback(box, scores, labels);
    }
    return;
  }
  _sentMiniRetry = 0;

  // 任何非 early return 的场景：先 dispose 旧实例再清空 box
  if (ovSentMiniChart) { try { ovSentMiniChart.dispose(); } catch (_) {} ovSentMiniChart = null; }
  box.innerHTML = "";
  // Y轴 6 个刻度的 value→文案 映射
  const yLabelMap = { 0: "冰点", 20: "过冷", 40: "微冷", 60: "微热", 80: "过热", 100: "沸点" };

  const smallData = scores.length < 3;
  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        const p = ps && ps[0];
        if (!p || p.value == null) return "";
        return `<b>${labels[p.dataIndex] || ""}</b><br>${p.marker}情绪分：${p.value}`;
      },
    },
    grid: { left: 60, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: "category",
      data: labels,
      show: true,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#2a3550" } },
      axisLabel: { color: "#8a96b5", fontSize: 11, rotate: 30, interval: 0 },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      min: 0, max: 100, interval: 20,
      axisLabel: { color: "#8a96b5", fontSize: 11, formatter: (val) => yLabelMap[val] || val },
      splitLine: { lineStyle: { color: "#16203a" } },
      splitArea: {
        show: !smallData,
        areaStyle: [
          { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(0,229,255,0)" },
            { offset: 1, color: "rgba(0,152,255,.18)" },
          ]) },
          { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(0,229,255,0)" },
            { offset: 1, color: "rgba(0,152,255,.10)" },
          ]) },
          { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(0,229,255,.03)" },
            { offset: 1, color: "rgba(255,140,0,.03)" },
          ]) },
          { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(255,80,80,.10)" },
            { offset: 1, color: "rgba(255,140,0,0)" },
          ]) },
          { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(255,80,80,.18)" },
            { offset: 1, color: "rgba(255,140,0,0)" },
          ]) },
        ],
      },
    },
    series: [{
      type: "line", data: scores, smooth: true, symbol: "circle", symbolSize: 6,
      lineStyle: { width: 2.5, color: "#4d7cff" },
      itemStyle: { color: "#4d7cff", borderColor: "#0d1526", borderWidth: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(77,124,255,.30)" },
          { offset: 1, color: "rgba(77,124,255,0)" },
        ]),
      },
    }],
  };
  // --- Task 17 加固层 5：echarts 操作 try/catch，失败立刻走 SVG Fallback，绝不空白
  try {
    ovSentMiniChart = echarts.init(box);
    ovSentMiniChart.setOption(option, true);
    ovSentMiniChart.resize();
  } catch (e) {
    console.warn("情绪走势图 ECharts 失败，进入 SVG Fallback", e);
    if (ovSentMiniChart) { try { ovSentMiniChart.dispose(); } catch (_) {} ovSentMiniChart = null; }
    try { box.innerHTML = ""; } catch (_) {}
    renderSentFallback(box, scores, labels);
  }
}

// ── Task 17 加固层 4/5：原生 SVG Fallback（ECharts 多次失败或 0 尺寸兜底，永不空白）────
// 视觉尽量接近 ECharts：5 段冷暖渐变背景 + Y 6 刻度 + X 日期标签 + polyline 折线 + circle 圆点
function renderSentFallback(box, scores, labels) {
  const yLabelMap = { 0: "冰点", 20: "过冷", 40: "微冷", 60: "微热", 80: "过热", 100: "沸点" };
  const n = scores.length;
  if (!n) return;

  // Fallback 容器：高 280px，宽度 100%，相对定位（刻度用绝对定位）
  const fb = document.createElement("div");
  fb.className = "sent-fallback";
  fb.style.cssText = "position:relative;width:100%;height:280px;padding:10px 8px 40px 56px;box-sizing:border-box;";

  // 5 段冷暖渐变背景（对应 splitArea 的 5 个区域）
  const bands = [
    "linear-gradient(180deg, rgba(0,229,255,0) 0%, rgba(0,152,255,.18) 100%)", // 0-20
    "linear-gradient(180deg, rgba(0,229,255,0) 0%, rgba(0,152,255,.10) 100%)", // 20-40
    "linear-gradient(180deg, rgba(0,229,255,.03) 0%, rgba(255,140,0,.03) 100%)", // 40-60
    "linear-gradient(180deg, rgba(255,80,80,.10) 0%, rgba(255,140,0,0) 100%)", // 60-80
    "linear-gradient(180deg, rgba(255,80,80,.18) 0%, rgba(255,140,0,0) 100%)", // 80-100
  ];
  const bandsWrap = document.createElement("div");
  bandsWrap.style.cssText = "position:absolute;top:10px;left:56px;right:8px;bottom:40px;display:flex;flex-direction:column;";
  bands.forEach((bg) => {
    const b = document.createElement("div");
    b.style.cssText = `flex:1;background:${bg};border-bottom:1px solid #16203a;`;
    bandsWrap.appendChild(b);
  });
  fb.appendChild(bandsWrap);

  // Y 轴刻度（6 个，左侧负偏移）
  Object.keys(yLabelMap).forEach((yk) => {
    const yv = Number(yk);
    const row = document.createElement("div");
    // 100 - yv 从 top 起，top=10px 处对应 100（沸点），bottom=40px 对应 0（冰点）
    const topPercent = (100 - yv) / 100;
    const plotTop = 10;
    const plotBottom = 40;
    const fbHeight = 280;
    const plotH = fbHeight - plotTop - plotBottom;
    row.style.cssText = `position:absolute;left:0;width:48px;top:${plotTop + plotH * topPercent}px;transform:translateY(-50%);text-align:right;padding-right:8px;color:#8a96b5;font-size:11px;line-height:1;`;
    row.textContent = yLabelMap[yk];
    fb.appendChild(row);
  });

  // X 轴日期标签（底部 rotate 30°）
  const plotLeftPad = 56, plotRightPad = 8, plotBottomPad = 40;
  labels.forEach((lb, i) => {
    const tag = document.createElement("div");
    const ratio = n === 1 ? 0 : i / (n - 1);
    const leftPx = plotLeftPad + ratio * (fb.clientWidth ? fb.clientWidth - plotLeftPad - plotRightPad : 300);
    tag.style.cssText = `position:absolute;bottom:18px;transform:translateX(-50%) rotate(-30deg);transform-origin:center top;color:#8a96b5;font-size:11px;white-space:nowrap;`;
    // 用 CSS left 百分比更可靠（fb.clientWidth 在未插入 DOM 前为 0）
    tag.style.left = `calc(${plotLeftPad}px + ${ratio * 100}% * (100% - ${plotLeftPad + plotRightPad}px) / 100%)`;
    tag.textContent = lb;
    fb.appendChild(tag);
  });

  // SVG polyline 折线 + circle 圆点
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  // svg 区域 = 绘图区（不含刻度 padding），用 left/top 绝对定位
  svg.setAttribute("style", `position:absolute;left:${plotLeftPad}px;top:10px;right:${plotRightPad}px;bottom:${plotBottomPad}px;width:calc(100% - ${plotLeftPad + plotRightPad}px);height:${280 - 10 - plotBottomPad}px;`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("viewBox", "0 0 1000 230"); // 用 viewBox 归一化坐标

  const plotW = 1000, plotH = 230;
  const pts = scores.map((sc, i) => {
    const x = n === 1 ? plotW / 2 : (i / (n - 1)) * plotW;
    const y = (1 - sc / 100) * plotH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  // 折线下面积渐变填充（对应 ECharts 的 areaStyle）
  const defs = document.createElementNS(svgNS, "defs");
  const g = document.createElementNS(svgNS, "linearGradient");
  g.setAttribute("id", "sentAreaFb");
  g.setAttribute("x1", "0"); g.setAttribute("y1", "0"); g.setAttribute("x2", "0"); g.setAttribute("y2", "1");
  const s1 = document.createElementNS(svgNS, "stop");
  s1.setAttribute("offset", "0%"); s1.setAttribute("stop-color", "rgba(77,124,255,.30)");
  const s2 = document.createElementNS(svgNS, "stop");
  s2.setAttribute("offset", "100%"); s2.setAttribute("stop-color", "rgba(77,124,255,0)");
  g.appendChild(s1); g.appendChild(s2); defs.appendChild(g); svg.appendChild(defs);

  // 填充 polygon（折线 -> 底部 -> 起点）
  const areaPts = pts.slice().concat([`${(n === 1 ? plotW / 2 : plotW).toFixed(1)},${plotH}`, `0,${plotH}`]);
  const area = document.createElementNS(svgNS, "polygon");
  area.setAttribute("points", areaPts.join(" "));
  area.setAttribute("fill", "url(#sentAreaFb)");
  svg.appendChild(area);

  // 折线
  const poly = document.createElementNS(svgNS, "polyline");
  poly.setAttribute("points", pts.join(" "));
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "#4d7cff");
  poly.setAttribute("stroke-width", "2.5");
  svg.appendChild(poly);

  // 圆点
  scores.forEach((sc, i) => {
    const x = n === 1 ? plotW / 2 : (i / (n - 1)) * plotW;
    const y = (1 - sc / 100) * plotH;
    const c = document.createElementNS(svgNS, "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", "4");
    c.setAttribute("fill", "#4d7cff");
    c.setAttribute("stroke", "#0d1526");
    c.setAttribute("stroke-width", "1.5");
    svg.appendChild(c);
  });

  fb.appendChild(svg);
  box.appendChild(fb);
}

// ── 情绪变化方向：较昨日 ↑/↓/→ + 变化数值，红升绿降 ──
function renderSentimentChange(s) {
  const el = $("#ov-sent-change");
  if (!el) return;
  const cur = s.score;
  const prev = s.prev_score;
  if (cur == null || prev == null) {
    el.innerHTML = '<span class="sent-change-label">较昨日</span><span class="sent-change-val flat">--</span>';
    return;
  }
  const diff = cur - prev;
  let arrow, cls;
  if (diff > 0) { arrow = "↑"; cls = "up"; }        // 上升：红色
  else if (diff < 0) { arrow = "↓"; cls = "down"; } // 下降：绿色
  else { arrow = "→"; cls = "flat"; }               // 持平：灰色
  const sign = diff > 0 ? "+" : "";
  el.innerHTML = `<span class="sent-change-label">较昨日</span>` +
    `<span class="sent-change-val ${cls}">${arrow} ${sign}${diff}</span>`;
}

// ── 6 因子徽章：涨停/跌停/炸板/炸板率/晋级率/最高连板，2×3 网格渲染 ──
function renderSentimentFactors(s) {
  const box = $("#ov-sent-factors");
  if (!box) return;
  if (!s) { box.innerHTML = ""; return; }

  // 辅助函数：根据阈值返回颜色
  // 涨停 zt_count：≥150 红；≥80 橙；<50 绿；中间区间(50~79)默认灰色
  const ztColor = (v) => v >= 150 ? "#ff4d5f" : v >= 80 ? "#ffb454" : v < 50 ? "#00d68f" : "#8a96b5";
  // 跌停 dt_count：>30 红；>10 橙；≤10 绿
  const dtColor = (v) => v > 30 ? "#ff4d5f" : v > 10 ? "#ffb454" : "#00d68f";
  // 炸板 zb_count：中性灰
  const zbColor = () => "#8a96b5";
  // 炸板率 break_rate：>40 红；>30 橙；≤30 绿
  const brColor = (v) => v > 40 ? "#ff4d5f" : v > 30 ? "#ffb454" : "#00d68f";
  // 晋级率 promo_rate：≥16 红；≥13 橙；<8 绿；中间区间(8~12)默认灰色
  const prColor = (v) => v >= 16 ? "#ff4d5f" : v >= 13 ? "#ffb454" : v < 8 ? "#00d68f" : "#8a96b5";
  // 最高连板 max_height：≥5 红；≥3 橙；<3 灰
  const mhColor = (v) => v >= 5 ? "#ff4d5f" : v >= 3 ? "#ffb454" : "#8a96b5";

  // 因子配置：字段名、标签、单位、颜色函数
  const factors = [
    { key: "zt_count",    label: "涨停家数", unit: "家",   colorFn: ztColor },
    { key: "dt_count",    label: "跌停家数", unit: "只",   colorFn: dtColor },
    { key: "zb_count",    label: "炸板家数", unit: "只",   colorFn: zbColor },
    { key: "break_rate",  label: "炸板率",   unit: "%",    colorFn: brColor },
    { key: "promo_rate",  label: "晋级率",   unit: "%",    colorFn: prColor },
    { key: "max_height",  label: "最高连板", unit: "连板", colorFn: mhColor },
  ];

  // 渲染每个因子徽章
  box.innerHTML = factors.map((f) => {
    const v = s[f.key];
    const isNull = v == null;
    const displayVal = isNull ? "--" : v;
    const color = isNull ? "#8a96b5" : f.colorFn(Number(v));
    const unitHtml = isNull ? "" : `<small> ${f.unit}</small>`;
    return `<div class="factor-badge">
      <span class="fb-label">${f.label}</span>
      <span class="fb-val mono" style="color:${color}">${displayVal}${unitHtml}</span>
    </div>`;
  }).join("");
}

function renderZt(zt, ladder) {
  $("#ov-ladder").textContent = ladder.map((l) => `${l.days}板×${l.count}`).join("  ") || "";
  const sorted = [...zt].sort((a, b) => b.limit_days - a.limit_days).slice(0, 10);
  const rows = sorted.map((s) => `<tr>
      <td>${s.name}</td>
      <td><span class="badge ${s.limit_days >= 2 ? "on" : "off"}">${s.limit_days}板</span></td>
      <td class="num mono ${colorClass(s.pct)}">+${fmt(s.pct)}%</td>
      <td class="num mono">${fmt(s.seal_fund_yi)}</td>
      <td class="num mono">${s.first_seal}</td>
      <td>${s.industry}</td></tr>`).join("");
  const empty = `<tr><td colspan="6" style="text-align:center;color:#5a6a8a">今日无涨停</td></tr>`;
  $("#ov-zt").innerHTML = `<thead><tr><th>名称</th><th>连板</th><th class="num">涨幅</th><th class="num">封单(亿)</th><th class="num">首封</th><th>行业</th></tr></thead><tbody>${rows || empty}</tbody>`;
}

function renderZbDt(zb, dt) {
  $("#ov-zb-count").textContent = zb.length + " 只";
  $("#ov-dt-count").textContent = dt.length + " 只";
  const zbRows = zb.slice(0, 10).map((s) => `<tr>
      <td>${s.name}</td>
      <td class="num mono ${colorClass(s.pct)}">${s.pct > 0 ? "+" : ""}${fmt(s.pct)}%</td>
      <td class="num mono">${fmt(s.amplitude)}%</td>
      <td>${s.industry}</td></tr>`).join("");
  const zbEmpty = `<tr><td colspan="4" style="text-align:center;color:#5a6a8a">今日无炸板</td></tr>`;
  $("#ov-zb").innerHTML = `<thead><tr><th>名称</th><th class="num">涨幅</th><th class="num">振幅</th><th>行业</th></tr></thead><tbody>${zbRows || zbEmpty}</tbody>`;

  const dtRows = dt.slice(0, 10).map((s) => `<tr>
      <td>${s.name}</td>
      <td class="num mono down">${fmt(s.pct)}%</td>
      <td class="num mono">${s.dt_days}天</td>
      <td>${s.industry}</td></tr>`).join("");
  const dtEmpty = `<tr><td colspan="4" style="text-align:center;color:#5a6a8a">今日无跌停</td></tr>`;
  $("#ov-dt").innerHTML = `<thead><tr><th>名称</th><th class="num">跌幅</th><th class="num">连续</th><th>行业</th></tr></thead><tbody>${dtRows || dtEmpty}</tbody>`;
}

function renderBoards(b) {
  const mk = (list) => list.slice(0, 10).map((x, i) => `<tr>
      <td class="num mono">${i + 1}</td>
      <td>${x.name}</td>
      <td class="num mono ${colorClass(x.avg_pct)}">${x.avg_pct > 0 ? "+" : ""}${fmt(x.avg_pct)}%</td>
      <td>${x.leader_name}</td>
      <td class="num mono">${fmt(x.amount_yi)}</td></tr>`).join("");
  const hdr = `<thead><tr><th>#</th><th>板块</th><th class="num">涨幅</th><th>领涨股</th><th class="num">成交额(亿)</th></tr></thead>`;
  $("#ov-boards").innerHTML = hdr + `<tbody>${mk(b.industry || [])}</tbody>`;
  $("#ov-concept").innerHTML = hdr + `<tbody>${mk(b.concept || [])}</tbody>`;
}

// Task 14：行业领涨领跌 Top10 横条进度条卡渲染
function renderBoardsTop10(boards) {
  const upBox = document.getElementById("boards-up");
  const downBox = document.getElementById("boards-down");
  if (!upBox || !downBox) return;

  // 仅使用行业板块数据
  const industry = boards.industry || [];

  // 空态处理：无行业数据时两侧均显示占位
  if (!industry.length) {
    upBox.innerHTML = '<div class="boards-empty">暂无行业板块数据</div>';
    downBox.innerHTML = '<div class="boards-empty">暂无行业板块数据</div>';
    return;
  }

  // 领涨 Top10：按 avg_pct 降序取前 10（原数据已降序）
  const boards_up = industry.slice(0, 10);
  // 领跌 Top10：复制数组后按 avg_pct 升序取前 10（avg_pct 越小跌幅越大）
  const boards_down = [...industry].sort((a, b) => a.avg_pct - b.avg_pct).slice(0, 10);

  // 统一归一化基准：取领涨最大涨幅、领跌最大跌幅的绝对值中的较大者，
  // 并设置 0.01 的下限，避免全为 0 时除以 0
  const maxAbs = Math.max(
    boards_up[0]?.avg_pct ?? 0,
    -(boards_down[0]?.avg_pct ?? 0),
    0.01
  );

  // 渲染左侧领涨栏：顺序排列，红条右向，DOM 顺序：rank → name → pct.up → bar-track
  upBox.innerHTML = boards_up.map((x, i) => {
    const name = x.name || "";
    const avg_pct = x.avg_pct ?? 0;
    // 归一化宽度，并限制在 0~100% 之间
    const width = Math.min(100, Math.max(0, avg_pct / maxAbs * 100));
    return `<div class="boards-bar-row up">
      <span class="rank" data-rank="${i + 1}">${i + 1}</span>
      <span class="name">${name}</span>
      <span class="pct up">+${fmt(avg_pct)}%</span>
      <div class="bar-track"><div class="bar up" style="width:${width}%"></div></div>
    </div>`;
  }).join("");

  // 渲染右侧领跌栏：顺序排列（跌幅最大排第1），绿条左向，DOM 顺序：bar-track → pct.down → name → rank
  downBox.innerHTML = boards_down.map((x, i) => {
    const name = x.name || "";
    const avg_pct = x.avg_pct ?? 0;
    // 归一化宽度（使用跌幅绝对值），并限制在 0~100% 之间
    const width = Math.min(100, Math.max(0, -avg_pct / maxAbs * 100));
    return `<div class="boards-bar-row down">
      <div class="bar-track"><div class="bar down" style="width:${width}%"></div></div>
      <span class="pct down">${fmt(avg_pct)}%</span>
      <span class="name">${name}</span>
      <span class="rank" data-rank="${i + 1}">${i + 1}</span>
    </div>`;
  }).join("");
}

$("#ov-refresh").addEventListener("click", () => loadOverview(true));

// ── 概览指数自动刷新 ──────────────────────
let ovRefreshTimer = null;

// 全卡自动刷新：双档定时器
let ovFastTimer = null;
let ovSlowTimer = null;
let ovSlowCounter = 0;
let ovCurrentCompareDays = 60;

// 轻量刷新指数行情条：仅拉取 /api/overview 缓存数据并更新 #ov-indexes
async function refreshIndexStrip() {
  // 非交易时段不刷新，避免无谓请求
  if (!isTradeSession()) return;
  try {
    const o = await fetch("/api/overview").then((r) => r.json());
    renderIndexStrip(o);
    updateDataTime();
  } catch (e) {
    console.error("指数行情条刷新失败", e);
  }
}

// 启动概览自动刷新：双档定时 + 分档刷新 + 非交易降频
function startOvAutoRefresh() {
  stopOvAutoRefresh();
  ovSlowCounter = 0;
  if (isTradeSession()) {
    // 交易时段：fast=60s 调 doFastRefresh（不调 loadGold，避免超 60s 上限），slow=300s 调 doSlowRefresh
    ovFastTimer = setInterval(doFastRefresh, 60000);
    ovSlowTimer = setInterval(doSlowRefresh, 300000);
  } else if (isGoldTradeSession()) {
    // Task 8/12：非 A 股交易时段但黄金在交易，fast=120s 让黄金按交易时间刷新，slow=600s
    ovFastTimer = setInterval(doNonTradeFastRefresh, 120000);
    ovSlowTimer = setInterval(doSlowRefresh, 600000);
  } else {
    // 周末：黄金也休市，仅 slow=600s
    ovSlowTimer = setInterval(doSlowRefresh, 600000);
  }
  // Task 17：概览 Tab 重新显示后，50ms 让 flex 布局到位，再 resize 情绪图；
  // 如果当前是 Fallback SVG 兜底（没有 canvas + 有 .sent-fallback），且 sentLatest 有缓存，
  // 则立刻用 sentLatest 再渲染一次，让 ECharts 有第二次机会。
  setTimeout(() => {
    if (ovSentMiniChart) {
      try { ovSentMiniChart.resize(); } catch (_) {}
    }
    if (sentLatest) {
      const box = document.getElementById("ov-sent-big") || document.getElementById("ov-sent-mini");
      if (box) {
        const fb = box.querySelector(":scope > .sent-fallback");
        if (fb && !box.querySelector(":scope canvas")) {
          renderSentimentMini(sentLatest);
        }
      }
    }
  }, 50);
}

// 停止概览自动刷新（切换到其他页面时调用）
function stopOvAutoRefresh() {
  if (ovFastTimer) { clearInterval(ovFastTimer); ovFastTimer = null; }
  if (ovSlowTimer) { clearInterval(ovSlowTimer); ovSlowTimer = null; }
  if (typeof ovRefreshTimer !== 'undefined' && ovRefreshTimer) { clearInterval(ovRefreshTimer); ovRefreshTimer = null; }
}

function doFastRefresh() {
  loadOverview(false, true);
  loadLiangneng();
  loadDistribution();
  loadWatch();
}

// Task 12：非交易时段轻量刷新——只调 loadGold(false) 让黄金每 120s 刷新一次
function doNonTradeFastRefresh() {
  loadGold(false);
}

function doSlowRefresh() {
  ovSlowCounter += 1;
  loadGold(false);
  if (ovSlowCounter % 2 === 0) {
    loadIndexCompare(ovCurrentCompareDays);
  }
  if (ovSlowCounter % 2 === 0) {
    loadIndexKline();
  }
}

// ═══ 指数走势对比 ══════════════════════
let indexCompareChart = null;
function loadIndexCompare(days=60) {
  ovCurrentCompareDays = days;
  fetch("/api/index_compare?days="+days)
    .then(r=>r.json())
    .then(d=>{ renderIndexCompare(d, days); })
    .catch(e=>console.error("指数对比加载失败",e));
}
function renderIndexCompare(d, days) {
  const hintEl = document.getElementById("index-compare-hint");
  if (hintEl && days) hintEl.textContent = `近${days}日 归一化累计涨幅（起始日=100）`;
  const box = document.getElementById("index-compare-chart");
  if (!box) return;
  const dates = d.dates||[]; const series = d.series||[];
  if (!dates.length || !series.length) {
    box.innerHTML = `<div class="boards-empty" style="height:360px">暂无指数对比数据</div>`;
    if (indexCompareChart){indexCompareChart.dispose();indexCompareChart=null;} return;
  }
  const colors = ["#4d7cff","#ff4d5f","#00d68f","#ffb454"];
  if (!indexCompareChart) indexCompareChart = echarts.init(box);
  indexCompareChart.setOption({
    backgroundColor:"transparent",
    legend:{ data: series.map(x=>x.name), textStyle:{color:"#c6d2ef",fontSize:12}, top:0 },
    tooltip:{ trigger:"axis", backgroundColor:"#0d1226", borderColor:"#1c2540",
              textStyle:{color:"#c6d2ef",fontSize:12}},
    grid:{ left:50, right:20, top:40, bottom:60 },
    xAxis:{ type:"category", data: dates, boundaryGap:false,
            axisLabel:{color:"#8a96b5",fontSize:11, rotate:45,
                       formatter:(v)=> v.length===8 ? `${v.slice(4,6)}-${v.slice(6)}` : v },
            axisLine:{lineStyle:{color:"#2a3656"}} },
    yAxis:{ type:"value", scale:true,
            axisLabel:{color:"#8a96b5",fontSize:11, formatter:v=>v.toFixed(1)},
            splitLine:{lineStyle:{color:"#1c2540"}} },
    series: series.map((s,i)=>({
      name:s.name, type:"line", data:s.values, smooth:true,
      symbol:"circle", symbolSize:5, showSymbol:false,
      lineStyle:{ width:2, color: colors[i%colors.length] },
      itemStyle:{ color: colors[i%colors.length], borderColor:"#0d1526", borderWidth:1.5 },
    }))
  }, true);
  indexCompareChart.resize();
}

// ═══ 指数K线 ══════════════════════════
let ikChart = null;
let ikCode = "sh000001";
let ikDays = 120;

async function loadIndexKline() {
  try {
    const d = await fetch(`/api/index_kline?code=${ikCode}&days=${ikDays}`).then((x) => x.json());
    if (d.error) return;
    $("#ik-name").textContent = `${d.name} · ${d.dates[0]} ~ ${d.dates[d.dates.length - 1]}`;
    renderIndexKline(d);
  } catch (e) {
    console.error("指数K线加载失败", e);
  }
}

function renderIndexKline(d) {
  const labels = d.dates.map((x) => x.slice(5)); // MM-DD
  const volFmt = (v) => (v >= 1e8 ? (v / 1e8).toFixed(2) + "亿" : v >= 1e4 ? (v / 1e4).toFixed(1) + "万" : v);
  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", axisPointer: { type: "cross" }, backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        if (!ps.length) return "";
        const i = ps[0].dataIndex;
        const k = d.kline[i];
        let s = `<b>${d.dates[i]}</b><br>开 ${k[0]}　收 ${k[1]}<br>低 ${k[2]}　高 ${k[3]}<br>`;
        ps.forEach((p) => {
          if (p.seriesName === "成交量") { if (p.value != null) s += `${p.marker}成交量：${volFmt(p.value)}<br>`; }
          else if (p.seriesName.startsWith("MA") && p.value != null) s += `${p.marker}${p.seriesName}：${p.value}<br>`;
        });
        return s;
      },
    },
    legend: { data: ["MA5", "MA10", "MA20", "MA60", "MA120"], textStyle: { color: "#8ba0c9" }, top: 0 },
    grid: [
      { left: 52, right: 20, top: 30, height: "58%" },
      { left: 52, right: 20, top: "74%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: labels, gridIndex: 0, boundaryGap: true, axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9" } },
      { type: "category", data: labels, gridIndex: 1, boundaryGap: true, axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9" } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, splitLine: { lineStyle: { color: "#16203a" } }, axisLabel: { color: "#8ba0c9" } },
      { type: "value", gridIndex: 1, splitNumber: 2, axisLabel: { color: "#8ba0c9", formatter: volFmt }, splitLine: { show: false } },
    ],
    series: [
      { name: "K线", type: "candlestick", data: d.kline,
        itemStyle: { color: "#ff4d5f", color0: "#00d68f", borderColor: "#ff4d5f", borderColor0: "#00d68f" } },
      { name: "MA5", type: "line", data: d.ma5, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#ffd166" } },
      { name: "MA10", type: "line", data: d.ma10, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#00e5ff" } },
      { name: "MA20", type: "line", data: d.ma20, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#7c5cff" } },
      { name: "MA60", type: "line", data: d.ma60, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#ff6b6b" } },
      { name: "MA120", type: "line", data: d.ma120, smooth: true, showSymbol: false, lineStyle: { width: 1 }, itemStyle: { color: "#4ecdc4" } },
      { name: "成交量", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: d.volume, barMaxWidth: 12,
        itemStyle: { color: (p) => (d.kline[p.dataIndex][1] >= d.kline[p.dataIndex][0] ? "rgba(255,77,95,.55)" : "rgba(0,214,143,.55)") } },
    ],
  };
  if (!ikChart) ikChart = echarts.init(document.getElementById("index-kline-chart"));
  ikChart.setOption(option, true);
  ikChart.resize();
}
$("#ik-code").addEventListener("change", () => { ikCode = $("#ik-code").value; loadIndexKline(); });
document.querySelectorAll("#ik-range .seg-btn").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#ik-range .seg-btn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    ikDays = Number(b.dataset.days);
    loadIndexKline();
  });
});
document.querySelectorAll("#index-compare-range .seg-btn").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#index-compare-range .seg-btn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    const days = Number(b.dataset.days);
    loadIndexCompare(days);
  });
});

// ═══ 市场量能 ══════════════════════════
let liangnengChart = null;
let lnMode = "intraday";   // 'intraday' 当日预测量能 | 'history' 近20日成交额
let lnLatest = null;

const fmtAmount = (v) => (v == null ? "--" : Math.round(v) + "亿");

async function loadLiangneng() {
  try {
    const d = await fetch("/api/liangneng").then((x) => x.json());
    lnLatest = d;
    $("#ln-date").textContent = d.trade_date ? d.trade_date.slice(5) : "--";
    $("#ln-actual").textContent = fmtAmount(d.actual);
    $("#ln-predict").textContent = fmtAmount(d.predict);
    $("#ln-yesterday").textContent = fmtAmount(d.yesterday);

    const chg = $("#ln-change");
    if (d.change_pct == null) {
      chg.textContent = "--";
      chg.className = "ln-chg mono";
    } else {
      const up = d.change_pct > 0;
      const pct = (up ? "+" : "") + d.change_pct.toFixed(2) + "%";
      const abs = d.change_abs != null ? (up ? "放量" : "缩量") + Math.round(Math.abs(d.change_abs)) + "亿" : "";
      chg.textContent = `(${pct}，${abs})`;
      chg.className = "ln-chg mono " + colorClass(d.change_pct);
    }
    renderLiangneng();
  } catch (e) {
    console.error("市场量能加载失败", e);
  }
}

function renderLiangneng() {
  if (!lnLatest) return;
  const d = lnLatest;
  const hasIntraday = !!(d.intraday && d.intraday.length);
  const hasTrend = !!(d.trend && d.trend.length);

  // 当前模式无数据时自动切到有数据的一侧
  if (lnMode === "intraday" && !hasIntraday && hasTrend) lnMode = "history";
  else if (lnMode === "history" && !hasTrend && hasIntraday) lnMode = "intraday";
  $("#ln-toggle").textContent = lnMode === "intraday" ? "历史量能" : "当日追测";

  const box = document.getElementById("liangneng-chart");
  if ((lnMode === "intraday" && !hasIntraday) || (lnMode === "history" && !hasTrend)) {
    // 两组数据都为空：给空态提示，避免留出大块空白
    if (liangnengChart) { liangnengChart.dispose(); liangnengChart = null; }
    box.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#5a6a8a;font-size:13px">暂无量能历史数据（接口受限），盘后会自动补全</div>';
    return;
  }

  const option = lnMode === "intraday" ? buildIntradayOption(d) : buildHistoryOption(d);
  if (!liangnengChart) {
    box.innerHTML = "";
    liangnengChart = echarts.init(box);
  }
  liangnengChart.setOption(option, true);
  liangnengChart.resize();
}

function buildIntradayOption(d) {
  const intra = d.intraday || [];
  // 生成完整交易时段 242 个分钟刻度：
  // 上午：9:30（570）~ 11:30（690）共 121 分钟
  // 下午：13:00（780）~ 15:00（900）共 121 分钟
  const xData = [];
  // 上午段
  for (let m = 570; m <= 690; m++) {
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    xData.push(`${hh}:${mm}`);
  }
  // 下午段
  for (let m = 780; m <= 900; m++) {
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    xData.push(`${hh}:${mm}`);
  }
  // 构建时刻 -> 涨跌幅映射
  const chgMap = Object.fromEntries(intra.map((x) => [x.time, x.chg]));
  // series 数据：已有时刻填 Number(值)，未到/无数据时刻填 null（留白）
  const seriesData = xData.map((t) => {
    const v = chgMap[t];
    return v != null ? Number(v) : null;
  });

  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        const p = ps && ps[0];
        if (!p || p.value == null) return "";
        const val = Array.isArray(p.value) ? p.value[1] : p.value;
        if (val == null) return "";
        return `<b>${p.axisValue}</b><br>${p.marker}预测量能：${val}%`;
      },
    },
    grid: { left: 52, right: 20, top: 26, bottom: 28 },
    xAxis: {
      type: "category", data: xData, boundaryGap: false,
      axisLine: { lineStyle: { color: "#2a3550" } },
      axisLabel: {
        color: "#8ba0c9",
        // 每 30 个点一个标签（半小时刻度）+ 强制 15:00 标签
        interval: function (idx, val) { return idx % 30 === 0 || val === "15:00"; },
      },
    },
    yAxis: {
      type: "value", axisLabel: { color: "#8ba0c9", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#16203a" } },
    },
    series: [{
      name: "预测量能", type: "line",
      data: seriesData,
      smooth: false,          // 分时图用尖锐折线（传统分时感）
      connectNulls: false,    // 午休 11:30 -> 13:00 之间断开不跨接
      symbol: "none",
      lineStyle: { width: 2.5, color: "#ff9f43" },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
        [{ offset: 0, color: "rgba(255,159,67,.32)" }, { offset: 1, color: "rgba(255,159,67,0)" }]) },
      markLine: {
        silent: true, symbol: "none",
        label: { color: "#8ba0c9", fontSize: 10, position: "insideStartTop", formatter: "昨日 0%" },
        lineStyle: { color: "#5b8ff9", type: "dashed" },
        data: [{ yAxis: 0 }],
      },
    }],
  };
}

function buildHistoryOption(d) {
  const trend = d.trend || [];
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        const p = ps && ps[0];
        return p && p.value != null ? `<b>${p.axisValue}</b><br>${p.marker}两市成交额：${p.value}亿` : "";
      },
    },
    grid: { left: 56, right: 20, top: 26, bottom: 28 },
    xAxis: {
      type: "category", data: trend.map((x) => x.date), boundaryGap: true,
      axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9", interval: "auto" },
    },
    yAxis: {
      type: "value", axisLabel: { color: "#8ba0c9" }, splitLine: { lineStyle: { color: "#16203a" } },
    },
    series: [{
      name: "成交额", type: "bar", data: trend.map((x) => x.amount), barMaxWidth: 18,
      itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
        [{ offset: 0, color: "#00e5ff" }, { offset: 1, color: "rgba(0,229,255,.15)" }]) },
    }],
  };
}

$("#ln-toggle").addEventListener("click", () => {
  lnMode = lnMode === "intraday" ? "history" : "intraday";
  renderLiangneng();
});

// ═══ 涨跌统计柱状图 ═════════════════════
let distChart = null;

async function loadDistribution() {
  try {
    const d = await fetch("/api/market_distribution").then((x) => x.json());
    renderDistribution(d);
  } catch (e) { console.error("涨跌统计加载失败", e); }
}

function renderDistribution(d) {
  // X 轴共 11 个柱子：最左侧涨停 + 9 个涨跌幅区间 + 最右侧跌停
  const ranges = d.ranges || [];
  const bars = [
    { name: "涨停", count: d.zt_count || 0 },
    ...ranges,
    { name: "跌停", count: d.dt_count || 0 },
  ];
  const labels = bars.map(r => r.name);
  const counts = bars.map(r => r.count);
  const total = d.total || 1;
  // 颜色：涨停红、跌停绿、涨幅红、跌幅绿、平盘灰
  const colors = bars.map(r => {
    const n = r.name;
    if (n === "涨停") return "#ff4d5f";
    if (n === "跌停") return "#00d68f";
    if (n === "平盘") return "#5a6a8a";
    if (n.includes("-")) return "#00d68f"; // 跌幅绿色
    return "#ff4d5f"; // 涨幅红色
  });
  const option = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", backgroundColor:"#0d1226", borderColor:"#1c2540",
      textStyle:{color:"#c6d2ef",fontSize:12},
      formatter: (ps) => {
        const i = ps[0].dataIndex;
        const r = bars[i];
        const pct = (r.count / total * 100).toFixed(1);
        return `<b>${r.name}</b><br>${r.count} 只（占比 ${pct}%）`;
      }
    },
    grid: { left: 48, right: 20, top: 30, bottom: 45 },
    // 11 个柱子标签较多，旋转 30 度避免拥挤
    xAxis: { type: "category", data: labels, axisLine:{lineStyle:{color:"#2a3550"}}, axisLabel:{color:"#8ba0c9",fontSize:11,interval:0,rotate:30} },
    yAxis: { type: "value", axisLabel:{color:"#8ba0c9"}, splitLine:{lineStyle:{color:"#16203a"}} },
    series: [{
      type: "bar", data: counts, barMaxWidth: 40,
      itemStyle: { color: (p) => colors[p.dataIndex] },
      label: { show: true, position: "top", color: "#c6d2ef", fontSize: 11 }
    }]
  };
  if (!distChart) distChart = echarts.init(document.getElementById("distribution-chart"));
  distChart.setOption(option, true);
  distChart.resize();
  // 柱状图下方渲染涨跌汇总双色进度条
  renderDistSummary(d);
}

// 涨跌汇总：横向红绿双色对比进度条，宽度按涨跌比例动态调整
function renderDistSummary(d) {
  const box = $("#dist-summary");
  if (!box) return;
  const total = d.total || 0;
  const up = d.up_count || 0;
  const down = d.down_count || 0;
  const upPct = total ? (up / total * 100) : 0;
  const downPct = total ? (down / total * 100) : 0;
  const divider = (up > 0 && down > 0) ? '<div class="dist-divider" aria-hidden="true"></div>' : '';
  box.innerHTML = `<div class="dist-bar-labels">
      <span class="dist-up">上涨 ${up} 家（${upPct.toFixed(1)}%）</span>
      <span class="dist-down">下跌 ${down} 家（${downPct.toFixed(1)}%）</span>
    </div>
    <div class="dist-bar" title="上涨 ${up} / 下跌 ${down} / 共 ${total} 家">
      <div class="dist-seg up" style="width:${upPct.toFixed(2)}%"></div>${divider}
      <div class="dist-seg down" style="width:${downPct.toFixed(2)}%"></div>
    </div>`;
}

// ═══ 市场情绪 ══════════════════════════
let emotionChart = null;
let curDays = 15;
let iceThreshold = 30;   // 冰点阈值（情绪分 <= 该值判定为冰点，可自定义）
let lastTrend = null;

const fmtDate = (d) => (d ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : "");

async function loadSentiment(force) {
  if (force) { $("#se-score").textContent = "…"; $("#se-level").textContent = "正在重新计算（首次约30~60秒）…"; }
  const qs = new URLSearchParams({ days: curDays });
  if (force) qs.set("force", "1");
  const t = await fetch("/api/emotion_trend?" + qs.toString()).then((x) => x.json());
  const s = t.latest;
  if (!s) { $("#se-score").textContent = "!!"; $("#se-level").textContent = "数据不可用"; return; }
  $("#se-score").textContent = s.score;
  $("#se-score").style.color = s.score <= 45 ? "#00d68f" : s.score >= 80 ? "#ff4d5f" : "#00e5ff";
  $("#se-level").textContent = s.level;
  $("#se-date").textContent = `近 ${t.labels.length} 个交易日 · 最新 ${fmtDate(s.date)}`;
  $("#se-dims").innerHTML = [
    `涨停 ${s.zt_count}`, `跌停 ${s.dt_count}`, `炸板率 ${s.break_rate}%`, `晋级率 ${s.promo_rate}%`, `最高 ${s.max_height}板`,
  ].map((d) => `<span class="dim">${d}</span>`).join("");
  renderContrib(s.contributions);
  renderLevelGuide(s.level);
  lastTrend = t;
  renderEmotionChart(t);
}

// 渲染情绪分各维度贡献度（水平条形图，正贡献蓝色、负贡献红色）
function renderContrib(c) {
  const box = $("#se-contrib");
  if (!box || !c) { if (box) box.innerHTML = ""; return; }
  const order = ["涨停家数", "连板高度", "晋级率", "炸板率", "跌停惩罚"];
  const maxAbs = Math.max(1, ...order.map((k) => Math.abs(c[k] || 0)));
  box.innerHTML = order.map((k) => {
    const v = c[k] || 0;
    const pct = Math.min(100, Math.abs(v) / maxAbs * 100);
    const cls = v >= 0 ? "pos" : "neg";
    const sign = v > 0 ? "+" : "";
    return `<div class="contrib-row">
      <span class="contrib-name">${k}</span>
      <div class="contrib-track">
        <div class="contrib-bar ${cls}" style="width:${pct.toFixed(1)}%"></div>
      </div>
      <span class="contrib-val ${cls}">${sign}${v}</span>
    </div>`;
  }).join("");
}

// 情绪等级说明数据：名称 / 分数区间 / 描述 / 操作建议
const LEVEL_GUIDE = [
  { name: "冰点", range: "0-25", desc: "市场极度恐慌，涨停家数稀少，跌停家数增多", advice: "可关注情绪反转机会，分批低吸强势股" },
  { name: "偏冷", range: "26-45", desc: "情绪低迷，赚钱效应较弱，炸板率偏高", advice: "谨慎操作，控制仓位，等待情绪回暖" },
  { name: "正常", range: "46-65", desc: "情绪平稳，涨停家数适中，接力赚钱效应一般", advice: "正常仓位，跟随主线题材轮动" },
  { name: "偏热", range: "66-80", desc: "情绪升温，涨停家数增多，连板高度抬升", advice: "可适度加仓，关注领涨龙头" },
  { name: "过热", range: "81-100", desc: "情绪亢奋，涨停家数爆量，炸板率可能上升", advice: "注意风险，逢高减仓，警惕分歧" },
];

// 渲染情绪等级说明卡片，并高亮当前等级
function renderLevelGuide(curLevel) {
  const box = $("#se-levels");
  if (!box) return;
  box.innerHTML = LEVEL_GUIDE.map((lv) => {
    const on = lv.name === curLevel ? " on" : "";
    return `<div class="lvl-card${on}">
      <div class="lvl-head"><span class="lvl-name">${lv.name}</span><span class="lvl-range">${lv.range}</span></div>
      <div class="lvl-desc">${lv.desc}</div>
      <div class="lvl-advice">${lv.advice}</div>
    </div>`;
  }).join("");
}

function renderEmotionChart(t) {
  const labels = t.labels;
  const idxSeries = (t.indexes || []).map((x) => ({
    name: x.name, type: "line", yAxisIndex: 1, xAxisIndex: 0,
    data: x.values, smooth: true, showSymbol: false,
    lineStyle: { width: 1.5 }, emphasis: { focus: "series" },
  }));
  const linear = (c1, c2) => new echarts.graphic.LinearGradient(0, 0, 0, 1,
    [{ offset: 0, color: c1 }, { offset: 1, color: c2 }]);
  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        if (!ps.length) return "";
        const i = ps[0].dataIndex;
        let s = `<b>${fmtDate(t.dates[i])}</b><br>`;
        ps.forEach((p) => { if (p.value != null && p.value !== "") s += `${p.marker}${p.seriesName}：${p.value}<br>`; });
        return s;
      },
    },
    legend: { textStyle: { color: "#8ba0c9" }, top: 0, type: "scroll" },
    grid: [
      { left: 48, right: 48, top: 42, height: 235 },
      { left: 48, right: 48, top: 325, height: 70 },
    ],
    xAxis: [
      { type: "category", data: labels, gridIndex: 0, boundaryGap: false, axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9", interval: "auto" } },
      { type: "category", data: labels, gridIndex: 1, axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, min: 0, max: 100, splitLine: { lineStyle: { color: "#16203a" } }, axisLabel: { color: "#8ba0c9" } },
      { type: "value", gridIndex: 0, scale: true, axisLabel: { color: "#8ba0c9", formatter: "{value}%" }, splitLine: { show: false } },
      { type: "value", gridIndex: 1, axisLabel: { color: "#8ba0c9" }, splitLine: { show: false } },
    ],
    series: [
      {
        name: "情绪分", type: "line", xAxisIndex: 0, yAxisIndex: 0,
        data: t.scores, smooth: true, symbol: "circle", symbolSize: 6,
        lineStyle: { width: 2.5, color: "#4d7cff" },
        itemStyle: { color: "#4d7cff", borderColor: "#0d1226", borderWidth: 2 },
        areaStyle: { color: linear("rgba(77,124,255,.35)", "rgba(77,124,255,0)") },
        markLine: {
          silent: true, symbol: "none", label: { color: "#8ba0c9", fontSize: 10, position: "insideStartTop" },
          data: [
            { yAxis: iceThreshold, label: { formatter: "冰点" + iceThreshold } },
            { yAxis: 80, label: { formatter: "过热80" } },
          ],
          lineStyle: { color: "#3a4a75", type: "dashed" },
        },
      },
      ...idxSeries,
      {
        name: "涨停家数", type: "bar", xAxisIndex: 1, yAxisIndex: 2,
        data: t.zt_count, barMaxWidth: 14,
        itemStyle: { color: linear("#ffb347", "rgba(255,179,71,.35)") },
      },
    ],
  };
  if (!emotionChart) emotionChart = echarts.init(document.getElementById("emotion-chart"));
  emotionChart.setOption(option, true);
  emotionChart.resize();
}
$("#se-refresh").addEventListener("click", () => loadSentiment(true));
// 冰点阈值可自定义：改后刷新主图参考线并重新拉低点数据
$("#ice-threshold").addEventListener("change", () => {
  let v = parseInt($("#ice-threshold").value, 10);
  if (Number.isNaN(v)) v = 30;
  iceThreshold = Math.max(0, Math.min(100, v));
  $("#ice-threshold").value = iceThreshold;
  if (lastTrend) renderEmotionChart(lastTrend);
  loadLowNext();
});
// 低点图时间范围切换
document.querySelectorAll("#ln-days .seg-btn").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#ln-days .seg-btn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    lnDays = Number(b.dataset.days);
    loadLowNext();
  });
});
document.querySelectorAll("#se-range .seg-btn").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#se-range .seg-btn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    curDays = Number(b.dataset.days);
    $("#se-date").textContent = "加载中…";
    loadSentiment(false);
  });
});
window.addEventListener("resize", () => { if (emotionChart) emotionChart.resize(); if (lowNextChart) lowNextChart.resize(); if (ikChart) ikChart.resize(); if (liangnengChart) liangnengChart.resize(); if (distChart) distChart.resize(); if (ovSentMiniChart) ovSentMiniChart.resize(); if (goldHistoryChart) goldHistoryChart.resize(); if (indexCompareChart) indexCompareChart.resize(); });

// ═══ 情绪低点 · 次日指数表现 ══════════════
let lowNextChart = null;
let lnData = null;
let lnIndex = 0;
let lnDays = 0;   // 低点图时间窗口（<=0 表示全部历史）

async function loadLowNext() {
  try {
    const t = await fetch(`/api/emotion_low_next?threshold=${iceThreshold}&days=${lnDays}`).then((x) => x.json());
    lnData = t;
    $("#ln-hint").textContent = `情绪分 ≤${iceThreshold}（冰点）当日收盘 → 下一交易日收盘涨跌幅`;
    const seg = $("#ln-range");
    seg.innerHTML = (t.indexes || []).map((ix, i) =>
      `<button class="seg-btn ${i === lnIndex ? "on" : ""}" data-i="${i}">${ix.name}</button>`).join("");
    seg.querySelectorAll(".seg-btn").forEach((b) => {
      b.addEventListener("click", () => {
        seg.querySelectorAll(".seg-btn").forEach((x) => x.classList.remove("on"));
        b.classList.add("on");
        lnIndex = Number(b.dataset.i);
        renderLowNext();
      });
    });
    renderLowNext();
  } catch (e) {
    console.error("情绪低点次日涨幅加载失败", e);
  }
}

function renderLowNext() {
  if (!lnData) return;
  const ix = (lnData.indexes || [])[lnIndex];
  if (!ix) return;
  const items = ix.items || [];
  const st = ix.stats || {};
  const scores = lnData.low_scores || [];
  $("#ln-stats").innerHTML = [
    ["冰点样本数", st.n == null ? "--" : st.n, "flat"],
    ["平均次日涨幅", st.avg == null ? "--" : st.avg + "%", colorClass(st.avg)],
    ["次日上涨概率", st.win_rate == null ? "--" : st.win_rate + "%", (st.win_rate != null && st.win_rate >= 50) ? "up" : "flat"],
  ].map(([l, n, c]) => `<div class="stat"><div class="num ${c}">${n}</div><div class="lbl">${l}</div></div>`).join("");

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        if (!ps.length || ps[0].value == null) return "";
        const it = items[ps[0].dataIndex];
        const sc = scores[ps[0].dataIndex];
        const ret = it.ret > 0 ? "+" + it.ret : it.ret;
        const diff = st.avg != null ? it.ret - st.avg : null;
        const diffStr = diff != null ? `<br>较平均(${st.avg}%)：${diff >= 0 ? "+" : ""}${diff.toFixed(2)}%` : "";
        return `<b>${fmtDate(it.date)}</b> 冰点(情绪${sc ?? "?"})<br>次日 ${fmtDate(it.next_date)}：${ret}%${diffStr}`;
      },
    },
    grid: { left: 48, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "category", data: items.map((it) => fmtDate(it.date)), axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9", interval: "auto" } },
    yAxis: { type: "value", axisLabel: { color: "#8ba0c9", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#16203a" } } },
    series: [{
      type: "bar", data: items.map((it) => it.ret), barMaxWidth: 20,
      itemStyle: { color: (p) => (p.value >= 0 ? "#ff4d5f" : "#00d68f") },
      // 冰点次日平均涨幅基准虚线
      markLine: {
        silent: true, symbol: "none",
        label: { color: "#ffd700", fontSize: 11, position: "insideEndTop", formatter: () => `平均 ${st.avg}%` },
        lineStyle: { color: "#ffd700", type: "dashed", width: 1.5 },
        data: [{ yAxis: st.avg }],
      },
    }],
  };
  if (!lowNextChart) lowNextChart = echarts.init(document.getElementById("low-next-chart"));
  lowNextChart.setOption(option, true);
  lowNextChart.resize();
}

// ═══ 推送规则 ══════════════════════════
let CONFIG = { watchlist: [], rules: [] };

async function loadConfig() {
  CONFIG = await fetch("/api/config").then((x) => x.json());
  $("#fe-webhook").value = CONFIG.feishu_webhook || "";
  renderRules();
}

function renderRules() {
  const tb = $("#rules-tbody");
  if (!CONFIG.rules.length) {
    tb.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#4d5d7d">还没有规则，先在下方添加</td></tr>`;
    return;
  }
  tb.innerHTML = CONFIG.rules.map((r, i) => `<tr>
    <td>${r.name}</td>
    <td class="mono">${r.metric} ${r.op} ${r.value}</td>
    <td class="num">${r.value}</td>
    <td class="num mono">${r.cooldown_minutes}分</td>
    <td>${r.message || ""}</td>
    <td><label class="custom-w"><input type="checkbox" ${r.enabled ? "checked" : ""} data-i="${i}" class="r-toggle"><span class="sl"></span></label></td>
    <td><button class="btn danger sm r-del" data-i="${i}">删除</button></td>
  </tr>`).join("");

  tb.querySelectorAll(".r-toggle").forEach((c) => c.addEventListener("change", async (e) => {
    CONFIG.rules[e.target.dataset.i].enabled = e.target.checked;
    await saveConfig();
  }));
  tb.querySelectorAll(".r-del").forEach((b) => b.addEventListener("click", async (e) => {
    CONFIG.rules.splice(Number(e.target.dataset.i), 1);
    await saveConfig(); renderRules();
  }));
}

async function saveConfig() {
  await fetch("/api/config", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feishu_webhook: $("#fe-webhook").value.trim(), rules: CONFIG.rules, watchlist: CONFIG.watchlist }),
  });
}

$("#fe-save").addEventListener("click", async () => { await saveConfig(); alert("已保存"); });

$("#r-add").addEventListener("click", async () => {
  const rule = {
    name: $("#r-name").value.trim() || "未命名规则",
    metric: $("#r-metric").value,
    op: $("#r-op").value,
    value: Number($("#r-value").value),
    message: $("#r-message").value.trim(),
    cooldown_minutes: Number($("#r-cooldown").value) || 60,
    enabled: true,
  };
  CONFIG.rules.push(rule);
  await saveConfig();
  renderRules();
});

$("#r-check").addEventListener("click", async () => {
  $("#r-check").textContent = "检查中…";
  const r = await fetch("/api/rules/check", { method: "POST" }).then((x) => x.json());
  $("#r-check").textContent = "立即检查并推送";
  const m = r.metrics;
  $("#r-result").innerHTML =
    `当前指标：情绪分 <b>${m.sentiment}</b> | 炸板率 ${m.break_rate}% | 晋级率 ${m.promo_rate}% | 涨停 ${m.zt_count} 家 | 上证 ${m.index_pct}%<br>` +
    (r.triggered.length
      ? `✅ 触发 ${r.triggered.length} 条：${r.triggered.map((t) => t.name).join("、")}，已推送 ${r.sent} 条`
      : `未触发任何规则`);
});

// ── 选股推送列表 ────────────────────────────────
const SCOPE_LABELS = {
  sh_main: "沪主", sz_main: "深主", kcb: "科创", cyb: "创业", bj: "北交"
};

async function loadScreenRules() {
  try {
    const indicators = await fetch("/api/indicators").then((r) => r.json());
    // 只显示开启了飞书推送的
    const pushList = indicators.filter((ind) => ind.config?.feishu_push);
    renderScreenRules(pushList, indicators.length);
  } catch (e) {
    console.error("加载选股推送失败:", e);
  }
}

function renderScreenRules(list, total) {
  const tb = $("#screen-rules-tbody");
  if (!list.length) {
    tb.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#4d5d7d">暂无选股推送，去「智能选股」页开启</td></tr>`;
    return;
  }
  tb.innerHTML = list.map((ind) => {
    const cfg = ind.config || {};
    const scope = (cfg.scope || []).map((s) => SCOPE_LABELS[s] || s).join("、") || "--";
    return `<tr>
      <td>${escapeHtml(ind.name)}</td>
      <td style="font-size:12px">${scope}</td>
      <td class="mono">${cfg.push_time || "--"}</td>
      <td><span style="color:var(--green)">✓ 已开启</span></td>
      <td><label class="custom-w">
        <input type="checkbox" ${ind.enabled ? "checked" : ""} data-id="${ind.id}" class="sr-toggle">
        <span class="sl"></span>
      </label></td>
      <td><button class="btn ghost sm sr-del" data-id="${ind.id}" style="color:var(--red)">关闭推送</button></td>
    </tr>`;
  }).join("");

  // 绑定启用/停用事件
  tb.querySelectorAll(".sr-toggle").forEach((c) => {
    c.addEventListener("change", async (e) => {
      const id = e.target.dataset.id;
      const enabled = e.target.checked;
      try {
        await fetch(`/api/indicators/${id}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        }).then((x) => x.json());
        loadScreenRules();
      } catch (e2) {
        alert("操作失败");
        loadScreenRules();
      }
    });
  });

  // 绑定关闭推送事件
  tb.querySelectorAll(".sr-del").forEach((b) => {
    b.addEventListener("click", async (e) => {
      const id = e.target.dataset.id;
      if (!confirm("确定关闭这个选股推送吗？可在智能选股页重新开启。")) return;
      try {
        // 先获取当前指标的配置
        const indicators = await fetch("/api/indicators").then((r) => r.json());
        const ind = indicators.find((x) => x.id === id);
        if (!ind) return;
        const cfg = { ...(ind.config || {}), feishu_push: false };
        await fetch(`/api/indicators/${id}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: cfg }),
        }).then((x) => x.json());
        loadScreenRules();
      } catch (e2) {
        alert("操作失败");
      }
    });
  });
}

$("#r-refresh-screen").addEventListener("click", loadScreenRules);

// ═══ 自选看板 ══════════════════════════
// 自选标的实时行情（已迁移到市场概览底部，不再显示大盘指数行情）
async function loadWatch() {
  await loadConfig();
  const codes = CONFIG.watchlist.map((w) => w.code);
  const q = await fetch("/api/quotes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ codes }) }).then((x) => x.json());
  renderWatch(q);
  $("#w-time").textContent = new Date().toLocaleString();
}

function renderWatch(q) {
  const tb = $("#w-tbody");
  // 空列表提示
  if (!CONFIG.watchlist.length) {
    tb.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#4d5d7d">暂无自选标的，请在上方添加</td></tr>`;
    return;
  }
  tb.innerHTML = CONFIG.watchlist.map((w) => {
    // 删除按钮：data-code 用于定位要删除的标的
    const del = `<td><button class="btn danger sm w-del" data-code="${w.code}">删除</button></td>`;
    const qq = q[w.code];
    if (!qq) return `<tr><td>${w.name || w.code}</td><td class="mono">${w.code}</td><td colspan="4" style="color:#4d5d7d">数据缺失</td>${del}</tr>`;
    return `<tr><td>${qq.name || w.name}</td><td class="mono">${w.code}</td>
      <td class="num mono">${fmt(qq.price, 3)}</td>
      <td class="num mono ${colorClass(qq.change_pct)}">${qq.change_pct > 0 ? "+" : ""}${fmt(qq.change_pct)}%</td>
      <td class="num mono">${fmt(qq.amount_yi)}</td>
      <td class="num mono">${fmt(qq.turnover_pct)}%</td>${del}</tr>`;
  }).join("");
  // 绑定每行删除按钮事件
  tb.querySelectorAll(".w-del").forEach((b) =>
    b.addEventListener("click", () => delWatch(b.dataset.code))
  );
}

// 规范化股票代码：去除 sh/sz/bj 市场前缀，统一为 6 位纯数字代码
function normalizeCode(input) {
  return input.trim().toLowerCase().replace(/^(sh|sz|bj)/, "");
}

// 添加自选标的：输入代码后调用 /api/quotes 验证，有效则加入 watchlist 并刷新
async function addWatch() {
  const input = $("#w-add-input");
  const msg = $("#w-add-msg");
  const raw = input.value.trim();
  if (!raw) { msg.textContent = "请输入股票代码"; msg.className = "w-add-msg err"; return; }
  const code = normalizeCode(raw);
  // 校验代码格式：6 位数字
  if (!/^\d{6}$/.test(code)) {
    msg.textContent = "代码格式不正确（应为 6 位数字）";
    msg.className = "w-add-msg err";
    return;
  }
  // 去重：已存在则不重复添加
  if (CONFIG.watchlist.some((w) => w.code === code)) {
    msg.textContent = "该标的已在自选列表中";
    msg.className = "w-add-msg err";
    return;
  }
  msg.textContent = "验证中…"; msg.className = "w-add-msg";
  try {
    // 调用 /api/quotes 验证代码有效性
    const q = await fetch("/api/quotes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes: [code] }),
    }).then((x) => x.json());
    const qq = q[code];
    if (!qq || !qq.name) {
      msg.textContent = "代码无效，未查到该标的";
      msg.className = "w-add-msg err";
      return;
    }
    // 验证通过，加入 watchlist 并持久化
    CONFIG.watchlist.push({ code, name: qq.name });
    await saveConfig();
    msg.textContent = `已添加：${qq.name}`;
    msg.className = "w-add-msg ok";
    input.value = "";
    loadWatch();  // 刷新自选表格
  } catch (e) {
    msg.textContent = "添加失败：" + e;
    msg.className = "w-add-msg err";
  }
}

// 删除自选标的：从 watchlist 移除并持久化，然后刷新表格
async function delWatch(code) {
  CONFIG.watchlist = CONFIG.watchlist.filter((w) => w.code !== code);
  await saveConfig();
  loadWatch();
}

$("#w-add-btn").addEventListener("click", addWatch);
// 回车键也可触发添加
$("#w-add-input").addEventListener("keydown", (e) => { if (e.key === "Enter") addWatch(); });

// ═══ 选股页状态 ═══
let SC_STRATEGIES = [];       // 所有策略
let SC_CURRENT_STRATEGY = null;  // 当前选中策略 id
let SC_CODE_EDIT = false;     // 代码编辑模式
let SC_TASK_ID = null;
let SC_POLL_TIMER = null;
let SC_LAST_RESULTS = [];
let scBtChart = null;

async function loadScreener() {
  if (SC_STRATEGIES.length === 0) {
    await loadStrategies();
  }
}

// ── Tab 切换 ──
document.querySelectorAll(".sc-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    document.querySelectorAll(".sc-tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".sc-tab-pane").forEach((p) => {
      p.classList.toggle("active", p.dataset.pane === target);
    });
    if (target === "backtest" && scBtChart) {
      setTimeout(() => scBtChart.resize(), 100);
    }
  });
});

// ── 策略列表 ──
async function loadStrategies() {
  try {
    SC_STRATEGIES = await fetch("/api/indicators").then((r) => r.json());
  } catch (e) {
    SC_STRATEGIES = [];
  }
  renderStrategyList();
  renderBtStrategyOptions();
  if (SC_STRATEGIES.length > 0 && !SC_CURRENT_STRATEGY) {
    selectStrategy(SC_STRATEGIES[0].id);
  } else if (SC_STRATEGIES.length === 0) {
    SC_CURRENT_STRATEGY = null;
    clearStrategyView();
  }
}

function renderStrategyList() {
  const box = $("#sc-strategy-list");
  const keyword = ($("#sc-strategy-search")?.value || "").toLowerCase();

  if (!SC_STRATEGIES.length) {
    box.innerHTML = '<div class="sc-empty-tip">暂无策略，点击上方新建</div>';
    return;
  }

  const filtered = keyword
    ? SC_STRATEGIES.filter((s) =>
        s.name.toLowerCase().includes(keyword) ||
        (s.desc || "").toLowerCase().includes(keyword)
      )
    : SC_STRATEGIES;

  if (!filtered.length) {
    box.innerHTML = '<div class="sc-empty-tip">没有匹配的策略</div>';
    return;
  }

  box.innerHTML = filtered.map((s) => {
    const timerEnabled = s.config?.timer?.enabled;
    const running = timerEnabled ? "running" : "stopped";
    const clockIcon = timerEnabled ? '<span class="sc-strategy-icon" title="定时选股">⏰</span>' : "";
    return `
      <div class="sc-strategy-item ${SC_CURRENT_STRATEGY === s.id ? "active" : ""}" data-id="${s.id}">
        <span class="sc-strategy-dot ${running}" title="${timerEnabled ? "运行中" : "已停止"}"></span>
        <div class="sc-strategy-info">
          <div class="sc-strategy-item-name">${escapeHtml(s.name)}</div>
          <div class="sc-strategy-item-desc">${escapeHtml(s.desc || "暂无描述")}</div>
        </div>
        ${clockIcon}
      </div>`;
  }).join("");

  box.querySelectorAll(".sc-strategy-item").forEach((item) => {
    item.addEventListener("click", () => selectStrategy(item.dataset.id));
  });
}

$("#sc-strategy-search")?.addEventListener("input", renderStrategyList);

function renderBtStrategyOptions() {
  const group = $("#sc-bt-my-indicators");
  if (!group) return;
  const currentOpt = '<option value="current">使用当前策略</option>';
  const customOpts = SC_STRATEGIES.map((s) =>
    `<option value="ind_${s.id}">${escapeHtml(s.name)}</option>`
  ).join("");
  group.innerHTML = currentOpt + customOpts;
}

function clearStrategyView() {
  $("#sc-code").value = "";
  $("#sc-code-name").textContent = "--";
  $("#sc-code-desc").textContent = "--";
  $("#sc-strategy-name").textContent = "--";
  $("#sc-result-count").textContent = "--";
  $("#sc-results tbody").innerHTML =
    '<tr><td colspan="9" style="text-align:center;color:#4d5d7d">选择策略后点击"立即选股"</td></tr>';
  $("#sc-push-result").style.display = "none";
  $("#sc-edit-code").style.display = "none";
  $("#sc-save-code").style.display = "none";
  $("#sc-cancel-code").style.display = "none";
  $("#sc-check-syntax").style.display = "none";
}

function selectStrategy(id) {
  const s = SC_STRATEGIES.find((x) => x.id === id);
  if (!s) return;
  SC_CURRENT_STRATEGY = id;
  SC_CODE_EDIT = false;

  $("#sc-code").value = s.code || "";
  $("#sc-code").readOnly = true;
  $("#sc-code-name").textContent = s.name || "--";
  $("#sc-code-desc").textContent = s.desc || "--";
  $("#sc-strategy-name").textContent = s.name || "--";

  $("#sc-edit-code").style.display = "";
  $("#sc-save-code").style.display = "none";
  $("#sc-cancel-code").style.display = "none";
  $("#sc-check-syntax").style.display = "none";
  $("#sc-code-meta").style.display = "";
  $("#sc-code-name-edit").style.display = "none";

  const cfg = s.config || {};
  const scope = cfg.scope || ["all"];
  const scopeStr = Array.isArray(scope) ? scope.join(",") : scope;
  let preset = "custom";
  if (scopeStr === "all") preset = "all";
  else if (scopeStr === "sh_main,sz_main") preset = "hs_a";
  $("#sc-scope-preset").value = preset;
  $("#sc-scope-custom").style.display = preset === "custom" ? "" : "none";

  document.querySelectorAll("#sc-scope-custom input[type='checkbox']").forEach((cb) => {
    cb.checked = scope.includes(cb.value);
  });

  const exclude = cfg.exclude || ["st", "suspend"];
  document.querySelectorAll(".sc-config-wrap .sc-chk-grid input[type='checkbox']").forEach((cb) => {
    cb.checked = exclude.includes(cb.value);
  });

  $("#sc-adjust").value = cfg.adjust || "qfq";
  $("#sc-limit").value = cfg.limit || 100;
  $("#sc-sort").value = cfg.sort_by || "mcap_yi";

  const timer = cfg.timer || {};
  $("#sc-timer-enabled").checked = !!timer.enabled;
  $("#sc-timer-options").style.display = timer.enabled ? "" : "none";
  $("#sc-push-time").value = timer.time || "15:05";

  $("#sc-result-count").textContent = "--";
  $("#sc-results tbody").innerHTML =
    '<tr><td colspan="9" style="text-align:center;color:#4d5d7d">点击"立即选股"开始选股</td></tr>';
  $("#sc-push-result").style.display = "none";

  renderStrategyList();
}

$("#sc-scope-preset").addEventListener("change", (e) => {
  const val = e.target.value;
  const customBox = $("#sc-scope-custom");
  if (val === "custom") {
    customBox.style.display = "";
  } else {
    customBox.style.display = "none";
  }
});

$("#sc-timer-enabled").addEventListener("change", (e) => {
  $("#sc-timer-options").style.display = e.target.checked ? "" : "none";
});

// ── 新建策略 ──
$("#sc-new-strategy").addEventListener("click", () => {
  SC_CURRENT_STRATEGY = null;
  SC_CODE_EDIT = true;
  $("#sc-code").value = "";
  $("#sc-code").readOnly = false;
  $("#sc-code-name").textContent = "新策略";
  $("#sc-code-desc").textContent = "--";
  $("#sc-strategy-name").textContent = "新策略（未保存）";
  $("#sc-code-meta").style.display = "none";
  $("#sc-code-name-edit").style.display = "";
  $("#sc-name").value = "";
  $("#sc-desc").value = "";

  $("#sc-edit-code").style.display = "none";
  $("#sc-save-code").style.display = "";
  $("#sc-cancel-code").style.display = "";
  $("#sc-check-syntax").style.display = "";

  $("#sc-result-count").textContent = "--";
  $("#sc-results tbody").innerHTML =
    '<tr><td colspan="9" style="text-align:center;color:#4d5d7d">保存策略后可进行选股</td></tr>';
  $("#sc-push-result").style.display = "none";

  renderStrategyList();
  document.querySelector('.sc-tab[data-tab="formula"]').click();
});

// ── 编辑代码 ──
$("#sc-edit-code").addEventListener("click", () => {
  if (!SC_CURRENT_STRATEGY) return;
  SC_CODE_EDIT = true;
  const s = SC_STRATEGIES.find((x) => x.id === SC_CURRENT_STRATEGY);
  if (!s) return;

  $("#sc-code").readOnly = false;
  $("#sc-code-meta").style.display = "none";
  $("#sc-code-name-edit").style.display = "";
  $("#sc-name").value = s.name || "";
  $("#sc-desc").value = s.desc || "";

  $("#sc-edit-code").style.display = "none";
  $("#sc-save-code").style.display = "";
  $("#sc-cancel-code").style.display = "";
  $("#sc-check-syntax").style.display = "";
});

$("#sc-cancel-code").addEventListener("click", () => {
  if (SC_CURRENT_STRATEGY) {
    selectStrategy(SC_CURRENT_STRATEGY);
  } else {
    SC_CODE_EDIT = false;
    clearStrategyView();
  }
});

$("#sc-check-syntax").addEventListener("click", async () => {
  const code = $("#sc-code").value;
  if (!code.trim()) { alert("代码不能为空"); return; }
  try {
    const r = await fetch("/api/indicators/check-syntax", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }).then((x) => x.json());
    if (r.ok) {
      alert("✓ 语法检查通过");
    } else {
      alert("✗ 语法错误：\n" + r.error);
    }
  } catch (e) {
    alert("检查失败: " + e);
  }
});

$("#sc-save-code").addEventListener("click", async () => {
  const code = $("#sc-code").value;
  const name = $("#sc-name").value.trim();
  const desc = $("#sc-desc").value.trim();
  if (!name) { alert("请填写策略名称"); return; }
  if (!code.trim()) { alert("代码不能为空"); return; }

  let r;
  if (SC_CURRENT_STRATEGY) {
    r = await fetch(`/api/indicators/${SC_CURRENT_STRATEGY}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, desc, code }),
    }).then((x) => x.json());
  } else {
    r = await fetch("/api/indicators", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, desc, code }),
    }).then((x) => x.json());
  }

  if (r.error) { alert("保存失败：" + r.error); return; }
  await loadStrategies();
  selectStrategy(r.id);
  alert("保存成功");
});

// ── 保存配置 ──
$("#sc-save-config-btn").addEventListener("click", async () => {
  if (!SC_CURRENT_STRATEGY) {
    alert("请先选择或创建一个策略");
    return;
  }

  let scope;
  const preset = $("#sc-scope-preset").value;
  if (preset === "all") scope = ["all"];
  else if (preset === "hs_a") scope = ["sh_main", "sz_main"];
  else {
    scope = Array.from(document.querySelectorAll("#sc-scope-custom input:checked"))
      .map((cb) => cb.value);
    if (scope.length === 0) { alert("请至少选择一个板块"); return; }
  }

  const exclude = Array.from(
    document.querySelectorAll(".sc-config-wrap .sc-chk-grid input:checked")
  ).map((cb) => cb.value);

  const config = {
    scope,
    exclude,
    adjust: $("#sc-adjust").value,
    limit: Number($("#sc-limit").value) || 100,
    sort_by: $("#sc-sort").value,
    timer: {
      enabled: $("#sc-timer-enabled").checked,
      time: $("#sc-push-time").value,
      target: $("#sc-feishu-target").value,
    },
  };

  const r = await fetch(`/api/indicators/${SC_CURRENT_STRATEGY}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  }).then((x) => x.json());

  if (r.error) { alert("保存失败：" + r.error); return; }
  await loadStrategies();
  alert("配置已保存");
});

$("#sc-reset-config").addEventListener("click", () => {
  if (SC_CURRENT_STRATEGY) {
    selectStrategy(SC_CURRENT_STRATEGY);
  }
});

// ── 立即选股 ──
$("#sc-run-screen").addEventListener("click", async () => {
  if (!SC_CURRENT_STRATEGY) {
    alert("请先选择一个策略"); return;
  }
  const s = SC_STRATEGIES.find((x) => x.id === SC_CURRENT_STRATEGY);
  if (!s) return;

  $("#sc-run-screen").style.display = "none";
  $("#sc-cancel-screen").style.display = "";
  $("#sc-progress").style.display = "";
  $("#sc-progress-fill").style.width = "0%";
  $("#sc-progress-text").textContent = "准备中…";
  $("#sc-results tbody").innerHTML =
    '<tr><td colspan="9" style="text-align:center;color:#4d5d7d">正在扫描股票池…</td></tr>';

  try {
    const r = await fetch("/api/screen/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: s.code, config: s.config }),
    }).then((x) => x.json());
    if (r.error) { alert(r.error); resetScreenBtn(); return; }
    SC_TASK_ID = r.task_id;
    pollScreenProgress();
  } catch (e) {
    alert("选股启动失败: " + e);
    resetScreenBtn();
  }
});

function resetScreenBtn() {
  $("#sc-run-screen").style.display = "";
  $("#sc-cancel-screen").style.display = "none";
}

$("#sc-cancel-screen").addEventListener("click", async () => {
  if (!SC_TASK_ID) return;
  await fetch(`/api/screen/cancel/${SC_TASK_ID}`, { method: "POST" });
});

function pollScreenProgress() {
  if (SC_POLL_TIMER) clearInterval(SC_POLL_TIMER);
  SC_POLL_TIMER = setInterval(async () => {
    if (!SC_TASK_ID) { clearInterval(SC_POLL_TIMER); return; }
    try {
      const st = await fetch(`/api/screen/state/${SC_TASK_ID}`).then((r) => r.json());
      const pct = st.total ? Math.round(st.progress / st.total * 100) : 0;
      $("#sc-progress-fill").style.width = pct + "%";
      const estDays = st.est_days ? `（K线 ${st.est_days} 天）` : "";
      $("#sc-progress-text").textContent =
        `已扫描 ${st.progress || 0} / ${st.total || 0} 只 · 命中 ${st.results?.length || 0} 只 ${estDays}`;

      if (st.status === "done") {
        clearInterval(SC_POLL_TIMER);
        SC_TASK_ID = null;
        resetScreenBtn();
        renderScreenResults(st.results || []);
        $("#sc-progress").style.display = "none";
      } else if (st.status === "error") {
        clearInterval(SC_POLL_TIMER);
        SC_TASK_ID = null;
        resetScreenBtn();
        alert("选股失败: " + st.error);
        $("#sc-progress").style.display = "none";
      } else if (st.status === "cancelled") {
        clearInterval(SC_POLL_TIMER);
        SC_TASK_ID = null;
        resetScreenBtn();
        $("#sc-progress-text").textContent = "已取消";
        setTimeout(() => { $("#sc-progress").style.display = "none"; }, 1500);
      }
    } catch (e) {}
  }, 1500);
}

function renderScreenResults(results) {
  SC_LAST_RESULTS = results;
  $("#sc-result-count").textContent = `命中 ${results.length} 只`;
  $("#sc-push-result").style.display = results.length > 0 ? "" : "none";

  if (!results.length) {
    $("#sc-results tbody").innerHTML =
      '<tr><td colspan="9" style="text-align:center;color:#4d5d7d">暂无符合条件的股票</td></tr>';
    return;
  }

  const today = new Date().toLocaleDateString("zh-CN");
  $("#sc-results tbody").innerHTML = results.map((r) => {
    const cls = r.change_pct > 0 ? "change-up" : r.change_pct < 0 ? "change-down" : "change-flat";
    const sign = r.change_pct > 0 ? "+" : "";
    return `<tr>
      <td class="mono">${r.code}</td>
      <td>${r.name}</td>
      <td class="num mono">${r.price.toFixed(2)}</td>
      <td class="num mono ${cls}">${sign}${r.change_pct.toFixed(2)}%</td>
      <td class="num mono">${r.mcap_yi.toFixed(1)}</td>
      <td class="num mono">${(r.amount_yi || 0).toFixed(2)}</td>
      <td>--</td>
      <td class="mono" style="font-size:12px;color:var(--sub)">${today}</td>
      <td>${r.industry || "--"}</td>
    </tr>`;
  }).join("");
}

// ── 推送飞书 ──
$("#sc-push-result").addEventListener("click", async () => {
  if (!SC_LAST_RESULTS.length || !SC_CURRENT_STRATEGY) return;
  const btn = $("#sc-push-result");
  const origText = btn.textContent;
  btn.textContent = "推送中…";
  btn.disabled = true;
  try {
    const s = SC_STRATEGIES.find((x) => x.id === SC_CURRENT_STRATEGY);
    const r = await fetch("/api/feishu/push-screen", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        indicator_id: SC_CURRENT_STRATEGY,
        indicator_name: s?.name || "智能选股",
        results: SC_LAST_RESULTS,
      }),
    }).then((x) => x.json());
    if (r.ok) {
      alert("推送成功");
    } else {
      alert("推送失败：" + (r.error || "未知错误"));
    }
  } catch (e) {
    alert("推送失败: " + e);
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
  }
});

// ── 回测 ──
const BUILTIN_BT_INDICATORS = {
  macd: "DIF:=EMA(C,12)-EMA(C,26);\nDEA:=EMA(DIF,9);\n买入信号:CROSS(DIF,DEA);",
  kdj: "K:=KDJ.K;\nD:=KDJ.D;\n买入信号:CROSS(K,D);",
  ma5_10: "MA5:=MA(C,5);\nMA10:=MA(C,10);\n买入信号:CROSS(MA5,MA10);",
  ma20_60: "MA20:=MA(C,20);\nMA60:=MA(C,60);\n买入信号:CROSS(MA20,MA60);",
  rsi: "RSI1:=RSI(C,14);\n买入信号:CROSS(RSI1,30);",
  boll: "UPPER:=BOLL(20,2);\n买入信号:CROSS(C,UPPER);",
};

$("#sc-bt-run").addEventListener("click", async () => {
  const indicator = $("#sc-bt-indicator").value;
  let code;
  if (indicator === "current") {
    if (!SC_CURRENT_STRATEGY) { alert("请先选择一个策略"); return; }
    const s = SC_STRATEGIES.find((x) => x.id === SC_CURRENT_STRATEGY);
    code = s?.code || "";
  } else if (indicator.startsWith("ind_")) {
    const indId = indicator.substring(4);
    const ind = SC_STRATEGIES.find((x) => x.id === indId);
    if (!ind) { alert("找不到该策略"); return; }
    code = ind.code;
  } else {
    code = BUILTIN_BT_INDICATORS[indicator];
  }
  if (!code.trim()) { alert("策略代码为空"); return; }

  const pool = $("#sc-bt-pool").value;
  const days = Number($("#sc-bt-days").value) || 250;
  const adjust = $("#sc-bt-adjust").value;

  $("#sc-bt-run").textContent = "回测中…";
  $("#sc-bt-run").disabled = true;

  try {
    const benchCode = pool === "hs300" ? "sh000300" : pool === "zz500" ? "sh000905" : "sh000001";
    const r = await fetch("/api/screen/backtest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, stock_code: benchCode, days, adjust }),
    }).then((x) => x.json());
    if (r.error) { alert(r.error); return; }
    renderScBacktest(r);
  } catch (e) {
    alert("回测失败: " + e);
  } finally {
    $("#sc-bt-run").textContent = "开始回测";
    $("#sc-bt-run").disabled = false;
  }
});

function renderScBacktest(r) {
  $("#sc-bt-empty").style.display = "none";
  $("#sc-bt-stats").style.display = "grid";
  $("#sc-bt-chart-card").style.display = "block";
  $("#sc-bt-trades-card").style.display = "block";

  const totalRet = Number(r.total_ret || 0);
  const annualRet = Number(r.annual_ret || 0);
  const maxDd = Number(r.max_drawdown || 0);
  const winRate = Number(r.win_rate || 0);
  const profitRatio = Number(r.profit_ratio || 0);

  $("#sc-bt-total-ret").textContent = totalRet.toFixed(2) + "%";
  $("#sc-bt-total-ret").className = "sc-stat-value " + (totalRet >= 0 ? "positive" : "negative");

  $("#sc-bt-annual-ret").textContent = annualRet.toFixed(2) + "%";
  $("#sc-bt-annual-ret").className = "sc-stat-value " + (annualRet >= 0 ? "positive" : "negative");

  $("#sc-bt-max-dd").textContent = maxDd.toFixed(2) + "%";

  $("#sc-bt-win-rate").textContent = winRate.toFixed(1) + "%";
  $("#sc-bt-win-rate").className = "sc-stat-value " + (winRate >= 50 ? "positive" : "");

  $("#sc-bt-profit-ratio").textContent = profitRatio.toFixed(2);
  $("#sc-bt-trade-count").textContent = r.trade_count || 0;

  if (!scBtChart) scBtChart = echarts.init($("#sc-bt-chart"));
  scBtChart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["策略净值", "基准收益"], textStyle: { color: "#8392ad" }, top: 0 },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    xAxis: { type: "category", data: r.dates, axisLine: { lineStyle: { color: "#1c2942" } }, axisLabel: { color: "#4d5d7d" } },
    yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "#1c2942" } }, axisLabel: { color: "#4d5d7d" } },
    series: [
      { name: "策略净值", type: "line", data: r.equity, smooth: true, showSymbol: false, lineStyle: { color: "#ff4d5f", width: 2 }, areaStyle: { color: "rgba(255,77,95,.08)" } },
      { name: "基准收益", type: "line", data: r.benchmark, smooth: true, showSymbol: false, lineStyle: { color: "#7c5cff", width: 1.5, type: "dashed" } },
    ],
  });
  setTimeout(() => scBtChart.resize(), 50);

  const rows = r.trades?.length
    ? r.trades.map((t) => {
        const ret = t.ret * 100;
        const cls = ret >= 0 ? "change-up" : "change-down";
        return `<tr>
          <td class="mono">${t.buy_date}</td>
          <td class="mono">${t.sell_date}</td>
          <td class="num mono">${fmt(t.buy_price, 4)}</td>
          <td class="num mono">${fmt(t.sell_price, 4)}</td>
          <td class="num mono ${cls}">${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%</td>
          <td class="num mono">${t.days}</td></tr>`;
      }).join("")
    : `<tr><td colspan="6" style="text-align:center;color:#4d5d7d">该区间内无交易信号</td></tr>`;
  $("#sc-bt-trades").innerHTML =
    `<thead><tr><th>买入日</th><th>卖出日</th><th class="num">买入价</th><th class="num">卖出价</th><th class="num">单次收益</th><th class="num">持天数</th></tr></thead><tbody>${rows}</tbody>`;
}

// ═══ 综合黄金行情 ══════════════════════════
let goldHistoryChart = null;

function loadGold(force) {
  fetch("/api/gold" + (force ? "?force=1" : ""))
    .then(r => r.json())
    .then(d => {
      renderGoldSpot(d.spot || []);
      renderGoldHistory(d.history_xau || [], d.history_source || "fallback_518880");
      const m = document.getElementById("gold-msg");
      if (m) { m.textContent = d.msg || ""; }
    })
    .catch(e => console.error("黄金加载失败", e));
}

function renderGoldSpot(spot) {
  const box = document.getElementById("gold-spot");
  if (!box) return;
  if (!spot.length) {
    box.innerHTML = `<div class="boards-empty">暂无黄金实时数据</div>`;
    return;
  }
  box.innerHTML = spot.map(s => {
    const pct = (s.pct == null ? 0 : Number(s.pct));
    const cls = pct > 0 ? "up" : (pct < 0 ? "down" : "flat");
    const sign = pct > 0 ? "+" : "";
    return `<div class="gold-col">
      <div class="gc-name">${s.name || '--'}</div>
      <div class="gc-price mono">${s.price == null ? '--' : s.price}</div>
      <div class="gc-pct mono ${cls}">${sign}${pct}%</div>
      <div class="gc-row"><span class="gc-lbl">日内高</span><span class="mono">${s.high == null ? '--' : s.high}</span></div>
      <div class="gc-row"><span class="gc-lbl">日内低</span><span class="mono">${s.low == null ? '--' : s.low}</span></div>
    </div>`;
  }).join("");
}

function renderGoldHistory(hist, source) {
  const labelEl = document.getElementById("gold-history-label");
  if (labelEl) {
    if (source === "XAUUSD") labelEl.textContent = "近30日 伦敦金 XAUUSD 走势（现货黄金，美元/盎司）";
    else if (source === "518880xratio") labelEl.textContent = "近30日 伦敦金近似走势（518880 × 系数折算，非真实伦敦金数据，仅供参考）";
    else labelEl.textContent = "近30日 黄金ETF 518880 走势（代理国内金价，非伦敦金 XAUUSD）";
  }
  const box = document.getElementById("gold-history-chart");
  if (!box) return;
  if (!hist.length) {
    box.innerHTML = `<div class="boards-empty" style="height:240px">暂无黄金历史数据</div>`;
    if (goldHistoryChart) { goldHistoryChart.dispose(); goldHistoryChart = null; }
    return;
  }
  if (!goldHistoryChart) goldHistoryChart = echarts.init(box);
  const dates = hist.map(x => x.date);
  const vals = hist.map(x => x.close);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const yMin = Math.floor(minV * 0.995 * 100) / 100;
  const yMax = Math.ceil(maxV * 1.005 * 100) / 100;
  const yInterval = Math.round((yMax - yMin) / 5 * 100) / 100;
  const isXau = (source === "XAUUSD" || source === "518880xratio");
  goldHistoryChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0d1226",
      borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: ps => {
        const p = ps?.[0];
        if (!p) return '';
        if (isXau) {
          return `<b>${p.axisValue}</b><br>${p.marker}伦敦金 XAUUSD 收盘：<span class="mono">${Number(p.value).toFixed(2)}</span> 美元/盎司`;
        } else {
          return `<b>${p.axisValue}</b><br>${p.marker}黄金ETF 518880 收盘：<span class="mono">${Number(p.value).toFixed(4)}</span> 元`;
        }
      }
    },
    grid: { left: 72, right: 20, top: 35, bottom: 40 },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: "#8a96b5", fontSize: 11, rotate: 30 },
      axisLine: { lineStyle: { color: "#2a3656" } }
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      interval: yInterval,
      name: isXau ? '收盘价（美元/盎司）' : '收盘价（元）',
      nameLocation: 'end',
      nameTextStyle: { color: '#8a96b5' },
      axisLabel: {
        color: "#8a96b5",
        fontSize: 11,
        formatter: isXau ? (v => Number(v).toFixed(2)) : (v => Number(v).toFixed(3))
      },
      splitLine: { lineStyle: { color: "#1c2540" } }
    },
    series: [{
      type: "line",
      data: vals,
      smooth: true,
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { width: 2, color: "#d4af37" },
      itemStyle: { color: "#ffcc66", borderColor: "#0d1526", borderWidth: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(212,175,55,.35)" },
          { offset: 1, color: "rgba(212,175,55,0)" }
        ])
      }
    }]
  }, true);
  goldHistoryChart.resize();
}

// ── 初始化 ─────────────────────────────
loadOverview();
loadConfig();