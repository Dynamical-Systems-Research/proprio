---
name: openflexure-adaptive-autofocus
description: Run the staged OpenFlexure simulator autofocus procedure with calibration, bounded sweep and correction, repeated focus measurements, acquisition-budget control, and resource release. Use with the pinned OpenFlexure simulation controller; do not treat it as hardware-qualified.
---

# OpenFlexure Adaptive Autofocus

## Overview

Calibrate the camera, perform a centered autofocus sweep, correct the independently read stage
position, capture repeated focus evidence, and release simulator resources. This package publishes
a provider-replayed evolution of the demonstrated procedure; its evidence status is `STAGED`.

## Requirements

- Run the OpenFlexure microscope server at revision
  `d26b93e1be1093e9d696b634dd1f7dde3bb7142a` in simulation mode.
- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Preserve the 8.3-second incremental acquisition budget and ±1,000-step correction bounds.

## Workflow

1. Reset and run full camera calibration.
2. Run a centered 7,000-step autofocus sweep.
3. Apply a bounded 100-step probe and compare its readback with the sweep endpoint to infer stage
   polarity without accessing simulator internals.
4. Compute, clamp, and apply the polarity-correct residual move to the calibrated plane.
5. Settle, capture three repeated focus frames, release resources, and return all observations.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the proposal hash, pinned
simulator revision, changed/historical/locked replay results, and hardware claim boundary.

## Common mistakes

- Do not publish the earlier admitted parent as the current procedure; registered drift invalidated it.
- Do not substitute the public `relative_spread` diagnostic for the independent uncertainty gate.
- Do not omit repeated frames, settling, or resource release.
