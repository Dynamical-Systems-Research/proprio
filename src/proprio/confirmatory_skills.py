"""Deterministic reference skills for confirmatory verifier metrology."""

from __future__ import annotations

import hashlib


def _absorbance(integration_ms: float, *, wavelength_nm: float = 600.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.open_tray()
    controller.load_plate()
    controller.close_tray()
    blank = controller.read_blank({wavelength_nm:.12g}, {integration_ms:.12g})
    sample = controller.read_absorbance({wavelength_nm:.12g}, {integration_ms:.12g})
    controller.open_tray()
    controller.unload_plate()
    controller.shutdown()
    return {{"blank": blank, "sample": sample}}
"""


def _fluorescence(gain: float, *, excitation_nm: float = 485.0, emission_nm: float = 520.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.open_tray()
    controller.load_plate()
    controller.close_tray()
    blank = controller.read_fluorescence_blank(
        {excitation_nm:.12g}, {emission_nm:.12g}, {gain:.12g}
    )
    sample = controller.read_fluorescence({excitation_nm:.12g}, {emission_nm:.12g}, {gain:.12g})
    controller.open_tray()
    controller.unload_plate()
    controller.shutdown()
    return {{"blank": blank, "sample": sample}}
"""


def _pump(speed_rpm: float, *, volume_ml: float = 10.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.calibrate(0.05)
    controller.prime({speed_rpm:.12g})
    controller.pump_volume({speed_rpm:.12g}, {volume_ml:.12g})
    controller.halt()
    return {{"target_volume_ml": {volume_ml:.12g}}}
"""


def _blend(speed_rpm: float, *, volume_a: float = 6.0, volume_b: float = 4.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.calibrate_channel("A", 0.04)
    controller.calibrate_channel("B", 0.05)
    controller.prime_channel("A", {speed_rpm:.12g})
    controller.prime_channel("B", {speed_rpm:.12g})
    controller.pump_volume("A", {speed_rpm:.12g}, {volume_a:.12g})
    controller.pump_volume("B", {speed_rpm:.12g}, {volume_b:.12g})
    controller.halt_all()
    return {{"component_a_ml": {volume_a:.12g}, "component_b_ml": {volume_b:.12g}}}
"""


def _isothermal(timeout_s: float, *, temperature_c: float = 80.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.set_temperature({temperature_c:.12g})
    controller.wait_for_temperature({timeout_s:.12g}, 0.5)
    controller.hold(600.0)
    controller.deactivate()
    return {{"setpoint_c": {temperature_c:.12g}}}
"""


def _cycle(timeout_s: float, *, high_c: float = 60.0, low_c: float = 20.0) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.set_temperature({high_c:.12g})
    controller.wait_for_temperature({timeout_s:.12g}, 0.5)
    controller.hold(300.0)
    controller.set_temperature({low_c:.12g})
    controller.wait_for_temperature({timeout_s:.12g}, 0.5)
    controller.hold(120.0)
    controller.deactivate()
    return {{"cycle_complete": True}}
"""


def render_confirmatory_nominal(instrument_id: str) -> str:
    renderers = {
        "absorbance-plate-read": lambda: _absorbance(160.0),
        "fluorescence-plate-read": lambda: _fluorescence(10.0),
        "calibrated-pump-dose": lambda: _pump(100.0),
        "dual-pump-blend": lambda: _blend(80.0),
        "isothermal-hold": lambda: _isothermal(120.0),
        "thermal-cycle": lambda: _cycle(120.0),
    }
    return renderers[instrument_id]()


def render_confirmatory_repair(instrument_id: str) -> str:
    renderers = {
        "absorbance-plate-read": lambda: _absorbance(90.0),
        "fluorescence-plate-read": lambda: _fluorescence(6.0),
        "calibrated-pump-dose": lambda: _pump(60.0),
        "dual-pump-blend": lambda: _blend(50.0),
        "isothermal-hold": lambda: _isothermal(200.0),
        "thermal-cycle": lambda: _cycle(260.0),
    }
    return renderers[instrument_id]()


def render_confirmatory_invalid(instrument_id: str, failure_class: str) -> str:
    if failure_class == "unsafe_setting":
        renderers = {
            "absorbance-plate-read": lambda: _absorbance(300.0),
            "fluorescence-plate-read": lambda: _fluorescence(20.0),
            "calibrated-pump-dose": lambda: _pump(200.0),
            "dual-pump-blend": lambda: _blend(200.0),
            "isothermal-hold": lambda: _isothermal(30.0),
            "thermal-cycle": lambda: _cycle(30.0),
        }
        return renderers[instrument_id]()
    if failure_class == "wrong_target":
        renderers = {
            "absorbance-plate-read": lambda: _absorbance(90.0, wavelength_nm=450.0),
            "fluorescence-plate-read": lambda: _fluorescence(
                6.0, excitation_nm=520.0, emission_nm=485.0
            ),
            "calibrated-pump-dose": lambda: _pump(60.0, volume_ml=7.0),
            "dual-pump-blend": lambda: _blend(50.0, volume_a=8.0, volume_b=2.0),
            "isothermal-hold": lambda: _isothermal(200.0, temperature_c=60.0),
            "thermal-cycle": lambda: _cycle(260.0, high_c=50.0, low_c=25.0),
        }
        return renderers[instrument_id]()
    if failure_class == "cleanup_omitted":
        source = render_confirmatory_repair(instrument_id)
        return (
            source.replace("    controller.open_tray()\n    controller.unload_plate()\n", "")
            .replace("    controller.shutdown()\n", "")
            .replace("    controller.halt()\n", "")
            .replace("    controller.halt_all()\n", "")
            .replace("    controller.deactivate()\n", "")
        )
    if failure_class == "wrong_order":
        if instrument_id == "absorbance-plate-read":
            return """def run(controller):
    controller.reset()
    sample = controller.read_absorbance(600.0, 90.0)
    return {"sample": sample}
"""
        if instrument_id == "fluorescence-plate-read":
            return """def run(controller):
    controller.reset()
    sample = controller.read_fluorescence(485.0, 520.0, 6.0)
    return {"sample": sample}
"""
        if instrument_id == "calibrated-pump-dose":
            return """def run(controller):
    controller.reset()
    controller.pump_volume(60.0, 10.0)
    controller.halt()
    return {"target_volume_ml": 10.0}
"""
        if instrument_id == "dual-pump-blend":
            return """def run(controller):
    controller.reset()
    controller.pump_volume("A", 50.0, 6.0)
    controller.pump_volume("B", 50.0, 4.0)
    controller.halt_all()
    return {"blend_complete": True}
"""
        if instrument_id == "isothermal-hold":
            return """def run(controller):
    controller.reset()
    controller.set_temperature(80.0)
    controller.hold(600.0)
    controller.deactivate()
    return {"setpoint_c": 80.0}
"""
        if instrument_id == "thermal-cycle":
            return """def run(controller):
    controller.reset()
    controller.set_temperature(60.0)
    controller.hold(300.0)
    controller.set_temperature(20.0)
    controller.hold(120.0)
    controller.deactivate()
    return {"cycle_complete": True}
"""
    raise KeyError((instrument_id, failure_class))


def _fraction(instrument_id: str, failure_class: str, index: int) -> float:
    payload = f"confirmatory-metrology:{instrument_id}:{failure_class}:{index}".encode()
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (value + 0.5) / 2**64


def render_confirmatory_battery_case(
    instrument_id: str,
    failure_class: str,
    index: int,
) -> str:
    """Render deterministic but non-identical labeled metrology cases."""

    fraction = _fraction(instrument_id, failure_class, index)
    if failure_class == "valid":
        if instrument_id == "absorbance-plate-read":
            return _absorbance(45.0 + 50.0 * fraction)
        if instrument_id == "fluorescence-plate-read":
            return _fluorescence(2.0 + 4.5 * fraction)
        if instrument_id == "calibrated-pump-dose":
            return _pump(20.0 + 50.0 * fraction)
        if instrument_id == "dual-pump-blend":
            return _blend(20.0 + 35.0 * fraction)
        if instrument_id == "isothermal-hold":
            return _isothermal(180.0 + 100.0 * fraction)
        if instrument_id == "thermal-cycle":
            return _cycle(240.0 + 120.0 * fraction)
    if failure_class == "unsafe_setting":
        if instrument_id == "absorbance-plate-read":
            return _absorbance(101.0 + 149.0 * fraction)
        if instrument_id == "fluorescence-plate-read":
            return _fluorescence(7.1 + 7.9 * fraction)
        if instrument_id == "calibrated-pump-dose":
            return _pump(76.0 + 74.0 * fraction)
        if instrument_id == "dual-pump-blend":
            return _blend(61.0 + 89.0 * fraction)
        if instrument_id == "isothermal-hold":
            return _isothermal(20.0 + 159.0 * fraction)
        if instrument_id == "thermal-cycle":
            return _cycle(20.0 + 219.0 * fraction)
    if failure_class == "wrong_target":
        if instrument_id == "absorbance-plate-read":
            return _absorbance(90.0, wavelength_nm=420.0 + 100.0 * fraction)
        if instrument_id == "fluorescence-plate-read":
            return _fluorescence(
                6.0,
                excitation_nm=510.0 + 30.0 * fraction,
                emission_nm=470.0 + 30.0 * fraction,
            )
        if instrument_id == "calibrated-pump-dose":
            return _pump(60.0, volume_ml=5.0 + 3.0 * fraction)
        if instrument_id == "dual-pump-blend":
            return _blend(50.0, volume_a=7.0 + 2.0 * fraction, volume_b=3.0 - fraction)
        if instrument_id == "isothermal-hold":
            return _isothermal(200.0, temperature_c=50.0 + 20.0 * fraction)
        if instrument_id == "thermal-cycle":
            return _cycle(
                260.0,
                high_c=45.0 + 10.0 * fraction,
                low_c=22.0 + 6.0 * fraction,
            )
    if failure_class == "cleanup_omitted":
        source = render_confirmatory_battery_case(instrument_id, "valid", index)
        return (
            source.replace("    controller.open_tray()\n    controller.unload_plate()\n", "")
            .replace("    controller.shutdown()\n", "")
            .replace("    controller.halt()\n", "")
            .replace("    controller.halt_all()\n", "")
            .replace("    controller.deactivate()\n", "")
        )
    if failure_class == "wrong_order":
        return render_confirmatory_invalid(instrument_id, failure_class)
    raise KeyError((instrument_id, failure_class))
