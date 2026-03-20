# Drug-Database Evidence Extraction

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
│  Step 1: 注册信息 + 设计   │  → trial_linkage (NCT/DOI/PMID)
│                          │  → design (randomized/blinding/allocation/multicenter)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Step 2: PICO            │  → population (base + analysis populations)
│  + 硬匹配验证              │  → intervention / comparator / outcomes
│  + 一致性检查              │  → sub-pop sample_size ≤ base sample_size
│  + Review（如有错误）      │  → LLM 修正不可追溯的数值
└────────┬─────────────────┘
         │  ← 独立调用
         ▼
┌──────────────────────────┐
│  Step 3: 试验结构          │  → regimens (drug/dose/frequency/route/duration)
│  + 硬匹配验证              │  → arms (分组 + 样本量)
│  + 引用对齐检查            │  → comparisons (treatment vs control)
│  + Review（如有错误）      │  → arm.regimen_id → 已定义 regimen
└────────┬─────────────────┘
         │  ← 携带 Step 2 上下文
         ▼
┌──────────────────────────┐
│  Step 4: 效应估计         │  → 逐行扫描 Table/Figure
│  + 严格硬匹配              │  → value / CI / p_value 必须论文原文可追溯
│  + ID 引用检查            │  → comparison_id / outcome_id / population_id ← 上游定义
│  + Review（如有错误）      │  → LLM 查找正确值或删除
└────────┬─────────────────┘
         │  ← 携带 Step 2 + Step 3 上下文
         ▼
┌──────────────────────────┐
│  Step 5： 机制证据         │  → target_actions (药物-靶点关系)
│  + 轻度硬匹配              │  → biomarker_effects (生物标志物变化)
│  + ID 对齐                │  → claims (核心结论，1-3 条)
└────────┬─────────────────┘
         │  ← 携带 Step 3 + Step 4 上下文
         ▼
┌──────────────────────────┐
│  Step 6:  合并 + 元数据    │  → 合并 Step 1-5
│                          │  → 计算 confidence (high/moderate/low)
│                          │  → 写入 metadata
└────────┬─────────────────┘
         │
         ▼
   final.json + verification_reports.json
```

### 数据流概览

```
Step 1 → step1_linkage_design.json
  独立提取，无上下文依赖
  ↓
Step 2 → step2_pico.json + step2_pico_report.json
  独立提取
  硬匹配：sample_size, age, sex percent, timepoint value
  一致性：sub-pop size ≤ base size
  ↓
Step 3 → step3_trial_structure.json + step3_trial_structure_report.json
  输入：Step 2 PICO 作为上下文
  硬匹配：dose value, duration value, arm sample_size
  引用对齐：arm.regimen_id, comparison.ref_id, comparison.population_id
  ↓
Step 4 → step4_effects.json + step4_effects_report.json
  输入：Step 2 PICO + Step 3 structure 作为上下文
  严格硬匹配：value, ci.lower, ci.upper, p_value
  引用对齐：comparison_id, outcome_id, population_id
  ↓
Step 5 → step5_mechanism.json + step5_mechanism_report.json
  输入：Step 3 structure + Step 4 effects 作为上下文
  轻度硬匹配：biomarker value/ci/p_value
  引用对齐：comparison_id, linked_estimate_id
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
│   ├── pipeline.py          # 六步流水线 (Step 1-6) + 缓存/resume
│   ├── evaluate_match.py    # 硬匹配验证（anchor 提取 + 逐字段检查 + 一致性检查）
│   ├── review.py            # Review Agent（基于硬匹配错误报告的 LLM 修正）
│   ├── llm_client.py        # LLM 客户端（OpenAI 兼容 API）
│   └── ocr.py               # PDF → 图片 → GLM-OCR → Markdown
├── prompts/                 # LLM 提示词模板（.md 文件）
│   ├── step1_linkage_design.md
│   ├── step2_pico.md
│   ├── step3_trial_structure.md
│   ├── step4_effects.md
│   └── step5_mechanism.md
├── template/                # Schema 定义
│   ├── schema.json          # 目标 JSON schema（空骨架，LLM 填空用）
│   └── schema_annotation.md # Schema 字段说明文档（枚举值 + 标注规则）
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

```
/mnt/drug_pdf/S/
├── 00/
│   ├── paper1.pdf
│   ├── paper2.pdf
│   └── ...
└── 01/
    ├── paper3.pdf
    └── ...
```

输出按 batch 分目录：

```
output/
├── 00/
│   ├── paper1/
│   │   ├── step1_linkage_design.json
│   │   ├── step2_pico.json
│   │   ├── step2_pico_report.json
│   │   ├── step3_trial_structure.json
│   │   ├── step3_trial_structure_report.json
│   │   ├── step4_effects.json
│   │   ├── step4_effects_report.json
│   │   ├── step5_mechanism.json
│   │   ├── step5_mechanism_report.json
│   │   ├── final.json
│   │   └── verification_reports.json
│   └── ...
└── _batch_summary.json
```

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

| 参数                    | 说明                                         |
|-----------------------|--------------------------------------------|
| `-i`, `--input-dir`   | 输入目录，支持平铺 PDF 或含子文件夹（默认 `./evidence_card`） |
| `-o`, `--output-dir`  | 输出目录（默认 `./output`）                        |
| `--batch-size`        | 每批最多处理 N 个新 PDF（0 = 不限制，默认 0）              |
| `--batches`           | 只处理指定的子文件夹（如 `--batches 00 01`，默认全部）       |
| `--max-workers`       | 并发线程数（默认 1，即串行）                            |
| `--model`             | 覆盖默认 LLM 模型名                               |
| `--api-key`           | 覆盖环境变量中的 API Key                           |
| `--base-url`          | 覆盖环境变量中的 Base URL                          |
| `--ocr-dir`           | OCR 缓存目录（默认 `./cache_ocr`）                 |
| `--dpi`               | PDF 转图片 DPI（默认 200）                        |
| `--no-validate-pages` | 跳过 OCR 尾页过滤                                |
| `--resume`            | 跳过已完成的文件（检查 `final.json` 是否存在）             |


## 输出说明

### 主输出：`final.json`

完整的 schema-compliant JSON，包含七个顶层块：

```json
{
  "trial_linkage": {
    "nct_ids": [
      ...
    ],
    "pmid": "...",
    "doi": "...",
    "pmcid": "..."
  },
  "design": {
    "reported": {
      "randomized": "yes",
      "blinding": "double-blind",
      ...
    }
  },
  "pico": {
    "population": {
      "base_population": {
        ...
      },
      "analysis_populations": [
        ...
      ]
    },
    "intervention": {
      "label": "...",
      "drug_list": [
        ...
      ],
      ...
    },
    "comparator": {
      "label": "...",
      "type": "placebo",
      ...
    },
    "outcomes": [
      {
        "outcome_id": "O1",
        "label": "...",
        "role": "primary",
        ...
      }
    ]
  },
  "trial_structure": {
    "regimens": [
      {
        "regimen_id": "R1",
        "components": [
          ...
        ],
        ...
      }
    ],
    "arms": [
      {
        "arm_id": "A1",
        "regimen_id": "R1",
        "sample_size": 136,
        ...
      }
    ],
    "comparisons": [
      {
        "comparison_id": "C1",
        "treatment": {
          ...
        },
        "control": {
          ...
        },
        ...
      }
    ]
  },
  "effect_estimates": [
    {
      "estimate_id": "E1",
      "comparison_id": "C1",
      "outcome_id": "O1",
      "value": -0.13,
      "ci": {
        "lower": -0.35,
        "upper": 0.09
      },
      "p_value": 0.24,
      ...
    }
  ],
  "mechanism_evidence": {
    "target_actions": [
      ...
    ],
    "biomarker_effects": [
      ...
    ],
    "claims": [
      {
        "claim_id": "MC1",
        "text": "...",
        "scope": "clinical efficacy",
        ...
      }
    ]
  },
  "metadata": {
    "extraction_mode": "automated",
    "confidence": "high",
    "schema_version": "v1_patch_1",
    "timestamp": "2026-03-20T12:00:00Z"
  }
}
```

### 中间缓存文件

每步独立缓存，`--resume` 时自动跳过已完成步骤：

| 文件                                  | 内容                 |
|-------------------------------------|--------------------|
| `step1_linkage_design.json`         | 注册号 + 研究设计         |
| `step2_pico.json`                   | PICO 数据            |
| `step2_pico_report.json`            | PICO 硬匹配报告         |
| `step3_trial_structure.json`        | 试验结构               |
| `step3_trial_structure_report.json` | 试验结构硬匹配报告          |
| `step4_effects.json`                | 效应估计               |
| `step4_effects_report.json`         | 效应估计硬匹配报告（最严格）     |
| `step5_mechanism.json`              | 机制证据               |
| `step5_mechanism_report.json`       | 机制证据硬匹配报告          |
| `verification_reports.json`         | 所有步骤验证报告汇总 + 整体置信度 |

### 置信度评估

`metadata.confidence` 基于所有步骤的验证报告自动计算：

| 值            | 含义                |
|--------------|-------------------|
| `"high"`     | 所有步骤硬匹配零错误        |
| `"moderate"` | 有错误但 Review 后全部修正 |
| `"low"`      | Review 后仍有未修正的错误  |


## 关键模块详解

### 硬匹配验证（`evaluate_match.py`）

**解决的问题**：LLM 经常捏造论文中不存在的数值（数值幻觉），或引用不存在的上游 ID。硬匹配验证在每步提取后立即运行，完全不依赖
LLM，快速且确定性。

**HardMatchEvaluator** 提供五个检查器：

| 方法                           | 适用步骤   | 检查内容                                                   |
|------------------------------|--------|--------------------------------------------------------|
| `check_pico()`               | Step 2 | sample_size, age, sex percent, timepoint               |
| `check_pico_consistency()`   | Step 2 | sub-pop size ≤ base size                               |
| `check_trial_structure()`    | Step 3 | dose/duration/sample_size + arm↔regimen 引用             |
| `check_effect_estimates()`   | Step 4 | value/CI/p_value + comparison/outcome/population ID 引用 |
| `check_mechanism_evidence()` | Step 5 | biomarker value/CI/p_value + comparison/estimate ID 引用 |

**Anchor 提取逻辑**：从论文全文用正则提取所有数字，生成多种字符串表示（`0.85` → `"0.85"`, `"0.850"`, `".85"` 等），构建 O(1)
查找集合。

### Review Agent（`review.py`）

**仅在硬匹配发现错误时调用**，避免不必要的 LLM 开销。

工作方式：

1. 接收硬匹配错误报告（明确指出哪个字段的哪个值不可追溯）
2. 将错误报告 + 原始提取 JSON + 论文全文发送给 LLM
3. LLM 被要求：找到正确值替换，或设为 null
4. 修正后再次运行硬匹配验证，确认修正有效

### 分步 LLM 调用策略

各步骤的上下文依赖关系决定了 LLM 调用的输入：

| 步骤     | 输入上下文                                    | 说明                                    |
|--------|------------------------------------------|---------------------------------------|
| Step 1 | 论文全文                                     | 独立提取                                  |
| Step 2 | 论文全文                                     | 独立提取                                  |
| Step 3 | 论文全文 + Step 2 PICO                       | 需要知道 intervention/comparator 定义       |
| Step 4 | 论文全文 + Step 2 PICO + Step 3 structure    | 需要知道 comparison/outcome/population ID |
| Step 5 | 论文全文 + Step 3 structure + Step 4 effects | 需要对齐 comparison_id 和 estimate_id      |

每步给 LLM 一个**空 JSON skeleton**（从 `schema.json` 提取），LLM 负责填空。这保证了输出结构严格匹配 schema。

### OCR 模块（`ocr.py`）

复用自 causal_agent，流程不变：

1. PDF → 高分辨率图片（PyMuPDF, 默认 200 DPI）
2. 尾页过滤（GLM-4V 识别参考文献/附录页）
3. GLM-OCR 识别（Markdown 格式输出）
4. 结果缓存到 `cache_ocr/{pdf_stem}/combined.md`


## Schema 说明

完整的 schema 字段定义参见 `template/schema_annotation.md`。核心结构：

| 块                             | 说明    | 关键字段                                                   |
|-------------------------------|-------|--------------------------------------------------------|
| `trial_linkage`               | 试验注册号 | nct_ids, pmid, doi                                     |
| `design`                      | 研究设计  | randomized, blinding, allocation, multicenter          |
| `pico.population`             | 人群    | base_population (P0), analysis_populations (P1, P2...) |
| `pico.intervention`           | 干预    | label, drug_list                                       |
| `pico.comparator`             | 对照    | label, type (placebo/active/...)                       |
| `pico.outcomes`               | 结局    | O1/O2/..., role (primary/secondary), timepoint         |
| `trial_structure.regimens`    | 治疗方案  | R1/R2/..., components (drug/dose/frequency/route)      |
| `trial_structure.arms`        | 分组    | A1/A2/..., regimen_id, sample_size                     |
| `trial_structure.comparisons` | 比较关系  | C1/C2/..., treatment↔control, population_id            |
| `effect_estimates`            | 效应估计  | E1/E2/..., value, CI, p_value, direction               |
| `mechanism_evidence`          | 机制证据  | target_actions, biomarker_effects, claims              |
| `metadata`                    | 元数据   | extraction_mode, confidence, schema_version            |
