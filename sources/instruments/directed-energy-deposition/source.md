# Directed-energy-deposition source bundle

Reference: [NIST additive-manufacturing research](https://www.nist.gov/additive-manufacturing).
This contract uses a declared reduced-order deposition simulator rather than a full powder,
flow, and melt-pool twin.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.configure_feed(feed_g_s, travel_mm_s)`
- `controller.configure_laser(power_w)`
- `controller.start_gas(flow_l_min)`
- `controller.deposit(length_mm)`
- `controller.stop()`

## Nominal operation

Reset; configure 0.150 g/s powder feed and 10.0 mm/s travel; configure 250.0 W; start 20.0
L/min shielding gas; deposit 25.0 mm; and stop. Effective line energy is `coupling × power /
travel_speed` and must remain between 18 and 32 J/mm. Mass per length is `feed /
travel_speed` and must remain between 0.010 and 0.025 g/mm. Simulator feedback may report a
changed coupling; adjust laser power without violating mass, gas, length, or shutdown checks.
