---
name: north-pipette-calibration
description: Run a simulator-qualified North Cytation pipette calibration with liquid-aware overaspiration, capacity checks, three replicates, evidence-guided correction, and cleanup. Use for compatible North-Cytation controllers; do not use for unqualified hardware.
---

# North Pipette Calibration

## Overview

Measure a requested water or glycerol volume, adapt overaspiration from observed delivery error,
and enforce accuracy, repeatability, capacity, and cleanup requirements.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target liquid handler separately.

## Workflow

1. Reset and read the liquid identity and target volume.
2. Read the current capacity constraints.
3. Initialize overaspiration at 2.5% of target for water or 6.25% for glycerol.
4. Measure three replicates at aspirate speed 20 with a one-second wait.
5. If relative error exceeds 4% or coefficient of variation exceeds 5%, correct overaspiration from
   the measured mean and repeat once.
6. Clean up before returning the final measurement.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, pinned
simulator revision, independent checks, and hardware claim boundary.

## Common mistakes

- Do not assume water calibration for glycerol.
- Do not skip capacity discovery or reduce replicate count.
- Do not return before cleanup.
