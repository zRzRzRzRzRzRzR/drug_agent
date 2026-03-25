# Step 3: 提取试验结构（治疗方案、分组、比较关系）

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取完整的试验结构信息。

## 字段级标注规范

以下是该步骤涉及字段的详细标注规范（来自 schema_annotation.json）：

{annotation_guidance}

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
  - **component_id**: RC1, RC2, ...（全局唯一，不同 regimen 之间也不重复）
  - **kind**: drug / procedure / behavioral / device / other
  - **drug_name**: 药物通用名
  - **dose**: value + unit
  - **frequency**: code + label（code 仅限 QD/BID/TID/QID/PRN；weekly/monthly 等非每日频率 code 填 null，label 保留原文）
  - **route**: oral / intravenous / subcutaneous / etc.
  - **duration**: value + unit
- **regimen_notes**: 补充说明

**⚠️ Placebo regimen 的 drug_name**：
- Placebo regimen 的 component drug_name 应填 "placebo"，**不要填成试验药物名**
- 例如：如果 R1 是 placebo arm 的 regimen，drug_name = "placebo"

**⚠️ 剂量递增试验**：
- 如果试验药物有起始剂量 + 可选递增剂量（如 25mg → optional 50mg），需要建一个 regimen，dose 填起始剂量，在 regimen_notes 中说明递增规则

### 3.2 arms（研究分组）

- **arm_id**: A1, A2, ...
- **label**: 分组描述
- **type**: experimental / active_comparator / placebo_comparator / standard_of_care / control / unclear
- **regimen_id**: 对应 regimen 的 ID
- **sample_size**: 该组样本量

### 3.3 analysis_groups（可选）

如果不需要合并分组，保留空数组 `[]`。

### 3.4 comparisons（比较关系）

- **comparison_id**: C1, C2, ...
- **treatment**: `{"ref_type": "arm", "ref_id": "A1"}`
- **control**: `{"ref_type": "arm", "ref_id": "A2"}`
- **population_id**: 对应分析人群
- **analysis_set**: intent-to-treat / per-protocol / etc.
- **timepoint**: 时间点
- **model_spec**: 统计模型说明

**⚠️ 单臂试验处理**：
- 若上游 PICO 中 comparators = []（单臂试验），则 comparisons 也应为空数组 `[]`
- 不要凭空构造 comparison

---

## ⚠️ 硬匹配规则

> 所有数值字段（dose value、duration value、arm sample_size）必须能在论文原文中找到。
> **不要推断或计算**。

---

## 📋 多剂量探索试验的特殊处理

> **适用于**：Phase 1 dose-finding / dose-escalation。

### Regimen 粒度
- **每个不同的剂量/频率方案 = 一个独立的 regimen**

### Arm 粒度
- **每个剂量 cohort = 一个独立的 arm**

### Comparison 粒度
- **每个剂量 cohort vs 对应 placebo = 一个独立的 comparison**
- **不要把多个剂量合并成一个 comparison**

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
