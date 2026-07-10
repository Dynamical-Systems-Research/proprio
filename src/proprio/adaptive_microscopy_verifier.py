"""Independent repeated-measurement checks for adaptive OpenFlexure skills."""

from __future__ import annotations

import hashlib
import math
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from proprio.instrument_types import GateCheck
from proprio.microscopy_verifier import MicroscopyObservation, verify_microscopy_observation

MIN_REPEATS = 3


def _load_thresholds() -> dict[str, Any]:
    resource = files("proprio").joinpath("data/adaptive-microscopy-thresholds.yaml")
    payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if payload.get("status") not in {"preregistered_development", "calibrated"}:
        raise RuntimeError("adaptive microscopy thresholds have no valid development status")
    return payload


_THRESHOLDS = _load_thresholds()
CURVE = _THRESHOLDS["autofocus_curve"]
MIN_CURVE_SAMPLES = int(CURVE["minimum_samples"])
REFERENCE_Z = float(CURVE["reference_z"])
REFERENCE_TOLERANCE = float(CURVE["reference_tolerance_steps"])
MIN_PEAK_PROMINENCE = float(CURVE["peak_prominence_minimum"])
MAX_SELECTED_PEAK_ERROR = float(CURVE["selected_peak_tolerance_steps"])
MAX_TEMPORAL_RSE = float(_THRESHOLDS["temporal_relative_standard_error"]["maximum"])
ACQUISITION_TIME = _THRESHOLDS["acquisition_time_seconds"]
MAX_ACQUISITION_SECONDS = float(ACQUISITION_TIME["maximum"])
STAGE_STEPS_PER_SECOND = float(ACQUISITION_TIME["stage_steps_per_second"])
RAW_FRAME_SECONDS = float(ACQUISITION_TIME["raw_frame_seconds"])


def adaptive_verifier_sha256() -> str:
    digest = hashlib.sha256()
    digest.update(Path(__file__).read_bytes())
    threshold_resource = files("proprio").joinpath("data/adaptive-microscopy-thresholds.yaml")
    digest.update(threshold_resource.read_bytes())
    return digest.hexdigest()
REPLACED_RELATIVE_CHECKS = frozenset(
    {
        "fft-focus-improvement",
        "laplacian-focus-improvement",
        "independent-focus-agreement",
    }
)


def _check(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def _autofocus_curve(
    trace: tuple[dict[str, Any], ...],
    final_z: int | None,
) -> tuple[GateCheck, ...]:
    sweeps = [row for row in trace if row.get("operation") == "fast_autofocus"]
    if not sweeps:
        return (
            _check("autofocus-curve-complete", False, reason="no autofocus sweep"),
            _check("autofocus-reference-covered", False, reason="no autofocus sweep"),
            _check("autofocus-peak-prominent", False, reason="no autofocus sweep"),
            _check("autofocus-peak-selected", False, reason="no autofocus sweep"),
        )
    sweep = sweeps[-1]
    jpeg_times = np.asarray(sweep.get("jpeg_times", []), dtype=np.float64)
    jpeg_sizes = np.asarray(sweep.get("jpeg_sizes", []), dtype=np.float64)
    stage_times = np.asarray(sweep.get("stage_times", []), dtype=np.float64)
    positions = sweep.get("stage_positions", [])
    stage_z = np.asarray([row.get("z") for row in positions], dtype=np.float64)
    structural = (
        len(jpeg_times) == len(jpeg_sizes)
        and len(stage_times) == len(stage_z)
        and len(stage_times) >= 2
        and np.all(np.isfinite(jpeg_times))
        and np.all(np.isfinite(jpeg_sizes))
        and np.all(np.isfinite(stage_times))
        and np.all(np.isfinite(stage_z))
        and np.all(np.diff(jpeg_times) >= 0)
        and np.all(np.diff(stage_times) >= 0)
    )
    if not structural:
        return (
            _check(
                "autofocus-curve-complete",
                False,
                jpeg_samples=len(jpeg_times),
                stage_samples=len(stage_times),
                minimum_samples=MIN_CURVE_SAMPLES,
            ),
            _check("autofocus-reference-covered", False, reason="curve incomplete"),
            _check("autofocus-peak-prominent", False, reason="curve incomplete"),
            _check("autofocus-peak-selected", False, reason="curve incomplete"),
        )
    stage_displacements = np.diff(stage_z)
    primary_index = int(np.argmax(stage_displacements))
    primary_start = float(stage_times[primary_index])
    primary_stop = float(stage_times[primary_index + 1])
    primary_mask = (jpeg_times >= primary_start) & (jpeg_times <= primary_stop)
    primary_times = jpeg_times[primary_mask]
    primary_sizes = jpeg_sizes[primary_mask]
    complete = (
        stage_displacements[primary_index] > 0
        and len(primary_times) >= MIN_CURVE_SAMPLES
        and primary_stop > primary_start
    )
    if not complete:
        return (
            _check(
                "autofocus-curve-complete",
                False,
                jpeg_samples=len(primary_times),
                stage_samples=len(stage_times),
                minimum_samples=MIN_CURVE_SAMPLES,
                primary_stage_displacement=float(stage_displacements[primary_index]),
            ),
            _check("autofocus-reference-covered", False, reason="primary sweep incomplete"),
            _check("autofocus-peak-prominent", False, reason="primary sweep incomplete"),
            _check("autofocus-peak-selected", False, reason="primary sweep incomplete"),
        )
    sampled_z = np.interp(primary_times, stage_times, stage_z)
    peak_index = int(np.argmax(primary_sizes))
    peak_z = float(sampled_z[peak_index])
    edge = max(1, len(primary_sizes) // 10)
    edge_baseline = float(
        np.median(np.concatenate((primary_sizes[:edge], primary_sizes[-edge:])))
    )
    peak_value = float(primary_sizes[peak_index])
    prominence = (peak_value - edge_baseline) / max(peak_value, 1.0)
    minimum_z = float(np.min(sampled_z))
    maximum_z = float(np.max(sampled_z))
    covered = minimum_z <= REFERENCE_Z <= maximum_z
    peak_near_reference = abs(peak_z - REFERENCE_Z) <= REFERENCE_TOLERANCE
    selected_error = math.inf if final_z is None else abs(float(final_z) - peak_z)
    selected = peak_near_reference and selected_error <= MAX_SELECTED_PEAK_ERROR
    return (
        _check(
            "autofocus-curve-complete",
            True,
            jpeg_samples=len(primary_times),
            stage_samples=len(stage_times),
            minimum_samples=MIN_CURVE_SAMPLES,
            primary_stage_displacement=float(stage_displacements[primary_index]),
        ),
        _check(
            "autofocus-reference-covered",
            covered,
            minimum_z=minimum_z,
            maximum_z=maximum_z,
            reference_z=REFERENCE_Z,
        ),
        _check(
            "autofocus-peak-prominent",
            prominence >= MIN_PEAK_PROMINENCE,
            observed=prominence,
            minimum=MIN_PEAK_PROMINENCE,
            peak_z=peak_z,
            peak_value=peak_value,
            edge_baseline=edge_baseline,
        ),
        _check(
            "autofocus-peak-selected",
            selected,
            final_z=final_z,
            peak_z=peak_z,
            selected_peak_error=selected_error,
            maximum_error=MAX_SELECTED_PEAK_ERROR,
            reference_z=REFERENCE_Z,
            reference_tolerance=REFERENCE_TOLERANCE,
        ),
    )


def _acquisition_time(trace: tuple[dict[str, Any], ...]) -> GateCheck:
    sweep_steps = sum(
        abs(float(row.get("dz_steps", row.get("sweep_steps", 0.0))))
        for row in trace
        if row.get("operation") == "fast_autofocus"
    )
    correction_steps = sum(
        abs(float(row.get("delta_steps", 0.0)))
        for row in trace
        if row.get("operation") == "move_z"
    )
    raw_frames = sum(row.get("operation") == "capture_frame" for row in trace)
    observed = (sweep_steps + correction_steps) / STAGE_STEPS_PER_SECOND + (
        raw_frames * RAW_FRAME_SECONDS
    )
    return _check(
        "acquisition-time-budget",
        observed <= MAX_ACQUISITION_SECONDS,
        observed_seconds=observed,
        maximum_seconds=MAX_ACQUISITION_SECONDS,
        autofocus_steps=sweep_steps,
        correction_steps=correction_steps,
        stage_steps_per_second=STAGE_STEPS_PER_SECOND,
        raw_frames=raw_frames,
        raw_frame_seconds=RAW_FRAME_SECONDS,
    )


def verify_adaptive_microscopy(
    observation: MicroscopyObservation,
    frames: tuple[np.ndarray, ...],
    trace: tuple[dict[str, Any], ...],
) -> tuple[GateCheck, ...]:
    base = tuple(
        check
        for check in verify_microscopy_observation(observation)
        if check.check_id not in REPLACED_RELATIVE_CHECKS
    )
    resource_check = _acquisition_time(trace)
    baseline = observation.baseline
    if baseline is None or not frames:
        return (
            *base,
            resource_check,
            _check("repeat-count", False, observed=len(frames), minimum=MIN_REPEATS),
            _check("repeat-focus-confidence", False, reason="frames unavailable"),
        )
    stack = np.stack([np.asarray(frame, dtype=np.float64) for frame in frames])
    mean_frame = np.mean(stack, axis=0)
    temporal_sigma = float(np.median(np.std(stack, axis=0, ddof=1)))
    spatial_contrast = float(np.std(mean_frame))
    temporal_rse = temporal_sigma / math.sqrt(len(frames)) / max(spatial_contrast, 1e-12)
    uncertainty_ok = temporal_rse <= MAX_TEMPORAL_RSE
    repeat_count_ok = len(frames) >= MIN_REPEATS
    return (
        *base,
        *_autofocus_curve(trace, observation.final_z),
        resource_check,
        _check("repeat-count", repeat_count_ok, observed=len(frames), minimum=MIN_REPEATS),
        _check(
            "temporal-measurement-uncertainty",
            uncertainty_ok,
            observed_relative_standard_error=temporal_rse,
            maximum_relative_standard_error=MAX_TEMPORAL_RSE,
            temporal_noise_sigma=temporal_sigma,
            spatial_image_contrast=spatial_contrast,
            repeats=len(frames),
        ),
    )
