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
