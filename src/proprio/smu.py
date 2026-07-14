"""Keithley-2450-style transport simulator and independent circuit fixture."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import pyvisa

RESOURCE_NAME = "USB0::0x05E6::0x2450::04500001::0::INSTR"


@dataclass(frozen=True)
class OhmicFixture:
    resistance_ohm: float = 1000.0
    target_voltage_v: float = 1.0
    minimum_compliance_a: float = 0.0011
    maximum_safe_compliance_a: float = 0.01
    minimum_measurement_range_a: float = 0.0011
    maximum_measurement_range_a: float = 0.1
    relative_current_tolerance: float = 0.01

    @property
    def expected_current_a(self) -> float:
        return self.target_voltage_v / self.resistance_ohm


class SimulatedSMUController:
    """Narrow control surface backed by pyvisa-sim and a command trace."""

    def __init__(self, fixture: OhmicFixture | None = None) -> None:
        self.fixture = fixture or OhmicFixture()
        definition = files("proprio").joinpath("data/keithley-2450-sim.yaml")
        self.resource_manager = pyvisa.ResourceManager(f"{definition}@sim")
        self.instrument = self.resource_manager.open_resource(RESOURCE_NAME)
        self.instrument.write_termination = "\n"
        self.instrument.read_termination = "\n"
        self.trace: list[dict[str, Any]] = []
        self.voltage_v: float | None = None
        self.current_limit_a: float | None = None
        self.measurement_range_a: float | None = None
        self.output_enabled = False
        self.measurement_a: float | None = None
        self.closed = False

    def _append(self, operation: str, value: Any = None, response: Any = None) -> None:
        self.trace.append(
            {
                "sequence": len(self.trace),
                "operation": operation,
                "value": value,
                "response": response,
            }
        )

    def identify(self) -> str:
        response = str(self.instrument.query("*IDN?")).strip()
        self._append("identify", response=response)
        return response

    def reset(self) -> None:
        self.instrument.write("*RST")
        self._append("reset")

    def set_current_limit(self, amperes: float) -> None:
        self.instrument.write(f":SENS:CURR:PROT {float(amperes):.6f}")
        self.current_limit_a = float(amperes)
        self._append("set_current_limit", value=self.current_limit_a)

    def set_measurement_range(self, amperes: float) -> None:
        self.instrument.write(f":SENS:CURR:RANG {float(amperes):.6f}")
        self.measurement_range_a = float(amperes)
        self._append("set_measurement_range", value=self.measurement_range_a)

    def set_voltage(self, volts: float) -> None:
        self.instrument.write(f":SOUR:VOLT {float(volts):.6f}")
        self.voltage_v = float(volts)
        self._append("set_voltage", value=self.voltage_v)

    def enable_output(self) -> None:
        self.instrument.write(":OUTP 1")
        self.output_enabled = True
        self._append("enable_output")

    def measure_current(self) -> float:
        response = float(self.instrument.query(":MEAS:CURR?").strip())
        self.measurement_a = response
        self._append("measure_current", response=response)
        return response

    def disable_output(self) -> None:
        self.instrument.write(":OUTP 0")
        self.output_enabled = False
        self._append("disable_output")

    def error(self) -> str:
        response = str(self.instrument.query(":SYST:ERR?")).strip()
        self._append("error_query", response=response)
        return response

    def telemetry(self) -> dict[str, Any]:
        """Return the simulator state and independently configured fixture limits."""

        return {
            "voltage_v": self.voltage_v,
            "current_limit_a": self.current_limit_a,
            "measurement_range_a": self.measurement_range_a,
            "output_enabled": self.output_enabled,
            "measurement_a": self.measurement_a,
            "fixture": {
                "resistance_ohm": self.fixture.resistance_ohm,
                "target_voltage_v": self.fixture.target_voltage_v,
                "minimum_compliance_a": self.fixture.minimum_compliance_a,
                "maximum_safe_compliance_a": self.fixture.maximum_safe_compliance_a,
                "minimum_measurement_range_a": self.fixture.minimum_measurement_range_a,
                "maximum_measurement_range_a": self.fixture.maximum_measurement_range_a,
                "relative_current_tolerance": self.fixture.relative_current_tolerance,
                "expected_current_a": self.fixture.expected_current_a,
            },
        }

    def close(self) -> None:
        if self.closed:
            return
        self.instrument.close()
        self.resource_manager.close()
        self.closed = True

    def __enter__(self) -> SimulatedSMUController:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
