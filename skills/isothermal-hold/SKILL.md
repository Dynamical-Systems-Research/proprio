---
name: isothermal-hold
description: Run a simulator-qualified 80.0 C isothermal hold for 600 seconds after bounded stabilization, then deactivate temperature control. Use with a compatible temperature controller; do not use for unqualified hardware.
---

# Isothermal Hold

## Overview

Reach 80.0 °C within 0.5 °C using a 200-second timeout, hold for 600 seconds, and deactivate the
controller.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target thermal hardware separately.

## Workflow

1. Reset the controller and set 80.0 °C.
2. Wait up to 200 seconds for 0.5 °C tolerance.
3. Hold for 600 seconds only after stabilization.
4. Deactivate before returning.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not start the hold before the setpoint has settled.
- Do not shorten the validated dwell or omit deactivation.
- Do not interpret simulator qualification as hardware validation.
