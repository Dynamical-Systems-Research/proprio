---
name: dual-pump-blend
description: Run a simulator-qualified 6:4 dual-pump blend totaling 10.0 mL at 60 rpm with independent channel calibration and mandatory halt. Use with a compatible two-channel pump controller; do not use for unqualified hardware.
---

# Dual-Pump Blend

## Overview

Deliver 6.0 mL from channel A and 4.0 mL from channel B after independent calibration, then halt
both channels.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target pump array separately.

## Workflow

1. Reset the controller.
2. Calibrate A to 0.040 mL/revolution and B to 0.050 mL/revolution.
3. Prime both channels at 60 rpm.
4. Deliver 6.0 mL from A and 4.0 mL from B at 60 rpm.
5. Halt all channels before returning.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not swap channel calibrations or component volumes.
- Do not change one channel's speed independently.
- Do not return before `halt_all()`.
