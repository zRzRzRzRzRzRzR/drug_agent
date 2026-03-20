# Step 3: 提取试验结构（治疗方案、分组、比较关系）

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取完整的试验结构信息。

## 上游已提取的 PICO 信息

以下是 Step 2 提取的 PICO 数据，请确保你的提取与之一致：

```json
{pico_context}
```

## 任务

### 3.1 regimens（治疗方案）

每个 regimen 表示一个具体治疗方案，包含一个或多个 components：

- **regimen_id**: R1, R2, ...
- **label**: 方案描述
- **components**: 每个 component 包含：
  - **component_id**: RC1, RC2, ...
  - **kind**: drug / procedure / behavioral / device / other
  - **drug_name**: 药物通用名
  - **dose**: value + unit（如 `{"value": 10, "unit": "mg"}`）
  - **frequency**: code + label（如 `{"code": "QD", "label": "once daily"}`）
  - **route**: oral / intravenous / subcutaneous / etc.
  - **duration**: value + unit（如 `{"value": 24, "unit": "week"}`）
- **regimen_notes**: 补充说明

### 3.2 arms（研究分组）

- **arm_id**: A1, A2, ...
- **label**: 分组描述
- **type**: experimental / active_comparator / placebo_comparator / standard_of_care / control / unclear
- **regimen_id**: 对应 regimen 的 ID（必须是上面定义的 R1/R2/...）
- **sample_size**: 该组样本量

### 3.3 analysis_groups（可选）

用于池化/合并分组的情况：
- **group_id**: G1, G2, ...
- **label**: 描述
- **member_arm_ids**: 包含哪些 arm
- **pooling_method**: 池化方法说明

如果不需要合并分组，保留空数组 `[]`。

### 3.4 comparisons（比较关系）

- **comparison_id**: C1, C2, ...
- **treatment**: `{"ref_type": "arm", "ref_id": "A1"}`（引用 arm 或 group）
- **control**: `{"ref_type": "arm", "ref_id": "A2"}`（引用 arm 或 group）
- **population_id**: 对应分析人群（如 P1）
- **analysis_set**: intent-to-treat / per-protocol / etc.
- **timepoint**: 时间点
- **model_spec**: 统计模型说明

---

## ⚠️ 硬匹配规则

> 所有数值字段（dose value、duration value、arm sample_size）必须能在论文原文中找到。
> **不要推断或计算**。如果论文说 "10 mg or 25 mg" 就写两个 regimen，不要合并。

---

## 📋 多剂量探索试验的特殊处理

> **适用于**：Phase 1 dose-finding / dose-escalation、含多个剂量 cohort 的试验。

### Regimen 粒度
- **每个不同的剂量/频率方案 = 一个独立的 regimen**
  - 例如：inclisiran 25mg single dose = R1, 100mg single dose = R2, 300mg monthly×2 = R3, ...
  - placebo 也应按 phase 分开：single-dose phase placebo = 一个 regimen，multiple-dose phase placebo = 另一个 regimen
- 如果同一剂量有 with statin 和 without statin 两个 cohort，视为**同一 regimen 不同 arm**（statin 是背景治疗，不是 regimen 组成部分），或视为两个不同的 arm with regimen_notes 区分

### Arm 粒度
- **每个剂量 cohort = 一个独立的 arm**
  - 论文 Table 1/2/3 中的每个列（N=3, N=6 等）对应一个 arm

### Placebo pooling
- 如果论文明确说 "data from participants in the placebo group were combined across cohorts for analysis"：
  - 仍然为每个 phase 的 placebo 建一个 arm（如 A_placebo_single, A_placebo_multi）
  - 使用 `analysis_groups` 建一个 pooled placebo group（如 G1），并标注 member_arm_ids 和 pooling_method
  - comparison 的 control 可以引用该 group：`{"ref_type": "group", "ref_id": "G1"}`
- 如果论文没有 pooling：每个 placebo arm 直接作为 comparison 的 control

### Comparison 粒度（关键）
- **每个剂量 cohort vs 对应 placebo = 一个独立的 comparison**
  - 例如：C1 = 25mg vs placebo, C2 = 100mg vs placebo, C3 = 300mg vs placebo, ...
  - 对于 multiple-dose phase（with/without statin 的 cohort），每个 cohort vs pooled placebo 各一个 comparison
- **不要把多个剂量合并成一个 comparison**。论文 Table 2/3 中的每一列对应一个 comparison。

### population_id 对齐
- single-dose phase 的 comparison → 引用 Step 2 中 single-dose phase 的 population_id
- multiple-dose phase 的 comparison → 引用 Step 2 中 multiple-dose phase 的 population_id

---

## 一致性检查

- 每个 arm.regimen_id 必须指向已定义的 regimen
- 每个 comparison.treatment.ref_id 和 control.ref_id 必须指向已定义的 arm 或 group
- comparison.population_id 应来自 PICO 中已定义的 population_id

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

不要输出任何 JSON 以外的内容。

---

## 论文原文

{paper_text}
