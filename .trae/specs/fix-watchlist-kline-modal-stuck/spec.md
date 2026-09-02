# 修复自选K线弹窗卡住 Spec（fix-watchlist-kline-modal-stuck）

## Why
`templates/index.html` 中 `<script src="/static/app.js">` 在 L443，而 Modal 容器 `#wk-modal` 在 L446-462（位于 script 之后）。脚本执行到 `document.getElementById("wk-modal").addEventListener("click", ...)` 时，`#wk-modal` 还未渲染，`getElementById` 返回 null，调用 `null.addEventListener` 抛 `TypeError: Cannot read properties of null`。该错误中断了 app.js 后续所有事件绑定代码执行，导致 Modal 内的「关闭按钮 / ESC / 档位切换（60/120/250 日）」全部失效——这就是用户反馈"卡住、点击无响应"的根因。

## What Changes
- **把 Modal 容器从 script 之后移到 script 之前**：调整 `templates/index.html`，将 `#wk-modal` 的整段 DOM（L445-462）移到 `<script src="/static/app.js">`（L443）之前，保证脚本执行时 DOM 已就绪
- **追加 DOMContentLoaded 防御性包裹**（可选鲁棒性增强）：在 `static/app.js` 中把 Modal 相关的事件绑定代码（遮罩点击、关闭按钮、ESC、档位切换、window resize）用 `DOMContentLoaded` 包裹一层，作为防御性兜底，避免未来类似时序问题
- **充分测试**：确认修复后 Modal 打开/关闭/档位切换全部响应正常，且其他页面功能（指数K线、选股、提醒规则等）不受影响

## Impact
- Affected code:
  - `templates/index.html`：调整 Modal 容器 DOM 位置
  - `static/app.js`：可选追加 DOMContentLoaded 包裹（不强制，方案 A 已足够）
- Non-affected: 后端 `app.py` / `core/*` 零改动

## ADDED Requirements

### Requirement: Modal DOM 必须在 app.js 加载之前就绪
`templates/index.html` 中 `#wk-modal` 整段 DOM SHALL 出现在 `<script src="/static/app.js">` 标签之前，保证脚本顶层执行 `document.getElementById("wk-modal")` 能拿到非 null 节点，所有事件绑定代码能正常执行。

#### Scenario: 页面加载后所有 Modal 事件可用
- **WHEN** 用户打开页面，等待 app.js 加载完成
- **THEN** 点击自选表「查看K线」按钮后 Modal 弹出
- **AND** 点击遮罩层空白处能关闭
- **AND** 点击右上角 ✕ 能关闭
- **AND** 按 ESC 能关闭
- **AND** 点击「近 60 日 / 近 120 日 / 近 250 日」能切换档位并重新加载 K 线
- **AND** 浏览器 console 无 `TypeError: Cannot read properties of null` 错误

### Requirement: 其他页面功能不受影响
修复 Modal 位置时，不改动其他 DOM 节点位置和 script 加载顺序，所有原有功能（指数K线、指数走势对比、市场概览情绪卡片、选股、提醒规则、回测等）保持正常。

#### Scenario: 其他功能验证
- **WHEN** 修复后访问各页面
- **THEN** 指数K线卡片加载正常、档位切换正常
- **AND** 选股页策略列表加载正常
- **AND** 提醒规则页添加/检查功能正常
- **AND** 浏览器 console 全程无新错误

## Constraints
- **后端零改动**：不修改 `app.py` / `core/*`
- **不回滚其他改动**：仅调整 Modal DOM 位置，不撤销之前的 `add-watchlist-kline-modal` 实现
- **最小改动原则**：优先方案 A（移动 DOM 位置），如该方案能彻底修复问题，则不强制追加 DOMContentLoaded 包裹，避免过度设计
