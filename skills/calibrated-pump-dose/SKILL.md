---
name: calibrated-pump-dose
description: Run a simulator-qualified calibrated 10.0 mL pump dose at 75 rpm with mandatory halt. Use when an agent has a compatible peristaltic-pump controller and must execute the validated dosing procedure; do not use for unqualified hardware.
---

# Calibrated Pump Dose

## Overview

Calibrate a single pump, prime it, deliver 10.0 mL, and halt it within the simulator-qualified
operating envelope.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target pump separately.

## Workflow

1. Reset the controller.
2. Calibrate to 0.050 mL per revolution.
3. Prime at 75 rpm.
4. Deliver 10.0 mL at 75 rpm.
5. Halt before returning.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not dose before calibration or exceed the qualified speed.
- Do not return while the pump is running.
- Do not interpret simulator qualification as hardware validation.
