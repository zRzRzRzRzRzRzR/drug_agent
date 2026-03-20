"""
pipeline.py — Drug-Database Evidence Extraction Pipeline.

Multi-step extraction with hard-match verification at each step:

  Step 1: trial_linkage + design
  Step 2: PICO (population, intervention, comparator, outcomes)
    → hard-match + consistency check → review if errors
  Step 3: trial_structure (regimens, arms, comparisons)
    → needs Step 2 context
    → hard-match + arm↔regimen alignment → review if errors
  Step 4: effect_estimates
    → needs Step 2 + Step 3 context
    → strict hard-match on all values → review if errors
  Step 5: mechanism_evidence
    → needs Step 3 + Step 4 context
    → light hard-match on biomarker values → review if errors
  Step 6: Merge + metadata → final.json

Key design:
  - Each step outputs a cached JSON (stepN_xxx.json) for resume
  - Hard-match is mechanical (no LLM) — fast and deterministic
  - Review agent only runs when hard-match finds errors
  - Schema structure enforced by giving LLM the empty JSON skeleton to fill
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
    """Load a prompt template from the prompts directory."""
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
    """Load the target schema JSON."""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_annotation() -> str:
    """Load the schema annotation markdown."""
    return _ANNOTATION_PATH.read_text(encoding="utf-8")


def _extract_empty_block(schema: Dict, *keys: str) -> Dict:
    """Extract a sub-block from the schema as an empty skeleton."""
    obj = schema
    for key in keys:
        obj = obj[key]
    return json.loads(json.dumps(obj))  # deep copy


# ---------------------------------------------------------------------------
# Step 1: trial_linkage + design
# ---------------------------------------------------------------------------


def step1_linkage_design(client: GLMClient, pdf_text: str, schema: Dict) -> Dict:
    """Extract trial_linkage and design from the paper."""
    prompt_template = _load_prompt("step1_linkage_design")

    # Build empty skeleton for LLM to fill
    skeleton = {
        "trial_linkage": _extract_empty_block(schema, "trial_linkage"),
        "design": _extract_empty_block(schema, "design"),
    }

    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    result = client.call_json(full_prompt)

    print(
        f"[Step 1] trial_linkage: NCT={result.get('trial_linkage', {}).get('nct_ids', [])}",
        file=sys.stderr,
    )
    design = result.get("design", {}).get("reported", {})
    print(
        f"[Step 1] design: randomized={design.get('randomized')}, "
        f"blinding={design.get('blinding')}, allocation={design.get('allocation')}",
        file=sys.stderr,
    )
    return result


# ---------------------------------------------------------------------------
# Step 2: PICO
# ---------------------------------------------------------------------------


def step2_pico(
    client: GLMClient, pdf_text: str, schema: Dict, evaluator: HardMatchEvaluator
) -> Tuple[Dict, Dict]:
    """
    Extract PICO with hard-match verification and review.

    Returns:
        (pico_data, verification_report)
    """
    prompt_template = _load_prompt("step2_pico")

    skeleton = _extract_empty_block(schema, "pico")

    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    pico = client.call_json(full_prompt)

    # --- Hard-match verification ---
    print("[Step 2] Running hard-match on PICO ...", file=sys.stderr)
    match_results = evaluator.check_pico(pico)
    consistency_results = evaluator.check_pico_consistency(pico)
    all_results = match_results + consistency_results

    report = evaluator.generate_structured_report(all_results)

    n_err = report["errors"]
    n_warn = report["warnings"]
    print(
        f"[Step 2] Hard-match: {n_err} errors, {n_warn} warnings",
        file=sys.stderr,
    )

    # --- Review if errors ---
    if n_err > 0:
        error_text = evaluator.generate_error_report(all_results)
        pico = review_with_hard_match(pico, "pico", error_text, pdf_text, client)

        # Re-check after review
        match_results_2 = evaluator.check_pico(pico)
        consistency_results_2 = evaluator.check_pico_consistency(pico)
        report_2 = evaluator.generate_structured_report(
            match_results_2 + consistency_results_2
        )
        print(
            f"[Step 2] After review: {report_2['errors']} errors, {report_2['warnings']} warnings",
            file=sys.stderr,
        )
        report["after_review"] = report_2

    _print_pico_summary(pico)
    return pico, report


def _print_pico_summary(pico: Dict) -> None:
    pop = pico.get("population", {}).get("base_population", {})
    print(
        f"[Step 2] Population: n={pop.get('sample_size')}, "
        f"desc={str(pop.get('description', ''))[:80]}",
        file=sys.stderr,
    )
    interventions = pico.get("intervention", {})
    if isinstance(interventions, dict):
        print(
            f"[Step 2] Intervention: {interventions.get('label', '?')}",
            file=sys.stderr,
        )
    outcomes = pico.get("outcomes", [])
    print(f"[Step 2] Outcomes: {len(outcomes)} defined", file=sys.stderr)


# ---------------------------------------------------------------------------
# Step 3: trial_structure
# ---------------------------------------------------------------------------


def step3_trial_structure(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    pico: Dict,
    evaluator: HardMatchEvaluator,
) -> Tuple[Dict, Dict]:
    """
    Extract trial_structure with Step 2 context.
    """
    prompt_template = _load_prompt("step3_trial_structure")

    skeleton = _extract_empty_block(schema, "trial_structure")

    full_prompt = prompt_template.replace(
        "{schema_skeleton}", json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{pico_context}", json.dumps(pico, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    structure = client.call_json(full_prompt)

    # --- Hard-match verification ---
    print("[Step 3] Running hard-match on trial_structure ...", file=sys.stderr)
    match_results = evaluator.check_trial_structure(structure, pico)

    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    n_warn = report["warnings"]
    print(
        f"[Step 3] Hard-match: {n_err} errors, {n_warn} warnings",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(match_results)
        structure = review_with_hard_match(
            structure, "trial_structure", error_text, pdf_text, client
        )
        match_results_2 = evaluator.check_trial_structure(structure, pico)
        report_2 = evaluator.generate_structured_report(match_results_2)
        print(
            f"[Step 3] After review: {report_2['errors']} errors, {report_2['warnings']} warnings",
            file=sys.stderr,
        )
        report["after_review"] = report_2

    _print_structure_summary(structure)
    return structure, report


def _print_structure_summary(structure: Dict) -> None:
    n_reg = len(structure.get("regimens", []))
    n_arm = len(structure.get("arms", []))
    n_comp = len(structure.get("comparisons", []))
    print(
        f"[Step 3] Structure: {n_reg} regimens, {n_arm} arms, {n_comp} comparisons",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Step 4: effect_estimates
# ---------------------------------------------------------------------------


def step4_effects(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    pico: Dict,
    structure: Dict,
    evaluator: HardMatchEvaluator,
) -> Tuple[List[Dict], Dict]:
    """
    Extract effect_estimates with Step 2 + Step 3 context.
    Strict hard-match on all numeric values.
    """
    prompt_template = _load_prompt("step4_effects")

    skeleton_item = schema["effect_estimates"][0]  # template for one estimate

    full_prompt = prompt_template.replace(
        "{estimate_skeleton}", json.dumps(skeleton_item, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{pico_context}", json.dumps(pico, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace(
        "{structure_context}", json.dumps(structure, indent=2, ensure_ascii=False)
    )
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    result = client.call_json(full_prompt)

    # Handle both list and dict with "effect_estimates" key
    if isinstance(result, list):
        effects = result
    elif isinstance(result, dict):
        effects = result.get("effect_estimates", [])
    else:
        effects = []

    # --- Collect valid upstream IDs ---
    valid_comp_ids = {c.get("comparison_id") for c in structure.get("comparisons", [])}
    valid_outcome_ids = {o.get("outcome_id") for o in pico.get("outcomes", [])}
    valid_pop_ids = {
        pico.get("population", {}).get("base_population", {}).get("population_id", "P0")
    }
    for ap in pico.get("population", {}).get("analysis_populations", []):
        valid_pop_ids.add(ap.get("population_id"))

    # --- Hard-match verification ---
    print("[Step 4] Running hard-match on effect_estimates ...", file=sys.stderr)
    match_results = evaluator.check_effect_estimates(
        effects, valid_comp_ids, valid_outcome_ids, valid_pop_ids
    )

    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    n_warn = report["warnings"]
    print(
        f"[Step 4] Hard-match: {n_err} errors, {n_warn} warnings "
        f"across {len(effects)} estimates",
        file=sys.stderr,
    )

    if n_err > 0:
        error_text = evaluator.generate_error_report(match_results)
        effects = review_effects_with_context(
            effects, error_text, pdf_text, client, pico, structure
        )
        # Re-verify
        match_results_2 = evaluator.check_effect_estimates(
            effects, valid_comp_ids, valid_outcome_ids, valid_pop_ids
        )
        report_2 = evaluator.generate_structured_report(match_results_2)
        print(
            f"[Step 4] After review: {report_2['errors']} errors, "
            f"{report_2['warnings']} warnings",
            file=sys.stderr,
        )
        report["after_review"] = report_2

    print(f"[Step 4] Final: {len(effects)} effect estimates", file=sys.stderr)
    return effects, report


# ---------------------------------------------------------------------------
# Step 5: mechanism_evidence
# ---------------------------------------------------------------------------


def step5_mechanism(
    client: GLMClient,
    pdf_text: str,
    schema: Dict,
    structure: Dict,
    effects: List[Dict],
    evaluator: HardMatchEvaluator,
) -> Tuple[Dict, Dict]:
    """
    Extract mechanism_evidence with Step 3 + Step 4 context.
    """
    prompt_template = _load_prompt("step5_mechanism")

    skeleton = _extract_empty_block(schema, "mechanism_evidence")

    # Build context: valid comparison IDs and estimate IDs
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
    full_prompt = full_prompt.replace("{paper_text}", pdf_text)

    mechanism = client.call_json(full_prompt)

    # --- Light hard-match on biomarker values ---
    print("[Step 5] Running hard-match on mechanism_evidence ...", file=sys.stderr)
    match_results = evaluator.check_mechanism_evidence(
        mechanism, valid_comp_ids, valid_estimate_ids
    )

    report = evaluator.generate_structured_report(match_results)
    n_err = report["errors"]
    n_warn = report["warnings"]
    print(
        f"[Step 5] Hard-match: {n_err} errors, {n_warn} warnings",
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
# Step 6: Merge + metadata
# ---------------------------------------------------------------------------


def step6_merge(
    linkage_design: Dict,
    pico: Dict,
    structure: Dict,
    effects: List[Dict],
    mechanism: Dict,
) -> Dict:
    """Merge all steps into the final schema-compliant JSON."""
    final = {
        "trial_linkage": linkage_design.get("trial_linkage", {}),
        "design": linkage_design.get("design", {}),
        "pico": pico,
        "trial_structure": structure,
        "effect_estimates": effects,
        "mechanism_evidence": mechanism,
        "metadata": {
            "extraction_mode": "automated",
            "confidence": None,  # Will be set based on verification
            "schema_version": "v1_patch_1",
            "annotator_id": "drug_agent_v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    return final


def _compute_confidence(reports: List[Dict]) -> str:
    """Determine overall confidence based on verification reports."""
    total_errors = sum(r.get("errors", 0) for r in reports)
    total_errors_after = sum(
        r.get("after_review", {}).get("errors", 0)
        for r in reports
        if "after_review" in r
    )

    if total_errors == 0:
        return "high"
    elif total_errors_after == 0:
        return "moderate"  # Had errors but all fixed by review
    else:
        return "low"  # Still has errors after review


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class DrugExtractionPipeline:
    """
    Six-step pipeline for drug-database evidence extraction:
      Step 1: trial_linkage + design
      Step 2: PICO (with hard-match + review)
      Step 3: trial_structure (with hard-match + review)
      Step 4: effect_estimates (with strict hard-match + review)
      Step 5: mechanism_evidence (with light hard-match)
      Step 6: Merge + metadata
    """

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
        print(
            f"[Pipeline] Schema version: {self.schema.get('metadata', {}).get('schema_version', '?')}",
            file=sys.stderr,
        )

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
    ) -> Dict:
        """
        Run the full extraction pipeline on a single PDF.

        Returns:
            Complete schema-compliant JSON dict
        """
        pdf_name = Path(pdf_path).stem
        base_dir = Path(output_dir) if output_dir else None

        pdf_dir = None
        if base_dir:
            pdf_dir = base_dir / pdf_name
            pdf_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"[Pipeline] Processing: {pdf_name}", file=sys.stderr)
        if pdf_dir:
            print(f"[Pipeline] Output: {pdf_dir}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        t_start = time.time()
        pdf_text = self._get_pdf_text(pdf_path)
        evaluator = HardMatchEvaluator(pdf_text)

        all_reports = []

        # -- Step 1: trial_linkage + design --
        linkage_design = self._run_step(
            step_name="step1_linkage_design",
            step_func=lambda: step1_linkage_design(self.client, pdf_text, self.schema),
            pdf_dir=pdf_dir,
            resume=resume,
        )

        # -- Step 2: PICO --
        pico, pico_report = self._run_step_with_report(
            step_name="step2_pico",
            step_func=lambda: step2_pico(self.client, pdf_text, self.schema, evaluator),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if pico_report:
            all_reports.append(pico_report)

        # -- Step 3: trial_structure --
        structure, struct_report = self._run_step_with_report(
            step_name="step3_trial_structure",
            step_func=lambda: step3_trial_structure(
                self.client, pdf_text, self.schema, pico, evaluator
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if struct_report:
            all_reports.append(struct_report)

        # -- Step 4: effect_estimates --
        effects, effects_report = self._run_step_with_report(
            step_name="step4_effects",
            step_func=lambda: step4_effects(
                self.client, pdf_text, self.schema, pico, structure, evaluator
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if effects_report:
            all_reports.append(effects_report)

        # -- Step 5: mechanism_evidence --
        mechanism, mech_report = self._run_step_with_report(
            step_name="step5_mechanism",
            step_func=lambda: step5_mechanism(
                self.client, pdf_text, self.schema, structure, effects, evaluator
            ),
            pdf_dir=pdf_dir,
            resume=resume,
        )
        if mech_report:
            all_reports.append(mech_report)

        # -- Step 6: Merge --
        print("\n[Step 6] Merging all steps ...", file=sys.stderr)
        final = step6_merge(linkage_design, pico, structure, effects, mechanism)

        # Set confidence based on verification
        confidence = _compute_confidence(all_reports)
        final["metadata"]["confidence"] = confidence

        if pdf_dir:
            save_json(pdf_dir / "final.json", final)
            save_json(
                pdf_dir / "verification_reports.json",
                {"reports": all_reports, "overall_confidence": confidence},
            )

        elapsed = round(time.time() - t_start, 1)
        print(f"\n{'='*60}", file=sys.stderr)
        print(
            f"[Pipeline] Complete: {pdf_name} ({elapsed}s)",
            file=sys.stderr,
        )
        print(
            f"  Confidence: {confidence}",
            file=sys.stderr,
        )
        print(
            f"  Effects: {len(effects)} estimates",
            file=sys.stderr,
        )
        print(
            f"  Mechanism: {len(final['mechanism_evidence'].get('claims', []))} claims",
            file=sys.stderr,
        )
        print(f"{'='*60}\n", file=sys.stderr)

        return final

    def _run_step(
        self,
        step_name: str,
        step_func: Callable,
        pdf_dir: Optional[Path],
        resume: bool,
    ) -> Any:
        """Run a step with caching support. Returns the step result."""
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

    def _run_step_with_report(
        self,
        step_name: str,
        step_func: Callable,
        pdf_dir: Optional[Path],
        resume: bool,
    ) -> Tuple[Any, Optional[Dict]]:
        """Run a step that returns (data, report). Cache both."""
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
