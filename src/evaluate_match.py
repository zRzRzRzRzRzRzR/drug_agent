import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class MatchSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class MatchResult:
    field_path: str
    value: Any
    found: bool
    severity: MatchSeverity
    message: str
    candidates: List[str] = field(default_factory=list)


def extract_anchor_numbers(pdf_text: str) -> Set[str]:
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


def hard_match_value(val: Any, anchor_set: Set[str], pdf_text: str) -> bool:
    if val is None:
        return True

    try:
        num = float(val)
    except (ValueError, TypeError):
        return True

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

    text_collapsed = pdf_text.replace(" ", "").replace("\n", "")
    for c in candidates:
        if c in text_collapsed:
            return True

    return False


# Valid enums
_VALID_ACTION_TYPES = {"inhibitor", "agonist", "antagonist", "modulator", "unclear"}
_VALID_DIRECTIONS = {
    "treatment_better",
    "control_better",
    "no_significant_difference",
    "inconclusive",
    "unclear",
}
_VALID_ESTIMATE_TYPES = {
    "mean_difference",
    "risk_ratio",
    "odds_ratio",
    "hazard_ratio",
    "risk_difference",
    "rate_ratio",
    "unclear",
}
_VALID_POLARITIES = {"higher_better", "lower_better", "neutral", "unclear"}


class HardMatchEvaluator:
    def __init__(self, pdf_text: str):
        self.pdf_text = pdf_text
        self.anchor_set = extract_anchor_numbers(pdf_text)

    # -------------------------------------------------------------------
    # Null-field completeness checks
    # -------------------------------------------------------------------

    def _find_number_near_keyword(
        self, keywords: List[str], max_distance: int = 120
    ) -> Optional[str]:
        """
        Search pdf_text for a number appearing near any of the given keywords.
        Returns the first plausible candidate string, or None.
        """
        text = self.pdf_text.replace("\n", " ")
        for kw in keywords:
            for m in re.finditer(re.escape(kw), text, re.IGNORECASE):
                window_start = max(0, m.start() - max_distance)
                window_end = min(len(text), m.end() + max_distance)
                window = text[window_start:window_end]
                nums = re.findall(r"(?<![a-zA-Z])(\d+\.?\d*)", window)
                if nums:
                    return nums[0]
        return None

    def check_null_completeness(self, pico: Dict) -> List[MatchResult]:
        """
        Check for fields left as null that may actually be available in the paper.
        This produces WARNINGs (not ERRORs) — hints for the review step.
        """
        results = []
        population = pico.get("population", {})
        base_pop = population.get("base_population", {})

        # --- Age range ---
        age = base_pop.get("age", {})
        if isinstance(age, dict):
            if age.get("range_min") is None:
                candidate = self._find_number_near_keyword(
                    ["age ≥", "age >=", "aged ≥", "aged >=", "≥ ", "years or older",
                     "minimum age", "age range", "18 years", "age ⩾", "older than"]
                )
                if candidate:
                    results.append(
                        MatchResult(
                            field_path="pico.population.base_population.age.range_min",
                            value=None,
                            found=True,
                            severity=MatchSeverity.WARNING,
                            message=f"age.range_min is null but paper may contain age "
                            f"lower bound (found '{candidate}' near age keywords). "
                            f"Check if an age eligibility criterion exists.",
                            candidates=[candidate],
                        )
                    )

            if age.get("range_max") is None:
                candidate = self._find_number_near_keyword(
                    ["age ≤", "age <=", "aged ≤", "aged <=", "≤ ", "years or younger",
                     "maximum age", "younger than", "up to"]
                )
                if candidate:
                    results.append(
                        MatchResult(
                            field_path="pico.population.base_population.age.range_max",
                            value=None,
                            found=True,
                            severity=MatchSeverity.WARNING,
                            message=f"age.range_max is null but paper may contain age "
                            f"upper bound (found '{candidate}' near age keywords). "
                            f"Check if an age eligibility criterion exists.",
                            candidates=[candidate],
                        )
                    )

        # --- Sex percentage ---
        sex = base_pop.get("sex", {})
        if isinstance(sex, dict):
            if sex.get("female_percent") is None and sex.get("male_percent") is not None:
                male_pct = sex["male_percent"]
                try:
                    inferred = round(100.0 - float(male_pct), 1)
                    results.append(
                        MatchResult(
                            field_path="pico.population.base_population.sex.female_percent",
                            value=None,
                            found=True,
                            severity=MatchSeverity.WARNING,
                            message=f"female_percent is null but male_percent={male_pct}. "
                            f"Consider setting female_percent={inferred} (100 - male_percent).",
                            candidates=[str(inferred)],
                        )
                    )
                except (ValueError, TypeError):
                    pass

            if sex.get("male_percent") is None and sex.get("female_percent") is not None:
                female_pct = sex["female_percent"]
                try:
                    inferred = round(100.0 - float(female_pct), 1)
                    results.append(
                        MatchResult(
                            field_path="pico.population.base_population.sex.male_percent",
                            value=None,
                            found=True,
                            severity=MatchSeverity.WARNING,
                            message=f"male_percent is null but female_percent={female_pct}. "
                            f"Consider setting male_percent={inferred} (100 - female_percent).",
                            candidates=[str(inferred)],
                        )
                    )
                except (ValueError, TypeError):
                    pass

        # --- Sample size ---
        if base_pop.get("sample_size") is None:
            candidate = self._find_number_near_keyword(
                ["enrolled", "included", "participants", "patients", "subjects",
                 "sample size", "n =", "N =", "ITT", "intention-to-treat"]
            )
            if candidate:
                results.append(
                    MatchResult(
                        field_path="pico.population.base_population.sample_size",
                        value=None,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"sample_size is null but paper may contain sample "
                        f"size (found '{candidate}' near enrollment keywords).",
                        candidates=[candidate],
                    )
                )

        # --- Region ---
        region = base_pop.get("region", {})
        if isinstance(region, dict) and not region.get("country_list"):
            # Quick scan for common country patterns
            country_keywords = [
                "United States", "USA", "UK", "United Kingdom", "China", "Japan",
                "Germany", "France", "Italy", "Spain", "Canada", "Australia",
                "Brazil", "India", "Korea", "Netherlands", "Sweden", "Denmark",
                "Norway", "Finland", "Belgium", "Switzerland", "Austria", "Poland",
                "Israel", "Turkey", "Mexico", "Argentina", "South Africa",
                "Russia", "Taiwan", "Hong Kong", "Singapore",
            ]
            found_countries = []
            text_lower = self.pdf_text.lower()
            for country in country_keywords:
                if country.lower() in text_lower:
                    found_countries.append(country)
            if found_countries:
                results.append(
                    MatchResult(
                        field_path="pico.population.base_population.region.country_list",
                        value=[],
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"country_list is empty but paper mentions: "
                        f"{', '.join(found_countries[:5])}. "
                        f"Check if study region is reported.",
                        candidates=found_countries[:5],
                    )
                )

        return results

    def check_value(self, value: Any, field_path: str) -> Optional[MatchResult]:
        if value is None:
            return None
        try:
            float(value)
        except (ValueError, TypeError):
            return None

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
        results = []
        if isinstance(obj, dict):
            for key, val in obj.items():
                full_path = f"{path_prefix}.{key}" if path_prefix else key
                if target_fields and key not in target_fields:
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
    # PICO checks
    # -------------------------------------------------------------------

    def check_pico(self, pico: Dict) -> List[MatchResult]:
        results = []
        population = pico.get("population", {})
        results.extend(self._check_numeric_fields(population, "pico.population"))

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
        results = []
        population = pico.get("population", {})
        base_pop = population.get("base_population", {})
        base_n = base_pop.get("sample_size")

        if base_n is not None:
            for ap in population.get("analysis_populations", []):
                ap_n = ap.get("sample_size")
                if ap_n is not None and ap_n > base_n:
                    results.append(
                        MatchResult(
                            field_path=f"pico.population.analysis_populations.{ap.get('population_id', '?')}.sample_size",
                            value=ap_n,
                            found=True,
                            severity=MatchSeverity.ERROR,
                            message=f"Analysis population sample_size ({ap_n}) > base_population ({base_n})",
                        )
                    )

        # v2: Safety outcome polarity should be neutral
        for i, outcome in enumerate(pico.get("outcomes", [])):
            role = outcome.get("role", "")
            polarity = outcome.get("polarity", "")
            if role == "safety" and polarity not in ("neutral", "unclear", None):
                results.append(
                    MatchResult(
                        field_path=f"pico.outcomes[{i}].polarity",
                        value=polarity,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Safety outcome O{i+1} has polarity='{polarity}', expected 'neutral' for safety outcomes",
                    )
                )

        return results

    # -------------------------------------------------------------------
    # Design consistency checks (v2)
    # -------------------------------------------------------------------

    def check_design_consistency(
        self, linkage_design: Dict, pico: Dict
    ) -> List[MatchResult]:
        """Check consistency between design and PICO."""
        results = []
        design = linkage_design.get("design", {}).get("reported", {})
        allocation = design.get("allocation", "unclear")

        comparators = pico.get("comparators", [])
        if allocation == "single-arm" and len(comparators) > 0:
            # Check if any comparator has meaningful content
            for i, comp in enumerate(comparators):
                ctype = comp.get("type", "")
                label = comp.get("label", "")
                if ctype and ctype not in ("unclear",) and label:
                    results.append(
                        MatchResult(
                            field_path=f"pico.comparators[{i}]",
                            value=comp.get("comparator_id"),
                            found=True,
                            severity=MatchSeverity.ERROR,
                            message=f"allocation='single-arm' but comparator {comp.get('comparator_id')} exists with type='{ctype}'. Single-arm studies should have comparators=[]",
                        )
                    )

        return results

    # -------------------------------------------------------------------
    # Trial structure checks
    # -------------------------------------------------------------------

    def check_trial_structure(self, structure: Dict, pico: Dict) -> List[MatchResult]:
        results = []

        # Numeric hard-match on arms sample_size, dose values, duration values
        results.extend(self._check_numeric_fields(structure, "trial_structure"))

        # Reference integrity checks
        regimen_ids = set()
        for reg in structure.get("regimens", []):
            regimen_ids.add(reg.get("regimen_id"))

        arm_ids = set()
        for i, arm in enumerate(structure.get("arms", [])):
            arm_ids.add(arm.get("arm_id"))
            rid = arm.get("regimen_id")
            if rid and rid not in regimen_ids:
                results.append(
                    MatchResult(
                        field_path=f"trial_structure.arms[{i}].regimen_id",
                        value=rid,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=f"Arm {arm.get('arm_id')} references regimen_id={rid} which does not exist",
                    )
                )

        group_ids = set()
        for g in structure.get("analysis_groups", []):
            group_ids.add(g.get("group_id"))

        valid_refs = arm_ids | group_ids
        for i, comp in enumerate(structure.get("comparisons", [])):
            for role in ("treatment", "control"):
                ref = comp.get(role, {})
                ref_id = ref.get("ref_id")
                if ref_id and ref_id not in valid_refs:
                    results.append(
                        MatchResult(
                            field_path=f"trial_structure.comparisons[{i}].{role}.ref_id",
                            value=ref_id,
                            found=False,
                            severity=MatchSeverity.ERROR,
                            message=(
                                f"Comparison {comp.get('comparison_id')} {role} "
                                f"references {ref_id} which is not a valid arm or group"
                            ),
                        )
                    )

        return results

    # -------------------------------------------------------------------
    # Effect estimates checks
    # -------------------------------------------------------------------

    def check_effect_estimates(
        self,
        effects: List[Dict],
        valid_comparison_ids: Set[str],
        valid_outcome_ids: Set[str],
        valid_population_ids: Set[str],
    ) -> List[MatchResult]:
        results = []

        for i, est in enumerate(effects):
            prefix = f"effect_estimates[{i}]"
            eid = est.get("estimate_id", f"E{i+1}")

            # Numeric hard match
            r = self.check_value(est.get("value"), f"{prefix}.value")
            if r and not r.found:
                results.append(r)

            ci = est.get("ci", {})
            if isinstance(ci, dict):
                for bound in ("lower", "upper"):
                    r = self.check_value(ci.get(bound), f"{prefix}.ci.{bound}")
                    if r and not r.found:
                        results.append(r)

            p = est.get("p_value")
            if p is not None:
                r = self.check_value(p, f"{prefix}.p_value")
                if r and not r.found:
                    results.append(r)

            # Reference ID checks
            cid = est.get("comparison_id")
            if cid and cid not in valid_comparison_ids:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.comparison_id",
                        value=cid,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=f"Estimate {eid} references comparison_id={cid} not defined in trial_structure",
                    )
                )

            oid = est.get("outcome_id")
            if oid and oid not in valid_outcome_ids:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.outcome_id",
                        value=oid,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=f"Estimate {eid} references outcome_id={oid} not defined in pico.outcomes",
                    )
                )

            pid = est.get("population_id")
            if pid and pid not in valid_population_ids:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.population_id",
                        value=pid,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=f"Estimate {eid} references population_id={pid} not defined in pico.population",
                    )
                )

            # v2: Enum validation
            est_type = est.get("estimate_type")
            if est_type and est_type not in _VALID_ESTIMATE_TYPES:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.estimate_type",
                        value=est_type,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Estimate {eid} has invalid estimate_type='{est_type}'. Valid: {_VALID_ESTIMATE_TYPES}",
                    )
                )

            direction = est.get("direction")
            if direction and direction not in _VALID_DIRECTIONS:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.direction",
                        value=direction,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Estimate {eid} has invalid direction='{direction}'. Valid: {_VALID_DIRECTIONS}",
                    )
                )

        return results

    def check_effects_null_completeness(
        self, effects: List[Dict]
    ) -> List[MatchResult]:
        """
        Check for effect_estimates with p_value but missing value/CI.
        This is a common extraction failure: LLM finds p-values but skips
        the actual between-group difference values from tables.
        """
        results = []
        for i, est in enumerate(effects):
            prefix = f"effect_estimates[{i}]"
            eid = est.get("estimate_id", f"E{i+1}")

            has_p = est.get("p_value") is not None
            has_value = est.get("value") is not None
            ci = est.get("ci", {}) or {}
            has_ci = ci.get("lower") is not None or ci.get("upper") is not None

            # If we have p_value but no value, something is likely missing
            if has_p and not has_value:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.value",
                        value=None,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Estimate {eid} has p_value={est.get('p_value')} "
                        f"but value is null. Check the paper's tables for "
                        f"the between-group difference / effect size. "
                        f"Look for 'Difference' or 'vs placebo' rows in tables.",
                    )
                )

            if has_p and not has_ci:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.ci",
                        value=None,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Estimate {eid} has p_value={est.get('p_value')} "
                        f"but CI is missing. Check the paper's tables for "
                        f"confidence interval values (often in parentheses).",
                    )
                )

            # If we have value but no CI, also flag
            if has_value and not has_ci:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.ci",
                        value=None,
                        found=True,
                        severity=MatchSeverity.WARNING,
                        message=f"Estimate {eid} has value={est.get('value')} "
                        f"but CI is missing. Check if paper reports confidence intervals.",
                    )
                )

        return results

    # -------------------------------------------------------------------
    # Mechanism evidence checks
    # -------------------------------------------------------------------

    def check_mechanism_evidence(
        self,
        mechanism: Dict,
        valid_comparison_ids: Set[str],
        valid_estimate_ids: Set[str],
    ) -> List[MatchResult]:
        results = []

        # v2: Validate ID prefixes
        for i, ta in enumerate(mechanism.get("target_actions", [])):
            aid = ta.get("action_id", "")
            if aid and not aid.startswith("TA"):
                results.append(
                    MatchResult(
                        field_path=f"mechanism_evidence.target_actions[{i}].action_id",
                        value=aid,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=f"target_actions action_id should start with 'TA' (e.g. TA1), got '{aid}'",
                    )
                )

            # v2: Validate action_type enum
            action_type = ta.get("action_type", "")
            if action_type and action_type not in _VALID_ACTION_TYPES:
                results.append(
                    MatchResult(
                        field_path=f"mechanism_evidence.target_actions[{i}].action_type",
                        value=action_type,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=f"Invalid action_type='{action_type}'. Valid values: {_VALID_ACTION_TYPES}. "
                        f"Use 'inhibitor' not 'inhibits', 'agonist' not 'activates', etc.",
                    )
                )

        for i, bm in enumerate(mechanism.get("biomarker_effects", [])):
            prefix = f"mechanism_evidence.biomarker_effects[{i}]"

            bid = bm.get("biomarker_id", "")
            if bid and not bid.startswith("B"):
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.biomarker_id",
                        value=bid,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=f"biomarker_effects biomarker_id should start with 'B' (e.g. B1), got '{bid}'",
                    )
                )

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
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.comparison_id",
                        value=cid,
                        found=False,
                        severity=MatchSeverity.ERROR,
                        message=f"Biomarker effect references comparison_id={cid} not in trial_structure",
                    )
                )

            lid = bm.get("linked_estimate_id")
            if lid and lid not in valid_estimate_ids:
                results.append(
                    MatchResult(
                        field_path=f"{prefix}.linked_estimate_id",
                        value=lid,
                        found=False,
                        severity=MatchSeverity.WARNING,
                        message=f"Biomarker effect references linked_estimate_id={lid} not in effect_estimates",
                    )
                )

        # v2: Validate claim IDs
        for i, claim in enumerate(mechanism.get("claims", [])):
            cid = claim.get("claim_id", "")
            if cid and not cid.startswith("MC"):
                results.append(
                    MatchResult(
                        field_path=f"mechanism_evidence.claims[{i}].claim_id",
                        value=cid,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=f"claims claim_id should start with 'MC' (e.g. MC1), got '{cid}'",
                    )
                )

            # v2: scope must be single value
            scope = claim.get("scope", "")
            if scope and "," in str(scope):
                results.append(
                    MatchResult(
                        field_path=f"mechanism_evidence.claims[{i}].scope",
                        value=scope,
                        found=True,
                        severity=MatchSeverity.ERROR,
                        message=f"claims scope must be single value, got '{scope}'. Split into multiple claims if needed.",
                    )
                )

        return results

    # -------------------------------------------------------------------
    # Report generation
    # -------------------------------------------------------------------

    def generate_error_report(self, results: List[MatchResult]) -> str:
        errors = [r for r in results if r.severity == MatchSeverity.ERROR]
        warnings = [r for r in results if r.severity == MatchSeverity.WARNING]

        if not errors and not warnings:
            return "All values passed hard-match verification."

        lines = []
        lines.append(
            f"Hard-match verification: {len(errors)} errors, {len(warnings)} warnings\n"
        )

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
        return {
            "total_checks": len(results),
            "errors": len([r for r in results if r.severity == MatchSeverity.ERROR]),
            "warnings": len(
                [r for r in results if r.severity == MatchSeverity.WARNING]
            ),
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
