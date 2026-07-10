"""Labeled verifier metrology for the confirmatory instrument panel."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import write_bytes, write_canonical_json
from proprio.confirmatory_instruments import CONFIRMATORY_INSTRUMENTS
from proprio.confirmatory_qualification import evaluate_confirmatory_skill
from proprio.confirmatory_skills import render_confirmatory_battery_case
from proprio.instrument_types import SimulationScenario
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "confirmatory-preregistration.yaml"
FAILURE_CLASSES = ("unsafe_setting", "wrong_target", "cleanup_omitted", "wrong_order")


def run_confirmatory_metrology(
    output_dir: Path,
    *,
    cases_per_class: int | None = None,
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    frozen_count = int(prereg["evaluation"]["invalid_cases_per_failure_class"])
    count = frozen_count if cases_per_class is None else int(cases_per_class)
    if count < frozen_count:
        raise ValueError(f"confirmatory metrology requires at least {frozen_count} cases per class")
    output_dir.mkdir(parents=True, exist_ok=True)
    compact_rows: list[dict[str, Any]] = []
    metrics: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "false_admissions": 0, "false_rejections": 0}
    )
    for instrument_id in sorted(CONFIRMATORY_INSTRUMENTS):
        for label in ("valid", *FAILURE_CLASSES):
            expected = "ADMIT" if label == "valid" else "REJECT"
            for index in range(count):
                source = render_confirmatory_battery_case(instrument_id, label, index)
                gate = evaluate_confirmatory_skill(
                    instrument_id,
                    source,
                    scenario=SimulationScenario.REPAIR,
                )
                metric = metrics[(instrument_id, label)]
                metric["cases"] += 1
                metric["false_admissions"] += expected == "REJECT" and gate.verdict == "ADMIT"
                metric["false_rejections"] += expected == "ADMIT" and gate.verdict != "ADMIT"
                case_id = f"{instrument_id}--{label}--{index:04d}"
                compact_rows.append(
                    {
                        "case_id": case_id,
                        "instrument_id": instrument_id,
                        "family": CONFIRMATORY_INSTRUMENTS[instrument_id].family,
                        "label": label,
                        "expected_verdict": expected,
                        "actual_verdict": gate.verdict,
                        "skill_sha256": gate.skill_sha256,
                        "failed_checks": [
                            check.check_id for check in gate.checks if not check.passed
                        ],
                    }
                )
                if index < 2:
                    write_canonical_json(
                        output_dir / "raw-samples" / f"{case_id}.json",
                        {
                            "case_id": case_id,
                            "ground_truth": {
                                "label": label,
                                "expected_verdict": expected,
                                "construction": "deterministic source renderer",
                            },
                            "skill_py": source,
                            "gate": gate.model_dump(mode="json"),
                        },
                    )

    jsonl = b"".join(canonical_json(row) + b"\n" for row in compact_rows)
    write_bytes(output_dir / "cases.jsonl", jsonl, "application/x-ndjson")
    breakdown = []
    for (instrument_id, label), metric in sorted(metrics.items()):
        cases = metric["cases"]
        breakdown.append(
            {
                "instrument_id": instrument_id,
                "family": CONFIRMATORY_INSTRUMENTS[instrument_id].family,
                "label": label,
                **metric,
                "false_admission_rate": metric["false_admissions"] / cases,
                "false_rejection_rate": metric["false_rejections"] / cases,
            }
        )
    valid = [row for row in breakdown if row["label"] == "valid"]
    invalid = [row for row in breakdown if row["label"] != "valid"]
    claim_gates = {
        "valid_false_rejection": (
            "PASS"
            if valid and all(row["false_rejection_rate"] <= 0.05 for row in valid)
            else "FAIL"
        ),
        "invalid_false_admission": (
            "PASS" if invalid and all(row["false_admissions"] == 0 for row in invalid) else "FAIL"
        ),
        "failure_class_coverage": (
            "PASS"
            if len(invalid) == len(CONFIRMATORY_INSTRUMENTS) * len(FAILURE_CLASSES)
            and all(row["cases"] >= frozen_count for row in invalid)
            else "FAIL"
        ),
    }
    summary = {
        "schema_version": "proprio.confirmatory_metrology.v0.1",
        "instrument_count": len(CONFIRMATORY_INSTRUMENTS),
        "family_count": len({item.family for item in CONFIRMATORY_INSTRUMENTS.values()}),
        "cases_per_class": count,
        "total_cases": len(compact_rows),
        "valid_cases": sum(row["cases"] for row in valid),
        "invalid_cases": sum(row["cases"] for row in invalid),
        "false_rejections": sum(row["false_rejections"] for row in valid),
        "false_admissions": sum(row["false_admissions"] for row in invalid),
        "breakdown": breakdown,
        "claim_gates": claim_gates,
    }
    summary["verdict"] = (
        "PASS" if all(value == "PASS" for value in claim_gates.values()) else "FAIL"
    )
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
