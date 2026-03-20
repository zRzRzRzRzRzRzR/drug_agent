# Drug-Databse Evidence Extraction Schema 说明文档

## 1. trial_linkage

用于记录试验注册号与文献的对应关系。

| 字段      | 类型            | 说明                      |
|---------|---------------|-------------------------|
| nct_ids | array[string] | ClinicalTrials.gov 试验编号 |
| pmid    | string        | PubMed ID               |
| doi     | string        | DOI编号                   |
| pmcid   | string        | PubMed Central ID       |

## 2. design

该字段用于描述临床试验的**研究设计特征（Study Design Characteristics）**。
这些信息用于刻画研究的基本方法学结构，例如是否随机分配、盲法类型、试验分组结构以及是否为多中心研究。
所有字段均采用**单选枚举（single-choice）**形式，禁止自由文本填写。

### 标注原则

- 仅依据文中**明确描述**进行判断，不得基于常识或推断填写。
- 若文中未提及该信息，统一标记为 `"unclear"`。
- 所有术语需进行**标准化归一（normalization）**后填写。

### 字段定义

| 字段          | 类型   | 可选值                                                                                     |
|-------------|------|-----------------------------------------------------------------------------------------|
| randomized  | enum | `"yes"` / `"no"` / `"unclear"`                                                          |
| blinding    | enum | `"open-label"` / `"single-blind"` / `"double-blind"` / `"triple-blind"` / `"unclear"`   |
| allocation  | enum | `"parallel"` / `"crossover"` / `"factorial"` / `"single-arm"` / `"other"` / `"unclear"` |
| multicenter | enum | `"yes"` / `"no"` / `"unclear"`                                                          |

### 判定规则

#### 1. randomized

- `"yes"`：出现以下表达之一：
    - randomized / randomised
    - randomly assigned / random allocation
    - patients were randomized
- `"no"`：出现以下表达之一：
    - non-randomized / nonrandomized
    - observational study
    - single-arm study
- `"unclear"`：未明确说明

---

#### 2. blinding

- `"open-label"`：open / open-label
- `"single-blind"`：single-blind / single-masked
- `"double-blind"`：double-blind / double-masked
- `"triple-blind"`：triple-blind
- `"unclear"`：未说明

---

#### 3. allocation

- `"parallel"`：parallel / parallel-group
- `"crossover"`：crossover / cross-over
- `"factorial"`：factorial design
- `"single-arm"`：single-arm / single group
- `"other"`：存在明确分组设计但不属于上述类型
- `"unclear"`：未说明

---

#### 4. multicenter

- `"yes"`：multicenter / multi-center / conducted at multiple sites
- `"no"`：single-center / single-centre
- `"unclear"`：未说明

### 作用域（Scope）限制（重要）

为避免误判，以上字段仅在**研究设计相关语境**中进行判断，例如：

- 包含关键词：`study`, `trial`, `design`, `assigned`, `phase`
- 常见位置：
    - Methods
    - Study Design
    - Trial Design

禁止在以下语境中进行标注：

- 方法学描述（如：random forest, random sampling）
- 背景介绍（Introduction）
- 讨论部分（Discussion）

---

### 示例

原文：
> This multicenter, controlled, open, randomized, parallel-group study...

标注结果：

```json
{
  "randomized": "yes",
  "blinding": "open-label",
  "allocation": "parallel",
  "multicenter": "yes"
}
```

---

## 3. pico

- `base_population`：研究所针对的基础总体，表示论文中最核心、最原始的研究对象定义。
- `analysis_populations`：从基础总体中派生出的具体分析人群，例如 ITT（intent-to-treat）、PP（per-protocol）或安全性分析集。

---

### 标注原则

- 仅依据文中**明确报告**的信息填写，不得主观推断。
- 若某字段未报告，则填 `null`。
- 所有数值字段应尽量保留原文单位与含义，不进行额外换算。
- `base_population` 描述总体定义，`analysis_populations` 描述具体分析集；若文中未区分分析集，可保留空数组 `[]` 或仅填写最主要分析集。
- 若存在多个分析集，每个分析集均应拥有唯一的 `population_id`。
- `derived_from` 必须指向其来源总体的 `population_id`。

---

### 字段结构总览

| 字段路径                              | 类型            | 说明                 |
|-----------------------------------|---------------|--------------------|
| `population.base_population`      | object        | 基础研究总体             |
| `population.analysis_populations` | array[object] | 分析人群列表，可包含一个或多个分析集 |

---

## 3.1 pico.population

### 3.1.1 base_population

表示研究纳入标准所定义的基础受试总体。

### 字段定义

| 字段              | 类型              | 说明                                                                    |
|-----------------|-----------------|-----------------------------------------------------------------------|
| `population_id` | string          | 人群唯一标识符。基础总体固定建议使用 `"P0"`                                             |
| `description`   | string \| null  | 对基础总体的自然语言描述，如“Adults with type 2 diabetes requiring insulin therapy” |
| `sample_size`   | integer \| null | 基础总体样本量                                                               |
| `region`        | object \| null  | 地理信息对象                                                                |
| `age`           | object \| null  | 年龄统计信息                                                                |
| `sex`           | object \| null  | 性别构成信息                                                                |

---

### 3.1.1.1 base_population.population_id

| 字段              | 类型     | 说明                    |
|-----------------|--------|-----------------------|
| `population_id` | string | 基础总体唯一标识符，固定写为 `"P0"` |

#### 标注要求

- `base_population.population_id` 固定为 `"P0"`。
- 不得与 `analysis_populations` 中的 ID 重复。

---

### 3.1.1.2 base_population.description （可选）

| 字段            | 类型             | 说明                  |
|---------------|----------------|---------------------|
| `description` | string \| null | 对研究总体的文字描述，建议尽量贴近原文 |

#### 标注要求

- 优先提取论文中对纳入人群的核心定义。
- 可以适度标准化语言，但不得改变原意。
- 若文中未明确描述，则填 `null`。

#### 示例

- `"Adults with type 2 diabetes requiring insulin therapy"`
- `"Patients with advanced non-small cell lung cancer"`
- `"Postmenopausal women with osteoporosis"`

---

### 3.1.1.3 base_population.sample_size

| 字段            | 类型              | 说明       |
|---------------|-----------------|----------|
| `sample_size` | integer \| null | 基础总体总样本量 |

#### 标注要求

- 填写基础纳入总体的总样本量。
- 若仅报告随机化人数或某分析集人数，需根据上下文判断是否属于基础总体。
- 若无法确认，则填 `null`。

---

### 3.1.1.4 base_population.region

用于记录研究总体的国家和大区信息。

| 字段             | 类型             | 说明                                           |
|----------------|----------------|----------------------------------------------|
| `country_list` | array[string]  | 国家列表                                         |
| `region`       | string \| null | 宏观区域，如 `"North America"`、`"Europe"`、`"Asia"` |

#### 标注要求

- `country_list` 记录文中明确提到的国家。
- 若研究为多国研究，应尽可能列出所有明确报告的国家。
- `region` 为归一化的大区名称。
- 若国家未知但区域明确，可仅填 `region`。
- 若均未报告，则：
    - `country_list`: `[]`
    - `region`: `null`

#### region 推荐枚举

- `"North America"`
- `"South America"`
- `"Europe"`
- `"Asia"`
- `"Africa"`
- `"Oceania"`
- `"Middle East"`
- `"Global"`
- `null`

---

### 3.1.1.5 base_population.age

用于记录年龄分布统计。

| 字段          | 类型             | 说明                        |
|-------------|----------------|---------------------------|
| `mean`      | number \| null | 平均年龄                      |
| `sd`        | number \| null | 年龄标准差                     |
| `median`    | number \| null | 年龄中位数                     |
| `iqr`       | string \| null | 四分位距，建议保留原文格式，如 `"48–62"` |
| `range_min` | number \| null | 最小年龄                      |
| `range_max` | number \| null | 最大年龄                      |

#### 标注要求

- 尽量按原文统计方式记录，不强行转换。
- 若原文给出 mean ± SD，则填写 `mean` 和 `sd`。
- 若原文给出 median (IQR)，则填写 `median` 和 `iqr`。
- 若原文给出年龄范围，则填写 `range_min` 和 `range_max`。
- 可同时填写多个字段，只要原文支持。
- 若完全未报告，则各字段均填 `null`。

---

### 3.1.1.6 base_population.sex

用于记录性别构成。

| 字段               | 类型             | 说明          |
|------------------|----------------|-------------|
| `female_percent` | number \| null | 女性占比（百分比）   |
| `male_percent`   | number \| null | 男性占比（百分比）   |
| `other_percent`  | number \| null | 其他性别占比（百分比） |

#### 标注要求

- 优先记录百分比。
- 若原文提供人数但未提供百分比，可换算为百分比。
- 若仅报告男性或女性人数/比例，可在可计算前提下补全另一项；否则未明确项填 `null`。
- 若未报告，则全部填 `null`。

---

## 3.1.2 analysis_populations

表示从基础总体派生出的分析人群，用于不同分析目的。

例如：

- intent-to-treat (ITT)
- modified intent-to-treat (mITT)
- per-protocol (PP)
- safety population
- subgroup population

每个分析集均为一个对象，存放于 `analysis_populations` 数组中。

---

### analysis_populations 字段定义

| 字段              | 类型              | 说明                                                        |
|-----------------|-----------------|-----------------------------------------------------------|
| `population_id` | string          | 分析集唯一标识符，如 `"P1"`、`"P2"`                                  |
| `derived_from`  | string          | 来源总体 ID，通常指向 `"P0"`                                       |
| `role`          | string \| null  | 分析集角色，如 `"primary"`、`"secondary"`、`"safety"`、`"subgroup"` |
| `analysis_set`  | string \| null  | 分析集名称，如 `"intent-to-treat"`、`"per-protocol"`              |
| `sample_size`   | integer \| null | 该分析集样本量                                                   |
| `region`        | object \| null  | 地理信息对象                                                    |
| `age`           | object \| null  | 年龄统计信息                                                    |
| `sex`           | object \| null  | 性别构成信息                                                    |

---

### 3.1.2.1 analysis_populations.population_id

| 字段              | 类型     | 说明       |
|-----------------|--------|----------|
| `population_id` | string | 分析集唯一标识符 |

#### 标注要求

- 每个分析集必须有唯一 ID。
- 推荐依次编号为 `"P1"`、`"P2"`、`"P3"` 等。

---

### 3.1.2.2 analysis_populations.derived_from

| 字段             | 类型     | 说明         |
|----------------|--------|------------|
| `derived_from` | string | 指向来源总体的 ID |

#### 标注要求

- 通常填写 `"P0"`。
- 若某分析集是从其他分析集进一步派生，也可指向对应上级 population ID。
- 必须保证引用对象存在。

---

### 3.1.2.3 analysis_populations.role

| 字段     | 类型             | 推荐可选值                                                                              |
|--------|----------------|------------------------------------------------------------------------------------|
| `role` | string \| null | `"primary"` / `"secondary"` / `"safety"` / `"subgroup"` / `"exploratory"` / `null` |

#### 标注要求

- `"primary"`：主要分析集
- `"secondary"`：次要分析集
- `"safety"`：安全性分析集
- `"subgroup"`：亚组分析集
- `"exploratory"`：探索性分析集
- 若文中未说明，则填 `null`

---

### 3.1.2.4 analysis_populations.analysis_set

| 字段             | 类型             | 说明      |
|----------------|----------------|---------|
| `analysis_set` | string \| null | 具体分析集名称 |

#### 常见值

- `"intent-to-treat"`
- `"modified intent-to-treat"`
- `"per-protocol"`
- `"safety population"`
- `"full analysis set"`

#### 标注要求

- 尽量保留原始术语并做轻度标准化。
- 若文中未明确命名，则填 `null`。

---

### 3.1.2.5 analysis_populations.sample_size

| 字段            | 类型              | 说明      |
|---------------|-----------------|---------|
| `sample_size` | integer \| null | 该分析集样本量 |

#### 标注要求

- 若分析集样本量与基础总体不同，应单独填写。
- 若未报告，则填 `null`。

---

### 3.1.2.6 analysis_populations.region / age / sex

这些字段定义与 `base_population` 相同，用于记录该分析集特有的人群特征。

#### 标注要求

- 若论文分别报告某分析集的人群特征，则填写该分析集自己的值。
- 若未单独报告，可根据团队规范选择：
    - 填 `null`，表示未单独报告；或
    - 复用 `base_population` 的值，但需保证团队内一致。
- 更严格的做法是：**未单独报告则填 `null`**。

---

## 示例

```json
{
  "population": {
    "base_population": {
      "population_id": "P0",
      "description": "Adults with type 2 diabetes requiring insulin therapy",
      "sample_size": 273,
      "region": {
        "country_list": [
          "USA"
        ],
        "region": "North America"
      },
      "age": {
        "mean": 55.0,
        "sd": 9.0,
        "median": null,
        "iqr": null,
        "range_min": 28,
        "range_max": 71
      },
      "sex": {
        "female_percent": 56,
        "male_percent": 44,
        "other_percent": null
      }
    },
    "analysis_populations": [
      {
        "population_id": "P1",
        "derived_from": "P0",
        "role": "primary",
        "analysis_set": "intent-to-treat",
        "sample_size": 273,
        "region": {
          "country_list": [
            "USA"
          ],
          "region": "North America"
        },
        "age": {
          "mean": 55.0,
          "sd": 9.0
        },
        "sex": {
          "female_percent": 56,
          "male_percent": 44
        }
      }
    ]
  }
}
```

---

## 3.2 pico.interventions

该对象用于对研究中的干预措施进行**粗粒度语义描述**，用于概括研究问题中的暴露/治疗内容。

### 设计定位

- `pico.interventions` 仅用于表达研究问题层面的干预描述；
- 不承担精确计算任务；
- 不要求完整表示剂量、频率、给药途径或多成分组合结构；
- 更精细的治疗方案结构应在 `trial_structure.regimens` 和 `trial_structure.arms` 中定义。

### 标注原则

- 尽量贴近原文概括主要干预内容；
- 允许轻度标准化，但不得改变原意；
- 若研究存在多个实验干预，可使用数组记录多个对象；
- 若无法识别药物成分，`drug_list` 可为空数组 `[]`；
- 不在本层处理剂量、频率、route、duration 等细粒度属性。

### 字段定义

| 字段                | 类型             | 说明                       |
|-------------------|----------------|--------------------------|
| `intervention_id` | string         | 干预唯一标识符，推荐 `"I1"`、`"I2"` |
| `label`           | string         | 干预的自然语言概括描述              |
| `type`            | enum           | 干预类型                     |
| `drug_list`       | array[string]  | 干预涉及的主要药物成分（如可识别）        |
| `notes`           | string \| null | 补充说明                     |

### intervention.type 可选值

| 值               | 说明      |
|-----------------|---------|
| `"drug"`        | 药物干预    |
| `"procedure"`   | 手术/操作   |
| `"behavioral"`  | 行为或教育干预 |
| `"device"`      | 器械干预    |
| `"combination"` | 联合干预    |
| `"other"`       | 其他      |
| `"unclear"`     | 未说明     |

---

## 3.3 pico.comparators

该对象用于对研究中的对照条件进行**粗粒度语义描述**。

### 设计定位

- `pico.comparators` 仅用于概括研究问题中的对照条件；
- 不承担精确结构化建模；
- 若需表达多臂试验中的具体组别对应关系，应使用 `trial_structure` 中的 `arms` 与 `comparisons`。

### 标注原则

- 应尽量明确对照条件的语义类型；
- 可为 placebo、active comparator、standard of care 等；
- 若为复杂治疗方案，仅保留粗粒度描述；
- 细粒度结构放在 `trial_structure`。

### 字段定义

| 字段              | 类型             | 说明                       |
|-----------------|----------------|--------------------------|
| `comparator_id` | string         | 对照唯一标识符，推荐 `"K1"`、`"K2"` |
| `label`         | string         | 对照条件描述                   |
| `type`          | enum           | 对照类型                     |
| `drug_list`     | array[string]  | 对照中涉及的主要药物成分（如适用）        |
| `notes`         | string \| null | 补充说明                     |

### comparator.type 可选值

| 值                         | 说明       |
|---------------------------|----------|
| `"placebo"`               | 安慰剂      |
| `"active comparator"`     | 主动对照     |
| `"standard of care"`      | 标准治疗     |
| `"no treatment"`          | 无治疗      |
| `"behavioral comparator"` | 行为/教育类对照 |
| `"unclear"`               | 未说明      |

---

## 3.4 pico.outcomes

该对象用于记录研究中的**结局指标（outcomes）**。

支持多个 outcome（数组结构）。

---

### 标注原则

- 每个 outcome 单独建一个对象（O1, O2, O3…）
- 必须区分 primary / secondary outcome
- 尽量提取明确时间点（timepoint）
- outcome 描述应贴近原文

---

### 字段定义

| 字段             | 类型             | 说明               |
|----------------|----------------|------------------|
| `outcome_id`   | string         | 结局唯一标识符，如 `"O1"` |
| `label`        | string         | 结局描述             |
| `role`         | enum           | 结局角色             |
| `timepoint`    | object \| null | 观察时间点            |
| `polarity`     | enum           | 指标方向             |
| `outcome_type` | enum           | 数据类型             |

---

### 3.4.1 outcome_id

- 唯一标识 outcome
- 推荐 `"O1"`、`"O2"`、`"O3"`

---

### 3.4.2 label

- 提取原文结局描述
- 示例：
    - `"Change in HbA1c from baseline to 24 weeks"`
    - `"Overall survival"`

---

### 3.4.3 role

| 值               | 说明    |
|-----------------|-------|
| `"primary"`     | 主要结局  |
| `"secondary"`   | 次要结局  |
| `"exploratory"` | 探索性结局 |
| `"safety"`      | 安全性结局 |
| `"unclear"`     | 未说明   |

---

### 3.4.4 timepoint

| 字段      | 类型             | 说明     |
|---------|----------------|--------|
| `label` | string         | 原文时间描述 |
| `value` | number \| null | 数值     |
| `unit`  | string \| null | 单位     |

#### 示例

```json
"timepoint": {
"label": "week 24",
"value": 24,
"unit": "week"
}
```

### 标注原则

- 若原文有明确时间点，尽量结构化
- 若无法解析数值，保留 label，其他为 null

### 3.4.5 polarity

- 表示指标“越大越好”还是“越小越好”。

| 值                 | 说明                |
|-------------------|-------------------|
| `"higher_better"` | 数值越高越好（如生存率）      |
| `"lower_better"`  | 数值越低越好（如HbA1c、血压） |
| `"neutral"`       | 无明确方向             |
| `"unclear"`       | 不确定               |

### 3.4.6 outcome_type

| 值                 | 说明             |
|-------------------|----------------|
| `"continuous"`    | 连续变量（HbA1c、血压） |
| `"binary"`        | 二分类（死亡/存活）     |
| `"time-to-event"` | 生存分析           |
| `"ordinal"`       | 有序分类           |
| `"count"`         | 计数数据           |
| `"unclear"`       | 未说明            |

#### 示例

```json
{
  "interventions": [
    {
      "intervention_id": "I1",
      "label": "Simple algorithm for mealtime insulin adjustment",
      "type": "behavioral",
      "drug_list": [
        "insulin glulisine",
        "insulin glargine"
      ],
      "notes": "High-level intervention summary only"
    }
  ],
  "comparators": [
    {
      "comparator_id": "K1",
      "label": "Carbohydrate counting with insulin-to-carbohydrate ratio",
      "type": "active comparator",
      "drug_list": [
        "insulin glulisine",
        "insulin glargine"
      ],
      "notes": "Comparator described at semantic level only"
    }
  ],
  "outcomes": [
    {
      "outcome_id": "O1",
      "label": "Change in HbA1c from baseline to 24 weeks",
      "role": "primary",
      "timepoint": {
        "label": "week 24",
        "value": 24,
        "unit": "week"
      },
      "polarity": "lower_better",
      "outcome_type": "continuous"
    }
  ]
}
```

## 4. trial_structure

该对象用于描述临床试验的**结构化设计（trial structure）**，包括：

- 治疗方案（regimens）
- 研究分组（arms）
- 分析分组（analysis groups，可选）
- 比较关系（comparisons）

该层用于将 **PICO → 可计算对比单元（contrast-ready structure）**。

---

### 标注原则

- 所有实体（regimen / arm / comparison）必须具备唯一 ID。
- 各层之间通过 ID 建立引用关系（如 arm → regimen）。
- 不允许自由文本替代结构化字段（如 dose / frequency）。
- 若信息未报告，填 `null` 或空数组 `[]`。
- 所有时间单位、频率、给药方式需标准化。

---

## 4.1 regimens

表示具体治疗方案（treatment regimen），可包含一个或多个组成成分（components）。

---

### 字段定义

| 字段           | 类型            | 说明                  |
|--------------|---------------|---------------------|
| `regimen_id` | string        | 治疗方案唯一 ID（如 `"R1"`） |
| `label`      | string        | 治疗方案描述              |
| `components` | array[object] | 组成成分列表              |

---

### 4.1.1 components

每个 component 表示一个具体干预单元（如一个药物或行为）。

| 字段             | 类型             | 说明                 |
|----------------|----------------|--------------------|
| `component_id` | string         | 成分唯一 ID（如 `"RC1"`） |
| `kind`         | enum           | 成分类型               |
| `drug_name`    | string \| null | 药物名称（通用名）          |
| `dose`         | object \| null | 剂量信息               |
| `frequency`    | object \| null | 给药频率               |
| `route`        | string \| null | 给药途径               |
| `duration`     | object \| null | 持续时间               |

---

#### kind 可选值

| 值              | 说明    |
|----------------|-------|
| `"drug"`       | 药物干预  |
| `"procedure"`  | 操作/手术 |
| `"behavioral"` | 行为干预  |
| `"device"`     | 医疗设备  |
| `"other"`      | 其他    |

---

### 4.1.2 dose

| 字段      | 类型             | 说明                     |
|---------|----------------|------------------------|
| `value` | number \| null | 数值                     |
| `unit`  | string \| null | 单位（如 `"mg"`、`"units"`） |

---

### 4.1.3 frequency

| 字段      | 类型             | 说明     |
|---------|----------------|--------|
| `code`  | string \| null | 标准频率编码 |
| `label` | string \| null | 原文描述   |

#### 常见 code

- `"QD"`：once daily
- `"BID"`：twice daily
- `"TID"`：three times daily
- `"QID"`：four times daily
- `"PRN"`：as needed

---

### 4.1.4 route

常见值：

- `"oral"`
- `"intravenous"`
- `"subcutaneous"`
- `"intramuscular"`
- `"inhalation"`
- `"topical"`
- `"unclear"`

---

### 4.1.5 duration

| 字段      | 类型             | 说明                               |
|---------|----------------|----------------------------------|
| `value` | number \| null | 数值                               |
| `unit`  | string \| null | 单位（如 `"day"`、`"week"`、`"month"`） |

---

## 4.2 arms

表示研究中的分组（study arms）。

---

### 字段定义

| 字段            | 类型              | 说明              |
|---------------|-----------------|-----------------|
| `arm_id`      | string          | 分组 ID（如 `"A1"`） |
| `label`       | string          | 分组描述            |
| `type`        | enum            | 分组类型            |
| `regimen_id`  | string          | 对应治疗方案 ID       |
| `sample_size` | integer \| null | 该组样本量           |

---

### arm.type 可选值

| 值                      | 说明   |
|------------------------|------|
| `"experimental"`       | 实验组  |
| `"active_comparator"`  | 主动对照 |
| `"placebo_comparator"` | 安慰剂  |
| `"standard_of_care"`   | 标准治疗 |
| `"control"`            | 一般对照 |
| `"unclear"`            | 未说明  |

---

## 4.3 analysis_groups（可选）

用于描述特定分析子集（如 ITT / PP / subgroup），当前可为空数组。

---

### 字段定义（如使用）

| 字段              | 类型             | 说明            |
|-----------------|----------------|---------------|
| `group_id`      | string         | 分析组 ID        |
| `population_id` | string         | 对应 population |
| `description`   | string \| null | 描述            |

---

## 4.4 comparisons

表示**可计算的对比单元（contrast unit）**，是后续 effect size 计算的核心。

---

### 字段定义

| 字段              | 类型             | 说明              |
|-----------------|----------------|-----------------|
| `comparison_id` | string         | 对比 ID（如 `"C1"`） |
| `treatment`     | object         | 处理组引用           |
| `control`       | object         | 对照组引用           |
| `population_id` | string         | 对应人群（如 `"P1"`）  |
| `analysis_set`  | string \| null | 分析集名称           |
| `timepoint`     | object \| null | 时间点             |
| `model_spec`    | object \| null | 统计模型说明          |

---

### 4.4.1 treatment / control

| 字段         | 类型     | 说明                    |
|------------|--------|-----------------------|
| `ref_type` | enum   | `"arm"` / `"regimen"` |
| `ref_id`   | string | 引用 ID                 |

---

### 4.4.2 timepoint

同 outcomes 中定义：

| 字段      | 类型             |
|---------|----------------|
| `label` | string         |
| `value` | number \| null |
| `unit`  | string \| null |

---

### 4.4.3 model_spec

描述统计分析模型。

| 字段             | 类型             | 说明    |
|----------------|----------------|-------|
| `adjustment`   | string \| null | 协变量调整 |
| `model_family` | enum \| null   | 模型类型  |
| `notes`        | string \| null | 备注    |

---

#### model_family 可选值

| 值                       | 说明    |
|-------------------------|-------|
| `"ANCOVA"`              | 协方差分析 |
| `"linear_regression"`   | 线性回归  |
| `"logistic_regression"` | 逻辑回归  |
| `"cox_model"`           | Cox模型 |
| `"mixed_model"`         | 混合模型  |
| `"unclear"`             | 未说明   |

---

## 示例

```json
{
  "trial_structure": {
    "regimens": [
      ...
    ],
    "arms": [
      ...
    ],
    "comparisons": [
      ...
    ]
  }
}
```

## 5. effect_estimates

该对象用于记录研究中的**效应估计（effect estimates）**，是从 comparison + outcome + population 组合中提取的**可计算统计结果
**。

该层是后续：

- meta-analysis
- causal inference
- evidence grading
  的核心数据来源。

---

### 标注原则

- 每一个 effect estimate 必须唯一对应：
    - 一个 comparison
    - 一个 outcome
    - 一个 population
    - 一个 timepoint
- 所有数值必须来自文中明确报告，不得推断。
- 若置信区间或 p 值未报告，可填 `null`。
- 方向（direction）需根据统计显著性和效应值共同判断。

---

### 字段定义

| 字段              | 类型             | 说明                         |
|-----------------|----------------|----------------------------|
| `estimate_id`   | string         | 效应估计唯一 ID（如 `"E1"`）        |
| `comparison_id` | string         | 对应 comparison ID           |
| `outcome_id`    | string         | 对应 outcome ID              |
| `population_id` | string         | 对应 population ID           |
| `analysis_set`  | string \| null | 分析集（如 `"intent-to-treat"`） |
| `timepoint`     | object \| null | 时间点                        |
| `estimate_type` | enum           | 效应类型                       |
| `value`         | number \| null | 效应值                        |
| `ci`            | object \| null | 置信区间                       |
| `p_value`       | number \| null | p 值                        |
| `direction`     | enum           | 效应方向                       |
| `effect_notes`  | string \| null | 备注                         |

#### analysis_set 可选值

| 值                            | 说明                              |
|------------------------------|---------------------------------|
| `"intent-to-treat"`          | 所有随机分配的受试者均纳入分析，按原分组分析          |
| `"modified intent-to-treat"` | 在 ITT 基础上设定额外纳入条件（如至少接受一次治疗）    |
| `"per-protocol"`             | 仅纳入严格遵循研究方案的受试者                 |
| `"safety population"`        | 所有接受过至少一次治疗的受试者，用于安全性分析         |
| `"full analysis set"`        | 接近 ITT 的分析集，通常允许少量排除（如无基线或无数据者） |

---

### 5.1 estimate_type 可选值

| 值                   | 说明      |
|---------------------|---------|
| `"mean_difference"` | 均值差     |
| `"risk_ratio"`      | 风险比（RR） |
| `"odds_ratio"`      | 比值比（OR） |
| `"hazard_ratio"`    | 风险比（HR） |
| `"risk_difference"` | 风险差     |
| `"rate_ratio"`      | 发生率比    |
| `"unclear"`         | 未说明     |

---

### 5.2 value

- 表示效应估计值
- 必须与 `estimate_type` 一致

示例：

- mean_difference → -0.13
- hazard_ratio → 0.85

---

### 5.3 ci（置信区间）

| 字段      | 类型             | 说明         |
|---------|----------------|------------|
| `lower` | number \| null | 下限         |
| `upper` | number \| null | 上限         |
| `level` | number \| null | 置信水平（如 95） |

#### 标注规则

- 若文中提供 CI，则尽量完整提取
- 若未报告，则填 `null`

---

### 5.4 p_value

- 填写文中报告的 p 值
- 若仅报告 `p < 0.05`：
    - 可记录为 `0.05`
    - 或按团队规范保留为字符串（需统一）

---

### 5.5 direction（关键字段）

| 值                             | 说明       |
|-------------------------------|----------|
| `"treatment_better"`          | 干预组显著更优  |
| `"control_better"`            | 对照组显著更优  |
| `"no_significant_difference"` | 无统计学显著差异 |
| `"inconclusive"`              | 信息不足     |
| `"unclear"`                   | 无法判断     |

#### 判定规则

- 若 p ≥ 0.05 → `"no_significant_difference"`
- 若 p < 0.05：
    - 根据 effect value 和 polarity 判断方向
- 若为 non-inferiority / equivalence：
    - 可标记 `"no_significant_difference"` 并在 notes 中说明

---

### 5.6 effect_notes

- 用于记录：
    - 非劣效（non-inferiority）
    - 等效性（equivalence）
    - 特殊统计说明

---

## 示例

```json
{
  "estimate_id": "E1",
  "comparison_id": "C1",
  "outcome_id": "O1",
  "population_id": "P1",
  "analysis_set": "intent-to-treat",
  "estimate_type": "mean_difference",
  "value": -0.13,
  "ci": {
    "lower": -0.35,
    "upper": 0.09,
    "level": 95
  },
  "p_value": 0.24,
  "direction": "no_significant_difference",
  "effect_notes": "non-inferiority established"
}
```

## 6. mechanism_evidence

该对象用于记录研究中的**机制证据与结论性陈述（mechanistic and interpretive evidence）**。

该部分用于补充：

- 临床结果背后的机制解释
- 生物学或药理学证据
- 作者在论文中的核心结论

---

### 标注原则

- 仅提取文中**明确表述**的内容，不进行主观推断。
- 优先提取：
    - Discussion
    - Conclusion
    - Abstract（结论部分）
- `claims.text` 应尽量贴近原文语义，可轻度规范化表达。
- `confidence` 表示证据强度（不是统计显著性）。

---

### 字段结构

| 字段                  | 类型            | 说明          |
|---------------------|---------------|-------------|
| `target_actions`    | array[object] | 药物作用机制（可选）  |
| `biomarker_effects` | array[object] | 生物标志物变化（可选） |
| `claims`            | array[object] | 结论性陈述（核心字段） |

---

## 6.1 target_actions（可选）

用于记录药物或干预的**分子或生物学作用机制**。

### 字段定义

| 字段                | 类型             | 说明          |
|-------------------|----------------|-------------|
| `action_id`       | string         | 唯一 ID       |
| `drug_name`       | string \| null | 药物名称        |
| `target`          | string \| null | 靶点（如蛋白/基因）  |
| `action_type`     | enum           | 作用类型        |
| `evidence_source` | string \| null | 来源（如文献、数据库） |

---

### action_type 可选值

| 值              | 说明  |
|----------------|-----|
| `"inhibitor"`  | 抑制  |
| `"agonist"`    | 激动  |
| `"antagonist"` | 拮抗  |
| `"modulator"`  | 调节  |
| `"unclear"`    | 未说明 |

---

## 6.2 biomarker_effects（可选）

用于记录干预对**生物标志物的影响**。

### 字段定义

| 字段             | 类型             | 说明      |
|----------------|----------------|---------|
| `biomarker_id` | string         | 唯一 ID   |
| `name`         | string         | 生物标志物名称 |
| `effect`       | enum           | 变化方向    |
| `notes`        | string \| null | 备注      |

---

### effect 可选值

| 值             | 说明  |
|---------------|-----|
| `"increase"`  | 升高  |
| `"decrease"`  | 降低  |
| `"no_change"` | 无变化 |
| `"unclear"`   | 未说明 |

---

## 6.3 claims（核心字段）

用于记录论文中的**核心结论或主张（claims）**。

---

### 字段定义

| 字段           | 类型     | 说明               |
|--------------|--------|------------------|
| `claim_id`   | string | 唯一 ID（如 `"MC1"`） |
| `text`       | string | 结论性描述            |
| `scope`      | enum   | 结论类型             |
| `confidence` | enum   | 证据强度             |

---

### 6.3.1 scope 可选值

| 值                     | 说明    |
|-----------------------|-------|
| `"clinical efficacy"` | 临床疗效  |
| `"safety"`            | 安全性   |
| `"mechanism"`         | 作用机制  |
| `"biomarker"`         | 生物标志物 |
| `"pharmacokinetics"`  | 药代动力学 |
| `"unclear"`           | 未说明   |

---

### 6.3.2 confidence 可选值

| 值            | 说明           |
|--------------|--------------|
| `"high"`     | 高置信（RCT主要结论） |
| `"moderate"` | 中等           |
| `"low"`      | 低（探索性或间接证据）  |
| `"unclear"`  | 未说明          |

---

### 标注建议

- 优先提取论文中**最核心的一句话结论**
- 避免拆分过细，建议每篇论文 1–3 条 claims
- 若为 RCT primary outcome 结论，通常标记为 `"high"`

---

### 示例

```json
{
  "claims": [
    {
      "claim_id": "MC1",
      "text": "Simple algorithm-based adjustment of mealtime insulin is as effective as carbohydrate counting in type 2 diabetes",
      "scope": "clinical efficacy",
      "confidence": "high"
    }
  ]
}
```

## 7. metadata

该对象用于记录**数据提取过程信息（provenance）与质量控制（quality control）**。

metadata 不描述研究内容本身，而是描述：

- 数据是如何被提取的
- 数据质量如何
- 使用的 schema 版本

该部分对于：

- 数据追溯（traceability）
- 质量评估（quality assessment）
- pipeline 管理
  具有重要意义。

---

### 标注原则

- 每条记录必须包含 metadata。
- metadata 应由标注者或系统自动生成，不依赖论文内容。
- 不得根据主观印象随意填写，需依据实际提取流程。

---

### 字段定义

| 字段                | 类型             | 说明              |
|-------------------|----------------|-----------------|
| `extraction_mode` | enum           | 数据提取方式          |
| `confidence`      | enum           | 数据整体质量评估        |
| `schema_version`  | string         | 当前使用的 schema 版本 |
| `annotator_id`    | string \| null | 标注者 ID（可选）      |
| `timestamp`       | string \| null | 提取时间（ISO格式，可选）  |

---

## 7.1 extraction_mode

表示该条数据的提取来源方式。

### 可选值

| 值                   | 说明             |
|---------------------|----------------|
| `"manual_fulltext"` | 人工基于全文提取（最高质量） |
| `"manual_abstract"` | 人工基于摘要提取       |
| `"llm_assisted"`    | LLM辅助提取（人工校对）  |
| `"automated"`       | 全自动抽取（无人工校验）   |

---

## 7.2 confidence

表示该条数据的**整体可信度（quality level）**。

### 可选值

| 值            | 说明              |
|--------------|-----------------|
| `"high"`     | 信息完整，字段一致，无明显歧义 |
| `"moderate"` | 存在少量缺失或轻微不确定    |
| `"low"`      | 信息不完整或存在明显不一致   |
| `"unclear"`  | 无法评估            |

---

### 判定建议

| 情况          | 推荐值          |
|-------------|--------------|
| 完整全文 + 清晰结果 | `"high"`     |
| 部分字段缺失      | `"moderate"` |
| 仅摘要或信息冲突    | `"low"`      |

---

## 7.3 schema_version

用于记录当前使用的数据结构版本。

### 标注要求

- 必须填写
- 格式建议：
    - `"v1"`
    - `"v1.1"`
    - `"v1_patch_1"`

---

## 7.4 annotator_id（可选）

用于标识数据标注来源。

### 示例

- `"annotator_01"`
- `"rong_manual"`
- `"llm_v1_pipeline"`

---

## 7.5 timestamp（可选）

记录数据生成时间。

### 格式要求

- 使用 ISO 8601 格式：
    - `"2026-03-17T21:30:00Z"`

---

## 示例

```json
{
  "metadata": {
    "extraction_mode": "manual_fulltext",
    "confidence": "high",
    "schema_version": "v1_patch_1",
    "annotator_id": "annotator_01",
    "timestamp": "2026-03-17T21:30:00Z"
  }
}
```
