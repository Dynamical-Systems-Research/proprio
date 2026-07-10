---
name: calibrated-pump-dose
description: Reset, calibrate, prime, deliver a precise 10.0 mL dose at up to 75 rpm, and halt.
---

# Calibrated pump-dose skill

1. **Reset** – Call `controller.reset()` to bring the pump to a known initial state.
2. **Calibrate** – Call `controller.calibrate(0.050)` to set the certified calibration to 0.050 mL/revolution.
3. **Prime** – Call `controller.prime(75)` to prime the tubing at 75 rpm.
4. **Deliver dose** – Call `controller.pump_volume(75, 10.0)` to deliver exactly 10.0 mL at 75 rpm.
5. **Halt** – Call `controller.halt()` to stop the pump.
6. Return an empty dictionary `{}`.

The delivered volume must be within 0.10 mL of the target 10.0 mL. The calibration value must remain 0.050 mL/rev. The pump must be stopped after the dose. Speed must not exceed the pump's supported maximum.
