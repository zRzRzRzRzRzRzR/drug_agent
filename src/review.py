"""
review.py — Review agent for drug extraction pipeline.

Takes hard-match error reports and asks the LLM to:
  1. Find the correct value in the paper text, OR
  2. Delete the value (set to null) if it cannot be found

Design:
  - Input: extracted JSON block + error report + paper text
  - Output: corrected JSON block
  - The LLM is told exactly which fields failed and why
  - No guessing — either find it in the paper or delete it
"""

import json
import sys
from typing import Any, Dict, List, Optional

from .llm_client import GLMClient


_REVIEW_SYSTEM_PROMPT = """你是一名临床试验数据审核专家。你会收到：

1. 从论文中提取的 JSON 数据块
2. 硬匹配验证报告（告诉你哪些数值在论文原文中找不到）
3. 论文原文

你的任务：
- 对于每个标记为 ERROR 的字段，去论文原文中找到正确的值
- 如果在论文中确实找不到该值，将其设为 null
- 对于 WARNING 字段，检查并确认或修正
- 不要修改未标记为错误的字段
- 不要捏造任何数值

输出严格 JSON，结构与输入完全一致，只修正有问题的字段。"""


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

    try:
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
    except Exception as e:
        print(
            f"  [Review] {block_name}: review failed ({e}), keeping original",
            file=sys.stderr,
        )
        return extracted_block


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
        print("  [Review] effect_estimates: no errors, skipping review", file=sys.stderr)
        return effects

    # Build context from upstream
    context_parts = []
    if pico:
        # Extract valid IDs for reference
        pop_ids = [pico.get("population", {}).get("base_population", {}).get("population_id", "P0")]
        for ap in pico.get("population", {}).get("analysis_populations", []):
            pop_ids.append(ap.get("population_id", ""))
        outcome_ids = [o.get("outcome_id", "") for o in pico.get("outcomes", [])]
        context_parts.append(f"Valid population_ids: {pop_ids}")
        context_parts.append(f"Valid outcome_ids: {outcome_ids}")

    if structure:
        comp_ids = [c.get("comparison_id", "") for c in structure.get("comparisons", [])]
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

    try:
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
    except Exception as e:
        print(
            f"  [Review] effect_estimates: review failed ({e}), keeping original",
            file=sys.stderr,
        )
        return effects
