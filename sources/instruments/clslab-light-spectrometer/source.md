# CLSLab:Light spectrometer source

Upstream source: `self-driving-lab-demo` revision
`34e4e8cd880bc7b788109d8a56da3f6fae978518`. Its `SensorSimulatorLight` combines measured RGB
LED basis spectra with AS7341 integration-time and gain behavior to produce an eight-channel
spectrum.

## Objective

Acquire a usable spectrum for RGB values (40, 60, 20), then clear the light source. Use `atime=100`
and `astep=999`. Select a gain compatible with the currently reported maximum signal. The detector
range may narrow or its effective gain may drift, so a fixed high gain is not reliable.

Valid evidence contains eight finite, nonnegative channels, a minimum signal of at least 1 count,
no channel above the current maximum, and a dark response after clear no greater than numerical
zero.

## Controller API

- `controller.reset()` resets the acquisition state.
- `controller.get_limits()` returns `maximum_signal`, `maximum_gain`, `maximum_atime`, and
  `maximum_astep`.
- `controller.configure(atime, astep, gain)` configures detector integration and gain.
- `controller.set_rgb(red, green, blue)` sets the simulated light source.
- `controller.measure()` returns a dictionary with exactly `channels` (the integer channel count),
  `minimum_signal`, `maximum_signal`, and `spectrum` (a dictionary of eight named channel values).
- `controller.clear()` turns the source off and records a dark measurement.

Use the returned scalar `minimum_signal` and `maximum_signal` fields for range decisions; do not
recompute extrema by iterating over `spectrum`. If a measured maximum exceeds the limit returned
by `get_limits()`, reduce the numeric gain with ordinary division, reconfigure, and measure again.
Gain calibration can change after an initial measurement and then stabilize, so use the most
recent scalar extrema for a subsequent correction. The bounded executor does not provide `min`,
`max`, floor division, or loop `break`.

Gain 64 is a normal starting point when the maximum signal is at least 40,000 counts. Gain 16 is a
conservative starting point for a narrower range. Detector gain calibration can drift; a counting-
range failure reports the observed minimum, maximum, and current maximum allowed signal so the
gain can be reduced on the next candidate. Simulator evidence, not either starting value,
determines qualification.

## Package contract

Submit `SKILL.md` and Python defining exactly `run(controller)`. Use only the controller methods
above, clear before every normal return, and return a dictionary. No imports, network access, file
access, simulator-state access, or verifier access are allowed.
