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
    if (t.dataset.page === "overview") loadOverview();
    if (t.dataset.page === "watch") loadWatch();
    if (t.dataset.page === "sentiment") { loadSentiment(); loadLowNext(); }
    if (t.dataset.page === "screener") loadScreener();
    if (t.dataset.page === "rules") loadScreenRules();
  });
});

// ── 时钟 ──────────────────────────────
function tick() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  $("#clock").textContent = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
setInterval(tick, 1000); tick();

// ═══ 市场概览（首页） ═══════════════════
async function loadOverview(force) {
  try {
    const o = await fetch("/api/overview" + (force ? "?force=1" : "")).then((x) => x.json());
    renderIndexStrip(o);
    renderOverviewSentiment(o.sentiment, o.trade_date);
    renderZt(o.zt_pool || [], o.ladder || []);
    renderZbDt(o.zb_pool || [], o.dt_pool || []);
    renderBoards(o.boards || { industry: [], concept: [] });
  } catch (e) {
    console.error("概览加载失败", e);
  }
  loadIndexKline();
  loadLiangneng();
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
$("#ov-refresh").addEventListener("click", () => loadOverview(true));

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
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis", backgroundColor: "#0d1226", borderColor: "#1c2540",
      textStyle: { color: "#c6d2ef", fontSize: 12 },
      formatter: (ps) => {
        const p = ps && ps[0];
        return p && p.value != null ? `<b>${p.axisValue}</b><br>${p.marker}预测量能：${p.value}%` : "";
      },
    },
    grid: { left: 52, right: 20, top: 26, bottom: 28 },
    xAxis: {
      type: "category", data: intra.map((x) => x.time), boundaryGap: false,
      axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9", interval: 30 },
    },
    yAxis: {
      type: "value", axisLabel: { color: "#8ba0c9", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#16203a" } },
    },
    series: [{
      name: "预测量能", type: "line", data: intra.map((x) => x.chg), smooth: true, symbol: "none",
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
  lastTrend = t;
  renderEmotionChart(t);
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
window.addEventListener("resize", () => { if (emotionChart) emotionChart.resize(); if (lowNextChart) lowNextChart.resize(); if (ikChart) ikChart.resize(); if (liangnengChart) liangnengChart.resize(); });

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
        return `<b>${fmtDate(it.date)}</b> 冰点(情绪${sc ?? "?"})<br>次日 ${fmtDate(it.next_date)}：${ret}%`;
      },
    },
    grid: { left: 48, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "category", data: items.map((it) => fmtDate(it.date)), axisLine: { lineStyle: { color: "#2a3550" } }, axisLabel: { color: "#8ba0c9", interval: "auto" } },
    yAxis: { type: "value", axisLabel: { color: "#8ba0c9", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#16203a" } } },
    series: [{
      type: "bar", data: items.map((it) => it.ret), barMaxWidth: 20,
      itemStyle: { color: (p) => (p.value >= 0 ? "#ff4d5f" : "#00d68f") },
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
async function loadWatch() {
  await loadConfig();
  const codes = CONFIG.watchlist.map((w) => w.code);
  const q = await fetch("/api/quotes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ codes }) }).then((x) => x.json());
  const idx = await fetch("/api/quotes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ codes: ["sh000001", "sz399001", "sz399006", "sh000300"] }) }).then((x) => x.json());
  renderIndex(idx);
  renderWatch(q);
  $("#w-time").textContent = new Date().toLocaleString();
}

function renderIndex(idx) {
  const order = ["sh000001", "sz399001", "sz399006", "sh000300"];
  $("#w-index").innerHTML = order.map((c) => {
    const q = idx[c]; if (!q) return "";
    return `<div class="stat"><div class="lbl">${q.name}</div>
      <div class="num ${colorClass(q.change_pct)}">${fmt(q.price)}</div>
      <div class="lbl ${colorClass(q.change_pct)}">${q.change_pct > 0 ? "+" : ""}${fmt(q.change_pct)}%</div></div>`;
  }).join("");
}

function renderWatch(q) {
  const tb = $("#w-tbody");
  tb.innerHTML = CONFIG.watchlist.map((w) => {
    const qq = q[w.code]; if (!qq) return `<tr><td>${w.name || w.code}</td><td class="mono">${w.code}</td><td colspan="4" style="color:#4d5d7d">数据缺失</td></tr>`;
    return `<tr><td>${qq.name || w.name}</td><td class="mono">${w.code}</td>
      <td class="num mono">${fmt(qq.price, 3)}</td>
      <td class="num mono ${colorClass(qq.change_pct)}">${qq.change_pct > 0 ? "+" : ""}${fmt(qq.change_pct)}%</td>
      <td class="num mono">${fmt(qq.amount_yi)}</td>
      <td class="num mono">${fmt(qq.turnover_pct)}%</td></tr>`;
  }).join("");
}
$("#w-refresh").addEventListener("click", loadWatch);

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

// ── 初始化 ─────────────────────────────
loadOverview();
loadConfig();
loadWatch();