---
name: thermal-cycle
description: Run a simulator-qualified 60 C to 20 C thermal cycle with bounded stabilization, fixed dwells, and final deactivation. Use with a compatible heating and cooling controller; do not use for unqualified hardware.
---

# Thermal Cycle

## Overview

Heat to 60.0 °C, dwell for 300 seconds, cool to 20.0 °C, dwell for 120 seconds, and deactivate the
controller.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target thermal hardware separately.

## Workflow

1. Reset and set 60.0 °C.
2. Wait up to 240 seconds for 0.5 °C tolerance, then hold for 300 seconds.
3. Set 20.0 °C.
4. Wait up to 240 seconds for 0.5 °C tolerance, then hold for 120 seconds.
5. Deactivate before returning.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not reverse the setpoint sequence or hold before stabilization.
- Do not alter the dwell durations.
- Do not leave temperature control active.
