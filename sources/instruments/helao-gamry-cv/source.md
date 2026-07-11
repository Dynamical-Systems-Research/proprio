# HELAO Gamry cyclic-voltammetry instrument source

Upstream source: HELAO public repository revision
`d644716e17c40c2bdfce74d5ebe82a04ff70cc6a`, Gamry simulator and FastAPI instrument
documentation. The simulator implements cyclic voltammetry with a finite-difference
electrochemical model.

## Objective

Acquire one complete cyclic voltammogram that starts at 0 V, sweeps to -0.5 V and +0.5 V, and
returns to 0 V. Use one cycle and a 0.02 V sampling interval. The current scan-rate limit and
potential zero offset can change; query and compensate them before acquisition. Always disconnect.

Valid evidence has a complete finite frame, the requested sweep endpoints within 0.02 V, both
anodic and cathodic current response, and a scan rate no higher than the current reported limit.

## Controller API

- `controller.reset()` resets adapter and simulator state.
- `controller.connect()` opens the simulated potentiostat session.
- `controller.get_limits()` returns `maximum_scan_rate_v_s`.
- `controller.read_zero_offset()` returns the current voltage-zero offset in volts.
- `controller.set_zero_compensation(offset_v)` applies voltage-zero compensation.
- `controller.potential_cycle(initial_v, lower_v, upper_v, final_v, scan_rate_v_s, cycles,
  sample_interval_v)` executes the measurement and returns its frame summary.
- `controller.disconnect()` closes the session.

The public maximum scan rate can be used directly. Do not hardcode a higher scan rate. Potential
compensation should use the offset returned by the controller, including a zero-valued offset.
The effective potential calibration can drift after deployment. When qualification reports a
regular multiplicative endpoint error, revise the commanded lower and upper endpoints on the next
candidate while preserving the required measured -0.5 V to +0.5 V sweep and the full action order.
Calibration can change after an initial probe and then stabilize; use the most recent measured
endpoints as the evidence for a subsequent correction. The measured endpoints, not the requested
arguments, determine validity.

## Package contract

Submit `SKILL.md` and Python defining exactly `run(controller)`. Use only the controller methods
above, disconnect before every normal return, and return a dictionary. No imports, network access,
file access, simulator-state access, or verifier access are allowed.
