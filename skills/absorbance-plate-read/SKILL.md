---
name: absorbance-plate-read
description: Run a simulator-qualified 600 nm absorbance plate read with blank subtraction and safe tray cleanup. Use when an agent has a compatible plate-reader controller and must acquire the validated reference measurement; do not use for unqualified hardware.
---

# Absorbance Plate Read

## Overview

Acquire paired blank and sample absorbance at 600 nm, preserve the validated 100 ms integration,
and leave the plate reader unloaded and shut down.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Treat the procedure as simulation-qualified only. Qualify the target reader separately.

## Workflow

1. Reset the reader, open the tray, load the plate, and close the tray.
2. Read the blank and sample at 600 nm with 100 ms integration.
3. Open the tray, unload the plate, and shut down the reader.
4. Return both raw readings. Compute net absorbance as sample minus blank downstream.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, simulator
conditions, independent checks, and hardware claim boundary.

## Common mistakes

- Do not omit the blank or change its acquisition settings relative to the sample.
- Do not leave the plate loaded or the reader active.
- Do not interpret simulator qualification as hardware validation.
