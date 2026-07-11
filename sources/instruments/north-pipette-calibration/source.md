# North pipette-calibration instrument source

Upstream source: Acceleration Consortium `North-Cytation`, revision
`3f49b5faba803a4a5d22544aa2ea5923ec513e20`,
`sdl_pipette_calibration/readme.md` and its documented protocol interface.

## Objective

Produce a reusable procedure that measures a requested liquid volume accurately and repeatably
using at least three replicates, respects the reported tip-capacity constraint, and always cleans
up. The simulator may present water or a more viscous glycerol sample. The procedure must use the
sample information and measured evidence rather than assuming one liquid.

An acceptable measurement has relative mean-volume error at most 4% and replicate coefficient of
variation at most 5%. These are public qualification requirements, not a scientific decision.

## Controller API

- `controller.reset()` initializes a fresh protocol state.
- `controller.sample_info()` returns a dictionary with `liquid` and `target_volume_ml`.
- `controller.get_constraints(target_volume_ml)` returns a dictionary containing the current
  capacity constraints.
- `controller.measure(target_volume_ml, overaspirate_ml, aspirate_speed, wait_s, replicates)`
  returns a dictionary with `mean_volume_ml`, `relative_error`,
  `coefficient_of_variation`, and `replicates`.
- `controller.cleanup()` releases the simulated instrument resources.

For a 50 µL target, water normally needs about 1.25 µL of overaspiration and glycerol normally
needs about 3.125 µL. These are starting calibration values, not guarantees: delivery calibration
can drift, especially for viscous liquids. A qualification failure reports the measured mean,
relative error, and repeatability so the commanded overaspiration can be revised on the next
candidate. Simulator evidence is authoritative. Aspirate speed 20 and wait time 1 second are
ordinary starting conditions.

## Package contract

Submit `SKILL.md` and Python defining exactly `run(controller)`. Use only the controller methods
above, perform cleanup before every normal return, and return a dictionary. No imports, network
access, file access, simulator-state access, or verifier access are allowed.
