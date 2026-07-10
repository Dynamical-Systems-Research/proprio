"""Reduced-order scientific-instrument simulators for diagnostic skill qualification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from proprio.instrument_types import SimulationScenario


class ReferenceController:
    """Stateful simulator surface that records every public action."""

    family: str
    instrument_id: str

    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.trace: list[dict[str, Any]] = []
        self.unavailable = scenario is SimulationScenario.UNAVAILABLE

    def _require_available(self) -> None:
        if self.unavailable:
            raise RuntimeError("instrument unavailable: simulated hardware link is down")

    def _log(self, operation: str, **values: Any) -> None:
        self.trace.append({"sequence": len(self.trace), "operation": operation, **values})

    def telemetry(self) -> dict[str, Any]:
        raise NotImplementedError


class OT2TransferController(ReferenceController):
    family = "liquid_handling"
    instrument_id = "ot2-transfer"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_transfer_ul = {
            SimulationScenario.NOMINAL: 120.0,
            SimulationScenario.REPAIR: 75.0,
            SimulationScenario.DRIFT: 45.0,
            SimulationScenario.UNAVAILABLE: 120.0,
        }[scenario]
        self.source_ul = 1000.0
        self.destination_ul = 0.0
        self.tip_ul = 0.0
        self.tip_attached = False
        self.violations: list[str] = []

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def pick_up_tip(self) -> None:
        self._require_available()
        self.tip_attached = True
        self._log("pick_up_tip")

    def aspirate(self, volume_ul: float) -> None:
        self._require_available()
        volume = float(volume_ul)
        if not self.tip_attached:
            self.violations.append("aspirate_without_tip")
        if volume > self.max_transfer_ul:
            self.violations.append("stroke_capacity_exceeded")
        if volume > self.source_ul:
            self.violations.append("source_depleted")
        self.source_ul -= volume
        self.tip_ul += volume
        self._log("aspirate", volume_ul=volume)

    def dispense(self, volume_ul: float) -> None:
        self._require_available()
        volume = float(volume_ul)
        if volume > self.tip_ul:
            self.violations.append("dispense_exceeds_tip_volume")
        self.tip_ul -= volume
        self.destination_ul += volume
        self._log("dispense", volume_ul=volume)

    def drop_tip(self) -> None:
        self._require_available()
        if abs(self.tip_ul) > 1e-9:
            self.violations.append("tip_not_empty")
        self.tip_attached = False
        self._log("drop_tip")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_max_transfer_ul": self.max_transfer_ul,
            "source_ul": self.source_ul,
            "destination_ul": self.destination_ul,
            "tip_ul": self.tip_ul,
            "tip_attached": self.tip_attached,
            "violations": list(self.violations),
        }


class StarTransferController(ReferenceController):
    family = "liquid_handling"
    instrument_id = "star-transfer"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.max_transfer_ul = {
            SimulationScenario.NOMINAL: 100.0,
            SimulationScenario.REPAIR: 60.0,
            SimulationScenario.DRIFT: 40.0,
            SimulationScenario.UNAVAILABLE: 100.0,
        }[scenario]
        self.source_ul = 1000.0
        self.destination_ul = 0.0
        self.channel_ul = 0.0
        self.channel_ready = False
        self.violations: list[str] = []

    def initialize_channel(self) -> None:
        self._require_available()
        self.channel_ready = True
        self._log("initialize_channel")

    def aspirate_channel(self, volume_ul: float) -> None:
        self._require_available()
        volume = float(volume_ul)
        if not self.channel_ready:
            self.violations.append("channel_not_initialized")
        if volume > self.max_transfer_ul:
            self.violations.append("stroke_capacity_exceeded")
        self.source_ul -= volume
        self.channel_ul += volume
        self._log("aspirate_channel", volume_ul=volume)

    def dispense_channel(self, volume_ul: float) -> None:
        self._require_available()
        volume = float(volume_ul)
        if volume > self.channel_ul:
            self.violations.append("dispense_exceeds_channel_volume")
        self.channel_ul -= volume
        self.destination_ul += volume
        self._log("dispense_channel", volume_ul=volume)

    def eject_tip(self) -> None:
        self._require_available()
        if abs(self.channel_ul) > 1e-9:
            self.violations.append("channel_not_empty")
        self.channel_ready = False
        self._log("eject_tip")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_max_transfer_ul": self.max_transfer_ul,
            "source_ul": self.source_ul,
            "destination_ul": self.destination_ul,
            "channel_ul": self.channel_ul,
            "channel_ready": self.channel_ready,
            "violations": list(self.violations),
        }


class ConstantCurrentCyclerController(ReferenceController):
    family = "battery_cycling"
    instrument_id = "constant-current-cycle"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.current_limit_a = {
            SimulationScenario.NOMINAL: 1.2,
            SimulationScenario.REPAIR: 0.8,
            SimulationScenario.DRIFT: 0.55,
            SimulationScenario.UNAVAILABLE: 1.2,
        }[scenario]
        self.current_a: float | None = None
        self.voltage_min_v: float | None = None
        self.voltage_max_v: float | None = None
        self.duration_s = 0.0
        self.running = False
        self.temperature_c = 25.0

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def configure_limits(self, minimum_v: float, maximum_v: float) -> None:
        self._require_available()
        self.voltage_min_v = float(minimum_v)
        self.voltage_max_v = float(maximum_v)
        self._log("configure_limits", minimum_v=self.voltage_min_v, maximum_v=self.voltage_max_v)

    def apply_current(self, amperes: float) -> None:
        self._require_available()
        self.current_a = float(amperes)
        self._log("apply_current", amperes=self.current_a)

    def run_for(self, seconds: float) -> None:
        self._require_available()
        self.duration_s += float(seconds)
        self.running = True
        current = abs(self.current_a or 0.0)
        overload = max(0.0, current - self.current_limit_a)
        self.temperature_c = 25.0 + 8.0 * current**2 + 30.0 * overload
        self._log("run_for", seconds=float(seconds), temperature_c=self.temperature_c)

    def stop(self) -> None:
        self._require_available()
        self.running = False
        self._log("stop")

    def telemetry(self) -> dict[str, Any]:
        current = float(self.current_a or 0.0)
        return {
            "reported_current_limit_a": self.current_limit_a,
            "current_a": self.current_a,
            "voltage_min_v": self.voltage_min_v,
            "voltage_max_v": self.voltage_max_v,
            "duration_s": self.duration_s,
            "delivered_capacity_ah": abs(current) * self.duration_s / 3600.0,
            "temperature_c": self.temperature_c,
            "running": self.running,
        }


class PulseCyclerController(ReferenceController):
    family = "battery_cycling"
    instrument_id = "pulse-characterization"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.current_limit_a = {
            SimulationScenario.NOMINAL: 2.0,
            SimulationScenario.REPAIR: 1.0,
            SimulationScenario.DRIFT: 0.7,
            SimulationScenario.UNAVAILABLE: 2.0,
        }[scenario]
        self.minimum_v: float | None = None
        self.maximum_v: float | None = None
        self.pulses: list[dict[str, float]] = []
        self.rest_s = 0.0
        self.running = False

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def configure_voltage_window(self, minimum_v: float, maximum_v: float) -> None:
        self._require_available()
        self.minimum_v = float(minimum_v)
        self.maximum_v = float(maximum_v)
        self._log(
            "configure_voltage_window",
            minimum_v=self.minimum_v,
            maximum_v=self.maximum_v,
        )

    def pulse_current(self, amperes: float, seconds: float) -> None:
        self._require_available()
        current = float(amperes)
        duration = float(seconds)
        resistance = 0.08
        delta_v = current * resistance
        self.pulses.append({"current_a": current, "seconds": duration, "delta_v": delta_v})
        self.running = True
        self._log(
            "pulse_current",
            current_a=current,
            seconds=duration,
            delta_v=delta_v,
        )

    def rest_for(self, seconds: float) -> None:
        self._require_available()
        self.rest_s += float(seconds)
        self._log("rest_for", seconds=float(seconds))

    def stop(self) -> None:
        self._require_available()
        self.running = False
        self._log("stop")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_current_limit_a": self.current_limit_a,
            "minimum_v": self.minimum_v,
            "maximum_v": self.maximum_v,
            "pulses": list(self.pulses),
            "rest_s": self.rest_s,
            "running": self.running,
        }


class PowderBedController(ReferenceController):
    family = "additive_manufacturing"
    instrument_id = "powder-bed-scan"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.absorptivity = {
            SimulationScenario.NOMINAL: 1.0,
            SimulationScenario.REPAIR: 1.35,
            SimulationScenario.DRIFT: 1.65,
            SimulationScenario.UNAVAILABLE: 1.0,
        }[scenario]
        self.bed_geometry: tuple[float, float] | None = None
        self.laser: tuple[float, float] | None = None
        self.gas_flow_l_min = 0.0
        self.scan_length_mm = 0.0
        self.active = False
        self.peak_temperature_c = 25.0

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def configure_bed(self, hatch_mm: float, depth_mm: float) -> None:
        self._require_available()
        self.bed_geometry = (float(hatch_mm), float(depth_mm))
        self._log(
            "configure_bed",
            hatch_mm=self.bed_geometry[0],
            depth_mm=self.bed_geometry[1],
        )

    def configure_laser(self, power_w: float, speed_mm_s: float) -> None:
        self._require_available()
        self.laser = (float(power_w), float(speed_mm_s))
        self._log("configure_laser", power_w=self.laser[0], speed_mm_s=self.laser[1])

    def start_gas(self, flow_l_min: float) -> None:
        self._require_available()
        self.gas_flow_l_min = float(flow_l_min)
        self._log("start_gas", flow_l_min=self.gas_flow_l_min)

    def scan(self, length_mm: float) -> None:
        self._require_available()
        self.active = True
        self.scan_length_mm = float(length_mm)
        if self.bed_geometry and self.laser:
            hatch, depth = self.bed_geometry
            power, speed = self.laser
            energy = self.absorptivity * power / (speed * hatch * depth)
            self.peak_temperature_c = 25.0 + 18.0 * energy
        self._log(
            "scan",
            length_mm=self.scan_length_mm,
            peak_temperature_c=self.peak_temperature_c,
        )

    def stop(self) -> None:
        self._require_available()
        self.active = False
        self._log("stop")

    def telemetry(self) -> dict[str, Any]:
        return {
            "absorptivity_factor": self.absorptivity,
            "bed_geometry": self.bed_geometry,
            "laser": self.laser,
            "gas_flow_l_min": self.gas_flow_l_min,
            "scan_length_mm": self.scan_length_mm,
            "peak_temperature_c": self.peak_temperature_c,
            "active": self.active,
        }


class DirectedEnergyController(ReferenceController):
    family = "additive_manufacturing"
    instrument_id = "directed-energy-deposition"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.coupling = {
            SimulationScenario.NOMINAL: 1.0,
            SimulationScenario.REPAIR: 1.4,
            SimulationScenario.DRIFT: 1.7,
            SimulationScenario.UNAVAILABLE: 1.0,
        }[scenario]
        self.feed_g_s: float | None = None
        self.travel_mm_s: float | None = None
        self.power_w: float | None = None
        self.gas_flow_l_min = 0.0
        self.length_mm = 0.0
        self.active = False
        self.peak_temperature_c = 25.0

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def configure_feed(self, feed_g_s: float, travel_mm_s: float) -> None:
        self._require_available()
        self.feed_g_s = float(feed_g_s)
        self.travel_mm_s = float(travel_mm_s)
        self._log("configure_feed", feed_g_s=self.feed_g_s, travel_mm_s=self.travel_mm_s)

    def configure_laser(self, power_w: float) -> None:
        self._require_available()
        self.power_w = float(power_w)
        self._log("configure_laser", power_w=self.power_w)

    def start_gas(self, flow_l_min: float) -> None:
        self._require_available()
        self.gas_flow_l_min = float(flow_l_min)
        self._log("start_gas", flow_l_min=self.gas_flow_l_min)

    def deposit(self, length_mm: float) -> None:
        self._require_available()
        self.active = True
        self.length_mm = float(length_mm)
        speed = float(self.travel_mm_s or 0.0)
        line_energy = self.coupling * float(self.power_w or 0.0) / max(speed, 1e-9)
        self.peak_temperature_c = 25.0 + 45.0 * line_energy
        self._log(
            "deposit",
            length_mm=self.length_mm,
            peak_temperature_c=self.peak_temperature_c,
        )

    def stop(self) -> None:
        self._require_available()
        self.active = False
        self._log("stop")

    def telemetry(self) -> dict[str, Any]:
        speed = float(self.travel_mm_s or 0.0)
        return {
            "coupling_factor": self.coupling,
            "feed_g_s": self.feed_g_s,
            "travel_mm_s": self.travel_mm_s,
            "power_w": self.power_w,
            "gas_flow_l_min": self.gas_flow_l_min,
            "length_mm": self.length_mm,
            "mass_per_length_g_mm": float(self.feed_g_s or 0.0) / max(speed, 1e-9),
            "peak_temperature_c": self.peak_temperature_c,
            "active": self.active,
        }


class HallSweepController(ReferenceController):
    family = "quantum_transport"
    instrument_id = "hall-sweep"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.required_settle_s = {
            SimulationScenario.NOMINAL: 0.2,
            SimulationScenario.REPAIR: 0.6,
            SimulationScenario.DRIFT: 1.0,
            SimulationScenario.UNAVAILABLE: 0.2,
        }[scenario]
        self.temperature_k: float | None = None
        self.temperature_tolerance_k: float | None = None
        self.current_a: float | None = None
        self.points: list[dict[str, float]] = []
        self.current_enabled = False

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def set_temperature(self, kelvin: float) -> None:
        self._require_available()
        self.temperature_k = float(kelvin)
        self._log("set_temperature", kelvin=self.temperature_k)

    def wait_stable(self, tolerance_k: float) -> None:
        self._require_available()
        self.temperature_tolerance_k = float(tolerance_k)
        self._log("wait_stable", tolerance_k=self.temperature_tolerance_k)

    def set_current(self, amperes: float) -> None:
        self._require_available()
        self.current_a = float(amperes)
        self.current_enabled = True
        self._log("set_current", amperes=self.current_a)

    def sweep_field(self, start_t: float, stop_t: float, points: int, settle_s: float) -> None:
        self._require_available()
        fields = np.linspace(float(start_t), float(stop_t), int(points))
        current = float(self.current_a or 0.0)
        settle = float(settle_s)
        attenuation = min(1.0, settle / self.required_settle_s)
        hall_coefficient = 0.02
        offset = 2e-6
        self.points = [
            {
                "field_t": float(field),
                "voltage_v": float(offset + attenuation * hall_coefficient * current * field),
                "settle_s": settle,
            }
            for field in fields
        ]
        self._log(
            "sweep_field",
            start_t=float(start_t),
            stop_t=float(stop_t),
            points=int(points),
            settle_s=settle,
        )

    def disable_current(self) -> None:
        self._require_available()
        self.current_enabled = False
        self._log("disable_current")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_required_settle_s": self.required_settle_s,
            "temperature_k": self.temperature_k,
            "temperature_tolerance_k": self.temperature_tolerance_k,
            "current_a": self.current_a,
            "points": list(self.points),
            "current_enabled": self.current_enabled,
        }


class CryogenicResistanceController(ReferenceController):
    family = "quantum_transport"
    instrument_id = "cryogenic-resistance"

    def __init__(self, scenario: SimulationScenario) -> None:
        super().__init__(scenario)
        self.current_limit_a = {
            SimulationScenario.NOMINAL: 1e-3,
            SimulationScenario.REPAIR: 4e-4,
            SimulationScenario.DRIFT: 2e-4,
            SimulationScenario.UNAVAILABLE: 1e-3,
        }[scenario]
        self.temperature_k: float | None = None
        self.temperature_tolerance_k: float | None = None
        self.current_a: float | None = None
        self.voltage_v: float | None = None
        self.current_enabled = False

    def reset(self) -> None:
        self._require_available()
        self._log("reset")

    def set_temperature(self, kelvin: float) -> None:
        self._require_available()
        self.temperature_k = float(kelvin)
        self._log("set_temperature", kelvin=self.temperature_k)

    def wait_stable(self, tolerance_k: float) -> None:
        self._require_available()
        self.temperature_tolerance_k = float(tolerance_k)
        self._log("wait_stable", tolerance_k=self.temperature_tolerance_k)

    def set_current(self, amperes: float) -> None:
        self._require_available()
        self.current_a = float(amperes)
        self.current_enabled = True
        self._log("set_current", amperes=self.current_a)

    def measure_four_wire(self) -> float:
        self._require_available()
        current = float(self.current_a or 0.0)
        base_resistance = 120.0
        heating = 4e5 * max(0.0, abs(current) - self.current_limit_a)
        self.voltage_v = current * (base_resistance + heating)
        self._log("measure_four_wire", voltage_v=self.voltage_v)
        return self.voltage_v

    def disable_current(self) -> None:
        self._require_available()
        self.current_enabled = False
        self._log("disable_current")

    def telemetry(self) -> dict[str, Any]:
        return {
            "reported_current_limit_a": self.current_limit_a,
            "temperature_k": self.temperature_k,
            "temperature_tolerance_k": self.temperature_tolerance_k,
            "current_a": self.current_a,
            "voltage_v": self.voltage_v,
            "current_enabled": self.current_enabled,
        }


@dataclass(frozen=True)
class InstrumentDefinition:
    instrument_id: str
    family: str
    controller_type: type[ReferenceController]
    allowed_methods: frozenset[str]


INSTRUMENTS = {
    "ot2-transfer": InstrumentDefinition(
        "ot2-transfer",
        "liquid_handling",
        OT2TransferController,
        frozenset({"reset", "pick_up_tip", "aspirate", "dispense", "drop_tip"}),
    ),
    "star-transfer": InstrumentDefinition(
        "star-transfer",
        "liquid_handling",
        StarTransferController,
        frozenset({"initialize_channel", "aspirate_channel", "dispense_channel", "eject_tip"}),
    ),
    "constant-current-cycle": InstrumentDefinition(
        "constant-current-cycle",
        "battery_cycling",
        ConstantCurrentCyclerController,
        frozenset({"reset", "configure_limits", "apply_current", "run_for", "stop"}),
    ),
    "pulse-characterization": InstrumentDefinition(
        "pulse-characterization",
        "battery_cycling",
        PulseCyclerController,
        frozenset({"reset", "configure_voltage_window", "pulse_current", "rest_for", "stop"}),
    ),
    "powder-bed-scan": InstrumentDefinition(
        "powder-bed-scan",
        "additive_manufacturing",
        PowderBedController,
        frozenset({"reset", "configure_bed", "configure_laser", "start_gas", "scan", "stop"}),
    ),
    "directed-energy-deposition": InstrumentDefinition(
        "directed-energy-deposition",
        "additive_manufacturing",
        DirectedEnergyController,
        frozenset({"reset", "configure_feed", "configure_laser", "start_gas", "deposit", "stop"}),
    ),
    "hall-sweep": InstrumentDefinition(
        "hall-sweep",
        "quantum_transport",
        HallSweepController,
        frozenset(
            {
                "reset",
                "set_temperature",
                "wait_stable",
                "set_current",
                "sweep_field",
                "disable_current",
            }
        ),
    ),
    "cryogenic-resistance": InstrumentDefinition(
        "cryogenic-resistance",
        "quantum_transport",
        CryogenicResistanceController,
        frozenset(
            {
                "reset",
                "set_temperature",
                "wait_stable",
                "set_current",
                "measure_four_wire",
                "disable_current",
            }
        ),
    ),
}


def build_controller(
    instrument_id: str,
    scenario: SimulationScenario,
) -> ReferenceController:
    return INSTRUMENTS[instrument_id].controller_type(scenario)
