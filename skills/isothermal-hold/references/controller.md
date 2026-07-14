# Isothermal temperature-control source bundle

Reference: [PyLabRobot TemperatureController](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/temperature_controlling/temperature_controller.py), which exposes setpoint, wait-with-timeout, and deactivate semantics. This package uses a reduced-order thermal simulator.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.set_temperature(celsius)`
- `controller.wait_for_temperature(timeout_s, tolerance_c)`
- `controller.hold(seconds)`
- `controller.deactivate()`

## Nominal operation

Reset; set 80.0 °C; wait up to 120 s with 0.5 °C tolerance; hold for 600 s; and deactivate. The setpoint must be reached inside tolerance before the hold, peak temperature must not exceed 85 °C, and the controller must return to inactive state. A changed thermal fixture can require a longer settling timeout; preserve setpoint, tolerance, hold, and deactivation while increasing timeout when feedback requires it.
