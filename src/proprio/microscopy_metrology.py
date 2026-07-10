"""Labeled metrology battery for the independent microscopy verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from proprio.artifacts import write_canonical_json
from proprio.microscopy_verifier import MicroscopyObservation, verify_microscopy_observation
from proprio.schema import canonical_json

INVALID_CLASSES = (
    "underswept-focus",
    "stale-frame",
    "saturated-frame",
    "low-contrast-frame",
    "truncated-frame",
    "calibration-missing",
    "release-missing",
    "wrong-order",
)
OPERATIONS = (
    "reset",
    "full_auto_calibrate",
    "fast_autofocus",
    "settle",
    "capture_frame",
    "release",
)


def _crop_pair(
    images: tuple[np.ndarray, ...],
    *,
    index: int,
    edge: int = 128,
) -> tuple[np.ndarray, ...]:
    height = min(image.shape[0] for image in images)
    width = min(image.shape[1] for image in images)
    if height < edge or width < edge:
        raise ValueError("metrology images are smaller than the preregistered crop")
    rng = np.random.default_rng(910_241 + index)
    top = int(rng.integers(0, height - edge + 1))
    left = int(rng.integers(0, width - edge + 1))
    return tuple(image[top : top + edge, left : left + edge].copy() for image in images)


def _observation(
    label: str,
    baseline: np.ndarray,
    valid: np.ndarray,
    underfocused: np.ndarray,
) -> MicroscopyObservation:
    frame = valid
    operations = OPERATIONS
    calibrated = True
    released = True
    final_z = 0
    complete = True
    if label == "underswept-focus":
        frame = underfocused
        final_z = 300
    elif label == "stale-frame":
        frame = baseline
    elif label == "saturated-frame":
        frame = np.full_like(valid, 255.0)
    elif label == "low-contrast-frame":
        mean = float(np.mean(valid))
        frame = mean + 0.01 * (valid - mean)
    elif label == "truncated-frame":
        frame = valid[:32, :32]
        complete = False
    elif label == "calibration-missing":
        calibrated = False
    elif label == "release-missing":
        released = False
    elif label == "wrong-order":
        operations = (
            "reset",
            "capture_frame",
            "full_auto_calibrate",
            "fast_autofocus",
            "settle",
            "release",
        )
    elif label != "valid":
        raise KeyError(label)
    return MicroscopyObservation(
        baseline=baseline,
        frame=frame,
        operations=operations,
        calibrated=calibrated,
        released=released,
        final_z=final_z,
        data_complete=complete,
    )


def run_microscopy_metrology(
    baseline: np.ndarray,
    focused: np.ndarray,
    underfocused: np.ndarray,
    *,
    output_dir: Path,
    cases_per_class: int = 300,
) -> dict[str, Any]:
    if cases_per_class < 300:
        raise ValueError("microscopy metrology requires at least 300 cases per class")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for label in ("valid", *INVALID_CLASSES):
        for index in range(cases_per_class):
            before, after, partial = _crop_pair(
                (baseline, focused, underfocused),
                index=index,
            )
            observation = _observation(label, before, after, partial)
            checks = verify_microscopy_observation(observation)
            fft = next(check for check in checks if check.check_id == "fft-focus-improvement")
            lap = next(check for check in checks if check.check_id == "laplacian-focus-improvement")
            admitted = all(check.passed for check in checks)
            rows.append(
                {
                    "case_id": f"{label}--{index:04d}",
                    "label": label,
                    "expected_valid": label == "valid",
                    "admitted": admitted,
                    "fft_valid": fft.passed,
                    "laplacian_valid": lap.passed,
                    "failed_checks": [check.check_id for check in checks if not check.passed],
                }
            )

    lines = b"".join(canonical_json(row) + b"\n" for row in rows)
    (output_dir / "cases.jsonl").write_bytes(lines)
    valid = [row for row in rows if row["expected_valid"]]
    invalid = [row for row in rows if not row["expected_valid"]]
    false_valid = sum(row["admitted"] for row in invalid)
    false_reject = sum(not row["admitted"] for row in valid)
    agreement = sum(row["fft_valid"] == row["laplacian_valid"] for row in rows) / len(rows)
    valid_concordance = sum(row["fft_valid"] == row["laplacian_valid"] for row in valid) / len(
        valid
    )
    invalid_agreement = sum(row["fft_valid"] == row["laplacian_valid"] for row in invalid) / len(
        invalid
    )
    per_class = {}
    for label in ("valid", *INVALID_CLASSES):
        selected = [row for row in rows if row["label"] == label]
        per_class[label] = {
            "cases": len(selected),
            "admitted": sum(row["admitted"] for row in selected),
            "false_valid": sum(row["admitted"] for row in selected) if label != "valid" else 0,
            "false_reject": sum(not row["admitted"] for row in selected) if label == "valid" else 0,
            "fft_valid": sum(row["fft_valid"] for row in selected),
            "laplacian_valid": sum(row["laplacian_valid"] for row in selected),
        }
    summary: dict[str, Any] = {
        "schema_version": "proprio.microscopy_metrology.v0.1",
        "cases_per_class": cases_per_class,
        "case_count": len(rows),
        "invalid_classes": list(INVALID_CLASSES),
        "false_valid": false_valid,
        "false_reject": false_reject,
        "false_reject_rate": false_reject / len(valid),
        "per_class": per_class,
        "alternate_implementation": {
            "primary": "normalized FFT high-frequency energy",
            "alternate": "SciPy spatial Laplacian variance",
            "agreement_rate": agreement,
            "valid_concordance_rate": valid_concordance,
            "invalid_agreement_rate": invalid_agreement,
            "joint_rule": "both focus measures and all acquisition checks must pass",
            "interpretation": (
                "Overall invalid-case disagreement is descriptive because complementary "
                "detectors are expected to fail on different artifacts."
            ),
        },
    }
    summary["verdict"] = (
        "PASS"
        if false_valid == 0 and summary["false_reject_rate"] <= 0.05 and valid_concordance >= 0.90
        else "FAIL"
    )
    write_canonical_json(output_dir / "summary.json", summary)
    sample = {
        label: next(row for row in rows if row["label"] == label)
        for label in ("valid", *INVALID_CLASSES)
    }
    (output_dir / "raw-sample.json").write_text(
        json.dumps(sample, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
