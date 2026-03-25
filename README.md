# Drug-Database Evidence Extraction v2

从临床试验论文 PDF 中自动提取药物关系、试验结构与效应估计，生成符合统一 schema 的 JSON 输出。


## 核心流程

```
PDF 论文
   │
   ▼
┌──────────────────────────┐
│  OCR: PDF → Markdown     │  → GLM-OCR 识别 + 尾页过滤 + 缓存
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 0: 多研究拆分        │  → 识别论文中独立研究单元
│                          │  → 多研究论文分别提取
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 1: 注册信息 + 设计   │  → trial_linkage (NCT/DOI/PMID)
│  + schema_annotation 指导  │  → design (randomized/blinding/allocation/multicenter)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 2: PICO            │  → population (base + analysis populations)
│  + 硬匹配验证              │  → intervention / comparator / outcomes
│  + 一致性检查              │  → sub-pop sample_size ≤ base sample_size
│  + Review（如有错误）      │  → safety polarity 校验
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 3: 试验结构          │  → regimens (drug/dose/frequency/route/duration)
│  + 硬匹配验证              │  → arms (分组 + 样本量)
│  + 引用对齐检查            │  → comparisons (treatment vs control)
│  + Review（如有错误）      │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 3.5: 跨层映射 (v2)  │  → 回填 interventions[].mapped_regimen_ids
│                          │  → 回填 comparators[].mapped_regimen_ids
│                          │  → 校验 drug_list ↔ regimen components 一致性
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 4: 效应估计         │  → 逐行扫描 Table/Figure
│  + 严格硬匹配              │  → value / CI / p_value 必须论文原文可追溯
│  + ID 引用检查            │  → comparison_id / outcome_id / population_id ← 上游定义
│  + Review（如有错误）      │  → 单臂试验自动输出 []
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 5: 机制证据          │  → target_actions (TA1/TA2... 药物-靶点关系)
│  + 轻度硬匹配              │  → biomarker_effects (B1/B2... 生物标志物变化)
│  + ID 前缀 + 枚举校验 (v2) │  → claims (MC1/MC2... 核心结论)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 6: 合并 + 元数据     │  → 合并 Step 1-5
│                          │  → 计算 confidence (high/moderate/low)
│                          │  → schema_version = "v2"
└────────┬─────────────────┘
         │
         ▼
   final.json + verification_reports.json
```

### 数据流概览

```
Step 0 → step0_split.json
  多研究拆分检测
  ↓
Step 1 → step1_linkage_design.json
  独立提取，注入 schema_annotation 字段级指导
  ↓
Step 2 → step2_pico.json + step2_pico_report.json
  独立提取，注入 schema_annotation 字段级指导
  硬匹配：sample_size, age, sex percent, timepoint value
  一致性：sub-pop size ≤ base size, safety polarity = neutral
  ↓
Step 3 → step3_trial_structure.json + step3_trial_structure_report.json
  输入：Step 2 PICO 作为上下文 + schema_annotation 指导
  硬匹配：dose value, duration value, arm sample_size
  引用对齐：arm.regimen_id, comparison.ref_id, comparison.population_id
  ↓
Step 3.5 → step3_5_cross_mapping.json (v2 新增)
  输入：Step 2 PICO + Step 3 structure
  回填：mapped_regimen_ids
  ↓
Step 4 → step4_effects.json + step4_effects_report.json
  输入：Step 2 PICO + Step 3 structure + schema_annotation 指导
  严格硬匹配：value, ci.lower, ci.upper, p_value
  引用对齐：comparison_id, outcome_id, population_id
  枚举校验：estimate_type, direction
  ↓
Step 5 → step5_mechanism.json + step5_mechanism_report.json
  输入：Step 3 structure + Step 4 effects + schema_annotation 指导
  轻度硬匹配：biomarker value/ci/p_value
  引用对齐：comparison_id, linked_estimate_id
  ID 前缀校验：TA*/B*/MC*
  枚举校验：action_type (inhibitor/agonist/antagonist/modulator/unclear)
  ↓
Step 6 → final.json + verification_reports.json
  合并所有步骤，计算整体 confidence
```

### 硬匹配验证机制

每步提取后，`evaluate_match.py` 对所有数值字段做**机械字符串匹配**（无 LLM 调用）：

1. 从论文全文提取所有数字，建立 anchor set（支持多种格式：整数、小数、省略前导零等）
2. 检查提取 JSON 中的每个数值是否能在 anchor set 中找到
3. 不可追溯的数值标记为 ERROR，生成错误报告
4. 仅在存在 ERROR 时调用 Review Agent（LLM），要求其在原文中查找正确值或删除

```
提取 JSON
   │
   ▼
┌──────────────────┐     匹配成功
│  硬匹配验证        │ ──────────────→ 直接通过
│  (无 LLM)         │
└────────┬─────────┘
         │ 匹配失败
         ▼
┌──────────────────┐
│  生成错误报告      │  → "value=999.99 at field X: NOT FOUND in paper"
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Review Agent    │  → LLM 查找正确值 / 设为 null
│  (LLM 调用)       │
└────────┬─────────┘
         │
         ▼
   修正后的 JSON
```


## 项目结构

```
.
├── src/
│   ├── __init__.py          # 公共导出
│   ├── pipeline.py          # 七步流水线 (Step 0-6) + Step 3.5 跨层映射 + 缓存/resume
│   ├── evaluate_match.py    # 硬匹配验证 + ID 前缀校验 + 枚举校验 + 一致性检查
│   ├── review.py            # Review Agent（基于硬匹配错误报告的 LLM 修正）
│   ├── llm_client.py        # LLM 客户端（OpenAI 兼容 API）
│   └── ocr.py               # PDF → 图片 → GLM-OCR → Markdown
├── prompts/                 # LLM 提示词模板（.md 文件，含 {annotation_guidance} 占位符）
│   ├── step0_split.md
│   ├── step1_linkage_design.md
│   ├── step2_pico.md
│   ├── step3_trial_structure.md
│   ├── step4_effects.md
│   └── step5_mechanism.md
├── template/                # Schema 定义
│   ├── schema.json          # 目标 JSON schema（空骨架，LLM 填空用）
│   └── schema_annotation.json  # Schema 字段级标注规范（枚举值 + 判定规则 + 注意事项）
├── batch_run.py             # 批处理脚本（支持子文件夹 batch 模式）
├── requirements.txt
└── .env                     # API 配置
```

## 环境配置

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env：
#   OPENAI_API_KEY=your_api_key
#   OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
#   DEFAULT_MODEL=glm-5
#   DEFAULT_TEMPERATURE=0.1
#   DEFAULT_MAX_TOKENS=16384
#   VISION_MODEL=glm-4.6v
```

## 运行方式

### 批量处理

支持两种输入目录结构：

1. **平铺模式**：`-i ./pdfs`，目录下直接放 PDF 文件
2. **子文件夹模式**：`-i /mnt/drug_pdf/S`，目录下按编号分子文件夹

```bash
# 处理指定子文件夹
python batch_run.py \
  -i /mnt/drug_pdf/S/ \
  -o output_0320 \
  --batches 00 \
  --resume

# 限制每批处理数量
python batch_run.py \
  -i /mnt/drug_pdf/S/ \
  -o output_0320 \
  --batch-size 5

# 多线程并发
python batch_run.py \
  -i /mnt/drug_pdf/S/ \
  -o output_0320 \
  --batches 00 01 \
  --max-workers 4

# 复用已有 OCR 缓存
python batch_run.py \
  -i /mnt/drug_pdf/S/ \
  -o output_0320 \
  --ocr-dir /path/to/existing/cache_ocr \
  --resume
```

### 常用参数

| 参数 | 说明 |
|------|------|
| `-i`, `--input-dir` | 输入目录，支持平铺 PDF 或含子文件夹（默认 `./evidence_card`） |
| `-o`, `--output-dir` | 输出目录（默认 `./output`） |
| `--batch-size` | 每批最多处理 N 个新 PDF（0 = 不限制，默认 0） |
| `--batches` | 只处理指定的子文件夹（如 `--batches 00 01`，默认全部） |
| `--max-workers` | 并发线程数（默认 1，即串行） |
| `--model` | 覆盖默认 LLM 模型名 |
| `--api-key` | 覆盖环境变量中的 API Key |
| `--base-url` | 覆盖环境变量中的 Base URL |
| `--ocr-dir` | OCR 缓存目录（默认 `./cache_ocr`） |
| `--dpi` | PDF 转图片 DPI（默认 200） |
| `--no-validate-pages` | 跳过 OCR 尾页过滤 |
| `--resume` | 跳过已完成的文件（检查 `final.json` 是否存在） |


## 输出说明

### 主输出：`final.json`

完整的 schema-compliant JSON，包含七个顶层块：

```json
{
  "trial_linkage": { "nct_ids": [...], "pmid": "...", "doi": "...", "pmcid": "..." },
  "design": { "reported": { "randomized": "yes", "blinding": "double-blind", ... } },
  "pico": {
    "population": { "base_population": {...}, "analysis_populations": [...] },
    "interventions": [{ "intervention_id": "I1", "mapped_regimen_ids": ["R1", "R2"], ... }],
    "comparators": [{ "comparator_id": "K1", "mapped_regimen_ids": ["R3"], ... }],
    "outcomes": [{ "outcome_id": "O1", "role": "primary", ... }]
  },
  "trial_structure": {
    "regimens": [{ "regimen_id": "R1", "components": [...], ... }],
    "arms": [{ "arm_id": "A1", "regimen_id": "R1", "sample_size": 136, ... }],
    "comparisons": [{ "comparison_id": "C1", "treatment": {...}, "control": {...}, ... }]
  },
  "effect_estimates": [
    { "estimate_id": "E1", "comparison_id": "C1", "outcome_id": "O1", "value": -0.13, ... }
  ],
  "mechanism_evidence": {
    "target_actions": [{ "action_id": "TA1", "action_type": "inhibitor", ... }],
    "biomarker_effects": [{ "biomarker_id": "B1", "effect": "decrease", ... }],
    "claims": [{ "claim_id": "MC1", "scope": "clinical efficacy", "confidence": "high", ... }]
  },
  "metadata": {
    "extraction_mode": "automated",
    "confidence": "high",
    "schema_version": "v2",
    "annotator_id": "drug_agent_v2",
    "timestamp": "2026-03-25T12:00:00Z"
  }
}
```

### 中间缓存文件

每步独立缓存，`--resume` 时自动跳过已完成步骤：

| 文件 | 内容 |
|------|------|
| `step0_split.json` | 多研究拆分结果 |
| `step1_linkage_design.json` | 注册号 + 研究设计 |
| `step2_pico.json` | PICO 数据 |
| `step2_pico_report.json` | PICO 硬匹配报告 |
| `step3_trial_structure.json` | 试验结构 |
| `step3_trial_structure_report.json` | 试验结构硬匹配报告 |
| `step3_5_cross_mapping.json` | 跨层映射结果（v2 新增） |
| `step4_effects.json` | 效应估计 |
| `step4_effects_report.json` | 效应估计硬匹配报告（最严格） |
| `step5_mechanism.json` | 机制证据 |
| `step5_mechanism_report.json` | 机制证据硬匹配报告 |
| `verification_reports.json` | 所有步骤验证报告汇总 + 整体置信度 |

### 置信度评估

`metadata.confidence` 基于所有步骤的验证报告自动计算：

| 值 | 含义 |
|------|------|
| `"high"` | 所有步骤硬匹配零错误 |
| `"moderate"` | 有错误但 Review 后全部修正 |
| `"low"` | Review 后仍有未修正的错误 |


## 关键模块详解

### 硬匹配验证（`evaluate_match.py`）

**解决的问题**：LLM 经常捏造论文中不存在的数值（数值幻觉），或引用不存在的上游 ID。硬匹配验证在每步提取后立即运行，完全不依赖 LLM，快速且确定性。

**HardMatchEvaluator** 提供的检查器：

| 方法 | 适用步骤 | 检查内容 |
|------|---------|---------|
| `check_pico()` | Step 2 | sample_size, age, sex percent, timepoint |
| `check_pico_consistency()` | Step 2 | sub-pop size ≤ base size; safety outcome polarity = neutral (v2) |
| `check_design_consistency()` | Step 1+2 | single-arm ↔ comparators=[] 一致性 (v2) |
| `check_trial_structure()` | Step 3 | dose/duration/sample_size + arm↔regimen 引用 |
| `check_effect_estimates()` | Step 4 | value/CI/p_value + comparison/outcome/population ID 引用 + estimate_type/direction 枚举 (v2) |
| `check_mechanism_evidence()` | Step 5 | biomarker value/CI/p_value + ID 前缀校验 TA\*/B\*/MC\* (v2) + action_type 枚举 (v2) + scope 单值 (v2) |

**Anchor 提取逻辑**：从论文全文用正则提取所有数字，生成多种字符串表示（`0.85` → `"0.85"`, `"0.850"`, `".85"` 等），构建 O(1) 查找集合。

### Schema Annotation 注入机制（v2 新增）

`schema_annotation.json` 包含每个字段的详细标注规范（枚举值定义、判定规则、优先级规则、冲突处理、禁止推断规则等）。Pipeline 按 step 标记自动提取对应段落，注入到每个 step 的 prompt 中：

```
schema_annotation.json
    │
    ├── // step 1 ... // step 2  →  注入 step1_linkage_design.md 的 {annotation_guidance}
    ├── // step 2 ... // step 3  →  注入 step2_pico.md 的 {annotation_guidance}
    ├── // step 3 ... // step 4  →  注入 step3_trial_structure.md 的 {annotation_guidance}
    ├── // step 4 ... // step 5  →  注入 step4_effects.md 的 {annotation_guidance}
    └── // step 5 ... // metadata →  注入 step5_mechanism.md 的 {annotation_guidance}
```

这样 LLM 在每个 step 都能看到该步骤所有字段的精确标注规范，而不仅仅是 prompt 中的简化说明。

### Step 3.5 跨层映射（v2 新增）

解决 v1 中 `mapped_regimen_ids` 始终为空的问题。在 Step 3（trial_structure）完成后、Step 4（effects）之前执行：

1. 将 PICO 的 interventions/comparators 与 trial_structure 的 regimens 做药物成分匹配
2. 回填 `interventions[].mapped_regimen_ids` 和 `comparators[].mapped_regimen_ids`
3. 校验单臂试验的一致性（comparators=[] 时不应有映射）

### Review Agent（`review.py`）

**仅在硬匹配发现错误时调用**，避免不必要的 LLM 开销。

工作方式：
1. 接收硬匹配错误报告（明确指出哪个字段的哪个值不可追溯）
2. 将错误报告 + 原始提取 JSON + 论文全文发送给 LLM
3. LLM 被要求：找到正确值替换，或设为 null
4. 修正后再次运行硬匹配验证，确认修正有效

### 分步 LLM 调用策略

| 步骤 | 输入上下文 | 说明 |
|------|----------|------|
| Step 0 | 论文全文 | 多研究拆分检测 |
| Step 1 | 论文全文 + annotation(step1) | 独立提取 |
| Step 2 | 论文全文 + annotation(step2) | 独立提取 |
| Step 3 | 论文全文 + Step 2 PICO + annotation(step3) | 需要 intervention/comparator 定义 |
| Step 3.5 | Step 2 PICO + Step 3 structure | 跨层映射（无论文全文） |
| Step 4 | 论文全文 + Step 2 PICO + Step 3 structure + annotation(step4) | 需要 comparison/outcome/population ID |
| Step 5 | 论文全文 + Step 3 structure + Step 4 effects + annotation(step5) | 需要对齐 comparison_id 和 estimate_id |

每步给 LLM 一个**空 JSON skeleton**（从 `schema.json` 提取）+ 对应的 **annotation guidance**（从 `schema_annotation.json` 提取），LLM 负责填空。

### OCR 模块（`ocr.py`）

1. PDF → 高分辨率图片（PyMuPDF, 默认 200 DPI）
2. 尾页过滤（GLM-4V 识别参考文献/附录页）
3. GLM-OCR 识别（Markdown 格式输出）
4. 结果缓存到 `cache_ocr/{pdf_stem}/combined.md`


## v2 变更日志

### 架构变更

- `schema_annotation.md` → `schema_annotation.json`：字段级标注规范从 Markdown 改为带注释的 JSON，方便按 step 分段提取并注入 prompt
- 新增 **Step 3.5 Cross-layer Mapping**：自动回填 `mapped_regimen_ids`
- `schema_version` 从 `"v1_patch_1"` 更新为 `"v2"`
- `annotator_id` 从 `"drug_agent_v1"` 更新为 `"drug_agent_v2"`

### Prompt 改进（基于 4 篇论文的评估反馈）

| 错误类型 | 修正方式 |
|----------|----------|
| `base_population.sample_size` 缺失 | 明确允许从 Table 各组 N 加总 |
| `sex` 只填一半 | 规定必须同时填 female% 和 male% |
| `age` 只填 range 不填 mean±SD | 规定论文两者都报告时两者都填 |
| 单臂试验创建假 comparator | 规定 single-arm → comparators=[], effects=[] |
| Safety outcome polarity 错标 | 规定 role=safety → polarity=neutral |
| Phase 1 outcome role 误标 primary | 未明确标注时填 exploratory |
| Placebo regimen drug_name 填成试验药 | 明确 placebo → drug_name="placebo" |
| mechanism ID 用 M1 而非 TA1 | 用表格强调 TA\*/B\*/MC\* 前缀 |
| action_type 用动词形式 | 枚举 inhibitor/agonist 而非 inhibits/activates |
| claims scope 填多个值 | 规定单值，多主题拆分为多条 claim |
| DOI 漏提取 | 增加搜索优先级指引 |
| Extension study randomized 误标 | 明确 open-label extension → randomized="no" |

### evaluate_match.py 新增校验

- mechanism ID 前缀校验（TA\*/B\*/MC\*）
- action_type 枚举校验（inhibitor/agonist/antagonist/modulator/unclear）
- claims scope 单值校验
- safety outcome polarity 警告
- estimate_type / direction 枚举校验
- design ↔ PICO 一致性检查（single-arm vs comparators）


## Schema 说明

完整的 schema 字段定义参见 `template/schema_annotation.json`。核心结构：

| 块 | 说明 | 关键字段 |
|------|------|---------|
| `trial_linkage` | 试验注册号 | nct_ids, pmid, doi |
| `design` | 研究设计 | randomized, blinding, allocation, multicenter |
| `pico.population` | 人群 | base_population (P0), analysis_populations (P1, P2...) |
| `pico.interventions` | 干预 | I1/I2..., drug_list, mapped_regimen_ids |
| `pico.comparators` | 对照 | K1/K2..., type (placebo/active/...), mapped_regimen_ids |
| `pico.outcomes` | 结局 | O1/O2..., role (primary/secondary), polarity, timepoint |
| `trial_structure.regimens` | 治疗方案 | R1/R2..., components (RC1/RC2... drug/dose/frequency/route) |
| `trial_structure.arms` | 分组 | A1/A2..., regimen_id, sample_size |
| `trial_structure.comparisons` | 比较关系 | C1/C2..., treatment↔control, population_id |
| `effect_estimates` | 效应估计 | E1/E2..., value, CI, p_value, direction |
| `mechanism_evidence` | 机制证据 | target_actions (TA\*), biomarker_effects (B\*), claims (MC\*) |
| `metadata` | 元数据 | extraction_mode, confidence, schema_version="v2" |

### ID 约定

| 前缀 | 实体 | 路径 |
|------|------|------|
| P0 | base population | pico.population.base_population |
| P1, P2... | analysis populations | pico.population.analysis_populations[] |
| I1, I2... | interventions | pico.interventions[] |
| K1, K2... | comparators | pico.comparators[] |
| O1, O2... | outcomes | pico.outcomes[] |
| R1, R2... | regimens | trial_structure.regimens[] |
| RC1, RC2... | regimen components | trial_structure.regimens[].components[] |
| A1, A2... | arms | trial_structure.arms[] |
| AG1, AG2... | analysis groups | trial_structure.analysis_groups[] |
| C1, C2... | comparisons | trial_structure.comparisons[] |
| E1, E2... | effect estimates | effect_estimates[] |
| TA1, TA2... | target actions | mechanism_evidence.target_actions[] |
| B1, B2... | biomarker effects | mechanism_evidence.biomarker_effects[] |
| MC1, MC2... | mechanism claims | mechanism_evidence.claims[] |
