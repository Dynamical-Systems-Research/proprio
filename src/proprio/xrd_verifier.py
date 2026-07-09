"""Independent measurement-validity verifier for calibrant/QC frames."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyFAI.integrator.azimuthal import AzimuthalIntegrator
from scipy.signal import find_peaks
from scipy.stats import chi2

from proprio.artifacts import source_sha256
from proprio.schema import CheckResult, Provenance, StatusLabel, ValidityRecord
from proprio.xrd_types import SyntheticFrame, XRDGeometry, load_preregistration


@dataclass(frozen=True)
class VerificationResult:
    record: ValidityRecord
    features: dict[str, float]


def _provenance(*, preregistration_sha256: str) -> Provenance:
    return Provenance(
        producer="proprio.xrd_verifier",
        producer_version="0.1.0",
        input_refs=(f"preregistration_sha256:{preregistration_sha256}",),
        implementation_sha256=source_sha256(Path(__file__)),
    )


def _integrator(geometry: XRDGeometry) -> AzimuthalIntegrator:
    return AzimuthalIntegrator(
        dist=geometry.distance_m,
        poni1=(geometry.center_y_px + 0.5) * geometry.pixel_size_m,
        poni2=(geometry.center_x_px + 0.5) * geometry.pixel_size_m,
        pixel1=geometry.pixel_size_m,
        pixel2=geometry.pixel_size_m,
        wavelength=geometry.wavelength_m,
    )


def _threshold(prereg: dict[str, Any], name: str) -> float:
    return float(prereg["thresholds"][name]["value"])


def _check(
    *,
    check_id: str,
    passed: bool,
    summary: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
    comparator: str,
    provenance: Provenance,
    units: str | None = None,
    details: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        status=StatusLabel.SUCCEEDED if passed else StatusLabel.FAILED,
        summary=summary,
        metric_name=metric_name,
        metric_value=float(metric_value),
        threshold=float(threshold),
        comparator=comparator,  # type: ignore[arg-type]
        units=units,
        details=details or {},
        provenance=provenance,
    )


def _local_peaks(
    radial: np.ndarray,
    intensity: np.ndarray,
    expected: list[float],
) -> tuple[list[float], list[float], list[float], float]:
    positions: list[float] = []
    amplitudes: list[float] = []
    widths: list[float] = []
    background = float(np.percentile(intensity, 20))
    for target in expected:
        mask = np.abs(radial - target) <= 1.5
        local_indices = np.flatnonzero(mask)
        if not len(local_indices):
            positions.append(float("nan"))
            amplitudes.append(0.0)
            widths.append(float("inf"))
            continue
        local = intensity[local_indices]
        peak_local = int(np.argmax(local))
        peak_index = int(local_indices[peak_local])
        positions.append(float(radial[peak_index]))
        amplitude = max(0.0, float(intensity[peak_index] - background))
        amplitudes.append(amplitude)
        weights = np.maximum(local - background, 0.0)
        if float(np.sum(weights)) > 0:
            centroid = float(np.sum(radial[local_indices] * weights) / np.sum(weights))
            variance = float(
                np.sum(weights * (radial[local_indices] - centroid) ** 2) / np.sum(weights)
            )
            width = 2.354820045 * math.sqrt(max(variance, 0.0))
        else:
            width = float("inf")
        widths.append(width)
    return positions, amplitudes, widths, background


def _cake_coverage(
    integrator: AzimuthalIntegrator,
    frame: np.ndarray,
    expected_peaks: list[float],
    radial_range: tuple[float, float],
) -> float:
    cake = integrator.integrate2d(
        frame,
        npt_rad=256,
        npt_azim=72,
        radial_range=radial_range,
        unit="2th_deg",
        method=("no", "histogram", "cython"),
    )
    radial = np.asarray(cake.radial)
    image = np.asarray(cake.intensity)
    background = float(np.percentile(image, 20))
    coverages: list[float] = []
    for peak in expected_peaks:
        peak_index = int(np.argmin(np.abs(radial - peak)))
        window = image[:, max(0, peak_index - 1) : peak_index + 2]
        sector_signal = np.max(window, axis=1)
        robust_peak = float(np.percentile(sector_signal, 75))
        cutoff = background + 0.2 * max(robust_peak - background, 0.0)
        coverages.append(float(np.mean(sector_signal > cutoff)))
    return float(np.median(coverages)) if coverages else 0.0


def _unexpected_peak_ratio(
    radial: np.ndarray,
    intensity: np.ndarray,
    expected_peaks: list[float],
) -> tuple[float, list[float]]:
    baseline = float(np.percentile(intensity, 20))
    prominence_floor = max(float(np.max(intensity) - baseline) * 0.08, 1.0)
    indices, properties = find_peaks(intensity, prominence=prominence_floor, distance=3)
    prominences = np.asarray(properties.get("prominences", []), dtype=float)
    if not len(indices) or float(np.sum(prominences)) <= 0:
        return 0.0, []
    locations = radial[indices]
    unexpected = np.asarray(
        [
            min(abs(float(location) - expected) for expected in expected_peaks) > 1.2
            for location in locations
        ]
    )
    ratio = float(np.sum(prominences[unexpected]) / np.sum(prominences))
    return ratio, [float(value) for value in locations[unexpected]]


def _reduced_chi2_lower_tail(
    frame: np.ndarray,
    geometry: XRDGeometry,
    variance_scale: float,
) -> tuple[float, float, int]:
    """Test whether azimuthal residuals are implausibly small.

    The mean intensity is fitted independently in narrow radius annuli. Under
    the declared Poisson counting model, the within-annulus Pearson statistic
    is chi-square distributed after subtracting one fitted mean per annulus.
    """

    y, x = np.indices(frame.shape, dtype=float)
    radius_px = np.hypot(y - geometry.center_y_px, x - geometry.center_x_px)
    annulus = np.floor(radius_px * 64.0).astype(int)
    flat_frame = np.asarray(frame, dtype=float).ravel()
    flat_annulus = annulus.ravel()
    counts = np.bincount(flat_annulus)
    sums = np.bincount(flat_annulus, weights=flat_frame)
    means = sums / np.maximum(counts, 1)
    eligible = counts[flat_annulus] >= 4
    expected = means[flat_annulus]
    statistic = float(
        np.sum(
            (flat_frame[eligible] - expected[eligible]) ** 2 / np.maximum(expected[eligible], 1.0)
        )
        / variance_scale
    )
    fitted_annuli = int(np.sum(counts >= 4))
    dof = max(1, int(np.sum(eligible)) - fitted_annuli)
    reduced = statistic / dof
    lower_tail = float(chi2.cdf(statistic, dof))
    return reduced, lower_tail, dof


def verify_calibrant_frame(case: SyntheticFrame) -> VerificationResult:
    prereg = load_preregistration()
    prereg_bytes = (
        Path(__import__("proprio").__file__ or "")
        .parent.joinpath("data/metrology-preregistration.yaml")
        .read_bytes()
    )
    prereg_hash = __import__("hashlib").sha256(prereg_bytes).hexdigest()
    provenance = _provenance(preregistration_sha256=prereg_hash)
    expected = [
        float(value)
        for value in prereg["calibrants"][case.truth.calibrant]["expected_peaks_deg"]
        if case.geometry.radial_range_deg[0] <= float(value) <= case.geometry.radial_range_deg[1]
    ]
    integrator = _integrator(case.geometry)
    result = integrator.integrate1d(
        case.frame,
        case.geometry.radial_bins,
        radial_range=case.geometry.radial_range_deg,
        unit="2th_deg",
        error_model="poisson",
        method=("no", "histogram", "cython"),
    )
    radial = np.asarray(result.radial, dtype=float)
    intensity = np.asarray(result.intensity, dtype=float)
    positions, amplitudes, widths, background = _local_peaks(radial, intensity, expected)
    residuals = np.asarray(positions) - np.asarray(expected)
    finite = np.isfinite(residuals)
    residuals = residuals[finite]
    zero_shift = float(np.median(residuals)) if len(residuals) else float("inf")
    residual_after_shift = residuals - zero_shift if len(residuals) else residuals
    displacement_residual = (
        float(np.max(residual_after_shift) - np.min(residual_after_shift))
        if len(residual_after_shift)
        else float("inf")
    )
    peak_fwhm = float(np.median([width for width in widths if math.isfinite(width)]))
    saturation_fraction = float(np.mean(case.frame >= case.telemetry.detector_max_counts))
    dead_time_fraction = 1.0 - case.telemetry.live_time_s / case.telemetry.real_time_s
    peak_snr_values = [
        amplitude / math.sqrt(max(amplitude + 2.0 * background, 1.0)) for amplitude in amplitudes
    ]
    peak_snr = float(np.median(peak_snr_values))
    cake_coverage = _cake_coverage(
        integrator,
        case.frame,
        expected,
        case.geometry.radial_range_deg,
    )
    unexpected_ratio, unexpected_locations = _unexpected_peak_ratio(radial, intensity, expected)
    reduced_chi2, chi2_lower_tail, dof = _reduced_chi2_lower_tail(
        case.frame,
        case.geometry,
        case.telemetry.reported_variance_scale,
    )

    checks = (
        _check(
            check_id="zero-shift",
            passed=abs(zero_shift) <= _threshold(prereg, "zero_shift_abs_max_deg"),
            summary="constant calibrant peak shift is within the preregistered bound",
            metric_name="absolute_zero_shift",
            metric_value=abs(zero_shift),
            threshold=_threshold(prereg, "zero_shift_abs_max_deg"),
            comparator="le",
            units="degree",
            provenance=provenance,
        ),
        _check(
            check_id="sample-displacement",
            passed=displacement_residual
            <= _threshold(prereg, "sample_displacement_residual_max_deg"),
            summary="angle-dependent peak-residual span is within the preregistered bound",
            metric_name="peak_residual_span_after_constant_shift",
            metric_value=displacement_residual,
            threshold=_threshold(prereg, "sample_displacement_residual_max_deg"),
            comparator="le",
            units="degree",
            provenance=provenance,
        ),
        _check(
            check_id="geometry-calibration",
            passed=peak_fwhm <= _threshold(prereg, "calibrated_peak_fwhm_max_deg"),
            summary="integrated calibrant peak width is within the geometry bound",
            metric_name="median_peak_fwhm",
            metric_value=peak_fwhm,
            threshold=_threshold(prereg, "calibrated_peak_fwhm_max_deg"),
            comparator="le",
            units="degree",
            provenance=provenance,
        ),
        _check(
            check_id="detector-saturation",
            passed=saturation_fraction <= _threshold(prereg, "saturation_fraction_max"),
            summary="clipped detector-pixel fraction is within the bound",
            metric_name="saturation_fraction",
            metric_value=saturation_fraction,
            threshold=_threshold(prereg, "saturation_fraction_max"),
            comparator="le",
            provenance=provenance,
        ),
        _check(
            check_id="detector-dead-time",
            passed=dead_time_fraction <= _threshold(prereg, "dead_time_fraction_max"),
            summary="detector live-time loss is within the bound",
            metric_name="dead_time_fraction",
            metric_value=dead_time_fraction,
            threshold=_threshold(prereg, "dead_time_fraction_max"),
            comparator="le",
            provenance=provenance,
        ),
        _check(
            check_id="counting-statistics",
            passed=peak_snr >= _threshold(prereg, "peak_snr_min"),
            summary="median expected-ring signal-to-noise meets the bound",
            metric_name="median_peak_snr",
            metric_value=peak_snr,
            threshold=_threshold(prereg, "peak_snr_min"),
            comparator="ge",
            provenance=provenance,
        ),
        _check(
            check_id="cake-ring-fidelity",
            passed=cake_coverage >= _threshold(prereg, "cake_coverage_min"),
            summary="expected rings cover enough azimuth sectors",
            metric_name="median_ring_azimuth_coverage",
            metric_value=cake_coverage,
            threshold=_threshold(prereg, "cake_coverage_min"),
            comparator="ge",
            provenance=provenance,
        ),
        _check(
            check_id="calibrant-indexing",
            passed=unexpected_ratio <= _threshold(prereg, "unexpected_peak_ratio_max"),
            summary="unexpected calibrant peak prominence is within the QC-only bound",
            metric_name="unexpected_peak_prominence_ratio",
            metric_value=unexpected_ratio,
            threshold=_threshold(prereg, "unexpected_peak_ratio_max"),
            comparator="le",
            provenance=provenance,
            details={"unexpected_peak_locations_deg": unexpected_locations},
        ),
        _check(
            check_id="chi2-lower-tail",
            passed=chi2_lower_tail >= _threshold(prereg, "reduced_chi2_lower_alpha"),
            summary="fit residual is not implausibly small for the declared uncertainty model",
            metric_name="chi2_lower_tail_probability",
            metric_value=chi2_lower_tail,
            threshold=_threshold(prereg, "reduced_chi2_lower_alpha"),
            comparator="ge",
            provenance=provenance,
            details={"reduced_chi2": reduced_chi2, "degrees_of_freedom": dof},
        ),
    )
    status = (
        StatusLabel.SUCCEEDED
        if all(check.status is StatusLabel.SUCCEEDED for check in checks)
        else StatusLabel.FAILED
    )
    features = {
        "zero_shift_abs_deg": abs(zero_shift),
        "sample_displacement_residual_deg": displacement_residual,
        "median_peak_fwhm_deg": peak_fwhm,
        "saturation_fraction": saturation_fraction,
        "dead_time_fraction": dead_time_fraction,
        "median_peak_snr": peak_snr,
        "cake_coverage": cake_coverage,
        "unexpected_peak_ratio": unexpected_ratio,
        "reduced_chi2": reduced_chi2,
        "chi2_lower_tail_probability": chi2_lower_tail,
    }
    return VerificationResult(
        record=ValidityRecord(
            status=status,
            measurement_kind="calibrant_qc",
            checks=checks,
        ),
        features=features,
    )
