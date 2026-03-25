# Step 4: 提取效应估计（Effect Estimates）

你是一名医学信息学研究员。请仔细阅读论文全文，提取所有报告的效应估计值。

## 字段级标注规范

以下是该步骤涉及字段的详细标注规范（来自 schema_annotation.json）：

{annotation_guidance}

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

对于论文中报告的统计效应结果，提取 effect_estimate。

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
- **effect_notes**: 补充说明

**⚠️ 单臂试验处理**：
- 若上游 trial_structure 中 comparisons = []（单臂试验），则 effect_estimates 也应为空数组 `[]`
- 单臂试验的描述性结果（如 response rate、median survival）应记入 Step 5 的 mechanism_evidence.claims
- **不要为单臂试验凭空创建 effect estimates**

---

## 📋 提取范围控制（重要）

### 必须提取（核心指标）
- 论文标为 **primary endpoint** 的结局 → 每个 comparison × primary outcome 各一条
- 论文标为 **key secondary endpoint** 的结局 → 每个 comparison × key secondary outcome 各一条

### 应该提取
- 其他 secondary endpoint，如果论文报告了具体数值和显著性
- 安全性终点的组间比较，如果论文报告了 risk ratio 或 p 值

### 不要逐一展开的（记入 mechanism_evidence 即可）
- 标记为 **exploratory** 的指标
  - **除非**论文在正文 Results 中用单独段落重点讨论了该指标的组间差异

### 数量预期
- 标准 RCT（2-3 arms, 2-5 outcomes）：通常 3-10 条 estimates
- Phase 3 多终点：通常 5-20 条 estimates
- Phase 1 多剂量探索：每个剂量 cohort × 核心指标，通常 10-25 条 estimates
- **如果你发现自己生成了 30+ 条 estimates，请检查是否把 exploratory lipids 全部展开了**

---

## 📋 Phase 1 / 多剂量探索的特殊处理

### estimate 的 value 来源
- Table 中通常有两行：
  - "Percent change (95% CI)" → 各组绝对变化，**不是** between-group difference
  - "Difference (percentage points)" → vs placebo 差异，**这才是** effect estimate 的 value
- **value 应来自 "Difference" 行**

### p_value 的处理
- 论文 Table 注释通常会说 "†P<0.05, ‡P<0.001, §P<0.01" 等
- 有标记且注释说 ‡P<0.001 → p_value 填 `0.001`（取上界）
- **没有任何标记** → p_value 填 `null`

### direction 判定
- 有显著性标记 + 效应方向与 outcome.polarity 一致 → "treatment_better"
- 有显著性标记 + 效应方向与 outcome.polarity 相反 → "control_better"
- p > 0.05 或明确写 "not significant" → "no_significant_difference"
- 没有显著性标记，也没有 p 值 → "inconclusive"
- 无法判断 → "unclear"

---

## ⚠️ 硬匹配规则（最严格）

> **value、ci.lower、ci.upper、p_value 中的每个数字必须能在论文原文中找到。**
>
> 违反此规则的值将被自动清零。
>
> - 不要自行计算差值
> - 不要反推 p 值
> - 百分比变化 ≠ 绝对差值
> - fold-change ≠ regression coefficient

---

## 枚举规则

1. **逐行扫描核心 Table**：对核心指标，如果 Table 中报告了 between-group difference / p 值，就是一条 estimate
2. **扫描 Figure**：森林图中的每个 OR/HR，每个效应值一条 estimate
3. **包含不显著结果**：p > 0.05 的 estimate 也要提取
4. **亚组分析**：总体一条 + 每个亚组一条

## 输出格式

输出严格 JSON **数组**，每个元素是一条 estimate，结构如下：

```json
{estimate_skeleton}
```

输出一个 JSON 数组（`[{...}, {...}, ...]`），不要输出任何 JSON 以外的内容。

如果是单臂试验且无 comparison，输出空数组 `[]`。

---

## 论文原文

{paper_text}
