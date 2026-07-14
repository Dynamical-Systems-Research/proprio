---
name: clslab-light-spectrometer
description: Run a simulator-qualified CLSLab eight-channel light spectrum acquisition for RGB 40,60,20 with detector-limit discovery, adaptive gain, and source clearing. Use for compatible CLSLab controllers; do not use for unqualified hardware.
---

# CLSLab Light Spectrometer

## Overview

Acquire an eight-channel spectrum inside the detector counting range, adapting gain from observed
scalar extrema and clearing the source before returning.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target spectrometer separately.

## Workflow

1. Reset and read detector limits.
2. Configure `atime=100`, `astep=999`, and gain 64 for a ≥40,000-count range or 16 otherwise.
3. Set RGB to `(40, 60, 20)` and measure.
4. For at most eight corrections, halve gain after saturation or double it after insufficient
   signal, never exceeding the reported maximum gain.
5. Clear the source and return the final spectrum and extrema.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, pinned
simulator revision, independent checks, and hardware claim boundary.

## Common mistakes

- Do not recompute extrema from channel values; use the returned scalar fields.
- Do not use an unbounded gain loop.
- Do not return before clearing the source.
