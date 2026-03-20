# Step 0: 多研究（Multi-study）论文拆分

你是一名医学信息学研究员。在进行结构化抽取前，请先判断该论文是否包含多个独立研究单元（study / trial），并决定是否需要拆分。

## 任务

### 1. 识别研究单元（study units）

请通读全文，识别论文中包含多少个独立研究单元。
**抽取单位是：独立的研究 / 临床试验（study / trial），而不是整篇论文（paper）。**

### 2. 判断是否需要拆分

当论文中存在多个彼此独立的研究单元时，需要拆分为多个 study。

判定为"独立研究"的标准（需综合判断，越多越强）：
- 存在不同试验名称（如 ORION-10、ORION-11）
- 存在不同 NCT ID
- 分别报告各自的：
  - 研究设计（design）
  - 人群 / 样本量（population / sample size）
  - 基线特征（baseline characteristics）
  - 疗效或安全性结果（efficacy / safety）

如果这些信息是**分别独立报告的**，则必须拆分。

### 3. 不应拆分的情况

以下情况属于同一研究的不同分析维度，**不得拆分**：
- 亚组分析（subgroup analysis）
- 不同时间点（multiple timepoints）
- 多个结局指标（multiple outcomes）
- 延长期研究（extension）仅作为补充
- 其他试验仅作为背景引用（Introduction / Discussion）

### 4. NCT ID 使用原则

- 多个 NCT ID 是强信号，但不能单独作为拆分依据
- 必须满足：每个 NCT 对应独立报告的设计 + 人群 + 结果
- 否则：不拆分

### 5. 决策优先级（必须遵守）

当存在不确定性时，按以下顺序判断：
1. 是否分别报告结果（**最重要**）
2. 是否有独立人群 / 样本量
3. 是否有独立设计
4. 是否有不同 NCT

**核心原则："是否独立报告结果" > 一切其他信号**

## 输出格式

输出严格 JSON，不要输出任何其他内容：

```json
{
  "n_studies": 1,
  "needs_split": false,
  "studies": [
    {
      "study_index": 1,
      "study_name": "研究名称（如 ORION-10）或 null",
      "nct_id": "NCTxxxxxxxx 或 null",
      "description": "一句话描述该研究"
    }
  ],
  "split_rationale": "用1-2句话说明为什么拆分或不拆分",
  "split_signals": ["信号1", "信号2"]
}
```

如果有多个独立研究：

```json
{
  "n_studies": 2,
  "needs_split": true,
  "studies": [
    {
      "study_index": 1,
      "study_name": "ORION-10",
      "nct_id": "NCT03399370",
      "description": "Phase 3 trial of inclisiran in US patients with ASCVD"
    },
    {
      "study_index": 2,
      "study_name": "ORION-11",
      "nct_id": "NCT03400800",
      "description": "Phase 3 trial of inclisiran in European/South African patients with ASCVD or risk equivalent"
    }
  ],
  "split_rationale": "两个试验有独立的 NCT ID、独立的人群、分别报告的结果",
  "split_signals": ["独立 NCT ID", "独立样本量 (1561 vs 1617)", "分别报告 primary endpoints"]
}
```

### 约束

- 不允许把多个独立研究合并为一个 study
- 不允许把一个研究错误拆分成多个 study
- 每个 study 必须是完整可独立解释的临床研究单元

---

## 论文原文

{paper_text}
