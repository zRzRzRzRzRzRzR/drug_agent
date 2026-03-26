import json
import sys
from typing import Dict, List, Optional

from .llm_client import GLMClient

_REVIEW_SYSTEM_PROMPT = """
你是一名临床试验数据审核专家。你会收到：

1. 从论文中提取的 JSON 数据块
2. 硬匹配验证报告（告诉你哪些数值在论文原文中找不到）
3. 论文原文

你的任务：
- 对于每个标记为 ERROR 的字段，去论文原文中找到正确的值
- 如果在论文中确实找不到该值，将其设为 null
- 对于 WARNING 字段，检查并确认或修正
- 特别注意：如果 WARNING 指出某个 null 字段在论文中可能存在对应值，请仔细搜索论文原文，如果确实能找到就填入正确值
- 不要修改未标记为错误的字段
- 不要捏造任何数值

输出严格 JSON，结构与输入完全一致，只修正有问题的字段。
"""

_NULL_REVIEW_SYSTEM_PROMPT = """
你是一名临床试验数据审核专家。你会收到：

1. 从论文中提取的 JSON 数据块（部分字段为 null）
2. 空值完整性检查报告（指出哪些 null 字段在论文中可能有对应值）
3. 论文原文

你的任务：
- 对于报告中指出的每个 null 字段，仔细搜索论文全文
- 如果确实能找到该字段的值（如年龄下限、性别比例、国家等），将 null 替换为正确值
- 如果论文中确实没有报告该信息，保持 null 不变
- 不要修改报告中未提及的字段
- 不要捏造任何数值——只填入论文中明确存在的信息
- 特别关注：入排标准中的年龄范围、表格中的人口统计学数据、方法部分的研究地区

输出严格 JSON，结构与输入完全一致。
"""


def review_with_hard_match(
    extracted_block: Dict,
    block_name: str,
    error_report: str,
    pdf_text: str,
    client: GLMClient,
) -> Dict:
    """
    Send hard-match errors to LLM for correction.

    Args:
        extracted_block: The extracted JSON block (e.g., pico, trial_structure)
        block_name: Name of the block (for logging)
        error_report: Human-readable error report from evaluate_match
        pdf_text: Full paper text
        client: GLM client

    Returns:
        Corrected JSON block
    """
    if "All values passed" in error_report:
        print(f"  [Review] {block_name}: no errors, skipping review", file=sys.stderr)
        return extracted_block

    prompt = f"""## 待审核的数据块: {block_name}

```json
{json.dumps(extracted_block, ensure_ascii=False, indent=2)}
```

## 硬匹配验证报告

{error_report}

## 修正要求

1. 对于每个 ERROR，在论文原文中搜索正确值并替换
2. 如果论文中确实没有报告该值，设为 null
3. 不要修改没有问题的字段
4. 保持 JSON 结构完全一致

## 论文原文

{pdf_text}

## 输出

输出修正后的完整 JSON（与输入结构一致）。只输出 JSON，不要其他内容。"""

    corrected = client.call_json(prompt, system_prompt=_REVIEW_SYSTEM_PROMPT)
    if isinstance(corrected, dict):
        print(
            f"  [Review] {block_name}: correction applied",
            file=sys.stderr,
        )
        return corrected
    else:
        print(
            f"  [Review] {block_name}: LLM returned non-dict, keeping original",
            file=sys.stderr,
        )
        return extracted_block


def review_null_completeness(
    extracted_block: Dict,
    block_name: str,
    null_report: str,
    pdf_text: str,
    client: GLMClient,
) -> Dict:
    """
    Review null fields that may have values available in the paper.
    Uses a specialized prompt that focuses on filling in missing data.
    """
    if "All values passed" in null_report:
        return extracted_block

    prompt = f"""## 待补全的数据块: {block_name}

```json
{json.dumps(extracted_block, ensure_ascii=False, indent=2)}
```

## 空值完整性检查报告

以下字段当前为 null，但论文中可能存在对应值：

{null_report}

## 补全要求

1. 对于报告中的每个 WARNING，在论文全文中仔细搜索对应信息
2. 重点搜索位置：
   - 入排标准（Inclusion/Exclusion criteria）→ 年龄范围
   - Table 1 / Baseline characteristics → 人口统计学数据
   - Methods / Study design → 研究地区、国家
   - CONSORT flow diagram → 样本量
3. 如果找到确切值，填入对应字段
4. 如果确实找不到，保持 null
5. 不要修改报告中未提及的字段
6. 不要捏造数值

## 论文原文

{pdf_text}

## 输出

输出补全后的完整 JSON（与输入结构一致）。只输出 JSON，不要其他内容。"""

    corrected = client.call_json(prompt, system_prompt=_NULL_REVIEW_SYSTEM_PROMPT)
    if isinstance(corrected, dict):
        # Log what changed
        _log_null_fills(extracted_block, corrected, block_name)
        return corrected
    else:
        print(
            f"  [Review] {block_name} null-completeness: LLM returned non-dict, keeping original",
            file=sys.stderr,
        )
        return extracted_block


def _log_null_fills(original: Dict, corrected: Dict, block_name: str) -> None:
    """Log fields that changed from null to a value."""
    fills = []
    _diff_nulls(original, corrected, "", fills)
    if fills:
        print(f"  [Review] {block_name} null-completeness: filled {len(fills)} fields", file=sys.stderr)
        for path, val in fills:
            print(f"    {path}: null -> {val}", file=sys.stderr)
    else:
        print(f"  [Review] {block_name} null-completeness: no new values found", file=sys.stderr)


def _diff_nulls(orig: Any, corr: Any, path: str, fills: List) -> None:
    """Recursively find fields that changed from null to non-null."""
    if isinstance(orig, dict) and isinstance(corr, dict):
        for k in orig:
            if k in corr:
                _diff_nulls(orig[k], corr[k], f"{path}.{k}" if path else k, fills)
    elif isinstance(orig, list) and isinstance(corr, list):
        for i in range(min(len(orig), len(corr))):
            _diff_nulls(orig[i], corr[i], f"{path}[{i}]", fills)
    elif orig is None and corr is not None:
        fills.append((path, corr))


def review_effects_with_context(
    effects: List[Dict],
    error_report: str,
    pdf_text: str,
    client: GLMClient,
    pico: Optional[Dict] = None,
    structure: Optional[Dict] = None,
) -> List[Dict]:
    """
    Review effect_estimates with upstream context.
    Handles both numeric hard-match errors and ID reference errors.
    """
    if "All values passed" in error_report:
        print(
            "  [Review] effect_estimates: no errors, skipping review", file=sys.stderr
        )
        return effects

    # Build context from upstream
    context_parts = []
    if pico:
        # Extract valid IDs for reference
        pop_ids = [
            pico.get("population", {})
            .get("base_population", {})
            .get("population_id", "P0")
        ]
        for ap in pico.get("population", {}).get("analysis_populations", []):
            pop_ids.append(ap.get("population_id", ""))
        outcome_ids = [o.get("outcome_id", "") for o in pico.get("outcomes", [])]
        context_parts.append(f"Valid population_ids: {pop_ids}")
        context_parts.append(f"Valid outcome_ids: {outcome_ids}")

    if structure:
        comp_ids = [
            c.get("comparison_id", "") for c in structure.get("comparisons", [])
        ]
        context_parts.append(f"Valid comparison_ids: {comp_ids}")

    context_str = "\n".join(context_parts) if context_parts else "(no upstream context)"

    prompt = f"""## 待审核的数据块: effect_estimates

```json
{json.dumps(effects, ensure_ascii=False, indent=2)}
```

## 上游有效ID

{context_str}

## 硬匹配验证报告

{error_report}

## 修正要求

1. 数值类错误：在论文原文中搜索正确值并替换，找不到则设为 null
2. ID引用错误：修正为上游已定义的有效 ID，或删除该 estimate
3. 不要修改没有问题的字段
4. 如果某条 estimate 的核心值（value）在论文中完全找不到，可以将整条删除

## 论文原文

{pdf_text}

## 输出

输出修正后的完整 effect_estimates 数组。只输出 JSON 数组，不要其他内容。"""

    corrected = client.call_json(prompt, system_prompt=_REVIEW_SYSTEM_PROMPT)
    if isinstance(corrected, list):
        print(
            f"  [Review] effect_estimates: corrected {len(corrected)} estimates",
            file=sys.stderr,
        )
        return corrected
    elif isinstance(corrected, dict) and "effect_estimates" in corrected:
        return corrected["effect_estimates"]
    else:
        print(
            f"  [Review] effect_estimates: unexpected output type, keeping original",
            file=sys.stderr,
        )
        return effects
