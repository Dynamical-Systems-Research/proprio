"""Independent physical postconditions for the confirmatory instrument panel."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from proprio.instrument_types import GateCheck


def _check(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def _operations(trace: Sequence[dict[str, Any]]) -> list[str]:
    return [str(row["operation"]) for row in trace]


def _verify_optical(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    readings = list(telemetry["readings"])
    operations = _operations(trace)
    cleanup = not telemetry["plate_loaded"] and not telemetry["active"]
    if instrument_id == "absorbance-plate-read":
        blank = next((row for row in readings if row["kind"] == "blank"), None)
        sample = next((row for row in readings if row["kind"] == "sample"), None)
        net = (
            float(sample["absorbance_au"]) - float(blank["absorbance_au"])
            if blank and sample
            else 0.0
        )
        integrations = [float(row["integration_ms"]) for row in readings]
        wavelengths = [float(row["wavelength_nm"]) for row in readings]
        return (
            _check(
                "blank-sample-pair",
                len(readings) == 2 and [row["kind"] for row in readings] == ["blank", "sample"],
                readings=readings,
            ),
            _check(
                "wavelength",
                wavelengths == [600.0, 600.0],
                observed_nm=wavelengths,
                target_nm=600.0,
            ),
            _check(
                "integration-support",
                bool(integrations)
                and all(
                    value <= float(telemetry["reported_max_integration_ms"])
                    for value in integrations
                ),
                observed_ms=integrations,
                maximum_ms=telemetry["reported_max_integration_ms"],
            ),
            _check(
                "blank-level",
                bool(blank) and float(blank["absorbance_au"]) <= 0.05,
                blank_au=None if blank is None else blank["absorbance_au"],
            ),
            _check(
                "beer-lambert-reference",
                0.75 <= net <= 0.85,
                net_absorbance_au=net,
                expected_band_au=[0.75, 0.85],
            ),
            _check("detector-unsaturated", not telemetry["saturated"], readings=readings),
            _check(
                "plate-lifecycle",
                cleanup and not telemetry["violations"],
                operations=operations,
                violations=telemetry["violations"],
            ),
        )

    blank = next((row for row in readings if row["kind"] == "blank"), None)
    sample = next((row for row in readings if row["kind"] == "sample"), None)
    normalized_signal = (
        float(sample["gain_normalized_counts"]) - float(blank["gain_normalized_counts"])
        if blank and sample
        else 0.0
    )
    gains = [float(row["gain"]) for row in readings]
    wavelength_pairs = [
        [float(row["excitation_nm"]), float(row["emission_nm"])] for row in readings
    ]
    return (
        _check(
            "blank-sample-pair",
            len(readings) == 2 and [row["kind"] for row in readings] == ["blank", "sample"],
            readings=readings,
        ),
        _check(
            "wavelength-pair",
            wavelength_pairs == [[485.0, 520.0], [485.0, 520.0]],
            observed_nm=wavelength_pairs,
        ),
        _check(
            "stokes-order",
            bool(wavelength_pairs)
            and all(excitation < emission for excitation, emission in wavelength_pairs),
            observed_nm=wavelength_pairs,
        ),
        _check(
            "gain-support",
            bool(gains) and all(value <= float(telemetry["reported_max_gain"]) for value in gains),
            observed_gain=gains,
            maximum_gain=telemetry["reported_max_gain"],
        ),
        _check(
            "fluorescence-reference",
            900.0 <= normalized_signal <= 1600.0,
            gain_normalized_blank_subtracted_counts=normalized_signal,
            expected_band=[900.0, 1600.0],
        ),
        _check("detector-unsaturated", not telemetry["saturated"], readings=readings),
        _check(
            "plate-lifecycle",
            cleanup and not telemetry["violations"],
            operations=operations,
            violations=telemetry["violations"],
        ),
    )


def _verify_delivery(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    operations = _operations(trace)
    speed_rows = [
        row for row in trace if row["operation"] in {"prime", "prime_channel", "pump_volume"}
    ]
    speeds = [float(row["speed_rpm"]) for row in speed_rows]
    support = bool(speeds) and all(
        speed <= float(telemetry["reported_max_speed_rpm"]) for speed in speeds
    )
    if instrument_id == "calibrated-pump-dose":
        return (
            _check(
                "certified-calibration",
                telemetry["calibration_ml_per_revolution"] == 0.05,
                observed=telemetry["calibration_ml_per_revolution"],
                certified=0.05,
            ),
            _check(
                "speed-support",
                support,
                observed_rpm=speeds,
                maximum_rpm=telemetry["reported_max_speed_rpm"],
            ),
            _check(
                "target-volume",
                abs(float(telemetry["delivered_ml"]) - 10.0) <= 0.10,
                observed_ml=telemetry["delivered_ml"],
                target_ml=10.0,
            ),
            _check("halted", telemetry["running"] is False, operations=operations),
            _check(
                "controller-violations",
                not telemetry["violations"],
                violations=telemetry["violations"],
            ),
        )

    calibrations = telemetry["calibrations_ml_per_revolution"]
    delivered = telemetry["delivered_ml"]
    total = float(delivered["A"]) + float(delivered["B"])
    fraction_a = float(delivered["A"]) / total if total else 0.0
    return (
        _check(
            "certified-calibrations",
            calibrations == {"A": 0.04, "B": 0.05},
            observed=calibrations,
            certified={"A": 0.04, "B": 0.05},
        ),
        _check(
            "speed-support",
            support,
            observed_rpm=speeds,
            maximum_rpm=telemetry["reported_max_speed_rpm"],
        ),
        _check(
            "total-volume",
            abs(total - 10.0) <= 0.10,
            observed_ml=total,
            target_ml=10.0,
        ),
        _check(
            "blend-ratio",
            abs(fraction_a - 0.60) <= 0.01,
            observed_fraction_a=fraction_a,
            target_fraction_a=0.60,
        ),
        _check(
            "halted",
            all(value is False for value in telemetry["running"].values()),
            operations=operations,
        ),
        _check(
            "controller-violations",
            not telemetry["violations"],
            violations=telemetry["violations"],
        ),
    )


def _verify_thermal(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    waits = telemetry["waits"]
    holds = telemetry["holds"]
    setpoints = telemetry["setpoints_c"]
    expected_setpoints = [80.0] if instrument_id == "isothermal-hold" else [60.0, 20.0]
    expected_holds = [600.0] if instrument_id == "isothermal-hold" else [300.0, 120.0]
    peak_limit = 85.0 if instrument_id == "isothermal-hold" else 65.0
    return (
        _check(
            "setpoint-sequence",
            setpoints == expected_setpoints,
            observed_c=setpoints,
            expected_c=expected_setpoints,
        ),
        _check(
            "transition-count",
            len(waits) == len(expected_setpoints),
            waits=waits,
        ),
        _check(
            "settled-before-hold",
            len(waits) == len(expected_setpoints)
            and all(bool(row["reached"]) for row in waits)
            and all(float(row["tolerance_c"]) <= 0.5 for row in waits),
            waits=waits,
        ),
        _check(
            "hold-durations",
            [float(row["seconds"]) for row in holds] == expected_holds
            and all(bool(row["settled"]) for row in holds),
            observed_s=[row["seconds"] for row in holds],
            expected_s=expected_holds,
        ),
        _check(
            "thermal-envelope",
            float(telemetry["peak_c"]) <= peak_limit,
            observed_peak_c=telemetry["peak_c"],
            maximum_c=peak_limit,
        ),
        _check("deactivated", telemetry["active"] is False, operations=_operations(trace)),
        _check(
            "controller-violations",
            not telemetry["violations"],
            violations=telemetry["violations"],
        ),
    )


def verify_confirmatory_instrument(
    instrument_id: str,
    family: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    if family == "optical_measurement":
        return _verify_optical(instrument_id, trace, telemetry)
    if family == "calibrated_delivery":
        return _verify_delivery(instrument_id, trace, telemetry)
    if family == "thermal_control":
        return _verify_thermal(instrument_id, trace, telemetry)
    raise KeyError(family)
