# Step 1: 提取试验注册信息与研究设计

你是一名医学信息学研究员。请仔细阅读下面的论文全文，提取**试验注册信息**和**研究设计特征**。

## 任务

### 1. trial_linkage

从论文中提取以下标识符：

- **nct_ids**: ClinicalTrials.gov 注册号（格式 NCTxxxxxxxx），可能有多个
- **pmid**: PubMed ID
- **doi**: DOI 编号
- **pmcid**: PubMed Central ID

搜索位置：标题页、摘要、方法部分、致谢、参考文献、脚注。
如果找不到，填 `null` 或空数组 `[]`。

### 2. design.reported

判断研究设计特征，**仅依据文中明确描述**，不得推断：

- **randomized**: `"yes"` / `"no"` / `"unclear"`
  - 出现 randomized / randomised / randomly assigned → `"yes"`
  - 出现 non-randomized / observational → `"no"`
  - 未说明 → `"unclear"`

- **blinding**: `"open-label"` / `"single-blind"` / `"double-blind"` / `"triple-blind"` / `"unclear"`

- **allocation**: `"parallel"` / `"crossover"` / `"factorial"` / `"single-arm"` / `"other"` / `"unclear"`

- **multicenter**: `"yes"` / `"no"` / `"unclear"`

**重要**：仅在研究设计相关语境（Methods, Study Design, Trial Design）中判断。不要因为 Introduction 或 Discussion 中出现 "random" 就标为 randomized。

## 输出格式

输出严格 JSON，填充以下骨架：

```json
{schema_skeleton}
```

不要输出任何 JSON 以外的内容。

---

## 论文原文

{paper_text}
