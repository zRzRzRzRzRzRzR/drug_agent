# Step 4: 提取效应估计（Effect Estimates）

你是一名医学信息学研究员。请仔细阅读论文全文，提取所有报告的效应估计值。

## 上游已提取的数据

### PICO（Step 2）

```json
{pico_context}
```

### 试验结构（Step 3）

```json
{structure_context}
```

## 任务

对于论文中报告的**每一个统计效应结果**，提取一条 effect_estimate。

### 字段说明

- **estimate_id**: E1, E2, E3, ...
- **comparison_id**: 必须引用 Step 3 中定义的 C1/C2/...
- **outcome_id**: 必须引用 Step 2 中定义的 O1/O2/...
- **population_id**: 必须引用 Step 2 中定义的 P0/P1/P2/...
- **analysis_set**: intent-to-treat / per-protocol / safety population / etc.（或 null）
- **timepoint**: 效应评估的时间点
- **estimate_type**: mean_difference / risk_ratio / odds_ratio / hazard_ratio / risk_difference / rate_ratio / unclear
- **value**: 效应估计值（必须是论文中报告的数字）
- **ci**: 置信区间 `{"lower": ..., "upper": ..., "level": 95}`
- **p_value**: p 值（必须是论文中报告的数字，不要反推）
- **direction**: treatment_better / control_better / no_significant_difference / inconclusive / unclear
- **effect_notes**: 补充说明（如 non-inferiority, per-protocol sensitivity analysis 等）

### 枚举规则

1. **逐行扫描每个 Table**：如果某行报告了效应值/CI/p值，就是一条 estimate
2. **扫描 Figure**：森林图中的每个 OR/HR，每个效应值一条 estimate
3. **包含不显著结果**：p > 0.05 的也要提取，direction 标为 no_significant_difference
4. **亚组分析**：总体一条 + 每个亚组一条，使用不同的 population_id 或在 effect_notes 中说明
5. **主要结局 + 次要结局 + 安全性终点**：全部都要

## ⚠️ 硬匹配规则（最严格）

> **value、ci.lower、ci.upper、p_value 中的每个数字必须能在论文原文中找到。**
>
> 违反此规则的值将被自动清零。
>
> - 不要自行计算差值（如论文只报告了组均值而未报告均值差，value 填 null）
> - 不要反推 p 值（如果论文只说 "significant"，p_value 填 null）
> - 百分比变化 ≠ 绝对差值
> - fold-change ≠ regression coefficient

## 输出格式

输出严格 JSON **数组**，每个元素是一条 estimate，结构如下：

```json
{estimate_skeleton}
```

输出一个 JSON 数组（`[{...}, {...}, ...]`），不要输出任何 JSON 以外的内容。

---

## 论文原文

{paper_text}
