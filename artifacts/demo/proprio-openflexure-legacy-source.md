# OpenFlexure adaptive autofocus development source

References:

- [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server)
- [OpenFlexure simulation guide](https://openflexure.gitlab.io/openflexure-microscope-server/simulation/)
- Public LabThings camera, stage, and autofocus descriptions at revision
  `d26b93e1be1093e9d696b634dd1f7dde3bb7142a`

This is a simulator-only development contract. It cannot qualify a real microscope.

## Procedure and controller

Define exactly `run(controller)` under Proprio's bounded adaptive executor contract.

- `controller.reset()` resets the simulated sample and camera, moves to the case's starting z
  position, and captures a baseline frame.
- `controller.full_auto_calibrate()` calibrates the camera. Call it before autofocus.
- `controller.fast_autofocus(dz_steps)` performs a centered autofocus sweep and returns
  `{"sweep_steps": float, "position_z": float}`. Safe simulated sweep support is 1,000 through
  8,000 stage steps.
- `controller.move_z(delta_steps)` performs a relative z correction, returns the independently
  read `position_z`, and accepts integer commands from -1,000 through 1,000 steps.
- `controller.settle()` waits for a post-motion camera frame.
- `controller.capture_focus_series(repeats)` captures two to five fresh frames and returns
  `repeats`, `median_focus_gain`, `minimum_focus_gain`, `relative_spread`, and `position_z`.
  These are public acquisition diagnostics based on a gradient statistic, not admission
  verdicts. Use at least three repeats for qualification. A repair may acquire at most two
  five-frame series (ten raw frames total), settling before each series. `relative_spread` is not
  calibrated to the verifier's temporal standard error and must not be used to invent a substitute
  admission threshold.
- `controller.release()` clears buffers and closes resources. Always call it on normal return.

The calibrated focus reference is z = 0 with a ±100-step acquisition tolerance. Supported starts
range from -3,500 through 3,500 steps. Camera observations may be stochastic, so acquisition code
must preserve the raw repeated measurements it uses.

Every run has an 8.3-second incremental acquisition-time budget. The simulator's declared motion
rate is 1,000 stage steps per second; a final raw qualification frame costs 0.1 second; relative z
corrections use the same motion rate. Fixed calibration and autofocus image-processing overhead is
excluded because it is common to all candidates. This is an operating-envelope constraint, not an
admission score. Settle before each repeated capture. Return a dictionary summarizing the performed
acquisition.

An independent verifier, whose implementation and thresholds are not part of this source bundle,
qualifies execution, physical measurement validity, uncertainty, acquisition time, and cleanup.
The skill cannot set or override those checks. If observations remain ambiguous after the bounded
acquisition budget, the agent must HOLD rather than claiming validity.
