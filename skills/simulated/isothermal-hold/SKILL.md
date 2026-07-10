---
name: isothermal-hold
description: Perform an isothermal hold at 80.0 °C for 600 seconds with temperature stabilization.
---

# Isothermal Hold

1. Reset the controller to its initial state.
2. Set the target temperature to 80.0 °C.
3. Wait for the temperature to reach 80.0 °C within ±0.5 °C tolerance, with a timeout of 200 seconds.
4. Hold the temperature steady for 600 seconds.
5. Deactivate the controller.
6. Return an empty dictionary.
