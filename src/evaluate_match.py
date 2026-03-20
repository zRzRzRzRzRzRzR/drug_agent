"""
evaluate_match.py — Hard-match evaluation for extracted JSON against paper text.

All numeric values in the extraction output MUST be traceable to the paper.
This module provides:
  1. Anchor number extraction from paper text
  2. Per-field hard-match checking
  3. Step-specific validators (PICO, structure, effects)
  4. Error report generation for the review agent

Design principle:
  - Mechanical string matching FIRST (no LLM needed)
  - Generate a structured error report
  - Feed errors to review agent for correction or deletion
"""

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class MatchSeverity(str, Enum):
    ERROR = "error"        # Value not found in paper — must fix or delete
    WARNING = "warning"    # Value found but ambiguous / multiple candidates
    INFO = "info"          # Structural check note


@dataclass
class MatchResult:
    field_path: str
    value: Any
    found: bool
    severity: MatchSeverity
    message: str
    candidates: List[str] = field(default_factory=list)  # nearby matches if any


# ---------------------------------------------------------------------------
# Anchor number extraction (adapted from causal_agent pipeline.py)
# ---------------------------------------------------------------------------


def extract_anchor_numbers(pdf_text: str) -> Set[str]:
    """
    Extract ALL numbers that appear in the paper text.
    Returns a set of string representations for fast lookup.
    """
    text_clean = pdf_text.replace("\n", " ").replace("\t", " ")

    raw_numbers = re.findall(r"(?<![a-zA-Z])(\d+\.?\d*)", text_clean)

    anchor_set: Set[str] = set()
    for n in raw_numbers:
        anchor_set.add(n)
        try:
            val = float(n)
            anchor_set.add(f"{val:.1f}")
            anchor_set.add(f"{val:.2f}")
            anchor_set.add(f"{val:.3f}")
            if val == int(val) and abs(val) < 100000:
                anchor_set.add(str(int(val)))
            if 0 < abs(val) < 1:
                anchor_set.add(f"{val:.2f}".lstrip("0"))
                anchor_set.add(f"{val:.3f}".lstrip("0"))
        except ValueError:
            pass

    return anchor_set


def hard_match_value(
    val: Any, anchor_set: Set[str], pdf_text: str
) -> bool:
    """
    Check if a numeric value can be traced to the paper text.
    """
    if val is None:
        return True

    try:
        num = float(val)
    except (ValueError, TypeError):
        return True  # Non-numeric, skip

    candidates = [
        f"{num:.1f}",
        f"{num:.2f}",
        f"{num:.3f}",
        f"{num:g}",
    ]
    if num == int(num) and abs(num) < 100000:
        candidates.append(str(int(num)))
    if 0 < abs(num) < 1:
        candidates.append(f"{num:.2f}".lstrip("0"))
        candidates.append(f"{num:.3f}".lstrip("0"))

    for c in candidates:
        if c in anchor_set:
            return True

    # Fallback: search in collapsed text
    text_collapsed = pdf_text.replace(" ", "").replace("\n", "")
    for c in candidates:
        if c in text_collapsed:
            return True

    return False


# ---------------------------------------------------------------------------
# HardMatchEvaluator
# ---------------------------------------------------------------------------


class HardMatchEvaluator:
    """
    Evaluates extracted JSON blocks against the paper text.
    All numeric values must be traceable.
    """

    def __init__(self, pdf_text: str):
        self.pdf_text = pdf_text
        self.anchor_set = extract_anchor_numbers(pdf_text)

    def check_value(self, value: Any, field_path: str) -> Optional[MatchResult]:
        """Check a single numeric value. Returns None if value is None/non-numeric."""
        if value is None:
            return None

        try:
            float(value)
        except (ValueError, TypeError):
            return None  # Non-numeric, no check needed

        found = hard_match_value(value, self.anchor_set, self.pdf_text)
        if found:
            return MatchResult(
                field_path=field_path,
                value=value,
                found=True,
                severity=MatchSeverity.INFO,
                message=f"OK: {value} found in paper",
            )
        else:
            return MatchResult(
                field_path=field_path,
                value=value,
                found=False,
                severity=MatchSeverity.ERROR,
                message=f"NOT FOUND: {value} at {field_path} — not traceable to paper text",
            )

    def _check_numeric_fields(
        self, obj: Any, path_prefix: str, target_fields: Optional[Set[str]] = None
    ) -> List[MatchResult]:
        """Recursively check all numeric fields in an object."""
        results = []

        if isinstance(obj, dict):
            for key, val in obj.items():
                full_path = f"{path_prefix}.{key}" if path_prefix else key
                if target_fields and key not in target_fields:
                    # Still recurse into nested objects
                    if isinstance(val, (dict, list)):
                        results.extend(
                            self._check_numeric_fields(val, full_path, target_fields)
                        )
                    continue

                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    result = self.check_value(val, full_path)
                    if result and not result.found:
                        results.append(result)
                elif isinstance(val, (dict, list)):
                    results.extend(
                        self._check_numeric_fields(val, full_path, target_fields)
                    )

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                full_path = f"{path_prefix}[{i}]"
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    result = self.check_value(item, full_path)
                    if result and not result.found:
                        results.append(result)
                elif isinstance(item, (dict, list)):
                    results.extend(
                        self._check_numeric_fields(item, full_path, target_fields)
                    )

        return results

    # -------------------------------------------------------------------
    # Step-specific validators
    # -------------------------------------------------------------------

    def check_pico(self, pico: Dict) -> List[MatchResult]:
        """
        Check PICO block: sample_size, age stats, sex percents, timepoint values.
        """
        results = []

        # Numeric fields to check in population
        population = pico.get("population", {})
        results.extend(
            self._check_numeric_fields(population, "pico.population")
        )

        # Outcomes timepoints
        outcomes = pico.get("outcomes", [])
        for i, outcome in enumerate(outcomes):
            tp = outcome.get("timepoint", {})
            if tp and isinstance(tp, dict):
                val = tp.get("value")
                r = self.check_value(val, f"pico.outcomes[{i}].timepoint.value")
                if r and not r.found:
                    results.append(r)

        return results

    def check_pico_consistency(self, pico: Dict) -> List[MatchResult]:
        """
        Structural consistency checks for PICO:
        - Sub-population sample_size <= base_population sample_size
        """
        results = []
        population = pico.get("population", {})
        base_pop = population.get("base_population", {})
        base_n = base_pop.get("sample_size")

        if base_n is not None:
            for ap in population.get("analysis_populations", []):
                ap_n = ap.get("sample_size")
                if ap_n is not None and ap_n > base_n:
                    results.append(MatchResult(
                        field_path=f"pico.population.analysis_populations.{ap.get('population_id', '?')}.sample_size",
                        value=ap_n,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=(
                            f"Analysis population {ap.get('population_id')} sample_size={ap_n} "
                            f"> base_population sample_size={base_n}"
                        ),
                    ))

        return results

    def check_trial_structure(
        self, structure: Dict, pico: Optional[Dict] = None
    ) -> List[MatchResult]:
        """
        Check trial_structure block:
        - Regimen dose/duration values
        - Arm sample sizes
        - Arm.regimen_id references valid regimen
        - Comparison treatment/control ref_ids reference valid arms/groups
        """
        results = []

        # Numeric checks on regimens
        regimens = structure.get("regimens", [])
        regimen_ids = set()
        for i, reg in enumerate(regimens):
            regimen_ids.add(reg.get("regimen_id"))
            results.extend(
                self._check_numeric_fields(reg, f"trial_structure.regimens[{i}]")
            )

        # Arms
        arms = structure.get("arms", [])
        arm_ids = set()
        for i, arm in enumerate(arms):
            arm_ids.add(arm.get("arm_id"))
            # Sample size check
            n = arm.get("sample_size")
            r = self.check_value(n, f"trial_structure.arms[{i}].sample_size")
            if r and not r.found:
                results.append(r)

            # Regimen reference check
            rid = arm.get("regimen_id")
            if rid and rid not in regimen_ids:
                results.append(MatchResult(
                    field_path=f"trial_structure.arms[{i}].regimen_id",
                    value=rid,
                    found=False,
                    severity=MatchSeverity.ERROR,
                    message=f"Arm {arm.get('arm_id')} references regimen_id={rid} which does not exist",
                ))

        # Analysis groups
        group_ids = set()
        for g in structure.get("analysis_groups", []):
            group_ids.add(g.get("group_id"))

        # Comparisons: reference checks
        valid_refs = arm_ids | group_ids
        for i, comp in enumerate(structure.get("comparisons", [])):
            for role in ("treatment", "control"):
                ref = comp.get(role, {})
                ref_id = ref.get("ref_id")
                if ref_id and ref_id not in valid_refs:
                    results.append(MatchResult(
                        field_path=f"trial_structure.comparisons[{i}].{role}.ref_id",
                        value=ref_id,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=(
                            f"Comparison {comp.get('comparison_id')} {role} "
                            f"references {ref_id} which is not a valid arm or group"
                        ),
                    ))

        return results

    def check_effect_estimates(
        self,
        effects: List[Dict],
        valid_comparison_ids: Set[str],
        valid_outcome_ids: Set[str],
        valid_population_ids: Set[str],
    ) -> List[MatchResult]:
        """
        Check effect_estimates:
        - value, CI bounds, p_value must all be in paper
        - comparison_id, outcome_id, population_id must reference upstream IDs
        """
        results = []

        for i, est in enumerate(effects):
            prefix = f"effect_estimates[{i}]"
            eid = est.get("estimate_id", f"E{i+1}")

            # Numeric hard match: value
            r = self.check_value(est.get("value"), f"{prefix}.value")
            if r and not r.found:
                results.append(r)

            # CI bounds
            ci = est.get("ci", {})
            if isinstance(ci, dict):
                for bound in ("lower", "upper"):
                    r = self.check_value(ci.get(bound), f"{prefix}.ci.{bound}")
                    if r and not r.found:
                        results.append(r)

            # p_value
            p = est.get("p_value")
            if p is not None:
                r = self.check_value(p, f"{prefix}.p_value")
                if r and not r.found:
                    results.append(r)

            # Reference ID checks
            cid = est.get("comparison_id")
            if cid and cid not in valid_comparison_ids:
                results.append(MatchResult(
                    field_path=f"{prefix}.comparison_id",
                    value=cid,
                    found=False,
                    severity=MatchSeverity.ERROR,
                    message=f"Estimate {eid} references comparison_id={cid} not defined in trial_structure",
                ))

            oid = est.get("outcome_id")
            if oid and oid not in valid_outcome_ids:
                results.append(MatchResult(
                    field_path=f"{prefix}.outcome_id",
                    value=oid,
                    found=False,
                    severity=MatchSeverity.ERROR,
                    message=f"Estimate {eid} references outcome_id={oid} not defined in pico.outcomes",
                ))

            pid = est.get("population_id")
            if pid and pid not in valid_population_ids:
                results.append(MatchResult(
                    field_path=f"{prefix}.population_id",
                    value=pid,
                    found=False,
                    severity=MatchSeverity.ERROR,
                    message=f"Estimate {eid} references population_id={pid} not defined in pico.population",
                ))

        return results

    def check_mechanism_evidence(
        self,
        mechanism: Dict,
        valid_comparison_ids: Set[str],
        valid_estimate_ids: Set[str],
    ) -> List[MatchResult]:
        """
        Check mechanism_evidence:
        - biomarker_effects numeric values
        - comparison_id / linked_estimate_id references
        """
        results = []

        for i, bm in enumerate(mechanism.get("biomarker_effects", [])):
            prefix = f"mechanism_evidence.biomarker_effects[{i}]"

            # Numeric checks
            r = self.check_value(bm.get("value"), f"{prefix}.value")
            if r and not r.found:
                results.append(r)

            bm_ci = bm.get("ci")
            if isinstance(bm_ci, dict):
                for bound in ("lower", "upper"):
                    r = self.check_value(bm_ci.get(bound), f"{prefix}.ci.{bound}")
                    if r and not r.found:
                        results.append(r)

            p = bm.get("p_value")
            if p is not None:
                r = self.check_value(p, f"{prefix}.p_value")
                if r and not r.found:
                    results.append(r)

            # Reference checks
            cid = bm.get("comparison_id")
            if cid and cid not in valid_comparison_ids:
                results.append(MatchResult(
                    field_path=f"{prefix}.comparison_id",
                    value=cid,
                    found=False,
                    severity=MatchSeverity.ERROR,
                    message=f"Biomarker effect references comparison_id={cid} not in trial_structure",
                ))

            lid = bm.get("linked_estimate_id")
            if lid and lid not in valid_estimate_ids:
                results.append(MatchResult(
                    field_path=f"{prefix}.linked_estimate_id",
                    value=lid,
                    found=False,
                    severity=MatchSeverity.WARNING,
                    message=f"Biomarker effect references linked_estimate_id={lid} not in effect_estimates",
                ))

        return results

    # -------------------------------------------------------------------
    # Error report generation
    # -------------------------------------------------------------------

    def generate_error_report(self, results: List[MatchResult]) -> str:
        """
        Generate a human/LLM-readable error report for the review agent.
        """
        errors = [r for r in results if r.severity == MatchSeverity.ERROR]
        warnings = [r for r in results if r.severity == MatchSeverity.WARNING]

        if not errors and not warnings:
            return "All values passed hard-match verification."

        lines = []
        lines.append(f"Hard-match verification: {len(errors)} errors, {len(warnings)} warnings\n")

        if errors:
            lines.append("## ERRORS (must fix or delete)\n")
            for r in errors:
                lines.append(f"- [{r.field_path}] value={r.value}")
                lines.append(f"  {r.message}\n")

        if warnings:
            lines.append("## WARNINGS (review recommended)\n")
            for r in warnings:
                lines.append(f"- [{r.field_path}] value={r.value}")
                lines.append(f"  {r.message}\n")

        return "\n".join(lines)

    def generate_structured_report(self, results: List[MatchResult]) -> Dict:
        """Generate a machine-readable report."""
        return {
            "total_checks": len(results),
            "errors": len([r for r in results if r.severity == MatchSeverity.ERROR]),
            "warnings": len([r for r in results if r.severity == MatchSeverity.WARNING]),
            "details": [
                {
                    "field_path": r.field_path,
                    "value": r.value,
                    "found": r.found,
                    "severity": r.severity.value,
                    "message": r.message,
                }
                for r in results
                if r.severity in (MatchSeverity.ERROR, MatchSeverity.WARNING)
            ],
        }
