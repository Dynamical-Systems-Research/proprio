---
name: keithley-2450-measure-current
description: "Measure current through a 1 kΩ resistor using a Keithley 2450 SourceMeter."
---

# Keithley 2450 Current Measurement

This skill configures the Keithley 2450 to source 1.000 V and measure the resulting current through a 1.000 kΩ load, with a current compliance of 2.000 mA and a measurement range of 10.000 mA.

## Workflow

1. Reset the instrument.
2. Set current compliance to 2.000 mA.
3. Set measurement range to 10.000 mA.
4. Set source voltage to 1.000 V.
5. Enable the output.
6. Measure the current.
7. Disable the output.
8. Return the measured current in amperes.

**Note:** Admission depends on execution in the simulator and independent circuit-law checks; model self-judgment is not the admission authority.
