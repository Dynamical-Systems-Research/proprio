# OT-2-style transfer source bundle

References: [PyLabRobot](https://github.com/PyLabRobot/pylabrobot) and the
[Acceleration Consortium OT-2 connector](https://github.com/AccelerationConsortium/opentrons-ot2).
This source defines a reduced-order simulation contract; it does not claim compatibility with
an unqualified physical OT-2.

## Package contract

Produce a `SKILL.md` and Python code defining exactly `run(controller)`. The code has no
imports and may call only the methods below. It returns a dictionary.

## Controller methods

- `controller.reset()`
- `controller.pick_up_tip()`
- `controller.aspirate(volume_ul)`
- `controller.dispense(volume_ul)`
- `controller.drop_tip()`

## Nominal operation

Reset, pick up one clean tip, transfer exactly 120.0 µL from the source to the destination,
then drop the empty tip. The nominal simulator reports a 120.0 µL maximum stroke, so one
aspirate/dispense pair is allowed. A deployed instrument can report a smaller stroke capacity;
split the transfer into equal or unequal strokes if execution evidence requires it. Never
discard residual liquid in a tip.
