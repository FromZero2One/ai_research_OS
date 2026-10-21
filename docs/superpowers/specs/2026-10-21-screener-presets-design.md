# 设计文档：Screener 预设标准库（v1.5）

- 日期：2026-10-21
- 状态：已确认（对话中确认方向，本文档细化为可执行方案）
- 前置：LLM 智能选股器 v1（分支 `feat/llm-screener`，迁移 head `b5d2f8a3c6e1`）

## 目标

把选股标准从"一份静态 markdown"升级为**可组合的指标库**：
- 指标存在库里（带分类、数据来源、中文说明）
- 标准做成可编辑的预设模板（内置五套经典风格 + 用户自建）
- 触发时选择股票池 + 勾选 1-N 个预设 + 选组合方式
- 保留 criteria.md 作为"自由文本模式"入口

## 明确的决策（对话确认）

| 决策点 | 结论 |
|---|---|
| 指标存储 | 数据库表 `screener.metric_defs`（key、中文名、分类、数据来源、说明） |
| 标准模板 | `screener.criteria_presets`（内置 5 套不可删，可复制改；用户自建可删） |
| 触发选择 | 前端多选预设 + 独立选股票池 + 组合方式（union / intersection / flatten） |
| 并集排名语义 | 票数排名（满足几个标准集），报告注明每只命中哪些组合 |
| criteria.md | 保留为自由文本模式，与预设模式二选一 |
| LLM 翻译 | 预设模式**不走 LLM 翻译**（结构化数据直接组装规则 JSON）；仅自由文本模式走翻译 |

## 数据模型

```sql
-- 指标定义库（种子数据由迁移写入）
CREATE TABLE screener.metric_defs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(64) UNIQUE NOT NULL,          -- roe / net_margin / ...
    name_cn VARCHAR(128) NOT NULL,            -- 净资产收益率(%)
    category VARCHAR(32) NOT NULL,            -- profitability/solvency/cashflow/growth/size/snapshot
    data_source VARCHAR(32) NOT NULL,         -- snapshot / yjbb / balance_sheet / cash_flow
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 标准预设模板
CREATE TABLE screener.criteria_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    description TEXT,
    style_tag VARCHAR(32),                    -- value/growth/quality/cycle/turnaround/custom
    quant_rules JSONB NOT NULL,               -- [{metric, op, value, missing_data_policy}]
    qualitative JSONB NOT NULL DEFAULT '[]',  -- [string]
    suggested_pool VARCHAR(16) DEFAULT 'all',
    is_builtin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at/updated_at
);

-- 运行记录加列
ALTER TABLE screener.screener_runs
    ADD COLUMN preset_ids JSONB,              -- 本次使用的预设 id 列表
    ADD COLUMN combine_mode VARCHAR(16),      -- union/intersection/flatten
    ADD COLUMN pool_override VARCHAR(16),     -- 本次股票池（覆盖预设建议）
    ADD COLUMN mode VARCHAR(16) DEFAULT 'presets';  -- presets/freeform
```

迁移：新 revision `c8e1b7d4f2a9`（基于 `b5d2f8a3c6e1`）。

## 内置五套预设（迁移种子数据）

1. **核心资产**（core）— 巴菲特式：ROE>15、净利率>10、经营现金流>0、负债率<50、市值>300亿
2. **高成长**（growth）— 费雪式：ROE>12、净利率>8、市值>100亿 + 定性（渗透率提升/主业驱动/细分前二）
3. **深度价值**（value）— 格雷厄姆式：负债率<40、流动比率>2、现金流>0、市值>50亿 + 定性（现金充裕/非壳/无暴雷）
4. **质量价值 GARP**（garp）— 芒格式：ROE>15、净利率>12、负债率<55、现金流>0、市值>200亿 + 定性（持续性/护城河/无违规/股东回报）
5. **周期反转**（cycle）— 逆向：市值>150亿、负债率<65 + 定性（周期底部/龙头低成本/无产能包袱）

## 组合语义（关键逻辑）

### union（并集 + 票数排名，默认）
- 初筛：对每个预设独立跑量化规则 → 通过者合并（去重），记录每只命中的预设集合
- 排名：命中预设数降序 → 初筛得分均值降序 → 市值降序
- 深判：定性条目 = 各预设 qualitative 去重拼接，criteria_hits 标注来源预设
- 报告：候选注明"命中：GARP + 核心资产"

### intersection（交集）
- 只保留**同时通过所有已选预设量化规则**的股票（条件 AND）
- 定性条目全部拼接近行深判

### flatten（拉平）
- 把所有预设的 quant_rules 合并成一个列表全部 AND（等价于 intersection 但报告按单条规则统计吻合度，不按预设分组）

## API

```
GET    /screener/metrics                   # 指标库（按 category 分组）
GET    /screener/presets                   # 预设列表（内置+自建）
POST   /screener/presets                   # 新建 {name, description, style_tag, quant_rules, qualitative, suggested_pool}
PUT    /screener/presets/{id}              # 修改（内置→另存副本）
DELETE /screener/presets/{id}              # 仅自建
POST   /screener/runs
       {
         "mode": "presets" | "freeform",
         "pool": "all|main|chinext|star|watchlist",
         "preset_ids": ["..."],            # mode=presets 必填
         "combine": "union|intersection|flatten"
         # mode=freeform 时沿用现有 criteria.md 流程
       }
```

`translate` 步骤在 presets 模式下跳过（直接组装 rules dict），run.rules 记录组装结果 + 来源预设。

## 前端（Screener.vue 改造 + 新组件）

1. **触发区改造**：模式切换（预设组合 / 自由文本）
   - 预设模式：股票池下拉 + 预设多选卡片（勾选，显示风格标签）+ 组合方式单选
   - 自由文本模式：现有 markdown 编辑器
2. **预设管理页签**：卡片列表（名称/风格/条件摘要/启用开关），新建/编辑抽屉
3. **编辑抽屉**：量化规则行编辑（指标下拉按分类分组 + 数据来源徽标、操作符、阈值、缺数据策略），定性条目列表编辑
4. **报告增强**：候选行显示"命中预设"标签

## 非目标（本版不做）

- 指标公式自定义（新增指标 = 改代码 + 种子数据，不做 UI 建指标）
- 预设的版本历史/回滚
- 批量回测预设历史表现

## 风险与对策

- **组合后候选爆炸**：union 可能出很多候选 → 深判上限仍 50，票数排名天然收敛
- **旧 runs 兼容**：preset_ids 为 NULL 即 v1 自由文本运行，详情页正常显示
- **内置预设被改坏**：PUT 内置预设 → 强制另存副本（前端提示 + 后端 409→201）
