# 推送规则页优化 Spec

## Why
当前推送规则页功能基础：规则仅支持单指标单条件、推送渠道仅飞书、规则列表只能删除重建无法编辑、缺少推送历史记录。需优化为支持组合条件、多渠道、规则编辑、推送历史，提升规则管理体验。

## What Changes
- 规则条件支持组合：单条规则支持多个子条件用 AND/OR 连接（当前仅单指标单条件）
- 推送渠道扩展：支持飞书、钉钉、企业微信三种 webhook（当前仅飞书）
- 规则列表支持内联编辑：点击规则行可展开编辑表单，无需删除重建
- 新增推送历史记录：记录最近 N 条推送的时间、规则名、触发指标值、推送结果
- 选股推送与规则推送统一管理：选股推送列表从当前独立卡片合并到规则列表中，用类型字段区分
- 规则列表增加「最后触发时间」列，方便查看规则活跃度

## Impact
- Affected code:
  - `app.py`：`/api/config` 支持新的规则结构（组合条件）、`/api/rules/check` 适配组合条件、新增 `/api/rules/history` 推送历史接口
  - `core/rules.py`：`check_rules` 支持组合条件评估（AND/OR）、增加多渠道发送
  - `core/notifier.py`：新增钉钉、企业微信 webhook 发送函数
  - `static/app.js`：规则列表渲染支持组合条件展示和内联编辑、推送历史渲染
  - `templates/index.html`：规则列表表格增加列、新增推送历史卡片、添加规则表单支持组合条件
  - `static/style.css`：组合条件展示、内联编辑表单样式

## ADDED Requirements

### Requirement: 组合条件规则
系统 SHALL 支持单条规则包含多个子条件，子条件间用 AND（全部满足）或 OR（任一满足）连接。每个子条件包含指标、比较符、阈值。

#### Scenario: 创建组合条件规则
- **WHEN** 用户创建规则时添加多个子条件并选择 AND/OR 逻辑
- **THEN** 规则保存组合条件，触发时按逻辑评估所有子条件

#### Scenario: 触发组合条件
- **WHEN** 市场指标满足规则的组合条件
- **THEN** 规则触发推送

### Requirement: 多渠道推送
系统 SHALL 支持飞书、钉钉、企业微信三种推送渠道，用户可为每条规则选择推送目标。

#### Scenario: 配置钉钉推送
- **WHEN** 用户在 webhook 配置中填写钉钉机器人 webhook 并选择钉钉为推送目标
- **THEN** 规则触发时推送消息到钉钉群

### Requirement: 推送历史记录
系统 SHALL 记录最近 100 条推送历史，包含推送时间、规则名称、触发指标值、推送渠道、推送结果（成功/失败）。

#### Scenario: 查看推送历史
- **WHEN** 用户在推送规则页查看推送历史卡片
- **THEN** 可见按时间倒序的推送历史列表，每条含时间、规则名、指标值、渠道、结果

## MODIFIED Requirements

### Requirement: 规则列表
原规则列表仅支持启用/禁用切换和删除。修改为：支持点击规则行展开内联编辑表单，可直接修改条件、阈值、冷却时间、提醒内容、推送渠道，保存后生效。列表增加「最后触发时间」列。

#### Scenario: 编辑规则
- **WHEN** 用户点击规则列表中某行
- **THEN** 展开内联编辑表单，修改后点击保存即更新规则

### Requirement: 规则数据结构
原规则结构为 `{name, metric, op, value, message, cooldown_minutes, enabled}`。修改为：`{name, conditions: [{metric, op, value}], logic: "and"/"or", channel: "feishu"/"dingtalk"/"wecom", message, cooldown_minutes, enabled}`。向后兼容：单条件规则自动转换为 conditions 数组。

#### Scenario: 旧规则兼容
- **WHEN** 加载已有单条件规则
- **THEN** 自动转换为 conditions 数组格式，logic 默认 "and"，channel 默认 "feishu"
