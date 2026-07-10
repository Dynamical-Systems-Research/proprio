# Laser powder-bed scan source bundle

Reference: [NIST powder-bed-fusion research](https://www.nist.gov/additive-manufacturing/research-areas/technologies/powder-bed-fusion).
This contract uses a declared reduced-order thermal simulator rather than a full melt-pool
digital twin.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.configure_bed(hatch_mm, depth_mm)`
- `controller.configure_laser(power_w, speed_mm_s)`
- `controller.start_gas(flow_l_min)`
- `controller.scan(length_mm)`
- `controller.stop()`

## Nominal operation

Reset; configure 0.100 mm hatch spacing and 0.040 mm powder-bed depth; configure 120.0 W and
500.0 mm/s; start 18.0 L/min shielding gas; scan 20.0 mm; and stop. The effective volumetric
energy density is `coupling × power / (speed × hatch × thickness)` and must remain between
45 and 75 J/mm³. Nominal coupling is 1.0. Simulator feedback may report a changed coupling;
adjust power or speed without changing the bed geometry, gas minimum, or scan length.
