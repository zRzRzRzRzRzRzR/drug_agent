# Step 5: 提取机制证据（Mechanism Evidence）

你是一名医学信息学研究员。请仔细阅读论文全文，提取药物作用机制、生物标志物效应和核心结论。

## 字段级标注规范

以下是该步骤涉及字段的详细标注规范（来自 schema_annotation.json）：

{annotation_guidance}

## 上游已提取的数据

### 试验结构（Step 3）

```json
{structure_context}
```

### 效应估计（Step 4）

```json
{effects_context}
```

## 任务

### 5.1 target_actions（药物靶点作用，可选）

提取论文中提到的药物-靶点关系：

- **action_id**: **必须使用 TA1, TA2, ... 前缀**（不要用 M1, M2）
- **drug_name**: 药物名称
- **target**: 靶点符号（蛋白/基因名）
- **action_type**: **必须从以下枚举中选择**：
  - `"inhibitor"` — 不要写 "inhibits"
  - `"agonist"` — 不要写 "activates"
  - `"antagonist"` — 不要写 "blocks"
  - `"modulator"` — 不要写 "modulates"
  - `"unclear"`
- **evidence_source**: 证据来源（如 "abstract", "introduction", "discussion"）

仅提取论文中**明确提到**的靶点关系。如果论文是纯临床试验未讨论机制，此数组可以为空 `[]`。

### 5.2 biomarker_effects（生物标志物效应，可选）

提取干预对生物标志物的影响：

- **biomarker_id**: **必须使用 B1, B2, ... 前缀**（不要用 M2, M3）
- **name**: 生物标志物名称
- **effect**: increase / decrease / no_change / unclear
- **notes**: 补充说明

**⚠️ 收录范围规则**：
- 仅收录论文中明确出现的 biomarker 变化
- 不收录纯背景知识或教科书式药理介绍
- 若某指标已在 outcomes 或 effect_estimates 中完整表达，mechanism_evidence 仅保留解释性或总结性部分

### 5.3 claims（核心结论，必填）

提取论文的**核心结论**（通常 1-3 条）：

- **claim_id**: **必须使用 MC1, MC2, ... 前缀**
- **text**: 结论性描述（贴近原文语义，可轻度标准化）
- **scope**: **必须为以下单一值之一**（不可写多个用逗号分隔）：
  - `"clinical efficacy"` / `"safety"` / `"mechanism"` / `"biomarker"` / `"pharmacokinetics"` / `"unclear"`
  - 如果一条结论同时涉及疗效和安全性，**拆分为两条 claim**
- **confidence**: high / moderate / low / unclear
  - high: 主要结果直接支持的 claim（如主要终点达到显著性差异）
  - moderate: 次要分析或探索性分析支持
  - low: 讨论推测、机制假说、小样本发现
  - **含 may, might, suggests 等推测性语言的 claim → 不应标记为 high**

**⚠️ 单臂试验的 claims**：
- 单臂试验没有 effect_estimates 时，claims 部分尤其重要
- 应提取论文的核心结论，包括：response rate、survival、safety profile 等描述性结论

优先提取来源：
- Abstract 结论部分
- Discussion 的核心结论
- Conclusion 段落

## ⚠️ 硬匹配规则

> biomarker_effects 中的数值字段必须能在论文原文中找到。
> 不要推断或计算。

## ⚠️ ID 格式规则（严格）

| 实体 | ID 前缀 | 示例 |
|------|---------|------|
| target_actions | TA | TA1, TA2 |
| biomarker_effects | B | B1, B2 |
| claims | MC | MC1, MC2 |

**绝对不要使用 M1, M2 作为 target_actions 的 ID。**

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

不要输出任何 JSON 以外的内容。

---

## 论文原文

{paper_text}
