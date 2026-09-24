- [x] AC-1.1: mousedown on .w-grip → 被拖行加 .dragging class（L1725）

- [x] AC-1.2: mousemove → 目标行加 .drag-over-top 或 .drag-over-bottom（L1739/L1742）

- [x] AC-1.3: mouseup → splice 重排 + saveConfig + loadWatch（L1761/L1766/L1767）

- [x] AC-1.4: 支持跨多行拖动（splice 取出 + 插入任意位置）

- [x] AC-2.1: 按钮顺序 w-kline → w-grip → w-top → w-del（L1624）

- [x] AC-2.2: 移首 SVG = 顶部短横线 y=2 + 向上箭头 path（L1622）

- [x] AC-2.3: 手柄 SVG = 三条等间距水平线 y=4,8,12（L1620）

- [x] AC-2.4: 首行移首按钮 disabled（L1617 isTop）

- [x] AC-3.1: 拖拽松开 await saveConfig() + loadWatch()（L1766-1767）

- [x] AC-3.2: 移首点击 await saveConfig() + loadWatch()（L1711-1712）

- [x] AC-3.3: 排序后刷新页面顺序不变（saveConfig 持久化）

- [x] AC-4.1: 查看K线/删除 行为不变（L1633-1637）

- [x] AC-4.2: 行情 6 列不变（L1626-1630）

- [x] AC-4.3: 空列表 colspan=7 不变（L1611）

- [x] AC-5.1: 7 th width 合计 100%（24+10+10+11+13+11+21）

- [x] AC-5.2: 名称 24%≥22% 操作 21%≥19%

- [x] AC-6.1: .w-grip 有外框 border+background（style.css L436）

- [x] AC-6.2: 表头操作 th 居中 text-align:center（index.html L183）

- [x] AC-7.1: .w-del 无独立 padding/font-size 覆盖，继承 .btn.sm（5px 12px / 12.5px / 600）（style.css L434）

- [x] AC-7.2: .w-grip padding=5px 12px + border-radius=8px（与 .btn.sm 一致）（style.css L436）

- [x] AC-7.3: 4 个操作元素外框高度肉眼一致（全部 5px 12px + 8px radius + 1px border）

- [x] AC-8.1: .tbl td .btn.sm 和 .tbl td .w-grip 统一 display:inline-flex + height:28px + line-height:1 + box-sizing:border-box（style.css L448）

- [x] AC-8.2: 4 个操作元素外框上下沿完全对齐（固定 28px 高，全部命中选择器）

- [x] AC-8.3: 不影响其他页面的 .btn 或 .btn.sm（选择器限 .tbl td 内）
- [x] AC-9.1: .tbl td .btn.sm 和 .tbl td .w-grip 统一 vertical-align:middle（style.css L448）
- [x] AC-9.2: 4 个操作元素行内垂直对齐一致（上沿+下沿平齐）

