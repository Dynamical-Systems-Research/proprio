# STAR-style channel transfer source bundle

References: [PyLabRobot Hamilton backends](https://github.com/PyLabRobot/pylabrobot) and
[PyHamilton](https://github.com/dgretton/pyhamilton). This is a reduced-order simulation
contract, not a qualified physical-device driver.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.initialize_channel()`
- `controller.aspirate_channel(volume_ul)`
- `controller.dispense_channel(volume_ul)`
- `controller.eject_tip()`

## Nominal operation

Initialize one channel, transfer exactly 120.0 µL, and eject an empty tip. The nominal
reported stroke capacity is 100.0 µL, so use a 100.0 µL stroke followed by a 20.0 µL stroke.
If simulator evidence reports a smaller capacity, repartition the same total across supported
strokes. Every aspiration must have a matching dispense before tip ejection.
