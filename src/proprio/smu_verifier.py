"""Independent circuit and lifecycle checks for the Keithley simulator."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from proprio.instrument_types import GateCheck


def _check(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def verify_keithley(
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    """Verify ordering, operating envelope, Ohm's law, and safe shutdown."""

    fixture = telemetry["fixture"]
    operations = [str(row["operation"]) for row in trace]
    output_index = operations.index("enable_output") if "enable_output" in operations else -1
    limit_index = operations.index("set_current_limit") if "set_current_limit" in operations else -1
    range_index = (
        operations.index("set_measurement_range") if "set_measurement_range" in operations else -1
    )
    measured = telemetry["measurement_a"]
    expected = float(fixture["expected_current_a"])
    relative_error = (
        abs(float(measured) - expected) / expected if measured is not None else float("inf")
    )
    voltage = telemetry["voltage_v"]
    compliance = telemetry["current_limit_a"]
    measurement_range = telemetry["measurement_range_a"]
    return (
        _check(
            "compliance-before-output",
            0 <= limit_index < output_index,
            limit_index=limit_index,
            output_index=output_index,
        ),
        _check(
            "range-before-output",
            0 <= range_index < output_index,
            range_index=range_index,
            output_index=output_index,
        ),
        _check(
            "voltage-contract",
            voltage is not None
            and abs(float(voltage) - float(fixture["target_voltage_v"])) <= 1e-9,
            observed_v=voltage,
            required_v=fixture["target_voltage_v"],
        ),
        _check(
            "compliance-contract",
            compliance is not None
            and float(fixture["minimum_compliance_a"])
            <= float(compliance)
            <= float(fixture["maximum_safe_compliance_a"]),
            observed_a=compliance,
            minimum_a=fixture["minimum_compliance_a"],
            maximum_a=fixture["maximum_safe_compliance_a"],
        ),
        _check(
            "range-contract",
            measurement_range is not None
            and float(fixture["minimum_measurement_range_a"])
            <= float(measurement_range)
            <= float(fixture["maximum_measurement_range_a"]),
            observed_a=measurement_range,
            minimum_a=fixture["minimum_measurement_range_a"],
            maximum_a=fixture["maximum_measurement_range_a"],
        ),
        _check(
            "ohms-law",
            relative_error <= float(fixture["relative_current_tolerance"]),
            measured_current_a=measured,
            expected_current_a=expected,
            relative_error=relative_error,
            tolerance=fixture["relative_current_tolerance"],
        ),
        _check(
            "output-disabled-at-return",
            not bool(telemetry["output_enabled"]),
            output_enabled=telemetry["output_enabled"],
        ),
    )
