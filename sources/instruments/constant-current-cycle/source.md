# Constant-current battery-cycle source bundle

References: [PyBaMM](https://github.com/pybamm-team/PyBaMM) experiment semantics and generic
programmable cycler control. This is a reduced-order cell and controller simulation.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.configure_limits(minimum_v, maximum_v)`
- `controller.apply_current(amperes)`; negative current discharges the cell
- `controller.run_for(seconds)`
- `controller.stop()`

## Nominal operation

Reset; configure a 2.8–4.2 V window; discharge exactly 0.500 Ah; and stop. Under the nominal
fixture, apply −1.000 A for 1800.0 s. Coulomb counting is `capacity_Ah = abs(current_A) ×
seconds / 3600`. A deployed fixture can report a smaller supported current. Preserve the
0.500 Ah target by reducing current magnitude and increasing duration when feedback requires
it. The simulated temperature must remain at or below 40 °C.
