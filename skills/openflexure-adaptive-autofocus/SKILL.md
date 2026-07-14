---
name: openflexure-adaptive-autofocus
description: Run the staged OpenFlexure simulator autofocus procedure with calibration, bounded sweep and correction, repeated focus measurements, acquisition-budget control, and resource release. Use with the pinned OpenFlexure simulation controller; do not treat it as hardware-qualified.
---

# OpenFlexure Adaptive Autofocus

## Overview

Calibrate the camera, perform a centered autofocus sweep, correct the independently read stage
position, capture repeated focus evidence, and release simulator resources. This package publishes
the corrected evolution proposal demonstrated by Proprio; its evidence status is `STAGED`.

## Requirements

- Run the OpenFlexure microscope server at revision
  `d26b93e1be1093e9d696b634dd1f7dde3bb7142a` in simulation mode.
- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Preserve the 8.3-second incremental acquisition budget and ±1,000-step correction bounds.

## Workflow

1. Reset and run full camera calibration.
2. Run a centered 6,800-step autofocus sweep.
3. Compute and clamp the first relative correction; use the registered direction repair for a
   sweep ending above 400 steps.
4. Read position after motion, clamp the residual, and apply the second bounded correction.
5. Settle, capture three repeated focus frames, release resources, and return all observations.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the proposal hash, pinned
simulator revision, changed/historical/locked replay results, and hardware claim boundary.

## Common mistakes

- Do not publish the earlier admitted parent as the current procedure; registered drift invalidated it.
- Do not substitute the public `relative_spread` diagnostic for the independent uncertainty gate.
- Do not omit repeated frames, settling, or resource release.
