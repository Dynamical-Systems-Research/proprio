# Hall-sweep source bundle

Reference: [QCoDeS](https://github.com/microsoft/Qcodes) modular instrument drivers and
simulated PyVISA magnet and source-measure instruments. This contract is a reduced-order Hall
measurement simulator.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.set_temperature(kelvin)`
- `controller.wait_stable(tolerance_k)`
- `controller.set_current(amperes)`
- `controller.sweep_field(start_t, stop_t, points, settle_s)`
- `controller.disable_current()`

## Nominal operation

Reset; set 10.0 K and wait to 0.05 K tolerance; source 0.001 A; sweep −1.0 to +1.0 T with 9
points and 0.2 s settling per point; then disable current. The odd-in-field Hall voltage must
be measurable, the current must not exceed 0.001 A, and field coverage must include both
endpoints. The simulated magnet can report a longer required settling time; increase settling
when feedback requires it.
