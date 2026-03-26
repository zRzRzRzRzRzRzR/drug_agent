# Step 2: 提取 PICO（人群、干预、对照、结局）

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取完整的 PICO 信息。

## 字段级标注规范

以下是该步骤涉及字段的详细标注规范（来自 schema_annotation.json）：

{annotation_guidance}

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

**⚠️ 不要遗漏分析人群**：如果论文明确报告了多个分析集（如 safety population + efficacy/ITT population + per-protocol population），必须为每个分析集建一个条目。

### 2.2 intervention（干预）
- **label**: 干预的自然语言概括
- **drug_list**: 涉及的主要药物成分
- **mapped_regimen_ids**: 暂时填 `[]`（Step 3.5 填充）

### 2.3 comparator（对照）
- **label**: 对照条件描述
- **type**: placebo / active comparator / standard of care / no treatment / unclear
- **mapped_regimen_ids**: 暂时填 `[]`（Step 3.5 填充）

**⚠️ 单臂试验（single-arm）处理规则**：
- 若研究设计为 single-arm / open-label extension / 所有受试者接受同一干预 → **comparators 必须为空数组 `[]`**
- **不要创建 type="no treatment" 的伪对照**
- 判断依据：论文中是否存在明确的对照组 / comparator arm

### 2.4 outcomes（结局）
- 每个结局一个对象（O1, O2, O3...）
- **label**: 结局描述（贴近原文）
- **role**: primary / secondary / exploratory / safety / unclear
- **timepoint**: 观察时间点（label + value + unit）
- **polarity**: higher_better / lower_better / neutral / unclear
- **outcome_type**: continuous / binary / time-to-event / ordinal / count / unclear

**⚠️ Safety outcome 规则**：
- 若 role = "safety"（如 adverse events、tolerability），**polarity 必须填 "neutral"**
- 不要将安全性指标的 polarity 标为 "lower_better"

**⚠️ Polarity 判定扩展规则**：
- `higher_better` 适用于：
  - 生存类指标：overall survival, progression-free survival, time-to-event endpoints
  - **响应率/达标率**：response rate, remission rate, **proportion achieving goal**, **proportion meeting target**, **goal attainment rate**, **percentage of patients reaching threshold**
  - 功能改善：quality of life score（明确更高更好时）
- `lower_better` 适用于：
  - 疾病负担/风险：HbA1c, blood pressure, LDL-C **水平/变化量**（注意区分 LDL-C 水平 vs 达标比例）
  - 事件发生率：mortality rate, relapse rate, MACE
- **关键区分**：
  - "Change in LDL-C from baseline" → **lower_better**（降低越多越好）
  - "Proportion of patients achieving LDL-C goals" → **higher_better**（达标越多越好，本质是 response rate）
  - "Time to progression" → **higher_better**（越久越好）
  - "Incidence of adverse events" → **neutral**（安全性指标）

**⚠️ Phase 1 / 探索性试验的 outcome.role 规则**：
- 如果论文明确标注了 primary/secondary endpoint → 按原文填写
- 如果论文**未明确标注** primary/secondary，但属于 Phase 1 剂量探索 → role 填 "exploratory"
- **不要因为某个指标是主要讨论对象就自动标为 "primary"**

---

## ⚠️ 硬匹配规则

> 所有数值字段（sample_size、age、sex percent、timepoint value）必须能在论文原文中找到对应的数字。
> **不要凭空捏造数值**。如果论文没有报告，填 `null`。

### 允许的简单计算（必须注明来源）

以下情况允许从论文已报告的数字做**简单加法/减法**，但必须在 description 中注明：

1. **sample_size 加总**：如果论文以表格分组报告了每组样本量（如 Table 1 各列的 N），但没有直接给出总数，可以加总得到 base_population.sample_size。
   - 例如：Table 1 报告 Placebo N=442, Mirabegron N=446 → 加总得到总 N=888
   - 在 description 中注明 "sample size summed from Table 1"

2. **sex percent 互补**：论文报告了 female% 但没有 male%，可以用 100% − female%。反之亦然。
   - **必须同时填写 female_percent 和 male_percent**（如果论文报告了其中一个）
   - 例如：论文只报告 "67.7% male" → male_percent = 67.7, female_percent = 32.3

3. **age 统计量**：论文如果同时报告了 mean 和 SD，两个都填。如果报告了 range（如 18-75），填 range_min 和 range_max。
   - **不要只填 range 而遗漏 mean±SD**（如果论文两者都报告了）
   - **不要只填 mean±SD 而遗漏 range_min**：如果入排标准写了 "aged ≥ 18 years" 或 "18 years or older"，则 range_min = 18
   - 搜索位置：Inclusion criteria、Eligibility criteria、Methods → Study population
   - **age.range_min 是高频遗漏字段，请特别留意**

4. **其他数值一律不允许计算**。

---

## 📋 多阶段试验的特殊处理

> **适用于**：Phase 1 剂量探索（dose-finding / dose-escalation）、含 single-dose phase + multiple-dose phase 的试验、含多个独立分析队列的试验。

### base_population（P0）
- description：概括整个试验的纳入标准
- sample_size：所有阶段的总人数（可从 Table 1 加总）
- **age**：取所有阶段中**最宽的年龄范围**
- region：所有阶段的研究地点合并

### analysis_populations — 按分析阶段拆分
- **每个独立分析阶段应建为一个 analysis_population**
  - 例如：
    - P1 = safety population（全部参与者）
    - P2 = single-dose phase pharmacodynamic population
    - P3 = multiple-dose phase pharmacodynamic population
- 每个 population 应有自己的 sample_size 和 age range

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
