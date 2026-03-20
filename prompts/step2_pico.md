# Step 2: 提取 PICO（人群、干预、对照、结局）

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取完整的 PICO 信息。

## 任务

### 2.1 population（人群）

#### base_population（基础总体，P0）
- **description**: 纳入标准所定义的基础受试总体的自然语言描述
- **sample_size**: 基础总体总样本量（整数）
- **region**: 国家列表和大区
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

## ⚠️ 硬匹配规则

> 所有数值字段（sample_size、age、sex percent、timepoint value）必须能在论文原文中找到对应的数字。
> **不要自行计算或推断数值**。如果论文没有报告，填 `null`。
> 例如：如果论文分别报告了各组年龄而非总体年龄，不要自己合并计算，填 `null` 并在描述中注明。

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

注意：
- 对未知字段使用 `null`（不是空字符串）
- outcomes 数组按照论文中的主要→次要→安全性顺序排列
- 不要输出任何 JSON 以外的内容

---

## 论文原文

{paper_text}
