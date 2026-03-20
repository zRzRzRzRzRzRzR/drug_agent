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
- **control**: `{"ref_type": "arm", "ref_id": "A2"}`
- **population_id**: 对应分析人群（如 P1）
- **analysis_set**: intent-to-treat / per-protocol / etc.
- **timepoint**: 时间点
- **model_spec**: 统计模型说明

## ⚠️ 硬匹配规则

> 所有数值字段（dose value、duration value、arm sample_size）必须能在论文原文中找到。
> **不要推断或计算**。如果论文说 "10 mg or 25 mg" 就写两个 regimen，不要合并。

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
