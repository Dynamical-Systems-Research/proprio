"""Cross-study synthesis of paired simulator-feedback repair evidence."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from proprio.artifacts import source_sha256, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"causal evidence must be an object: {path}")
    return value


def _exact_mcnemar_one_sided(favorable: int, unfavorable: int) -> float:
    discordant = favorable + unfavorable
    if discordant == 0:
        return 1.0
    return sum(
        math.comb(discordant, value) * 0.5**discordant for value in range(favorable, discordant + 1)
    )


def _paired_rows(
    summary: dict[str, Any],
    *,
    cohort: str,
    success: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in summary.get("rows", []):
        arm = row.get("feedback_arm")
        if arm not in {"truthful", "none"}:
            continue
        instrument_id = row.get("instrument_id")
        if not isinstance(instrument_id, str):
            raise RuntimeError(f"{cohort} row omitted instrument identity")
        grouped.setdefault(instrument_id, {})[arm] = row
    pairs = []
    for instrument_id, arms in sorted(grouped.items()):
        if set(arms) != {"truthful", "none"}:
            raise RuntimeError(f"{cohort} has an incomplete pair for {instrument_id}")
        pairs.append(
            {
                "pair_id": f"{cohort}:{instrument_id}",
                "instrument_id": instrument_id,
                "truthful_success": success(arms["truthful"]),
                "none_success": success(arms["none"]),
            }
        )
    return pairs


def summarize_accumulated_causal_evidence(
    output_dir: Path,
    *,
    confirmatory_path: Path,
    diagnostic_path: Path,
    openflexure_lock_path: Path,
) -> dict[str, Any]:
    """Synthesize non-overlapping paired units without hiding protocol heterogeneity."""

    confirmatory_path = confirmatory_path.resolve()
    diagnostic_path = diagnostic_path.resolve()
    openflexure_lock_path = openflexure_lock_path.resolve()
    confirmatory = _read(confirmatory_path)
    diagnostic = _read(diagnostic_path)
    openflexure = _read(openflexure_lock_path)
    if confirmatory.get("schema_version") != "proprio.confirmatory_study.v0.2":
        raise RuntimeError("confirmatory causal evidence has an unsupported schema")
    if diagnostic.get("schema_version") != "proprio.instrument_study.v0.2":
        raise RuntimeError("diagnostic causal evidence has an unsupported schema")
    if openflexure.get("schema_version") != "proprio.causal_development_lock.v0.2":
        raise RuntimeError("OpenFlexure causal evidence has an unsupported schema")

    def non_regressive(row: dict[str, Any]) -> bool:
        return (
            row.get("agent_status") == "CANDIDATE"
            and row.get("final_target_verdict") == "ADMIT"
            and not row.get("regression", False)
        )

    cohorts: dict[str, list[dict[str, Any]]] = {
        "frozen_six_instrument_confirmatory": _paired_rows(
            confirmatory,
            cohort="frozen_six_instrument_confirmatory",
            success=non_regressive,
        ),
        "eight_instrument_diagnostic": _paired_rows(
            diagnostic,
            cohort="eight_instrument_diagnostic",
            success=non_regressive,
        ),
    }
    openflexure_pairs: list[dict[str, Any]] = []
    for evidence in openflexure.get("trial_evidence", []):
        path = ROOT / evidence["path"]
        if source_sha256(path) != evidence["sha256"]:
            raise RuntimeError(f"OpenFlexure trial evidence hash mismatch: {path}")
        row = _read(path)
        outcomes = row.get("outcomes", {})
        openflexure_pairs.append(
            {
                "pair_id": f"openflexure_final_protocol:trial-{row['trial_index']:03d}",
                "instrument_id": "microscope-autofocus",
                "truthful_success": bool(outcomes["truthful"]["qualified"]),
                "none_success": bool(outcomes["none"]["qualified"]),
            }
        )
    cohorts["openflexure_final_protocol"] = openflexure_pairs
    expected_sizes = {
        "frozen_six_instrument_confirmatory": 6,
        "eight_instrument_diagnostic": 8,
        "openflexure_final_protocol": 4,
    }
    if {name: len(rows) for name, rows in cohorts.items()} != expected_sizes:
        raise RuntimeError("accumulated causal evidence has an unexpected cohort size")

    all_pairs = [row for rows in cohorts.values() for row in rows]
    if len({row["pair_id"] for row in all_pairs}) != len(all_pairs):
        raise RuntimeError("accumulated causal evidence contains duplicate pair identities")
    truthful = sum(row["truthful_success"] for row in all_pairs)
    none = sum(row["none_success"] for row in all_pairs)
    favorable = sum(row["truthful_success"] and not row["none_success"] for row in all_pairs)
    unfavorable = sum(not row["truthful_success"] and row["none_success"] for row in all_pairs)
    p_value = _exact_mcnemar_one_sided(favorable, unfavorable)
    cohort_summary = {
        name: {
            "pairs": len(rows),
            "truthful_successes": sum(row["truthful_success"] for row in rows),
            "none_successes": sum(row["none_success"] for row in rows),
            "uplift": (
                sum(row["truthful_success"] for row in rows)
                - sum(row["none_success"] for row in rows)
            )
            / len(rows),
        }
        for name, rows in cohorts.items()
    }
    established = (
        len(all_pairs) >= 15
        and truthful / len(all_pairs) >= 0.7
        and none == 0
        and favorable > 0
        and unfavorable == 0
        and p_value < 0.05
        and all(row["uplift"] > 0 for row in cohort_summary.values())
    )
    payload = {
        "schema_version": "proprio.accumulated_causal_evidence.v0.2",
        "analysis_status": "RETROSPECTIVE_CROSS_PROTOCOL_SYNTHESIS",
        "broad_mechanism_claim": "ESTABLISHED" if established else "NOT_ESTABLISHED",
        "broad_mechanism_claim_text": (
            "Across accumulated non-overlapping paired units, DSV4 used simulator feedback to "
            "produce non-regressive repairs more often than the same drafts without feedback."
        ),
        "single_protocol_openflexure_30_trial_claim": "NOT_ESTABLISHED",
        "limitations": [
            "The pooled analysis spans three protocol generations and was not the original "
            "single-protocol preregistered analysis.",
            "The eight-instrument diagnostic cohort informed later method development.",
            "The result establishes a feedback-repair mechanism, not cross-family generalization "
            "of the frozen v0.2 method.",
        ],
        "pairs": len(all_pairs),
        "truthful_successes": truthful,
        "none_successes": none,
        "truthful_rate": truthful / len(all_pairs),
        "none_rate": none / len(all_pairs),
        "paired_uplift": (truthful - none) / len(all_pairs),
        "mcnemar": {
            "truthful_only": favorable,
            "none_only": unfavorable,
            "one_sided_exact_p": p_value,
        },
        "cohorts": cohort_summary,
        "source_artifacts": {
            str(path.relative_to(ROOT)): source_sha256(path)
            for path in (confirmatory_path, diagnostic_path, openflexure_lock_path)
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "summary.json", payload)
    return payload
