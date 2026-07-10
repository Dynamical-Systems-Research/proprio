# Absorbance plate-reader source bundle

Reference: [PyLabRobot PlateReader](https://github.com/PyLabRobot/pylabrobot/blob/main/pylabrobot/plate_reading/plate_reader.py), whose public interface includes tray control and wavelength-specific absorbance acquisition. This package uses a reduced-order optical simulator, not a qualified commercial reader.

## Package contract

Produce `SKILL.md` and Python code defining exactly `run(controller)`. The code has no imports and calls only the methods below. Return a dictionary.

## Controller methods

- `controller.reset()`
- `controller.open_tray()`
- `controller.load_plate()`
- `controller.close_tray()`
- `controller.read_blank(wavelength_nm, integration_ms)` returning blank absorbance
- `controller.read_absorbance(wavelength_nm, integration_ms)` returning sample absorbance
- `controller.unload_plate()`
- `controller.shutdown()`

## Nominal operation

Reset; open and load the reference plate; close the tray; read the blank at 600 nm with 160 ms integration; read the sample at the same wavelength and integration; open and unload the plate; then shut down. Net sample absorbance must be 0.75–0.85 AU, blank absorbance at most 0.05 AU, and the detector must not saturate. A changed detector can report a smaller supported integration time; preserve wavelength, blank/sample pairing, and cleanup while reducing both integrations when feedback requires it.
