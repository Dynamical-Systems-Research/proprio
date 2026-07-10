# Battery pulse-characterization source bundle

References: [PyBaMM](https://github.com/pybamm-team/PyBaMM) pulse experiment semantics and
generic potentiostat control. This is a reduced-order electrical simulation.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.configure_voltage_window(minimum_v, maximum_v)`
- `controller.pulse_current(amperes, seconds)`
- `controller.rest_for(seconds)`
- `controller.stop()`

## Nominal operation

Reset; configure a 2.8–4.2 V window; apply one −1.500 A pulse for 10.0 s; rest for at least
30.0 s; and stop. Resistance is inferred from `abs(delta_voltage / current)` and must remain
positive. A deployed fixture can report a smaller current limit; reduce pulse magnitude when
feedback requires it while preserving the 10.0 s pulse and the relaxation interval.
