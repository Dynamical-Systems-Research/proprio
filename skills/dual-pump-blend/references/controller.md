# Dual-pump blend source bundle

Reference: [PyLabRobot Pump](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/pumps/pump.py), whose calibrated volume and halt semantics compose into multi-channel delivery. This package uses a reduced-order two-pump simulator.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Channel names are the strings `A` and `B`. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.calibrate_channel(channel, ml_per_revolution)`
- `controller.prime_channel(channel, speed_rpm)`
- `controller.pump_volume(channel, speed_rpm, volume_ml)`
- `controller.halt_all()`

## Nominal operation

Reset; calibrate channel A to 0.040 mL/revolution and B to 0.050 mL/revolution; prime both at 80 rpm; deliver 6.0 mL from A and 4.0 mL from B at 80 rpm; then halt all channels. Total volume must be 10.0 ± 0.10 mL and the A fraction must be 0.60 ± 0.01. A changed pump array can report a lower supported speed; preserve calibrations, component volumes, ratio, and cleanup while reducing every active speed when feedback requires it.
