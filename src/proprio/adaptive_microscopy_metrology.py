"""Independent synthetic fault battery for the adaptive microscopy verifier."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

from proprio.adaptive_microscopy_verifier import verify_adaptive_microscopy
from proprio.artifacts import write_canonical_json, write_jsonl
from proprio.microscopy_verifier import MicroscopyObservation


class MicroscopyFault(StrEnum):
    VALID = "valid"
    CURVE_TRUNCATED = "curve_truncated"
    REFERENCE_EXCLUDED = "reference_excluded"
    FLAT_PEAK = "flat_peak"
    SELECTED_PEAK_MISMATCH = "selected_peak_mismatch"
    INSUFFICIENT_REPEATS = "insufficient_repeats"
    HIGH_UNCERTAINTY = "high_uncertainty"
    SATURATION = "saturation"
    LOW_DYNAMIC_RANGE = "low_dynamic_range"
    TRUNCATED_FRAME = "truncated_frame"
    ACQUISITION_TIME = "acquisition_time"


EXPECTED_CHECK = {
    MicroscopyFault.CURVE_TRUNCATED: "autofocus-curve-complete",
    MicroscopyFault.REFERENCE_EXCLUDED: "autofocus-reference-covered",
    MicroscopyFault.FLAT_PEAK: "autofocus-peak-prominent",
    MicroscopyFault.SELECTED_PEAK_MISMATCH: "autofocus-peak-selected",
    MicroscopyFault.INSUFFICIENT_REPEATS: "repeat-count",
    MicroscopyFault.HIGH_UNCERTAINTY: "temporal-measurement-uncertainty",
    MicroscopyFault.SATURATION: "detector-unsaturated",
    MicroscopyFault.LOW_DYNAMIC_RANGE: "image-dynamic-range",
    MicroscopyFault.TRUNCATED_FRAME: "frame-complete",
    MicroscopyFault.ACQUISITION_TIME: "acquisition-time-budget",
}


def _pattern() -> np.ndarray:
    y, x = np.indices((128, 128))
    base = (((x // 8 + y // 8) % 2) * 170 + 40).astype(np.float64)
    return np.stack((base, base * 0.95, base * 0.9), axis=2)


def _curve(fault: MicroscopyFault) -> tuple[dict[str, Any], int]:
    z = np.linspace(-1000.0, 1000.0, 80)
    final_z = 0
    if fault is MicroscopyFault.REFERENCE_EXCLUDED:
        z = np.linspace(300.0, 1300.0, 80)
        center = 300.0
        final_z = 300
    else:
        center = 0.0
    sharpness = 1000.0 + 9000.0 * np.exp(-(((z - center) / 220.0) ** 2))
    times = np.arange(len(z), dtype=np.float64)
    if fault is MicroscopyFault.FLAT_PEAK:
        sharpness = np.full_like(sharpness, 1000.0)
    jpeg_times = times
    jpeg_sizes = sharpness
    if fault is MicroscopyFault.CURVE_TRUNCATED:
        jpeg_times = times[:10]
        jpeg_sizes = sharpness[:10]
    if fault is MicroscopyFault.SELECTED_PEAK_MISMATCH:
        final_z = 500
    trace = {
        "sequence": 2,
        "operation": "fast_autofocus",
        "dz_steps": 8000 if fault is MicroscopyFault.ACQUISITION_TIME else 4000,
        "position": [0, 0, final_z],
        "sweep_steps": 8000 if fault is MicroscopyFault.ACQUISITION_TIME else 4000,
        "sample_count": len(jpeg_times),
        "jpeg_times": list(jpeg_times),
        "jpeg_sizes": list(jpeg_sizes),
        "stage_times": [float(times[0]), float(times[-1])],
        "stage_positions": [
            {"x": 0, "y": 0, "z": float(z[0])},
            {"x": 0, "y": 0, "z": float(z[-1])},
        ],
    }
    return trace, final_z


def generate_microscopy_case(
    fault: MicroscopyFault,
    seed: int,
) -> tuple[MicroscopyObservation, tuple[np.ndarray, ...], tuple[dict[str, Any], ...]]:
    rng = np.random.default_rng(seed)
    sharp = _pattern()
    baseline = gaussian_filter(sharp, sigma=(5.0, 5.0, 0.0))
    if fault is MicroscopyFault.INSUFFICIENT_REPEATS:
        repeats = 2
    elif fault is MicroscopyFault.ACQUISITION_TIME:
        repeats = 5
    else:
        repeats = 3
    noise = 8.0 if fault is MicroscopyFault.HIGH_UNCERTAINTY else 0.8
    frames = tuple(sharp + rng.normal(0.0, noise, sharp.shape) for _ in range(repeats))
    if fault is MicroscopyFault.SATURATION:
        frames = tuple(np.full_like(sharp, 255.0) for _ in range(repeats))
    elif fault is MicroscopyFault.LOW_DYNAMIC_RANGE:
        frames = tuple(128.0 + rng.normal(0.0, 0.2, sharp.shape) for _ in range(repeats))
    elif fault is MicroscopyFault.TRUNCATED_FRAME:
        frames = tuple(frame[:64, :64] for frame in frames)
    curve, final_z = _curve(fault)
    operations = (
        "reset",
        "full_auto_calibrate",
        "fast_autofocus",
        "settle",
        *("capture_frame" for _ in range(repeats)),
        "release",
    )
    observation = MicroscopyObservation(
        baseline=baseline,
        frame=frames[-1],
        operations=operations,
        calibrated=True,
        released=True,
        final_z=final_z,
    )
    trace = (
        {"sequence": 0, "operation": "reset"},
        {"sequence": 1, "operation": "full_auto_calibrate"},
        curve,
        {"sequence": 3, "operation": "settle"},
        *({"sequence": 4 + index, "operation": "capture_frame"} for index in range(repeats)),
        {"sequence": 4 + repeats, "operation": "release"},
    )
    return observation, frames, trace


def _evaluate_case(fault: MicroscopyFault, seed: int, index: int) -> dict[str, Any]:
    observation, frames, trace = generate_microscopy_case(fault, seed)
    checks = verify_adaptive_microscopy(observation, frames, trace)
    observed_valid = all(check.passed for check in checks)
    expected_valid = fault is MicroscopyFault.VALID
    expected_check = EXPECTED_CHECK.get(fault)
    failed_checks = [check.check_id for check in checks if not check.passed]
    return {
        "schema_version": "proprio.adaptive_microscopy_metrology_case.v0.2",
        "case_id": f"{fault.value}-{index:04d}",
        "fault_class": fault.value,
        "seed": seed,
        "expected_valid": expected_valid,
        "observed_valid": observed_valid,
        "expected_failed_check": expected_check,
        "expected_check_detected": expected_check is None or expected_check in failed_checks,
        "failed_checks": failed_checks,
        "checks": [check.model_dump(mode="json") for check in checks],
        "frame_sha256s": [hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames],
    }


def run_adaptive_microscopy_metrology(
    output_dir: Path,
    *,
    cases_per_class: int = 300,
    seed_base: int = 742_000,
) -> dict[str, Any]:
    if cases_per_class < 300:
        raise ValueError("adaptive microscopy metrology requires at least 300 cases per class")
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        (fault, seed_base + fault_index * 100_000 + index, index)
        for fault_index, fault in enumerate(MicroscopyFault)
        for index in range(cases_per_class)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda args: _evaluate_case(*args), tasks))
    write_jsonl(output_dir / "cases.jsonl", rows)
    classes: dict[str, dict[str, Any]] = {}
    for fault in MicroscopyFault:
        selected = [row for row in rows if row["fault_class"] == fault.value]
        false_valid = sum(not row["expected_valid"] and row["observed_valid"] for row in selected)
        false_reject = sum(row["expected_valid"] and not row["observed_valid"] for row in selected)
        detection_miss = sum(not row["expected_check_detected"] for row in selected)
        classes[fault.value] = {
            "cases": len(selected),
            "false_valid": false_valid,
            "false_reject": false_reject,
            "expected_check_missed": detection_miss,
        }
    valid = classes[MicroscopyFault.VALID.value]
    invalid = [
        classes[fault.value] for fault in MicroscopyFault if fault is not MicroscopyFault.VALID
    ]
    passed = valid["false_reject"] / valid["cases"] <= 0.05 and all(
        row["false_valid"] == 0 and row["expected_check_missed"] == 0 for row in invalid
    )
    inspection_rows = [
        next(row for row in rows if row["fault_class"] == fault.value) for fault in MicroscopyFault
    ]
    inspection = {
        "schema_version": "proprio.adaptive_microscopy_raw_inspection.v0.2",
        "agent_inspection": "complete",
        "human_countersign": "pending",
        "cases": inspection_rows,
    }
    write_canonical_json(output_dir / "inspection.json", inspection)
    summary = {
        "schema_version": "proprio.adaptive_microscopy_metrology.v0.2",
        "cases_per_class": cases_per_class,
        "seed_base": seed_base,
        "generator": "independent analytic curve and image generator",
        "verifier": "src/proprio/adaptive_microscopy_verifier.py",
        "classes": classes,
        "total_cases": len(rows),
        "verdict": "PASS" if passed else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
