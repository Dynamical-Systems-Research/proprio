---
name: north-pipette-calibration
description: Measures a requested liquid volume with at least three replicates, adapts overaspiration to liquid type and measured shortfall, respects capacity constraints, and always cleans up.
---

# North Pipette Calibration

## Overview
Calibrate a pipette by measuring a target volume of liquid using three replicates.  
The procedure adapts overaspiration to the liquid type (water or glycerol) using the
starting calibration ratios from the source bundle, reads capacity constraints,
checks measurement qualification, and revises overaspiration if the measurement
fails accuracy or repeatability thresholds. Cleanup is performed before every return.

## Procedure

1. **Initialize** – Call `controller.reset()`.
2. **Read sample information** – Call `controller.sample_info()` to obtain the
   `liquid` name and `target_volume_ml`.
3. **Read capacity constraints** – Call `controller.get_constraints(target_volume_ml)`
   so the procedure is aware of the reported tip-capacity bound.
4. **Select initial overaspiration** – If `liquid` is `"water"` set `overaspirate_ml` to
   `0.025 * target_volume_ml`; otherwise (glycerol) set it to
   `0.0625 * target_volume_ml`.
5. **Measure** – Call `controller.measure(target_volume_ml, overaspirate_ml,
   aspirate_speed=20, wait_s=1, replicates=3)` and capture the returned dictionary.
6. **Check qualification and revise if needed** – If the measured `relative_error`
   exceeds 4% or the `coefficient_of_variation` exceeds 5%, revise the overaspiration
   by the ratio `target_volume_ml / mean_volume_ml` and re-measure.
7. **Clean up** – Call `controller.cleanup()`.
8. **Return** – Return the measurement dictionary.
