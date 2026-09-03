# Checklist

## Task 1: 情绪数据口径修正

- [x] Checkpoint 1: 测试乐咕 API 返回数据
  - [x] 1.1 打印 `legu.fetch_legu_history(force=True)` 返回的 `rows[-1]` 日期和数据
  - [x] 1.2 确认 `rows[-1]` 是当日（20260902）数据，zt_count=52（口径正确）
  - [x] 1.3 根因定位：乐咕缓存早盘不含当日数据时 `rows[-1]` 是前一日，原代码不校验日期就置 `legu_ok=True`

- [x] Checkpoint 2: 情绪数据修正
  - [x] 2.1 新增 `_filter_zt_pool(zt_list)` 函数（L128-158），过滤 ST/*ST 和上市不足 60 日新股
  - [x] 2.2 `get_sentiment()` 仅在 `rows[-1].get("date") == date` 时采用乐咕数据，否则回退东财过滤后涨停池
  - [x] 2.3 东财涨停池过滤后 `zt_count` 约 52（原 83）
  - [x] 2.4 `max_height` 基于过滤后的涨停池重算（排除 ST/新股连板）

## Task 2: K线弹窗三 grid 布局

- [x] Checkpoint 3: renderWatchKline grid 调整
  - [x] 3.1 grid[0] height 改为 "50%"（L1766，原 "46%"）
  - [x] 3.2 grid[1] top 改为 "66%", height 保持 "15%"（L1767）
  - [x] 3.3 grid[2] top 改为 "83%", height 改为 "20%"（L1768，原 "15%"）
  - [x] 3.4 三段间距增大（1% 和 2%），KDJ 的 150 刻度不与成交量 x 轴重叠

## Task 3: 指数K线副图 Y 轴刻度

- [x] Checkpoint 4: renderIndexKline grid left 增大
  - [x] 4.1 grid[0] left 改为 65（L846，原 52）
  - [x] 4.2 grid[1] left 改为 65（L847，原 52）
  - [x] 4.3 yAxis[1] 的 `splitNumber: 3` 保持不变（L855）
  - [x] 4.4 成交量副图 Y 轴刻度数字完整显示（left 65 像素留足空间）

## 整体验证

- [x] Checkpoint 5: 不修改 app.py 和 core/legu.py
  - [x] 5.1 `git diff --name-only app.py core/legu.py core/emotion_history.py` 输出为空
  - [x] 5.2 `core/sentiment.py` 仅 `get_sentiment()` 函数 + 新增 `_filter_zt_pool()` 有改动
  - [x] 5.3 `static/app.js` 仅 `renderWatchKline` 和 `renderIndexKline` 两函数有改动
