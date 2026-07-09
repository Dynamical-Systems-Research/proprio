"""Reproducible verifier-metrology battery and evidence artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from importlib.resources import files
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from proprio.artifacts import (
    file_sha256,
    source_sha256,
    write_bytes,
    write_canonical_json,
    write_jsonl,
)
from proprio.schema import StatusLabel
from proprio.xrd_generator import generate_calibrant_frame
from proprio.xrd_types import ValidityFault, load_preregistration
from proprio.xrd_verifier import verify_calibrant_frame

FAULT_TO_CHECK = {
    ValidityFault.GEOMETRY_MISCALIBRATION: "geometry-calibration",
    ValidityFault.ZERO_SHIFT: "zero-shift",
    ValidityFault.SAMPLE_DISPLACEMENT: "sample-displacement",
    ValidityFault.SATURATION: "detector-saturation",
    ValidityFault.DEAD_TIME: "detector-dead-time",
    ValidityFault.INSUFFICIENT_COUNTS: "counting-statistics",
    ValidityFault.CAKE_INTEGRATION_FAILURE: "cake-ring-fidelity",
    ValidityFault.UNINDEXED_PEAK: "calibrant-indexing",
    ValidityFault.CHI2_LOWER_TAIL: "chi2-lower-tail",
}

CHECK_TO_FEATURE = {
    "geometry-calibration": ("median_peak_fwhm_deg", "higher"),
    "zero-shift": ("zero_shift_abs_deg", "higher"),
    "sample-displacement": ("sample_displacement_residual_deg", "higher"),
    "detector-saturation": ("saturation_fraction", "higher"),
    "detector-dead-time": ("dead_time_fraction", "higher"),
    "counting-statistics": ("median_peak_snr", "lower"),
    "cake-ring-fidelity": ("cake_coverage", "lower"),
    "calibrant-indexing": ("unexpected_peak_ratio", "higher"),
    "chi2-lower-tail": ("chi2_lower_tail_probability", "lower"),
}


def _case_seed(base_seed: int, fault_index: int, case_index: int) -> int:
    return base_seed + fault_index * 100_000 + case_index


def _case_calibrant(case_index: int) -> str:
    return "si" if case_index % 10 == 0 else "lab6"


def _compact_case_row(case, verification) -> dict[str, Any]:
    return {
        "case_id": case.truth.case_id,
        "calibrant": case.truth.calibrant,
        "fault_class": case.truth.fault_class.value,
        "expected_valid": case.truth.expected_valid,
        "seed": case.truth.seed,
        "injected_parameters": case.truth.injected_parameters,
        "verifier_status": verification.record.status.value,
        "features": verification.features,
        "checks": {
            check.check_id: {
                "status": check.status.value,
                "metric_value": check.metric_value,
                "threshold": check.threshold,
                "comparator": check.comparator,
            }
            for check in verification.record.checks
        },
    }


def _risk(feature: float, direction: str) -> float:
    return float(feature if direction == "higher" else -feature)


def _roc(points: Iterable[tuple[float, bool]]) -> dict[str, Any]:
    ordered = sorted(points, key=lambda row: row[0], reverse=True)
    positives = sum(label for _, label in ordered)
    negatives = len(ordered) - positives
    if positives == 0 or negatives == 0:
        return {"auroc": None, "curve": []}
    true_positive = 0
    false_positive = 0
    curve = [{"threshold": None, "tpr": 0.0, "fpr": 0.0}]
    index = 0
    while index < len(ordered):
        threshold = ordered[index][0]
        while index < len(ordered) and ordered[index][0] == threshold:
            if ordered[index][1]:
                true_positive += 1
            else:
                false_positive += 1
            index += 1
        curve.append(
            {
                "threshold": threshold,
                "tpr": true_positive / positives,
                "fpr": false_positive / negatives,
            }
        )
    area = 0.0
    for left, right in pairwise(curve):
        area += (right["fpr"] - left["fpr"]) * (right["tpr"] + left["tpr"]) / 2.0
    return {"auroc": area, "curve": curve}


def _render_frame(path: Path, frame: np.ndarray) -> None:
    transformed = np.log1p(np.asarray(frame, dtype=float))
    low, high = np.percentile(transformed, [1, 99.8])
    normalized = np.clip((transformed - low) / max(high - low, 1e-9), 0.0, 1.0)
    image = Image.fromarray(np.asarray(normalized * 255.0, dtype=np.uint8), mode="L")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _report_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Proprio v0.1 verifier metrology",
        "",
        "This report is generated from the preregistered synthetic calibrant battery.",
        "Thresholds are read from the frozen preregistration and are not fitted on these cases.",
        "",
        f"Overall verdict: **{summary['verdict']}**",
        "",
        "| failure class | cases | false-valid | rate | target check | "
        "target-check misses | AUROC |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for fault, row in summary["invalid_classes"].items():
        auroc = row["auroc"]
        lines.append(
            f"| {fault} | {row['count']} | {row['false_valid']} | "
            f"{row['false_valid_rate']:.6f} | {row['target_check']} | "
            f"{row['target_check_false_valid']} | "
            f"{auroc:.6f} |"
        )
    valid = summary["valid_cases"]
    lines.extend(
        [
            "",
            "## Valid controls",
            "",
            f"- Cases: {valid['count']}",
            f"- False rejects: {valid['false_reject']}",
            f"- False-reject rate: {valid['false_reject_rate']:.6f}",
            "",
            "## Adversarial controls",
            "",
            f"- Invalid measurements rejected despite an always-valid claim: "
            f"{summary['adversarial']['always_valid_bot_independent_rejections']}",
            f"- Always-valid bot exploit rate: "
            f"{summary['adversarial']['always_valid_bot_exploit_rate']:.6f}",
            "",
            "## Independence",
            "",
            "- Generator: analytic NumPy Bragg-ring forward model.",
            "- Verifier: pyFAI integration plus independent peak, detector-telemetry, "
            "azimuthal-Poisson, and support checks.",
            "- Remaining correlated-oracle risk: both engines consume the same declared geometry, "
            "wavelength, and certified peak table/lattice provenance.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifact_manifest(output_dir: Path) -> None:
    manifest_rows = []
    for path in sorted(candidate for candidate in output_dir.rglob("*") if candidate.is_file()):
        if path.name == "artifact-manifest.json":
            continue
        manifest_rows.append(
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    write_canonical_json(
        output_dir / "artifact-manifest.json",
        {
            "schema_version": "proprio.artifact_manifest.v0.1",
            "artifacts": manifest_rows,
        },
    )


def run_metrology(
    *,
    output_dir: Path,
    cases_per_class: int | None = None,
    sample_count_per_class: int = 1,
) -> dict[str, Any]:
    """Run the labeled validity battery and persist all gate evidence."""

    prereg = load_preregistration()
    configured_count = int(prereg["battery"]["cases_per_class"])
    cases_per_class = cases_per_class or configured_count
    if cases_per_class <= 0:
        raise ValueError("cases_per_class must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)

    prereg_resource = files("proprio").joinpath("data/metrology-preregistration.yaml")
    prereg_payload = prereg_resource.read_bytes()
    write_bytes(
        output_dir / "metrology-preregistration.yaml",
        prereg_payload,
        "application/yaml",
    )

    base_seed = int(prereg["battery"]["seed"])
    rows: list[dict[str, Any]] = []
    for fault_index, fault in enumerate(ValidityFault):
        for case_index in range(cases_per_class):
            seed = _case_seed(base_seed, fault_index, case_index)
            case = generate_calibrant_frame(
                calibrant=_case_calibrant(case_index),
                fault=fault,
                seed=seed,
            )
            verification = verify_calibrant_frame(case)
            row = _compact_case_row(case, verification)
            rows.append(row)
            if case_index < sample_count_per_class:
                sample_dir = output_dir / "raw_samples"
                sample_dir.mkdir(parents=True, exist_ok=True)
                np.save(sample_dir / f"{fault.value}.npy", case.frame, allow_pickle=False)
                _render_frame(sample_dir / f"{fault.value}.png", case.frame)
                write_canonical_json(sample_dir / f"{fault.value}.record.json", row)

    write_jsonl(output_dir / "scored_cases.jsonl", rows)
    valid_rows = [row for row in rows if row["expected_valid"]]
    invalid_rows = [row for row in rows if not row["expected_valid"]]
    valid_false_reject = sum(row["verifier_status"] != StatusLabel.SUCCEEDED for row in valid_rows)
    valid_false_reject_rate = valid_false_reject / max(1, len(valid_rows))

    invalid_classes: dict[str, Any] = {}
    roc_payload: dict[str, Any] = {}
    for fault, target_check in FAULT_TO_CHECK.items():
        target_rows = [row for row in invalid_rows if row["fault_class"] == fault.value]
        false_valid = sum(row["verifier_status"] == StatusLabel.SUCCEEDED for row in target_rows)
        target_check_false_valid = sum(
            row["checks"][target_check]["status"] == StatusLabel.SUCCEEDED for row in target_rows
        )
        feature_name, direction = CHECK_TO_FEATURE[target_check]
        roc_points = [
            (_risk(float(row["features"][feature_name]), direction), False) for row in valid_rows
        ] + [(_risk(float(row["features"][feature_name]), direction), True) for row in target_rows]
        roc = _roc(roc_points)
        roc_payload[target_check] = {
            "fault_class": fault.value,
            "feature": feature_name,
            "invalid_direction": direction,
            **roc,
        }
        invalid_classes[fault.value] = {
            "count": len(target_rows),
            "false_valid": false_valid,
            "false_valid_rate": false_valid / max(1, len(target_rows)),
            "target_check": target_check,
            "target_check_false_valid": target_check_false_valid,
            "target_check_false_valid_rate": target_check_false_valid / max(1, len(target_rows)),
            "auroc": roc["auroc"],
        }

    invalid_gate = all(
        row["count"] >= configured_count
        and row["false_valid"] <= int(prereg["battery"]["false_valid_max_observed"])
        for row in invalid_classes.values()
    )
    valid_gate = valid_false_reject_rate <= float(prereg["battery"]["false_reject_rate_max"])
    false_valid_total = sum(row["verifier_status"] == StatusLabel.SUCCEEDED for row in invalid_rows)
    summary = {
        "schema_version": "proprio.verifier_metrology.v0.1",
        "verdict": "PASS" if invalid_gate and valid_gate else "FAIL",
        "preregistration_sha256": hashlib.sha256(prereg_payload).hexdigest(),
        "cases_per_class_requested": cases_per_class,
        "cases_per_class_required": configured_count,
        "valid_cases": {
            "count": len(valid_rows),
            "false_reject": valid_false_reject,
            "false_reject_rate": valid_false_reject_rate,
            "bar": float(prereg["battery"]["false_reject_rate_max"]),
            "passed": valid_gate,
        },
        "invalid_classes": invalid_classes,
        "adversarial": {
            "always_valid_bot_claimed_passes": len(invalid_rows),
            "always_valid_bot_independent_rejections": len(invalid_rows) - false_valid_total,
            "always_valid_bot_exploit_rate": false_valid_total / max(1, len(invalid_rows)),
        },
        "independence": {
            "generator": "analytic_numpy_bragg_ring_v1",
            "verifier": "pyfai_plus_independent_statistical_checks_v1",
            "generator_sha256": source_sha256(Path(__file__).with_name("xrd_generator.py")),
            "verifier_sha256": source_sha256(Path(__file__).with_name("xrd_verifier.py")),
            "residual_risk": (
                "shared declared geometry, wavelength, and calibrant provenance; "
                "no shared image-generation or integration implementation"
            ),
        },
    }
    write_canonical_json(output_dir / "summary.json", summary)
    write_canonical_json(output_dir / "roc.json", roc_payload)
    write_bytes(
        output_dir / "report.md",
        _report_markdown(summary).encode("utf-8"),
        "text/markdown",
    )

    write_artifact_manifest(output_dir)
    return summary
