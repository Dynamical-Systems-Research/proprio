# Cryogenic four-wire resistance source bundle

Reference: [QCoDeS](https://github.com/microsoft/Qcodes) modular instrument drivers and
simulated temperature-controller and source-measure instruments. This contract is a
reduced-order transport simulator.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.set_temperature(kelvin)`
- `controller.wait_stable(tolerance_k)`
- `controller.set_current(amperes)`
- `controller.measure_four_wire()` returning voltage in volts
- `controller.disable_current()`

## Nominal operation

Reset; set 4.2 K and wait to 0.02 K tolerance; source 0.001 A; measure four-wire voltage;
disable current; and return the voltage. The inferred resistance must lie between 100 and
140 Ω. The simulated fixture can report a smaller current limit as its thermal state changes;
reduce current when feedback requires it while preserving the temperature, measurement, and
cleanup sequence.
