---
name: keithley-2450-measure-current
description: Run a simulator-qualified Keithley 2450-style current measurement by sourcing 1.000 V into a certified 1.000 kOhm load with explicit compliance, range, and output shutdown. Use for the validated fixture workflow; do not use for unqualified hardware.
---

# Keithley 2450 Current Measurement

## Overview

Configure explicit current protection and measurement range, source 1.000 V, measure current, and
disable output before returning.

## Requirements

- Provide a controller implementing [the bounded controller contract](references/controller.md).
- Use the certified 1.000 kΩ fixture represented by this skill.
- Treat the procedure as simulation-qualified only.

## Workflow

1. Reset the instrument.
2. Set current compliance to 2.000 mA and measurement range to 10.000 mA.
3. Set the source to 1.000 V and enable output.
4. Measure current, disable output, and return `current_a`.

Use [`scripts/operate.py`](scripts/operate.py) as the exact bounded implementation.

## Verification

Read [`references/verification.json`](references/verification.json) for the code hash, independent
circuit-law checks, and hardware claim boundary.

## Common mistakes

- Do not use the obsolete 100 kΩ worksheet or autorange.
- Do not enable output before setting compliance and range.
- Do not return while output is enabled.
