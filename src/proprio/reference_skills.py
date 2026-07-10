"""Deterministic reference-skill renderers for simulator and verifier metrology."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def _liquid_ot2(strokes: list[float], *, cleanup: bool = True) -> str:
    actions = "\n".join(
        f"    controller.aspirate({value:.9g})\n    controller.dispense({value:.9g})"
        for value in strokes
    )
    close = "\n    controller.drop_tip()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.pick_up_tip()
{actions}{close}
    return {{"transferred_ul": {sum(strokes):.9g}}}
"""


def _liquid_star(strokes: list[float], *, cleanup: bool = True) -> str:
    actions = "\n".join(
        f"    controller.aspirate_channel({value:.9g})\n"
        f"    controller.dispense_channel({value:.9g})"
        for value in strokes
    )
    close = "\n    controller.eject_tip()" if cleanup else ""
    return f"""def run(controller):
    controller.initialize_channel()
{actions}{close}
    return {{"transferred_ul": {sum(strokes):.9g}}}
"""


def _constant_cycle(current_a: float, duration_s: float, *, cleanup: bool = True) -> str:
    close = "\n    controller.stop()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.configure_limits(2.8, 4.2)
    controller.apply_current({current_a:.12g})
    controller.run_for({duration_s:.12g}){close}
    return {{"target_capacity_ah": 0.5}}
"""


def _pulse(current_a: float, rest_s: float, *, cleanup: bool = True) -> str:
    close = "\n    controller.stop()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.configure_voltage_window(2.8, 4.2)
    controller.pulse_current({current_a:.12g}, 10.0)
    controller.rest_for({rest_s:.12g}){close}
    return {{"pulse_complete": True}}
"""


def _powder_bed(
    power_w: float, speed_mm_s: float, length_mm: float, *, cleanup: bool = True
) -> str:
    close = "\n    controller.stop()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.configure_bed(0.1, 0.04)
    controller.configure_laser({power_w:.12g}, {speed_mm_s:.12g})
    controller.start_gas(18.0)
    controller.scan({length_mm:.12g}){close}
    return {{"scan_complete": True}}
"""


def _directed_energy(
    power_w: float,
    feed_g_s: float,
    length_mm: float,
    *,
    cleanup: bool = True,
) -> str:
    close = "\n    controller.stop()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.configure_feed({feed_g_s:.12g}, 10.0)
    controller.configure_laser({power_w:.12g})
    controller.start_gas(20.0)
    controller.deposit({length_mm:.12g}){close}
    return {{"deposit_complete": True}}
"""


def _hall(
    current_a: float,
    settle_s: float,
    field_limit_t: float,
    *,
    cleanup: bool = True,
) -> str:
    close = "\n    controller.disable_current()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.set_temperature(10.0)
    controller.wait_stable(0.05)
    controller.set_current({current_a:.12g})
    controller.sweep_field({-field_limit_t:.12g}, {field_limit_t:.12g}, 9, {settle_s:.12g}){close}
    return {{"sweep_complete": True}}
"""


def _cryo(
    current_a: float,
    temperature_k: float,
    *,
    cleanup: bool = True,
) -> str:
    close = "\n    controller.disable_current()" if cleanup else ""
    return f"""def run(controller):
    controller.reset()
    controller.set_temperature({temperature_k:.12g})
    controller.wait_stable(0.02)
    controller.set_current({current_a:.12g})
    voltage = controller.measure_four_wire(){close}
    return {{"voltage_v": voltage}}
"""


def render_valid(instrument_id: str, rng: np.random.Generator) -> str:
    if instrument_id == "ot2-transfer":
        first = float(rng.uniform(45.0, 75.0))
        return _liquid_ot2([first, 120.0 - first])
    if instrument_id == "star-transfer":
        first = float(rng.uniform(30.0, 50.0))
        second = float(rng.uniform(30.0, 50.0))
        return _liquid_star([first, second, 120.0 - first - second])
    if instrument_id == "constant-current-cycle":
        current = float(rng.uniform(0.4, 0.8))
        return _constant_cycle(-current, 1800.0 / current)
    if instrument_id == "pulse-characterization":
        return _pulse(-float(rng.uniform(0.2, 1.0)), float(rng.uniform(30.0, 60.0)))
    if instrument_id == "powder-bed-scan":
        energy = float(rng.uniform(50.0, 70.0))
        speed = float(rng.uniform(400.0, 700.0))
        power = energy * speed * 0.1 * 0.04 / 1.35
        return _powder_bed(power, speed, 20.0)
    if instrument_id == "directed-energy-deposition":
        energy = float(rng.uniform(20.0, 30.0))
        mass_per_length = float(rng.uniform(0.012, 0.020))
        return _directed_energy(energy * 10.0 / 1.4, mass_per_length * 10.0, 25.0)
    if instrument_id == "hall-sweep":
        return _hall(
            float(rng.uniform(5e-4, 1e-3)),
            float(rng.uniform(0.6, 1.0)),
            1.0,
        )
    if instrument_id == "cryogenic-resistance":
        return _cryo(float(rng.uniform(1e-4, 4e-4)), 4.2)
    raise KeyError(instrument_id)


def render_invalid(
    instrument_id: str,
    failure_class: str,
    rng: np.random.Generator,
) -> str:
    if failure_class == "cleanup_omitted":
        source = render_valid(instrument_id, rng)
        return (
            source.replace("\n    controller.drop_tip()", "")
            .replace("\n    controller.eject_tip()", "")
            .replace("\n    controller.stop()", "")
            .replace("\n    controller.disable_current()", "")
        )
    if failure_class == "unsafe_setting":
        if instrument_id == "ot2-transfer":
            return _liquid_ot2([float(rng.uniform(80.0, 115.0)), 20.0])
        if instrument_id == "star-transfer":
            return _liquid_star([float(rng.uniform(65.0, 100.0)), 20.0])
        if instrument_id == "constant-current-cycle":
            current = float(rng.uniform(0.9, 1.3))
            return _constant_cycle(-current, 1800.0 / current)
        if instrument_id == "pulse-characterization":
            return _pulse(-float(rng.uniform(1.1, 2.0)), 30.0)
        if instrument_id == "powder-bed-scan":
            energy = float(rng.uniform(85.0, 115.0))
            return _powder_bed(energy * 500.0 * 0.1 * 0.04 / 1.35, 500.0, 20.0)
        if instrument_id == "directed-energy-deposition":
            energy = float(rng.uniform(36.0, 50.0))
            return _directed_energy(energy * 10.0 / 1.4, 0.15, 25.0)
        if instrument_id == "hall-sweep":
            return _hall(1e-3, float(rng.uniform(0.1, 0.5)), 1.0)
        if instrument_id == "cryogenic-resistance":
            return _cryo(float(rng.uniform(5e-4, 1e-3)), 4.2)
    if failure_class == "wrong_target":
        if instrument_id == "ot2-transfer":
            total = float(rng.uniform(70.0, 110.0))
            return _liquid_ot2([total / 2.0, total / 2.0])
        if instrument_id == "star-transfer":
            total = float(rng.uniform(70.0, 110.0))
            return _liquid_star([total / 2.0, total / 2.0])
        if instrument_id == "constant-current-cycle":
            current = float(rng.uniform(0.4, 0.8))
            target = float(rng.uniform(0.25, 0.4))
            return _constant_cycle(-current, target * 3600.0 / current)
        if instrument_id == "pulse-characterization":
            return _pulse(-0.8, float(rng.uniform(5.0, 25.0)))
        if instrument_id == "powder-bed-scan":
            return _powder_bed(88.0, 500.0, float(rng.uniform(8.0, 18.0)))
        if instrument_id == "directed-energy-deposition":
            return _directed_energy(180.0, 0.15, float(rng.uniform(10.0, 22.0)))
        if instrument_id == "hall-sweep":
            return _hall(8e-4, 0.6, float(rng.uniform(0.3, 0.8)))
        if instrument_id == "cryogenic-resistance":
            return _cryo(3e-4, float(rng.uniform(5.0, 12.0)))
    raise KeyError((instrument_id, failure_class))


def render_nominal(instrument_id: str) -> str:
    nominal: dict[str, Callable[[], str]] = {
        "ot2-transfer": lambda: _liquid_ot2([120.0]),
        "star-transfer": lambda: _liquid_star([100.0, 20.0]),
        "constant-current-cycle": lambda: _constant_cycle(-1.0, 1800.0),
        "pulse-characterization": lambda: _pulse(-1.5, 30.0),
        "powder-bed-scan": lambda: _powder_bed(120.0, 500.0, 20.0),
        "directed-energy-deposition": lambda: _directed_energy(250.0, 0.15, 25.0),
        "hall-sweep": lambda: _hall(1e-3, 0.2, 1.0),
        "cryogenic-resistance": lambda: _cryo(1e-3, 4.2),
    }
    return nominal[instrument_id]()


def render_repair_parent(instrument_id: str) -> str:
    """Render a skill valid before drift and intentionally invalid after drift."""

    sources: dict[str, Callable[[], str]] = {
        "ot2-transfer": lambda: _liquid_ot2([60.0, 60.0]),
        "star-transfer": lambda: _liquid_star([60.0, 60.0]),
        "constant-current-cycle": lambda: _constant_cycle(-0.8, 2250.0),
        "pulse-characterization": lambda: _pulse(-1.0, 30.0),
        "powder-bed-scan": lambda: _powder_bed(100.0, 500.0, 20.0),
        "directed-energy-deposition": lambda: _directed_energy(200.0, 0.15, 25.0),
        "hall-sweep": lambda: _hall(1e-3, 0.6, 1.0),
        "cryogenic-resistance": lambda: _cryo(4e-4, 4.2),
    }
    return sources[instrument_id]()


def render_drift_candidate(instrument_id: str) -> str:
    """Render a conservative skill valid across nominal, repair, and drift scenarios."""

    sources: dict[str, Callable[[], str]] = {
        "ot2-transfer": lambda: _liquid_ot2([40.0, 40.0, 40.0]),
        "star-transfer": lambda: _liquid_star([40.0, 40.0, 40.0]),
        "constant-current-cycle": lambda: _constant_cycle(-0.55, 3600.0 / 1.1),
        "pulse-characterization": lambda: _pulse(-0.7, 30.0),
        "powder-bed-scan": lambda: _powder_bed(90.0, 500.0, 20.0),
        "directed-energy-deposition": lambda: _directed_energy(185.0, 0.15, 25.0),
        "hall-sweep": lambda: _hall(1e-3, 1.0, 1.0),
        "cryogenic-resistance": lambda: _cryo(2e-4, 4.2),
    }
    return sources[instrument_id]()
