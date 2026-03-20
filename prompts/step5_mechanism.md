# Step 5: 提取机制证据（Mechanism Evidence）

你是一名医学信息学研究员。请仔细阅读论文全文，提取药物作用机制、生物标志物效应和核心结论。

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

- **evidence_id**: M1, M2, ...
- **drug_name**: 药物名称
- **relation**: inhibits / activates / modulates / binds / unclear
- **target.symbol**: 靶点符号（蛋白/基因名）
- **support.source**: 证据来源（如 "cited from [ref]", "this study"）
- **support.confidence**: high / moderate / low

仅提取论文中**明确提到**的靶点关系。如果论文是纯临床试验未讨论机制，此数组可以为空 `[]`。

### 5.2 biomarker_effects（生物标志物效应，可选）

提取干预对生物标志物的影响：

- **evidence_id**: M2, M3, ...（接续 target_actions 编号）
- **linked_estimate_id**: 如果该 biomarker 变化与 Step 4 中的某条 effect_estimate 直接对应，填写该 estimate_id；否则填 `null`
- **comparison_id**: 引用 Step 3 中的 comparison_id（如果可以对应的话）
- **biomarker.name**: 生物标志物名称
- **biomarker.unit**: 单位
- **timepoint**: 评估时间点
- **estimate_type**: mean_difference / percent_change / fold_change / etc.
- **value**: 效应值（必须来自论文原文）
- **ci**: 置信区间（如有）
- **p_value**: p 值（如有）
- **direction**: increase / decrease / no_change / unclear

### 5.3 claims（核心结论，必填）

提取论文的**核心结论**（通常 1-3 条）：

- **claim_id**: MC1, MC2, ...
- **text**: 结论性描述（贴近原文语义，可轻度标准化）
- **scope**: clinical efficacy / safety / mechanism / biomarker / pharmacokinetics / unclear
- **confidence**: high / moderate / low / unclear

优先提取来源：
- Abstract 结论部分
- Discussion 的核心结论
- Conclusion 段落

## ⚠️ 硬匹配规则

> biomarker_effects 中的 value、ci、p_value 必须能在论文原文中找到。
> 不要推断或计算。如果只有描述性结论（如 "drug reduced CRP"），不需要填数值字段。

## linked_estimate_id 填写规则

- 如果 biomarker_effect 本质上就是 Step 4 中某条 estimate 的生物标志物版本 → 填写对应 estimate_id
- 如果只是 Discussion 中的机制描述，无法明确对应某条 estimate → 填 `null`
- **不要强行关联**

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

不要输出任何 JSON 以外的内容。

---

## 论文原文

{paper_text}
