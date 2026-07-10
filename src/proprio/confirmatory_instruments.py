"""Reduced-order simulators reserved for the frozen confirmatory panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from proprio.instrument_types import SimulationScenario


class ConfirmatoryController:
    family: str
    instrument_id: str

    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.trace: list[dict[str, Any]] = []
        self.unavailable = scenario is SimulationScenario.UNAVAILABLE

    def _require_available(self) -> None:
        if self.unavailable:
            raise RuntimeError("instrument unavailable: simulated controller link is down")

    def _log(self, operation: str, **values: Any) -> None:
        self.trace.append({"sequence": len(self.trace), "operation": operation, **values})

    def telemetry(self) -> dict[str, Any]:
        raise NotImplementedError


class _PlateReaderController(ConfirmatoryController):
    family = "optical_measurement"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.tray_open = False
        self.plate_loaded = False
        self.active = True
        self.saturated = False
        self.violations: list[str] = []
        self.readings: list[dict[str, Any]] = []

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def open_tray(self) -> None:
        self._require_available()
        self.tray_open = True
        self._log("open_tray")

    def load_plate(self) -> None:
        self._require_available()
        if not self.tray_open:
            self.violations.append("load_with_tray_closed")
        self.plate_loaded = True
        self._log("load_plate")

    def close_tray(self) -> None:
        self._require_available()
        self.tray_open = False
        self._log("close_tray")

    def _check_read_ready(self) -> None:
        if not self.plate_loaded:
            self.violations.append("read_without_plate")
        if self.tray_open:
            self.violations.append("read_with_tray_open")

    def unload_plate(self) -> None:
        self._require_available()
        if not self.tray_open:
            self.violations.append("unload_with_tray_closed")
        self.plate_loaded = False
        self._log("unload_plate")

    def shutdown(self) -> None:
        self._require_available()
        if self.plate_loaded:
            self.violations.append("plate_left_loaded")
        self.active = False
        self._log("shutdown")

    def _base_telemetry(self) -> dict[str, Any]:
        return {
            "tray_open": self.tray_open,
            "plate_loaded": self.plate_loaded,
            "active": self.active,
            "saturated": self.saturated,
            "violations": list(self.violations),
            "readings": list(self.readings),
        }


class AbsorbancePlateController(_PlateReaderController):
    instrument_id = "absorbance-plate-read"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_integration_ms = {
            SimulationScenario.NOMINAL: 200.0,
            SimulationScenario.REPAIR: 100.0,
            SimulationScenario.DRIFT: 80.0,
            SimulationScenario.UNAVAILABLE: 200.0,
        }[scenario]

    def _read(self, kind: str, wavelength_nm: float, integration_ms: float) -> float:
        self._require_available()
        self._check_read_ready()
        integration = float(integration_ms)
        saturated = integration > self.max_integration_ms
        self.saturated = self.saturated or saturated
        if saturated:
            value = 2.5
        else:
            value = 0.02 if kind == "blank" else 0.82
        row = {
            "kind": kind,
            "wavelength_nm": float(wavelength_nm),
            "integration_ms": integration,
            "absorbance_au": value,
            "saturated": saturated,
        }
        self.readings.append(row)
        self._log(f"read_{kind}", **row)
        return value

    def read_blank(self, wavelength_nm: float, integration_ms: float) -> float:
        return self._read("blank", wavelength_nm, integration_ms)

    def read_absorbance(self, wavelength_nm: float, integration_ms: float) -> float:
        return self._read("sample", wavelength_nm, integration_ms)

    def telemetry(self) -> dict[str, Any]:
        return {
            **self._base_telemetry(),
            "reported_max_integration_ms": self.max_integration_ms,
        }


class FluorescencePlateController(_PlateReaderController):
    instrument_id = "fluorescence-plate-read"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_gain = {
            SimulationScenario.NOMINAL: 12.0,
            SimulationScenario.REPAIR: 7.0,
            SimulationScenario.DRIFT: 5.0,
            SimulationScenario.UNAVAILABLE: 12.0,
        }[scenario]

    def _read(self, kind: str, excitation_nm: float, emission_nm: float, gain: float) -> float:
        self._require_available()
        self._check_read_ready()
        gain_value = float(gain)
        saturated = gain_value > self.max_gain
        self.saturated = self.saturated or saturated
        base = 20.0 if kind == "blank" else 1220.0
        counts = 4095.0 if saturated else base * gain_value / 10.0
        row = {
            "kind": kind,
            "excitation_nm": float(excitation_nm),
            "emission_nm": float(emission_nm),
            "gain": gain_value,
            "counts": counts,
            "gain_normalized_counts": counts * 10.0 / max(gain_value, 1e-9),
            "saturated": saturated,
        }
        self.readings.append(row)
        self._log(f"read_fluorescence_{kind}", **row)
        return counts

    def read_fluorescence_blank(
        self, excitation_nm: float, emission_nm: float, gain: float
    ) -> float:
        return self._read("blank", excitation_nm, emission_nm, gain)

    def read_fluorescence(self, excitation_nm: float, emission_nm: float, gain: float) -> float:
        return self._read("sample", excitation_nm, emission_nm, gain)

    def telemetry(self) -> dict[str, Any]:
        return {**self._base_telemetry(), "reported_max_gain": self.max_gain}


class CalibratedPumpController(ConfirmatoryController):
    family = "calibrated_delivery"
    instrument_id = "calibrated-pump-dose"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_speed_rpm = {
            SimulationScenario.NOMINAL: 120.0,
            SimulationScenario.REPAIR: 75.0,
            SimulationScenario.DRIFT: 55.0,
            SimulationScenario.UNAVAILABLE: 120.0,
        }[scenario]
        self.calibration: float | None = None
        self.delivered_ml = 0.0
        self.running = False
        self.violations: list[str] = []

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def calibrate(self, ml_per_revolution: float) -> None:
        self._require_available()
        self.calibration = float(ml_per_revolution)
        self._log("calibrate", ml_per_revolution=self.calibration)

    def _speed(self, operation: str, speed_rpm: float) -> float:
        speed = float(speed_rpm)
        if speed > self.max_speed_rpm:
            self.violations.append("speed_support_exceeded")
        self.running = True
        self._log(operation, speed_rpm=speed)
        return speed

    def prime(self, speed_rpm: float) -> None:
        self._require_available()
        self._speed("prime", speed_rpm)

    def pump_volume(self, speed_rpm: float, volume_ml: float) -> None:
        self._require_available()
        self._speed("pump_volume", speed_rpm)
        if self.calibration is None:
            self.violations.append("uncalibrated_delivery")
        self.delivered_ml += float(volume_ml)
        self._log("volume_delivered", volume_ml=float(volume_ml))

    def halt(self) -> None:
        self._require_available()
        self.running = False
        self._log("halt")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_max_speed_rpm": self.max_speed_rpm,
            "calibration_ml_per_revolution": self.calibration,
            "delivered_ml": self.delivered_ml,
            "running": self.running,
            "violations": list(self.violations),
        }


class DualPumpController(ConfirmatoryController):
    family = "calibrated_delivery"
    instrument_id = "dual-pump-blend"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_speed_rpm = {
            SimulationScenario.NOMINAL: 100.0,
            SimulationScenario.REPAIR: 60.0,
            SimulationScenario.DRIFT: 45.0,
            SimulationScenario.UNAVAILABLE: 100.0,
        }[scenario]
        self.calibrations: dict[str, float] = {}
        self.delivered_ml = {"A": 0.0, "B": 0.0}
        self.running = {"A": False, "B": False}
        self.violations: list[str] = []

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def _channel(self, channel: str) -> str:
        value = str(channel)
        if value not in self.delivered_ml:
            raise ValueError(f"unknown channel: {value}")
        return value

    def calibrate_channel(self, channel: str, ml_per_revolution: float) -> None:
        self._require_available()
        name = self._channel(channel)
        self.calibrations[name] = float(ml_per_revolution)
        self._log(
            "calibrate_channel",
            channel=name,
            ml_per_revolution=self.calibrations[name],
        )

    def _run(self, operation: str, channel: str, speed_rpm: float) -> str:
        name = self._channel(channel)
        speed = float(speed_rpm)
        if speed > self.max_speed_rpm:
            self.violations.append(f"speed_support_exceeded:{name}")
        self.running[name] = True
        self._log(operation, channel=name, speed_rpm=speed)
        return name

    def prime_channel(self, channel: str, speed_rpm: float) -> None:
        self._require_available()
        self._run("prime_channel", channel, speed_rpm)

    def pump_volume(self, channel: str, speed_rpm: float, volume_ml: float) -> None:
        self._require_available()
        name = self._run("pump_volume", channel, speed_rpm)
        if name not in self.calibrations:
            self.violations.append(f"uncalibrated_delivery:{name}")
        self.delivered_ml[name] += float(volume_ml)
        self._log("volume_delivered", channel=name, volume_ml=float(volume_ml))

    def halt_all(self) -> None:
        self._require_available()
        self.running = {"A": False, "B": False}
        self._log("halt_all")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_max_speed_rpm": self.max_speed_rpm,
            "calibrations_ml_per_revolution": dict(self.calibrations),
            "delivered_ml": dict(self.delivered_ml),
            "running": dict(self.running),
            "violations": list(self.violations),
        }


class _ThermalController(ConfirmatoryController):
    family = "thermal_control"

    def __init__(
        self,
        scenario: SimulationScenario,
        required_s: dict[SimulationScenario, float],
    ) -> None:
        super().__init__(scenario)
        self.required_transition_s = required_s[scenario]
        self.current_c = 25.0
        self.target_c: float | None = None
        self.setpoints: list[float] = []
        self.waits: list[dict[str, Any]] = []
        self.holds: list[dict[str, Any]] = []
        self.active = False
        self.peak_c = 25.0
        self.last_wait_reached = False
        self.violations: list[str] = []

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def set_temperature(self, celsius: float) -> None:
        self._require_available()
        self.target_c = float(celsius)
        self.setpoints.append(self.target_c)
        self.active = True
        self.last_wait_reached = False
        self._log("set_temperature", celsius=self.target_c)

    def wait_for_temperature(self, timeout_s: float, tolerance_c: float) -> None:
        self._require_available()
        if self.target_c is None:
            raise RuntimeError("temperature target is not set")
        timeout = float(timeout_s)
        tolerance = float(tolerance_c)
        reached = timeout >= self.required_transition_s
        if reached:
            self.current_c = self.target_c
        else:
            fraction = max(0.0, timeout / self.required_transition_s)
            self.current_c += fraction * (self.target_c - self.current_c)
        self.peak_c = max(self.peak_c, self.current_c)
        self.last_wait_reached = reached and abs(self.current_c - self.target_c) <= tolerance
        row = {
            "target_c": self.target_c,
            "timeout_s": timeout,
            "tolerance_c": tolerance,
            "required_transition_s": self.required_transition_s,
            "reached": self.last_wait_reached,
            "observed_c": self.current_c,
        }
        self.waits.append(row)
        self._log("wait_for_temperature", **row)

    def hold(self, seconds: float) -> None:
        self._require_available()
        duration = float(seconds)
        if not self.last_wait_reached:
            self.violations.append("hold_before_settle")
        self.holds.append(
            {"target_c": self.target_c, "seconds": duration, "settled": self.last_wait_reached}
        )
        self._log("hold", seconds=duration, target_c=self.target_c)

    def deactivate(self) -> None:
        self._require_available()
        self.active = False
        self._log("deactivate")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_required_transition_s": self.required_transition_s,
            "current_c": self.current_c,
            "setpoints_c": list(self.setpoints),
            "waits": list(self.waits),
            "holds": list(self.holds),
            "active": self.active,
            "peak_c": self.peak_c,
            "violations": list(self.violations),
        }


class IsothermalController(_ThermalController):
    instrument_id = "isothermal-hold"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(
            scenario,
            {
                SimulationScenario.NOMINAL: 60.0,
                SimulationScenario.REPAIR: 180.0,
                SimulationScenario.DRIFT: 240.0,
                SimulationScenario.UNAVAILABLE: 60.0,
            },
        )


class ThermalCycleController(_ThermalController):
    instrument_id = "thermal-cycle"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(
            scenario,
            {
                SimulationScenario.NOMINAL: 90.0,
                SimulationScenario.REPAIR: 240.0,
                SimulationScenario.DRIFT: 300.0,
                SimulationScenario.UNAVAILABLE: 90.0,
            },
        )


@dataclass(frozen=True)
class ConfirmatoryDefinition:
    instrument_id: str
    family: str
    controller_type: type[ConfirmatoryController]
    allowed_methods: frozenset[str]
    condition_field: str


PLATE_METHODS = frozenset(
    {
        "reset",
        "open_tray",
        "load_plate",
        "close_tray",
        "unload_plate",
        "shutdown",
    }
)
THERMAL_METHODS = frozenset(
    {"reset", "set_temperature", "wait_for_temperature", "hold", "deactivate"}
)

CONFIRMATORY_INSTRUMENTS = {
    "absorbance-plate-read": ConfirmatoryDefinition(
        "absorbance-plate-read",
        "optical_measurement",
        AbsorbancePlateController,
        PLATE_METHODS | {"read_blank", "read_absorbance"},
        "max_integration_ms",
    ),
    "fluorescence-plate-read": ConfirmatoryDefinition(
        "fluorescence-plate-read",
        "optical_measurement",
        FluorescencePlateController,
        PLATE_METHODS | {"read_fluorescence_blank", "read_fluorescence"},
        "max_gain",
    ),
    "calibrated-pump-dose": ConfirmatoryDefinition(
        "calibrated-pump-dose",
        "calibrated_delivery",
        CalibratedPumpController,
        frozenset({"reset", "calibrate", "prime", "pump_volume", "halt"}),
        "max_speed_rpm",
    ),
    "dual-pump-blend": ConfirmatoryDefinition(
        "dual-pump-blend",
        "calibrated_delivery",
        DualPumpController,
        frozenset({"reset", "calibrate_channel", "prime_channel", "pump_volume", "halt_all"}),
        "max_speed_rpm",
    ),
    "isothermal-hold": ConfirmatoryDefinition(
        "isothermal-hold",
        "thermal_control",
        IsothermalController,
        THERMAL_METHODS,
        "required_transition_s",
    ),
    "thermal-cycle": ConfirmatoryDefinition(
        "thermal-cycle",
        "thermal_control",
        ThermalCycleController,
        THERMAL_METHODS,
        "required_transition_s",
    ),
}


def build_confirmatory_controller(
    instrument_id: str,
    scenario: SimulationScenario,
) -> ConfirmatoryController:
    return CONFIRMATORY_INSTRUMENTS[instrument_id].controller_type(scenario)
