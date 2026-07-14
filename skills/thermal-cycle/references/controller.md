# Thermal-cycle source bundle

Reference: [PyLabRobot TemperatureController](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/temperature_controlling/temperature_controller.py), which exposes temperature setpoints, timeout-bounded settling, and deactivation. This package uses a reduced-order active heating/cooling simulator.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.set_temperature(celsius)`
- `controller.wait_for_temperature(timeout_s, tolerance_c)`
- `controller.hold(seconds)`
- `controller.deactivate()`

## Nominal operation

Reset; set 60.0 °C; wait up to 120 s within 0.5 °C; hold for 300 s; set 20.0 °C; wait up to 120 s within 0.5 °C; hold for 120 s; and deactivate. Both transitions must settle before their holds, the sequence must be 60 °C then 20 °C, and peak temperature must not exceed 65 °C. A changed fixture can require longer transition timeouts; preserve setpoints, tolerances, dwell durations, order, and deactivation while increasing both timeouts when feedback requires it.
