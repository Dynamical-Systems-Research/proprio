---
name: helao-gamry-cv
description: Run a simulator-qualified HELAO Gamry cyclic voltammogram from 0 V through -0.5 V and +0.5 V back to 0 V with limit discovery, zero compensation, endpoint correction, and disconnect. Use for compatible HELAO controllers; do not use for unqualified hardware.
---

# HELAO Gamry Cyclic Voltammetry

## Overview

Acquire a complete one-cycle voltammogram while compensating the reported zero offset and correcting
multiplicative potential-scale drift from a probe acquisition.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target potentiostat separately.

## Workflow

1. Reset, connect, and read the maximum supported scan rate.
2. Read and apply the voltage-zero offset.
3. Probe one 0 → -0.5 → +0.5 → 0 V cycle at 0.02 V sampling.
4. Correct commanded endpoints from the measured probe extrema.
5. Acquire the corrected cycle, disconnect, and return the final frame.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, pinned
simulator revision, independent checks, and hardware claim boundary.

## Common mistakes

- Do not exceed the reported scan-rate limit or ignore zero offset.
- Do not treat requested endpoints as measured endpoints.
- Do not return before disconnecting.
