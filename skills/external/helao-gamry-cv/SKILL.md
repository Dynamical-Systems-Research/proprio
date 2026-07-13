---
name: helao-gamry-cv
description: Acquire one complete cyclic voltammogram from 0 V through -0.5 V and +0.5 V back to 0 V with 0.02 V sampling interval, compensating for scan-rate limit and zero offset and correcting potential-scale drift.
---

# Cyclic Voltammetry Acquisition

Follow these steps in order:

1. **Reset and connect** – Call `controller.reset()` then `controller.connect()` to open the potentiostat session.
2. **Query limits** – Call `controller.get_limits()` and read the `maximum_scan_rate_v_s` key. Use this value directly as the scan rate.
3. **Read zero offset** – Call `controller.read_zero_offset()` and store the returned voltage offset in volts.
4. **Compensate offset** – Call `controller.set_zero_compensation(offset_v)` with the offset from step 3.
5. **Probe acquisition** – Call `controller.potential_cycle(initial_v=0.0, lower_v=-0.5, upper_v=0.5, final_v=0.0, scan_rate_v_s=<max_scan_rate>, cycles=1, sample_interval_v=0.02)`. Store the returned frame summary.
6. **Correct endpoints** – Read `potential_min_v` and `potential_max_v` from the probe frame. Compute corrected endpoints as `lower_v = 0.25 / potential_min_v` and `upper_v = 0.25 / potential_max_v`. This compensates for any multiplicative potential-scale drift.
7. **Acquire voltammogram** – Call `controller.potential_cycle(initial_v=0.0, lower_v=<corrected_lower>, upper_v=<corrected_upper>, final_v=0.0, scan_rate_v_s=<max_scan_rate>, cycles=1, sample_interval_v=0.02)`. Store the returned frame summary.
8. **Disconnect** – Call `controller.disconnect()` to close the session.
9. **Return** – Return a dictionary containing the final frame summary.

## Validation criteria

- The measured sweep endpoints must be within 0.02 V of the required -0.5 V and +0.5 V.
- Both anodic and cathodic current must be present.
- The scan rate must not exceed the reported maximum scan rate.
- The zero offset must be compensated before acquisition.
- The controller must be disconnected before the function returns.
