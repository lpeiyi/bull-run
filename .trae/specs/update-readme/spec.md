# 更新 README.md Spec

## Why
项目经历多轮迭代（情绪 tab 融入概览、sent-card 删除、contrib 五维度修复、黄金行情区块新增、escapeHtml 修复等），但 README.md 仍停留在旧版结构（5 个 tab、仪表盘/涨停梯队/炸板池等已删区块、六维情绪数据、缺少 gold.py 等模块），需要全面梳理代码现状并同步更新，使文档与实际代码保持一致。

## What Changes
- 修正页面结构：5 个 tab → 3 个 tab（市场概览 / 智能选股 / 推送规则），原「市场情绪」tab 已融入概览，原「自选看板」tab 是概览页内区块
- 修正市场概览区块：删除已不存在的「情绪仪表盘」「涨停梯队」「炸板/跌停池」「热点概念」描述，新增 4 张情绪专区卡片描述（短线情绪+contrib五维度条形图 / 等级说明 / 走势大图 / 低点次日表现）
- 修正情绪分维度：六维 → 五维度贡献条（涨停家数 / 连板高度 / 晋级率 / 炸板率 / 跌停惩罚）
- 更新项目结构：补充 `core/gold.py`、`core/notifier.py`、`core/tdx.py` 等模块描述，修正 `app.py` 功能描述
- 新增黄金行情区块描述
- 修正配置文件说明：`config.json` 改为 `config.example.json` 示例 + `config.json` 实际使用
- 更新数据来源表：补充黄金数据来源

## Impact
- Affected specs: 无（纯文档更新）
- Affected code: `README.md`（唯一修改文件）

## MODIFIED Requirements
### Requirement: README.md 与代码现状一致
README.md SHALL 准确反映当前项目的页面结构（3 个 tab）、功能区块（概览页含情绪专区 4 卡片）、情绪分五维度贡献条、项目结构（含所有 core 模块）、数据来源和配置说明。

#### Scenario: 用户阅读 README 了解项目
- **WHEN** 用户打开 README.md
- **THEN** 能看到与实际代码一致的 tab 结构、功能区块列表、项目结构树、数据来源表
- **AND** 不存在已删除功能的描述（如仪表盘、涨停梯队、5 个 tab）
