---
name: fluorescence-plate-read
description: Run a simulator-qualified fluorescence plate read using 485 nm excitation, 520 nm emission, gain 7, paired blank subtraction, and safe tray cleanup. Use with a compatible plate-reader controller; do not use for unqualified hardware.
---

# Fluorescence Plate Read

## Overview

Acquire paired blank and sample fluorescence with matched optical settings, then unload the plate
and shut down the reader.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target reader separately.

## Workflow

1. Reset the reader, open the tray, load the plate, and close the tray.
2. Read the blank at 485 nm excitation, 520 nm emission, and gain 7.
3. Read the sample with the identical settings.
4. Open the tray, unload the plate, and shut down the reader.
5. Return both raw readings.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not change gain or wavelengths between blank and sample.
- Do not reverse excitation and emission wavelengths.
- Do not leave the plate loaded or the reader active.
