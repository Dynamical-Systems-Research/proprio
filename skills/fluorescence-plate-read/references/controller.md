# Fluorescence plate-reader source bundle

Reference: [PyLabRobot PlateReader](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/plate_reading/plate_reader.py), whose public interface accepts excitation wavelength, emission wavelength, and focal height. This package uses a reduced-order fluorescence simulator.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.open_tray()`
- `controller.load_plate()`
- `controller.close_tray()`
- `controller.read_fluorescence_blank(excitation_nm, emission_nm, gain)` returning counts
- `controller.read_fluorescence(excitation_nm, emission_nm, gain)` returning counts
- `controller.unload_plate()`
- `controller.shutdown()`

## Nominal operation

Reset; open and load the reference plate; close the tray; read a blank and sample using 485 nm excitation, 520 nm emission, and gain 10; open and unload the plate; then shut down. Emission must exceed excitation, blank-subtracted sample signal must be 900–1600 counts, and neither reading may saturate. A changed detector can report a lower supported gain; preserve the wavelength pair and cleanup while reducing blank and sample gain together when feedback requires it.
