# OpenFlexure microscope autofocus source bundle

References:

- [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server)
- [OpenFlexure simulation guide](https://openflexure.gitlab.io/openflexure-microscope-server/simulation/)
- Public LabThings descriptions at `/api/v3/camera/`, `/api/v3/stage/`, and
  `/api/v3/autofocus/` from revision
  `d26b93e1be1093e9d696b634dd1f7dde3bb7142a`

The server is an external GPL-3.0 simulator. Proprio does not redistribute or import its
implementation. The controller below is a thin adapter over its public camera, stage, and
autofocus actions. Real microscope qualification is outside this simulation study.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports,
uses only the methods below, executes a straight-line procedure, and returns a dictionary.

## Controller methods

- `controller.reset()` clears image buffers, loads the simulated sample, restores the declared
  image noise, moves the stage to the case's starting position, and captures a baseline frame.
- `controller.full_auto_calibrate()` calls the server's camera calibration workflow.
- `controller.fast_autofocus(dz_steps)` calls the server's centered autofocus sweep. The sweep
  begins `dz_steps / 2` below the current z-position and spans `dz_steps` total.
- `controller.settle()` waits for a fresh post-motion camera frame.
- `controller.capture_frame()` acquires the measurement frame through the camera API.
- `controller.release()` clears remote buffers and closes client resources.

## Measurement contract

Calibrate before autofocus. Under nominal simulated support, start 800 stage steps from the
calibrated focus plane and use a 2,000-step centered sweep. Settle, capture one complete frame,
and release resources. The independent gate requires the selected focus to lie within 100
steps of the calibrated reference plane, sufficient image dynamic range, no saturation, and
agreement between frequency-domain and spatial-domain focus improvements over the baseline.

A changed sample holder can place the start farther from the calibrated plane. Do not assume
the nominal sweep still covers focus. If execution evidence reports that the selected focus is
outside tolerance or the frame remains blurred, expand the centered sweep while preserving
calibration, settling, capture, and resource release.
