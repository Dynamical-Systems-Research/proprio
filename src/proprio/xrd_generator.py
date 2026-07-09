"""Independent analytic forward model for synthetic calibrant detector frames.

This module deliberately does not import pyFAI or verifier code. Ring locations
are generated from lattice parameters and Bragg's law, while the verifier reads
the separately preregistered expected-peak table and integrates with pyFAI.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from proprio.xrd_types import (
    FrameTelemetry,
    SyntheticFrame,
    SyntheticTruth,
    ValidityFault,
    XRDGeometry,
    geometry_from_preregistration,
    load_preregistration,
)


def _allowed_lattice_n(calibrant: str, limit: int = 12) -> list[int]:
    if calibrant == "lab6":
        return list(range(1, limit + 1))
    if calibrant == "si":
        allowed: set[int] = set()
        for h in range(0, 9):
            for k in range(0, 9):
                for ell in range(0, 9):
                    if h == k == ell == 0:
                        continue
                    parity = {h % 2, k % 2, ell % 2}
                    if len(parity) != 1:
                        continue
                    if h % 2 == 0 and (h + k + ell) % 4 != 0:
                        continue
                    allowed.add(h * h + k * k + ell * ell)
        return sorted(n for n in allowed if n <= 32)
    raise ValueError(f"unsupported calibrant: {calibrant}")


def _bragg_peak_positions_deg(
    *, calibrant: str, lattice_a_angstrom: float, wavelength_m: float
) -> list[float]:
    wavelength_angstrom = wavelength_m * 1e10
    peaks: list[float] = []
    for n in _allowed_lattice_n(calibrant):
        d_angstrom = lattice_a_angstrom / math.sqrt(n)
        argument = wavelength_angstrom / (2.0 * d_angstrom)
        if argument >= 1.0:
            continue
        peaks.append(2.0 * math.degrees(math.asin(argument)))
    return peaks


def _case_id(calibrant: str, fault: ValidityFault, seed: int) -> str:
    payload = f"{calibrant}:{fault.value}:{seed}".encode()
    return f"xrd_{hashlib.sha256(payload).hexdigest()[:20]}"


def generate_calibrant_frame(
    *,
    calibrant: str = "lab6",
    fault: ValidityFault = ValidityFault.VALID,
    seed: int = 0,
    geometry: XRDGeometry | None = None,
) -> SyntheticFrame:
    """Generate one labeled raw detector frame from analytic ground truth."""

    prereg = load_preregistration()
    geometry = geometry or geometry_from_preregistration(prereg)
    calibrant_config = prereg["calibrants"][calibrant]
    generator_config = prereg["generator"]
    rng = np.random.default_rng(seed)

    actual_center_y = geometry.center_y_px
    actual_center_x = geometry.center_x_px
    actual_distance_m = geometry.distance_m
    zero_shift_deg = 0.0
    intensity_scale = 1.0
    saturation_multiplier = 1.0
    dead_time_fraction = 0.0
    missing_sector_deg = 0.0
    unexpected_peak_deg: float | None = None
    reported_variance_scale = 1.0
    injected: dict[str, float] = {}

    if fault is ValidityFault.GEOMETRY_MISCALIBRATION:
        low, high = prereg["faults"][fault.value]["center_offset_px"]
        offset = float(rng.uniform(low, high))
        actual_center_y += offset
        actual_center_x -= 0.7 * offset
        injected["center_offset_px"] = offset
    elif fault is ValidityFault.ZERO_SHIFT:
        low, high = prereg["faults"][fault.value]["shift_deg"]
        zero_shift_deg = float(rng.uniform(low, high))
        injected["zero_shift_deg"] = zero_shift_deg
    elif fault is ValidityFault.SAMPLE_DISPLACEMENT:
        low, high = prereg["faults"][fault.value]["distance_fraction"]
        fraction = float(rng.uniform(low, high))
        actual_distance_m *= 1.0 + fraction
        injected["distance_fraction"] = fraction
    elif fault is ValidityFault.SATURATION:
        low, high = prereg["faults"][fault.value]["intensity_multiplier"]
        saturation_multiplier = float(rng.uniform(low, high))
        injected["intensity_multiplier"] = saturation_multiplier
    elif fault is ValidityFault.DEAD_TIME:
        low, high = prereg["faults"][fault.value]["fraction"]
        dead_time_fraction = float(rng.uniform(low, high))
        injected["dead_time_fraction"] = dead_time_fraction
    elif fault is ValidityFault.INSUFFICIENT_COUNTS:
        low, high = prereg["faults"][fault.value]["intensity_scale"]
        intensity_scale = float(rng.uniform(low, high))
        injected["intensity_scale"] = intensity_scale
    elif fault is ValidityFault.CAKE_INTEGRATION_FAILURE:
        low, high = prereg["faults"][fault.value]["missing_sector_deg"]
        missing_sector_deg = float(rng.uniform(low, high))
        injected["missing_sector_deg"] = missing_sector_deg
    elif fault is ValidityFault.UNINDEXED_PEAK:
        low, high = prereg["faults"][fault.value]["peak_deg"]
        unexpected_peak_deg = float(rng.uniform(low, high))
        injected["unexpected_peak_deg"] = unexpected_peak_deg
    elif fault is ValidityFault.CHI2_LOWER_TAIL:
        low, high = prereg["faults"][fault.value]["reported_variance_scale"]
        reported_variance_scale = float(rng.uniform(low, high))
        injected["reported_variance_scale"] = reported_variance_scale

    y, x = np.indices(geometry.shape, dtype=np.float64)
    dy_m = (y - actual_center_y) * geometry.pixel_size_m
    dx_m = (x - actual_center_x) * geometry.pixel_size_m
    radius_m = np.sqrt(dx_m * dx_m + dy_m * dy_m)
    two_theta_deg = np.degrees(np.arctan2(radius_m, actual_distance_m))
    azimuth_deg = np.degrees(np.arctan2(dy_m, dx_m))

    lattice_a = float(calibrant_config["lattice_a_angstrom"])
    peaks = _bragg_peak_positions_deg(
        calibrant=calibrant,
        lattice_a_angstrom=lattice_a,
        wavelength_m=geometry.wavelength_m,
    )
    radial_min, radial_max = geometry.radial_range_deg
    peaks = [peak + zero_shift_deg for peak in peaks if radial_min <= peak <= radial_max]
    if unexpected_peak_deg is not None:
        peaks.append(unexpected_peak_deg)

    background = float(generator_config["background_counts"])
    primary_counts = float(generator_config["primary_peak_counts"])
    sigma_deg = float(generator_config["peak_fwhm_deg"]) / 2.354820045
    expected = np.full(geometry.shape, background, dtype=np.float64)
    for index, peak in enumerate(peaks):
        weight = 1.0 / (1.0 + 0.35 * index)
        if unexpected_peak_deg is not None and math.isclose(peak, unexpected_peak_deg):
            weight = 0.9
        expected += (
            primary_counts * weight * np.exp(-0.5 * ((two_theta_deg - peak) / sigma_deg) ** 2)
        )

    expected *= intensity_scale * saturation_multiplier
    if dead_time_fraction > 0:
        expected /= 1.0 + expected * dead_time_fraction / max(primary_counts, 1.0)
    frame = rng.poisson(np.maximum(expected, 0.0)).astype(np.float64)

    if missing_sector_deg > 0:
        sector = np.abs(((azimuth_deg + 180.0) % 360.0) - 180.0) <= missing_sector_deg / 2.0
        replacement = rng.poisson(background * max(intensity_scale, 0.01), size=frame.shape)
        frame[sector] = replacement[sector]
    if fault is ValidityFault.SATURATION:
        frame = np.minimum(frame, geometry.detector_max_counts)

    telemetry = FrameTelemetry(
        exposure_s=geometry.exposure_s,
        real_time_s=geometry.exposure_s,
        live_time_s=geometry.exposure_s * (1.0 - dead_time_fraction),
        detector_max_counts=geometry.detector_max_counts,
        reported_variance_scale=reported_variance_scale,
    )
    truth = SyntheticTruth(
        case_id=_case_id(calibrant, fault, seed),
        calibrant=calibrant,
        fault_class=fault,
        expected_valid=fault is ValidityFault.VALID,
        seed=seed,
        injected_parameters=injected,
    )
    return SyntheticFrame(frame=frame, geometry=geometry, telemetry=telemetry, truth=truth)
