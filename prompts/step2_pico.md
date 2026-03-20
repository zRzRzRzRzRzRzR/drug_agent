# Step 2: 提取 PICO（人群、干预、对照、结局）

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取完整的 PICO 信息。

## 任务

### 2.1 population（人群）

#### base_population（基础总体，P0）
- **description**: 纳入标准所定义的基础受试总体的自然语言描述
- **sample_size**: 基础总体总样本量（整数）
- **region**: 国家列表和大区（region 应填写标准化的大区名称，如 `"Europe"`、`"North America"`，不要留 null）
- **age**: 按论文原始报告方式填写（mean±SD 或 median(IQR) 或 range）
- **sex**: 百分比

#### analysis_populations（分析人群）
- ITT、mITT、PP、safety population 等
- 每个分析集一个对象，有唯一 population_id（P1, P2, ...）
- derived_from 指向来源总体（通常是 P0）
- 如果论文未区分分析集，可只填一个 P1

### 2.2 intervention（干预）
- **label**: 干预的自然语言概括
- **drug_list**: 涉及的主要药物成分
- **mapped_regimen_ids**: 暂时填 `[]`（Step 3 填充）

### 2.3 comparator（对照）
- **label**: 对照条件描述
- **type**: placebo / active comparator / standard of care / no treatment / unclear
- **mapped_regimen_ids**: 暂时填 `[]`（Step 3 填充）

### 2.4 outcomes（结局）
- 每个结局一个对象（O1, O2, O3...）
- **label**: 结局描述（贴近原文）
- **role**: primary / secondary / exploratory / safety / unclear
- **timepoint**: 观察时间点（label + value + unit）
- **polarity**: higher_better / lower_better / neutral / unclear
- **outcome_type**: continuous / binary / time-to-event / ordinal / count / unclear

---

## ⚠️ 硬匹配规则

> 所有数值字段（sample_size、age、sex percent、timepoint value）必须能在论文原文中找到对应的数字。
> **不要凭空捏造数值**。如果论文没有报告，填 `null`。

### 例外：允许的简单计算（必须注明来源）

以下情况允许从论文已报告的数字做**简单加法/减法**，但必须在 description 中注明：

1. **sample_size 加总**：如果论文以表格分组报告了每组样本量（如 Table 1 各列的 N），但没有直接给出总数，可以加总得到 base_population.sample_size。
   - 例如：Table 1 报告 Placebo N=6, Inclisiran 25mg N=3, 100mg N=3, ... → 加总得到总 N
   - 在 description 中注明 "sample size summed from Table 1"

2. **sex percent 互补**：论文报告了 male% 但没有 female%，可以用 100% − male%。

3. **其他数值一律不允许计算**。不要计算均值差、不要合并不同组的年龄统计量、不要反推 p 值。

---

## 📋 多阶段试验的特殊处理

> **适用于**：Phase 1 剂量探索（dose-finding / dose-escalation）、含 single-dose phase + multiple-dose phase 的试验、含多个独立分析队列的试验。

### base_population（P0）
- description：概括整个试验的纳入标准
- sample_size：所有阶段的总人数（可从 Table 1 加总）
- **age**：取所有阶段中**最宽的年龄范围**
  - 例如：single-dose phase 18-60 岁，multiple-dose phase 18-75 岁 → range_min=18, range_max=75
- region：所有阶段的研究地点合并

### analysis_populations — 按分析阶段拆分
- **每个独立分析阶段应建为一个 analysis_population**
  - 例如：
    - P1 = safety population（全部参与者）
    - P2 = single-dose phase pharmacodynamic population
    - P3 = multiple-dose phase pharmacodynamic population
- 每个 population 应有自己的 sample_size 和 age range（如果阶段之间不同）

### 判断标准：什么算"独立分析阶段"？
- 论文分别报告了各阶段的样本量 / 基线特征 / 结果 → **拆**
- placebo 在阶段内 pooled 分析 → **拆**
- 仅仅是亚组分析（按性别/年龄分层）→ **不拆**

---

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

注意：
- 对未知字段使用 `null`（不是空字符串）
- outcomes 数组按照论文中的 primary → secondary → exploratory → safety 顺序排列
- 不要输出任何 JSON 以外的内容

---

## 论文原文

{paper_text}
