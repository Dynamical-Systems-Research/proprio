"""Image-grounded qualification for simulated microscope operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.ndimage import laplace

from proprio.instrument_types import GateCheck

FFT_IMPROVEMENT_MIN = 5.0
LAPLACIAN_IMPROVEMENT_MIN = 3.0
MIN_IMAGE_EDGE_PX = 128
MIN_DYNAMIC_RANGE = 20.0
MAX_SATURATED_FRACTION = 0.01


@dataclass(frozen=True)
class FocusScores:
    """Two independently implemented focus measures."""

    fft_high_frequency: float
    laplacian_variance: float


@dataclass(frozen=True)
class MicroscopyObservation:
    baseline: np.ndarray | None
    frame: np.ndarray | None
    operations: tuple[str, ...]
    calibrated: bool
    released: bool
    final_z: int | None
    data_complete: bool = True


def _grayscale(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float64)
    if array.ndim == 3:
        if array.shape[2] < 3:
            raise ValueError("color image must contain at least three channels")
        array = 0.2126 * array[..., 0] + 0.7152 * array[..., 1] + 0.0722 * array[..., 2]
    if array.ndim != 2:
        raise ValueError("image must be two-dimensional or RGB")
    if not np.all(np.isfinite(array)):
        raise ValueError("image contains non-finite values")
    return array


def focus_scores(image: np.ndarray) -> FocusScores:
    """Score sharpness with frequency- and spatial-domain implementations."""

    gray = _grayscale(image)
    centered = gray - float(np.mean(gray))
    spectrum = np.fft.rfft2(centered)
    fy = np.fft.fftfreq(gray.shape[0])[:, None]
    fx = np.fft.rfftfreq(gray.shape[1])[None, :]
    high_frequency = np.hypot(fy, fx) >= 0.18
    fft_energy = float(np.mean(np.abs(spectrum[high_frequency]) ** 2))
    laplacian_energy = float(np.var(laplace(gray, mode="reflect")))
    return FocusScores(
        fft_high_frequency=fft_energy,
        laplacian_variance=laplacian_energy,
    )


def _check(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def _ordered(operations: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    cursor = 0
    for operation in operations:
        if cursor < len(expected) and operation == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def verify_microscopy_observation(
    observation: MicroscopyObservation,
) -> tuple[GateCheck, ...]:
    """Check acquisition integrity without trusting the simulator's focus score."""

    expected_order = (
        "reset",
        "full_auto_calibrate",
        "fast_autofocus",
        "settle",
        "capture_frame",
        "release",
    )
    order_ok = _ordered(observation.operations, expected_order)
    frame = observation.frame
    baseline = observation.baseline
    shape_ok = (
        observation.data_complete
        and frame is not None
        and baseline is not None
        and frame.shape == baseline.shape
        and frame.ndim in {2, 3}
        and min(frame.shape[:2]) >= MIN_IMAGE_EDGE_PX
    )

    if shape_ok:
        assert frame is not None and baseline is not None
        gray = _grayscale(frame)
        baseline_scores = focus_scores(baseline)
        frame_scores = focus_scores(frame)
        fft_ratio = frame_scores.fft_high_frequency / max(
            baseline_scores.fft_high_frequency, 1e-12
        )
        laplacian_ratio = frame_scores.laplacian_variance / max(
            baseline_scores.laplacian_variance, 1e-12
        )
        dynamic_range = float(np.percentile(gray, 99.0) - np.percentile(gray, 1.0))
        saturated_fraction = float(np.mean(gray >= 254.5))
    else:
        baseline_scores = FocusScores(0.0, 0.0)
        frame_scores = FocusScores(0.0, 0.0)
        fft_ratio = 0.0
        laplacian_ratio = 0.0
        dynamic_range = 0.0
        saturated_fraction = 1.0

    fft_passed = fft_ratio >= FFT_IMPROVEMENT_MIN
    laplacian_passed = laplacian_ratio >= LAPLACIAN_IMPROVEMENT_MIN
    return (
        _check(
            "operation-order",
            order_ok,
            observed=list(observation.operations),
            required=list(expected_order),
        ),
        _check("camera-calibrated", observation.calibrated),
        _check(
            "calibrated-focus-reference",
            observation.final_z is not None and abs(observation.final_z) <= 100,
            observed_z=observation.final_z,
            reference_z=0,
            tolerance_steps=100,
        ),
        _check(
            "frame-complete",
            shape_ok,
            baseline_shape=None if baseline is None else list(baseline.shape),
            frame_shape=None if frame is None else list(frame.shape),
            minimum_edge_px=MIN_IMAGE_EDGE_PX,
        ),
        _check(
            "image-dynamic-range",
            dynamic_range >= MIN_DYNAMIC_RANGE,
            observed=dynamic_range,
            minimum=MIN_DYNAMIC_RANGE,
        ),
        _check(
            "detector-unsaturated",
            saturated_fraction <= MAX_SATURATED_FRACTION,
            observed_fraction=saturated_fraction,
            maximum_fraction=MAX_SATURATED_FRACTION,
        ),
        _check(
            "fft-focus-improvement",
            fft_passed,
            baseline=baseline_scores.fft_high_frequency,
            observed=frame_scores.fft_high_frequency,
            ratio=fft_ratio,
            minimum_ratio=FFT_IMPROVEMENT_MIN,
        ),
        _check(
            "laplacian-focus-improvement",
            laplacian_passed,
            baseline=baseline_scores.laplacian_variance,
            observed=frame_scores.laplacian_variance,
            ratio=laplacian_ratio,
            minimum_ratio=LAPLACIAN_IMPROVEMENT_MIN,
        ),
        _check(
            "independent-focus-agreement",
            fft_passed == laplacian_passed,
            fft_passed=fft_passed,
            laplacian_passed=laplacian_passed,
        ),
        _check("resource-release", observation.released),
    )
