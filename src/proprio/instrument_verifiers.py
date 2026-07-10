"""Independent physical postconditions over exported simulator telemetry."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from proprio.instrument_types import GateCheck


def _check(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def _operation_names(trace: Sequence[dict[str, Any]]) -> list[str]:
    return [str(row["operation"]) for row in trace]


def _verify_liquid(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    operations = _operation_names(trace)
    aspirate_name = "aspirate" if instrument_id == "ot2-transfer" else "aspirate_channel"
    volumes = [float(row["volume_ul"]) for row in trace if row["operation"] == aspirate_name]
    destination = float(telemetry["destination_ul"])
    source_loss = 1000.0 - float(telemetry["source_ul"])
    residual = abs(source_loss - destination)
    closed = not bool(telemetry.get("tip_attached", telemetry.get("channel_ready", False)))
    return (
        _check(
            "target-volume",
            abs(destination - 120.0) <= 0.5,
            observed_ul=destination,
            target_ul=120.0,
        ),
        _check("mass-balance", residual <= 1e-9, residual_ul=residual),
        _check(
            "stroke-capacity",
            all(volume <= float(telemetry["reported_max_transfer_ul"]) for volume in volumes),
            observed_strokes_ul=volumes,
            reported_max_transfer_ul=telemetry["reported_max_transfer_ul"],
        ),
        _check(
            "controller-violations", not telemetry["violations"], violations=telemetry["violations"]
        ),
        _check("tip-or-channel-closed", closed, operations=operations),
    )


def _verify_battery(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    if instrument_id == "constant-current-cycle":
        capacity = float(telemetry["delivered_capacity_ah"])
        current = abs(float(telemetry["current_a"] or 0.0))
        return (
            _check(
                "voltage-window",
                telemetry["voltage_min_v"] == 2.8 and telemetry["voltage_max_v"] == 4.2,
                observed=[telemetry["voltage_min_v"], telemetry["voltage_max_v"]],
            ),
            _check(
                "current-support",
                current <= float(telemetry["reported_current_limit_a"]),
                observed_a=current,
                maximum_a=telemetry["reported_current_limit_a"],
            ),
            _check(
                "coulomb-count", abs(capacity - 0.5) <= 0.025, observed_ah=capacity, target_ah=0.5
            ),
            _check(
                "temperature",
                float(telemetry["temperature_c"]) <= 40.0,
                observed_c=telemetry["temperature_c"],
                maximum_c=40.0,
            ),
            _check("stopped", telemetry["running"] is False, operations=_operation_names(trace)),
        )
    pulses = telemetry["pulses"]
    current_supported = all(
        abs(float(item["current_a"])) <= float(telemetry["reported_current_limit_a"])
        for item in pulses
    )
    resistances = [
        abs(float(item["delta_v"]) / float(item["current_a"]))
        for item in pulses
        if float(item["current_a"]) != 0.0
    ]
    return (
        _check(
            "voltage-window",
            telemetry["minimum_v"] == 2.8 and telemetry["maximum_v"] == 4.2,
            observed=[telemetry["minimum_v"], telemetry["maximum_v"]],
        ),
        _check("pulse-present", len(pulses) == 1, pulse_count=len(pulses)),
        _check(
            "current-support",
            current_supported,
            maximum_a=telemetry["reported_current_limit_a"],
            pulses=pulses,
        ),
        _check(
            "resistance-positive",
            bool(resistances) and all(0.05 <= value <= 0.12 for value in resistances),
            estimated_ohm=resistances,
        ),
        _check(
            "relaxation",
            float(telemetry["rest_s"]) >= 30.0,
            observed_s=telemetry["rest_s"],
            minimum_s=30.0,
        ),
        _check("stopped", telemetry["running"] is False, operations=_operation_names(trace)),
    )


def _verify_additive(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    if instrument_id == "powder-bed-scan":
        bed_geometry = telemetry["bed_geometry"] or (0.0, 0.0)
        laser = telemetry["laser"] or (0.0, 0.0)
        hatch, depth = map(float, bed_geometry)
        power, speed = map(float, laser)
        energy = float(telemetry["absorptivity_factor"]) * power / max(speed * hatch * depth, 1e-9)
        return (
            _check(
                "energy-density",
                45.0 <= energy <= 75.0,
                observed_j_mm3=energy,
                minimum_j_mm3=45.0,
                maximum_j_mm3=75.0,
            ),
            _check(
                "shielding",
                float(telemetry["gas_flow_l_min"]) >= 15.0,
                observed_l_min=telemetry["gas_flow_l_min"],
                minimum_l_min=15.0,
            ),
            _check(
                "thermal-envelope",
                float(telemetry["peak_temperature_c"]) <= 1500.0,
                observed_c=telemetry["peak_temperature_c"],
                maximum_c=1500.0,
            ),
            _check(
                "scan-complete",
                float(telemetry["scan_length_mm"]) == 20.0,
                observed_mm=telemetry["scan_length_mm"],
                target_mm=20.0,
            ),
            _check("stopped", telemetry["active"] is False, operations=_operation_names(trace)),
        )
    speed = float(telemetry["travel_mm_s"] or 0.0)
    line_energy = (
        float(telemetry["coupling_factor"]) * float(telemetry["power_w"] or 0.0) / max(speed, 1e-9)
    )
    mass_per_length = float(telemetry["mass_per_length_g_mm"])
    return (
        _check(
            "line-energy",
            18.0 <= line_energy <= 32.0,
            observed_j_mm=line_energy,
            minimum_j_mm=18.0,
            maximum_j_mm=32.0,
        ),
        _check(
            "mass-per-length",
            0.010 <= mass_per_length <= 0.025,
            observed_g_mm=mass_per_length,
            minimum_g_mm=0.010,
            maximum_g_mm=0.025,
        ),
        _check(
            "shielding",
            float(telemetry["gas_flow_l_min"]) >= 18.0,
            observed_l_min=telemetry["gas_flow_l_min"],
            minimum_l_min=18.0,
        ),
        _check(
            "thermal-envelope",
            float(telemetry["peak_temperature_c"]) <= 1600.0,
            observed_c=telemetry["peak_temperature_c"],
            maximum_c=1600.0,
        ),
        _check(
            "deposit-complete",
            float(telemetry["length_mm"]) == 25.0,
            observed_mm=telemetry["length_mm"],
            target_mm=25.0,
        ),
        _check("stopped", telemetry["active"] is False, operations=_operation_names(trace)),
    )


def _verify_quantum(
    instrument_id: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    current = abs(float(telemetry["current_a"] or 0.0))
    if instrument_id == "hall-sweep":
        points = telemetry["points"]
        fields = np.asarray([row["field_t"] for row in points], dtype=float)
        voltages = np.asarray([row["voltage_v"] for row in points], dtype=float)
        odd = (voltages - voltages[::-1]) / 2.0 if len(voltages) else np.asarray([])
        hall_signal = float(np.max(np.abs(odd))) if len(odd) else 0.0
        settle = min((float(row["settle_s"]) for row in points), default=0.0)
        return (
            _check(
                "temperature",
                telemetry["temperature_k"] == 10.0
                and float(telemetry["temperature_tolerance_k"] or 1.0) <= 0.05,
                observed_k=telemetry["temperature_k"],
                tolerance_k=telemetry["temperature_tolerance_k"],
            ),
            _check("current-heating", current <= 1e-3, observed_a=current, maximum_a=1e-3),
            _check(
                "field-coverage",
                len(fields) >= 9
                and float(fields.min(initial=0.0)) <= -1.0
                and float(fields.max(initial=0.0)) >= 1.0,
                points=len(fields),
            ),
            _check(
                "settling",
                settle >= float(telemetry["reported_required_settle_s"]),
                observed_s=settle,
                required_s=telemetry["reported_required_settle_s"],
            ),
            _check("hall-antisymmetry", hall_signal >= 1e-5, odd_signal_v=hall_signal),
            _check(
                "current-disabled",
                telemetry["current_enabled"] is False,
                operations=_operation_names(trace),
            ),
        )
    voltage = telemetry["voltage_v"]
    resistance = (
        abs(float(voltage) / float(telemetry["current_a"]))
        if voltage is not None and telemetry["current_a"]
        else 0.0
    )
    return (
        _check(
            "temperature",
            telemetry["temperature_k"] == 4.2
            and float(telemetry["temperature_tolerance_k"] or 1.0) <= 0.02,
            observed_k=telemetry["temperature_k"],
            tolerance_k=telemetry["temperature_tolerance_k"],
        ),
        _check(
            "current-heating",
            current <= float(telemetry["reported_current_limit_a"]),
            observed_a=current,
            maximum_a=telemetry["reported_current_limit_a"],
        ),
        _check(
            "resistance-positive",
            100.0 <= resistance <= 140.0,
            observed_ohm=resistance,
            expected_band_ohm=[100.0, 140.0],
        ),
        _check("four-wire-measured", voltage is not None, voltage_v=voltage),
        _check(
            "current-disabled",
            telemetry["current_enabled"] is False,
            operations=_operation_names(trace),
        ),
    )


def verify_instrument(
    instrument_id: str,
    family: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    if family == "liquid_handling":
        return _verify_liquid(instrument_id, trace, telemetry)
    if family == "battery_cycling":
        return _verify_battery(instrument_id, trace, telemetry)
    if family == "additive_manufacturing":
        return _verify_additive(instrument_id, trace, telemetry)
    if family == "quantum_transport":
        return _verify_quantum(instrument_id, trace, telemetry)
    raise KeyError(family)
