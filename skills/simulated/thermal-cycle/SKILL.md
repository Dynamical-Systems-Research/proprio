---
name: thermal-cycle
description: Performs a thermal cycling protocol, heating to 60 C then cooling to 20 C with dwells and deactivation.
---

# Thermal-cycle instrument skill

1. Reset the controller to its initial state.
2. Set the target temperature to 60.0 °C.
3. Wait for the temperature to settle within 0.5 °C of the setpoint, with a timeout of 240 s.
4. Hold the temperature steady for 300 s.
5. Set the target temperature to 20.0 °C.
6. Wait for the temperature to settle within 0.5 °C of the setpoint, with a timeout of 240 s.
7. Hold the temperature steady for 120 s.
8. Deactivate the controller (disable heating/cooling).
