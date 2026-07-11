---
name: light-spectrometer-spectrum-acquisition
description: Acquire an eight-channel spectrum for RGB (40,60,20) with adaptive gain, then clear the light source.
---

1. Reset the controller.
2. Retrieve detector limits via `get_limits()`.
3. Select starting gain: 64 if `maximum_signal` ≥ 40 000, otherwise 16.
4. Configure with `atime=100`, `astep=999`, and the selected gain.
5. Set the RGB source to (40, 60, 20).
6. Measure the spectrum.
7. If the measured `maximum_signal` exceeds the detector `maximum_signal` limit, halve the gain, reconfigure, and measure again. Otherwise if the measured `minimum_signal` is below 1 count, double the gain (capped at the detector's `maximum_gain`), reconfigure, and measure again. Repeat until both conditions are satisfied.
8. Clear the light source.
9. Return the spectrum data.
