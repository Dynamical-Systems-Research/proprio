"""Labeled verifier metrology for diagnostic reference-instrument simulations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from proprio.artifacts import write_canonical_json, write_jsonl
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_types import SimulationScenario
from proprio.reference_instruments import INSTRUMENTS
from proprio.reference_skills import render_invalid, render_valid

FAILURE_CLASSES = ("unsafe_setting", "wrong_target", "cleanup_omitted")


def run_instrument_metrology(
    output_dir: Path,
    *,
    cases_per_class: int = 300,
    seed: int = 20260709,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    family_summary: dict[str, Any] = {}
    total_false_reject = 0
    total_false_admit = 0

    for instrument_id, definition in sorted(INSTRUMENTS.items()):
        valid_rows = []
        for case_index in range(cases_per_class):
            source = render_valid(instrument_id, rng)
            result = evaluate_instrument_skill(
                instrument_id, source, scenario=SimulationScenario.REPAIR
            )
            row = {
                "instrument_id": instrument_id,
                "family": definition.family,
                "label": "valid",
                "case_index": case_index,
                "skill_sha256": result.skill_sha256,
                "verdict": result.verdict,
                "failed_checks": [check.check_id for check in result.checks if not check.passed],
            }
            rows.append(row)
            valid_rows.append(row)
        false_reject = sum(row["verdict"] != "ADMIT" for row in valid_rows)
        total_false_reject += false_reject

        invalid_summary = {}
        for failure_class in FAILURE_CLASSES:
            invalid_rows = []
            for case_index in range(cases_per_class):
                source = render_invalid(instrument_id, failure_class, rng)
                result = evaluate_instrument_skill(
                    instrument_id, source, scenario=SimulationScenario.REPAIR
                )
                row = {
                    "instrument_id": instrument_id,
                    "family": definition.family,
                    "label": "invalid",
                    "failure_class": failure_class,
                    "case_index": case_index,
                    "skill_sha256": result.skill_sha256,
                    "verdict": result.verdict,
                    "failed_checks": [
                        check.check_id for check in result.checks if not check.passed
                    ],
                }
                rows.append(row)
                invalid_rows.append(row)
            false_admit = sum(row["verdict"] == "ADMIT" for row in invalid_rows)
            total_false_admit += false_admit
            invalid_summary[failure_class] = {
                "cases": len(invalid_rows),
                "false_admit": false_admit,
                "false_admit_rate": false_admit / len(invalid_rows),
            }

        family_summary[instrument_id] = {
            "family": definition.family,
            "valid": {
                "cases": len(valid_rows),
                "false_reject": false_reject,
                "false_reject_rate": false_reject / len(valid_rows),
            },
            "invalid": invalid_summary,
        }

    write_jsonl(output_dir / "cases.jsonl", rows)
    valid_cases = cases_per_class * len(INSTRUMENTS)
    invalid_cases = cases_per_class * len(FAILURE_CLASSES) * len(INSTRUMENTS)
    summary = {
        "schema_version": "proprio.instrument_metrology.v0.2",
        "seed": seed,
        "cases_per_class": cases_per_class,
        "failure_classes": list(FAILURE_CLASSES),
        "valid_cases": valid_cases,
        "invalid_cases": invalid_cases,
        "false_reject": total_false_reject,
        "false_reject_rate": total_false_reject / valid_cases,
        "false_admit": total_false_admit,
        "false_admit_rate": total_false_admit / invalid_cases,
        "instruments": family_summary,
    }
    bars_pass = total_false_admit == 0 and summary["false_reject_rate"] <= 0.05
    summary["verdict"] = "PASS" if bars_pass else "FAIL"
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
