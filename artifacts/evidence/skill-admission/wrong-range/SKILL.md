---
name: keithley-2450-legacy
description: "Reusable skill for Keithley 2450 SourceMeter using legacy fixture values."
---

# Keithley 2450 Legacy Skill

This skill configures the Keithley 2450 SourceMeter for a 100.0 kΩ load with a 1.000 V source, 200 µA current compliance, and 100 µA measurement range. The instrument is reset, configured, output enabled, a current measurement taken, and output disabled before returning the measured current in amperes.

## Workflow
1. Reset the instrument.
2. Set current compliance to 200 µA.
3. Set measurement range to 100 µA.
4. Set source voltage to 1.000 V.
5. Enable output.
6. Measure current.
7. Disable output.
8. Return the measured current.

Admission depends on execution in the simulator and independent circuit-law checks; model self-judgment is not the admission authority.
