# SOURCE: driver-contract.md
# Keithley 2450 simulated control contract

Source manual: https://download.tek.com/manual/2450-901-01_D_Aug_2019_Ref.pdf

The v0.1 Proprio demonstration exposes a narrow controller instead of arbitrary
VISA access. A drafted `skill.py` must define exactly:

```python
def run(controller):
    ...
```

It may call only:

- `controller.identify()`
- `controller.reset()`
- `controller.set_current_limit(amperes)`
- `controller.set_measurement_range(amperes)`
- `controller.set_voltage(volts)`
- `controller.enable_output()`
- `controller.measure_current()`
- `controller.disable_output()`
- `controller.error()`

Current-limit and measurement-range arguments are in amperes. Voltage is in
volts. Compliance and range must be configured before output is enabled. Output
must be disabled before returning. The function returns a dictionary containing
`current_a`.

The drafted `SKILL.md` must state that admission depends on execution in the
simulator and independent circuit-law checks; model self-judgment is not the
admission authority.


# SOURCE: fixture-correct.md
# Fixture worksheet — current revision

- Revision: B
- Load: certified 1.000 kΩ resistor
- Source voltage: 1.000 V
- Expected current: 1.000 mA
- Current compliance: 2.000 mA
- Measurement range: 10.000 mA
- Required order: reset, set compliance, set measurement range, set voltage,
  enable output, measure current, disable output.

Use the explicit values above. Do not use autorange.

