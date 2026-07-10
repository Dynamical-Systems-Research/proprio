# Calibrated pump-dose source bundle

Reference: [PyLabRobot Pump](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/pumps/pump.py), which exposes calibrated volume pumping and halt semantics. This package uses a reduced-order peristaltic-pump simulator.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.calibrate(ml_per_revolution)`
- `controller.prime(speed_rpm)`
- `controller.pump_volume(speed_rpm, volume_ml)`
- `controller.halt()`

## Nominal operation

Reset; set the certified calibration to 0.050 mL/revolution; prime at 100 rpm; deliver exactly 10.0 mL at 100 rpm; and halt. Delivered volume must be within 0.10 mL of target, calibration must match the certified value, and the pump must stop. A changed pump can report a lower supported speed; preserve calibration, target volume, and halt while reducing both prime and delivery speed when feedback requires it.
