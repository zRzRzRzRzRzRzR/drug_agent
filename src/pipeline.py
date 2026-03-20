"""
pipeline.py — Drug-Database Evidence Extraction Pipeline.

Step 0: Multi-study split detection
Step 1-6: Per-study extraction with hard-match verification
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .evaluate_match import HardMatchEvaluator
from .llm_client import GLMClient
from .review import review_effects_with_context, review_with_hard_match

_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SRC_DIR.parent
_PROMPTS_DIR = _PROJECT_DIR / "prompts"
_TEMPLATE_DIR = _PROJECT_DIR / "template"
_SCHEMA_PATH = _TEMPLATE_DIR / "schema.json"
_ANNOTATION_PATH = _TEMPLATE_DIR / "schema_annotation.md"


def save_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> Saved: {path}", file=sys.stderr)


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    assert path.exists(), f"Prompt file not found: {path}"
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "latin1"):
        try:
            return raw.decode(enc, errors="strict")
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("utf-8", errors="replace")


def _load_schema() -> Dict:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_empty_block(schema: Dict, *keys: str) -> Any:
    obj = schema
    for key in keys:
        obj = obj[key]
    return json.loads(json.dumps(obj))


def _build_study_context(study_info: Optional[Dict]) -> str:
    if not study_info:
        return ""
    parts = [
        "\n## ⚠️ 多研究论文：当前仅处理以下研究单元\n",
        f"- **研究名称**: {study_info.get('study_name', 'N/A')}",
        f"- **NCT ID**: {study_info.get('nct_id', 'N/A')}",
        f"- **描述**: {study_info.get('description', 'N/A')}",
        "",
        "**重要**：本论文包含多个独立研究。请你**仅提取上述研究**的数据。",
        "忽略论文中属于其他研究的数据（如其他试验的样本量、效应值等）。",
        "论文全文仍然提供给你作为参考，但只提取当前研究的信息。\n",
    ]
    return "\n".join(parts)


def _inject_study_context(prompt: str, study_context: str) -> str:
    if not study_context:
        return prompt
    if "## 论文原文" in prompt:
        return prompt.replace("## 论文原文", f"{study_context}\n## 论文原文")
    elif "{paper_text}" in prompt:
        return prompt.replace("{paper_text}", f"{study_context}\n\n{{paper_text}}")
    else:
        return prompt + "\n" + study_context


# ---------------------------------------------------------------------------
# Step 0
# ---------------------------------------------------------------------------


def step0_split(client: GLMClient, pdf_text: str) -> Dict:
    prompt_template = _load_prompt("step0_split")
    full_prompt = prompt_template.replace("{paper_text}", pdf_text)
    result = client.call_json(full_prompt)

    n = result.get("n_studies", 1)
    needs_split = result.get("needs_split", False)
    print(f"[Step 0] Studies detected: {n}, needs_split={needs_split}", file=sys.stderr)
    if needs_split:
        for s in result.get("studies", []):
            print(
                f"  [{s.get('study_index')}] {s.get('study_name', '?')} "
                f"(NCT={s.get('nct_id', '?')}): {s.get('description', '')[:80]}",
                file=sys.stderr,
            )
    print(f"  Rationale: {result.get('split_rationale', 'N/A')}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Step 1
# ---------------------------------------------------------------------------


def step1_linkage_design(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    study_context: str = "",
) -> Dict:
    prompt_template = _load_prompt("step1_linkage_design")
    skeleton = {
        "trial_linkage": _extract_empty_block(schema, "trial_linkage"),
        "design": _extract_empty_block(schema, "design"),
    }
    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = _inject_study_context(full_prompt, study_context)
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    result = client.call_json(full_prompt)
    print(
        f"[Step 1] NCT={result.get('trial_linkage', {}).get('nct_ids', [])}",
        file=sys.stderr,
    )
    design = result.get("design", {}).get("reported", {})
    print(
        f"[Step 1] design: rand={design.get('randomized')}, blind={design.get('blinding')}",
        file=sys.stderr,
    )
    return result


# ---------------------------------------------------------------------------
# Step 2
# ---------------------------------------------------------------------------


def step2_pico(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    evaluator: HardMatchEvaluator,
    study_context: str = "",
) -> Tuple[Dict, Dict]:
    prompt_template = _load_prompt("step2_pico")
    skeleton = _extract_empty_block(schema, "pico")
    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = _inject_study_context(full_prompt, study_context)
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    pico = client.call_json(full_prompt)

    print("[Step 2] Running hard-match on PICO ...", file=sys.stderr)
    match_results = evaluator.check_pico(pico)
    consistency_results = evaluator.check_pico_consistency(pico)
    all_results = match_results + consistency_results
    report = evaluator.generate_structured_report(all_results)
    n_err = report["errors"]
    print(
        f"[Step 2] Hard-match: {n_err} errors, {report['warnings']} warnings",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(all_results)
        pico = review_with_hard_match(pico, "pico", error_text, pdf_text, client)
        match2 = evaluator.check_pico(pico) + evaluator.check_pico_consistency(pico)
        report_2 = evaluator.generate_structured_report(match2)
        print(f"[Step 2] After review: {report_2['errors']} errors", file=sys.stderr)
        report["after_review"] = report_2

    _print_pico_summary(pico)
    return pico, report


def _print_pico_summary(pico: Dict) -> None:
    pop = pico.get("population", {}).get("base_population", {})
    print(
        f"[Step 2] Population: n={pop.get('sample_size')}, desc={str(pop.get('description', ''))[:80]}",
        file=sys.stderr,
    )
    outcomes = pico.get("outcomes", [])
    print(f"[Step 2] Outcomes: {len(outcomes)} defined", file=sys.stderr)


# ---------------------------------------------------------------------------
# Step 3
# ---------------------------------------------------------------------------


def step3_trial_structure(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    pico: Dict,
    evaluator: HardMatchEvaluator,
    study_context: str = "",
) -> Tuple[Dict, Dict]:
    prompt_template = _load_prompt("step3_trial_structure")
    skeleton = _extract_empty_block(schema, "trial_structure")
    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{pico_context}", json.dumps(pico, indent=2, ensure_ascii=False)
    )
    full_prompt = _inject_study_context(full_prompt, study_context)
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    structure = client.call_json(full_prompt)

    print("[Step 3] Running hard-match on trial_structure ...", file=sys.stderr)
    match_results = evaluator.check_trial_structure(structure, pico)
    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    print(
        f"[Step 3] Hard-match: {n_err} errors, {report['warnings']} warnings",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(match_results)
        structure = review_with_hard_match(
            structure, "trial_structure", error_text, pdf_text, client
        )
        match2 = evaluator.check_trial_structure(structure, pico)
        report_2 = evaluator.generate_structured_report(match2)
        print(f"[Step 3] After review: {report_2['errors']} errors", file=sys.stderr)
        report["after_review"] = report_2

    n_reg = len(structure.get("regimens", []))
    n_arm = len(structure.get("arms", []))
    n_comp = len(structure.get("comparisons", []))
    print(
        f"[Step 3] Structure: {n_reg} regimens, {n_arm} arms, {n_comp} comparisons",
        file=sys.stderr,
    )
    return structure, report


# ---------------------------------------------------------------------------
# Step 4
# ---------------------------------------------------------------------------


def step4_effects(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    pico: Dict,
    structure: Dict,
    evaluator: HardMatchEvaluator,
    study_context: str = "",
) -> Tuple[List[Dict], Dict]:
    prompt_template = _load_prompt("step4_effects")
    skeleton_item = schema["effect_estimates"][0]
    full_prompt = prompt_template.replace(
        "{estimate_skeleton}", json.dumps(skeleton_item, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{pico_context}", json.dumps(pico, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{structure_context}", json.dumps(structure, indent=2, ensure_ascii=False)
    )
    full_prompt = _inject_study_context(full_prompt, study_context)
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    result = client.call_json(full_prompt)
    if isinstance(result, list):
        effects = result
    elif isinstance(result, dict):
        effects = result.get("effect_estimates", [])
    else:
        effects = []

    valid_comp_ids = {c.get("comparison_id") for c in structure.get("comparisons", [])}
    valid_outcome_ids = {o.get("outcome_id") for o in pico.get("outcomes", [])}
    valid_pop_ids = {
        pico.get("population", {}).get("base_population", {}).get("population_id", "P0")
    }
    for ap in pico.get("population", {}).get("analysis_populations", []):
        valid_pop_ids.add(ap.get("population_id"))

    print("[Step 4] Running hard-match on effect_estimates ...", file=sys.stderr)
    match_results = evaluator.check_effect_estimates(
        effects, valid_comp_ids, valid_outcome_ids, valid_pop_ids
    )
    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    print(
        f"[Step 4] Hard-match: {n_err} errors, {report['warnings']} warnings across {len(effects)} estimates",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(match_results)
        effects = review_effects_with_context(
            effects, error_text, pdf_text, client, pico, structure
        )
        match2 = evaluator.check_effect_estimates(
            effects, valid_comp_ids, valid_outcome_ids, valid_pop_ids
        )
        report_2 = evaluator.generate_structured_report(match2)
        print(f"[Step 4] After review: {report_2['errors']} errors", file=sys.stderr)
        report["after_review"] = report_2

    print(f"[Step 4] Final: {len(effects)} effect estimates", file=sys.stderr)
    return effects, report


# ---------------------------------------------------------------------------
# Step 5
# ---------------------------------------------------------------------------


def step5_mechanism(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    structure: Dict,
    effects: List[Dict],
    evaluator: HardMatchEvaluator,
    study_context: str = "",
) -> Tuple[Dict, Dict]:
    prompt_template = _load_prompt("step5_mechanism")
    skeleton = _extract_empty_block(schema, "mechanism_evidence")
    valid_comp_ids = {c.get("comparison_id") for c in structure.get("comparisons", [])}
    valid_estimate_ids = {e.get("estimate_id") for e in effects}

    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{structure_context}", json.dumps(structure, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{effects_context}", json.dumps(effects, indent=2, ensure_ascii=False)
    )
    full_prompt = _inject_study_context(full_prompt, study_context)
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    mechanism = client.call_json(full_prompt)

    print("[Step 5] Running hard-match on mechanism_evidence ...", file=sys.stderr)
    match_results = evaluator.check_mechanism_evidence(
        mechanism, valid_comp_ids, valid_estimate_ids
    )
    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    print(
        f"[Step 5] Hard-match: {n_err} errors, {report['warnings']} warnings",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(match_results)
        mechanism = review_with_hard_match(
            mechanism, "mechanism_evidence", error_text, pdf_text, client
        )

    print(
        f"[Step 5] Mechanism: {len(mechanism.get('target_actions', []))} targets, "
        f"{len(mechanism.get('biomarker_effects', []))} biomarkers, "
        f"{len(mechanism.get('claims', []))} claims",
        file=sys.stderr,
    )
    return mechanism, report


# ---------------------------------------------------------------------------
# Step 6
# ---------------------------------------------------------------------------


def step6_merge(
    linkage_design: Dict,
    pico: Dict,
    structure: Dict,
    effects: List[Dict],
    mechanism: Dict,
    study_info: Optional[Dict] = None,
) -> Dict:
    final = {
        "trial_linkage": linkage_design.get("trial_linkage", {}),
        "design": linkage_design.get("design", {}),
        "pico": pico,
        "trial_structure": structure,
        "effect_estimates": effects,
        "mechanism_evidence": mechanism,
        "metadata": {
            "extraction_mode": "automated",
            "confidence": None,
            "schema_version": "v1_patch_1",
            "annotator_id": "drug_agent_v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if study_info:
        final["metadata"]["study_name"] = study_info.get("study_name")
        final["metadata"]["study_index"] = study_info.get("study_index")
    return final


def _compute_confidence(reports: List[Dict]) -> str:
    total_errors = sum(r.get("errors", 0) for r in reports)
    total_errors_after = sum(
        r.get("after_review", {}).get("errors", 0)
        for r in reports
        if "after_review" in r
    )
    if total_errors == 0:
        return "high"
    elif total_errors_after == 0:
        return "moderate"
    else:
        return "low"


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class DrugExtractionPipeline:
    def __init__(
        self,
        client: GLMClient,
        ocr_text_func: Callable[[str], str],
        ocr_init_func: Optional[Callable] = None,
        ocr_output_dir: str = "./cache_ocr",
        ocr_dpi: int = 200,
        ocr_validate_pages: bool = True,
        max_retries: int = 1,
    ):
        self.client = client
        self.ocr_text_func = ocr_text_func
        self.schema = _load_schema()
        self.max_retries = max_retries
        print(f"[Pipeline] Schema: {_SCHEMA_PATH}", file=sys.stderr)

        if ocr_init_func is not None:
            ocr_init_func(
                ocr_output_dir=ocr_output_dir,
                client=client,
                dpi=ocr_dpi,
                validate_pages=ocr_validate_pages,
            )

    def _get_pdf_text(self, pdf_path: str) -> str:
        return self.ocr_text_func(pdf_path)

    def run(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        resume: bool = False,
        force_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Run the full pipeline. Returns list of final JSONs (one per study).
        Single-study papers return a list with one element.
        """
        pdf_name = Path(pdf_path).stem
        base_dir = Path(output_dir) if output_dir else None
        pdf_dir = None
        if base_dir:
            pdf_dir = base_dir / pdf_name
            pdf_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"[Pipeline] Processing: {pdf_name}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        t_start = time.time()
        pdf_text = self._get_pdf_text(pdf_path)
        evaluator = HardMatchEvaluator(pdf_text)

        # -- Step 0: Multi-study split --
        split_result = self._run_step(
            step_name="step0_split",
            step_func=lambda: step0_split(self.client, pdf_text),
            pdf_dir=pdf_dir,
            resume=resume,
        )

        needs_split = split_result.get("needs_split", False)
        studies = split_result.get("studies", [])

        if not needs_split or len(studies) <= 1:
            studies = [None]  # single study, no context needed

        # -- Run Step 1-6 per study --
        all_finals = []
        for study_idx, study_info in enumerate(studies):
            if study_info is not None:
                study_label = study_info.get("study_name") or f"Study {study_idx + 1}"
                study_context = _build_study_context(study_info)
                suffix = f"_{study_info.get('study_index', study_idx + 1)}"
                print(
                    f"\n{'━'*60}\n  Processing: {study_label}\n{'━'*60}",
                    file=sys.stderr,
                )
            else:
                study_context = ""
                suffix = ""

            final = self._run_single_study(
                pdf_text=pdf_text,
                evaluator=evaluator,
                schema=self.schema,
                study_info=study_info,
                study_context=study_context,
                suffix=suffix,
                pdf_dir=pdf_dir,
                resume=resume,
            )
            all_finals.append(final)

        elapsed = round(time.time() - t_start, 1)
        print(f"\n{'='*60}", file=sys.stderr)
        print(
            f"[Pipeline] Complete: {pdf_name} ({elapsed}s), {len(all_finals)} study(ies)",
            file=sys.stderr,
        )
        print(f"{'='*60}\n", file=sys.stderr)

        return all_finals

    def _run_single_study(
        self,
        pdf_text: str,
        evaluator: HardMatchEvaluator,
        schema: Dict,
        study_info: Optional[Dict],
        study_context: str,
        suffix: str,
        pdf_dir: Optional[Path],
        resume: bool,
    ) -> Dict:
        all_reports = []

        linkage_design = self._run_step(
            step_name=f"step1_linkage_design{suffix}",
            step_func=lambda: step1_linkage_design(
                self.client, pdf_text, schema, study_context
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )

        pico, pico_report = self._run_step_with_report(
            step_name=f"step2_pico{suffix}",
            step_func=lambda: step2_pico(
                self.client, pdf_text, schema, evaluator, study_context
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if pico_report:
            all_reports.append(pico_report)

        structure, struct_report = self._run_step_with_report(
            step_name=f"step3_trial_structure{suffix}",
            step_func=lambda: step3_trial_structure(
                self.client, pdf_text, schema, pico, evaluator, study_context
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if struct_report:
            all_reports.append(struct_report)

        effects, effects_report = self._run_step_with_report(
            step_name=f"step4_effects{suffix}",
            step_func=lambda: step4_effects(
                self.client, pdf_text, schema, pico, structure, evaluator, study_context
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if effects_report:
            all_reports.append(effects_report)

        mechanism, mech_report = self._run_step_with_report(
            step_name=f"step5_mechanism{suffix}",
            step_func=lambda: step5_mechanism(
                self.client,
                pdf_text,
                schema,
                structure,
                effects,
                evaluator,
                study_context,
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if mech_report:
            all_reports.append(mech_report)

        print(
            f"\n[Step 6] Merging{' [' + study_info.get('study_name', '') + ']' if study_info else ''} ...",
            file=sys.stderr,
        )
        final = step6_merge(
            linkage_design, pico, structure, effects, mechanism, study_info
        )

        confidence = _compute_confidence(all_reports)
        final["metadata"]["confidence"] = confidence

        if pdf_dir:
            save_json(pdf_dir / f"final{suffix}.json", final)
            save_json(
                pdf_dir / f"verification_reports{suffix}.json",
                {"reports": all_reports, "overall_confidence": confidence},
            )

        return final

    def _run_step(self, step_name, step_func, pdf_dir, resume):
        cache_path = pdf_dir / f"{step_name}.json" if pdf_dir else None
        if resume and cache_path and cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            print(f"\n[{step_name}] CACHED", file=sys.stderr)
            return cached
        print(f"\n[{step_name}] Running ...", file=sys.stderr)
        result = step_func()
        if cache_path:
            save_json(cache_path, result)
        return result

    def _run_step_with_report(self, step_name, step_func, pdf_dir, resume):
        cache_path = pdf_dir / f"{step_name}.json" if pdf_dir else None
        report_path = pdf_dir / f"{step_name}_report.json" if pdf_dir else None
        if resume and cache_path and cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            report = None
            if report_path and report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
            print(f"\n[{step_name}] CACHED", file=sys.stderr)
            return cached, report
        print(f"\n[{step_name}] Running ...", file=sys.stderr)
        data, report = step_func()
        if cache_path:
            save_json(cache_path, data)
        if report_path and report:
            save_json(report_path, report)
        return data, report
