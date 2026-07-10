# Held-out fixture-preflight manual inspection

Inspection date: 2026-07-10

Inspector: Codex agent

Human countersign authority: Jarrod approved the agent-produced structured inspection workflow;
no independent instrument-expert sign-off is claimed for this simulator-only panel.

## Scope

The three canonical raw records and their source-linked observations were read directly. The
inspection checks whether the structured summary reflects the observed upstream simulator state;
it does not reinterpret a failed contract or substitute a different simulator.

## OctoPrint virtual printer

- The pinned revision and observed revision both equal
  `800c56f226737a1aadf74a8251e2acfc14fb4b0f`.
- The nominal smoke is real: the uploaded and downloaded G-code hashes agree, the test job reaches
  100% completion, temperature enters the registered ±3 °C band, and heater targets return to zero
  with falling temperatures.
- The failure is also real: the upstream printer profile exposes no hotend/bed maximum, and the
  virtual printer exposes neither the registered heater-response shift nor a persistent readback
  offset. Those missing capabilities make the physical maximum check, repair fault, and drift
  event unavailable.
- The raw record therefore supports `FAIL` with honest status `HOLD`, not nominal admission.

## PyMoDAQ mock spectrometer

- The pinned revision equals `03ee39b672ce58a715cc29844fc45c9701a4ef3d`.
- Runtime discovery exposes `Mock` / `DAQ_1DViewer_Mock`; the selected `MockSpectro` identity is not
  present even though the README names it.
- Three acquisitions produced two 512-point channels. The first-channel Gaussian-fit
  R² values are approximately 0.647, below the registered 0.95 minimum; the second channel is
  approximately 0.980. Dropping the failed channel would be a post-exposure reinterpretation.
- `stop()` and `close()` expose no resource-state transition, and the registered reset,
  capability-query, and drift interfaces are absent.
- The raw record therefore supports `FAIL` with honest status `HOLD`.

## sinstruments Pace pressure controller

- The pinned sinstruments revision equals `da7c7235c59f8ac5117ea749264521c5e57374ff`.
- The 26-command raw transcript shows identification and stored-field access, while `*RST`, range,
  unit, and vent commands return `NACK`.
- Five pressure readings remain random values around a fixed base rather than responding to the
  commanded setpoint or output state. No physical trajectory, overshoot, settling, or vented state
  exists to verify.
- The Pace plugin is separately distributed and was not revision-pinned by the selected upstream
  repository, which independently prevents a reproducible binding fixture.
- The raw record therefore supports `FAIL` with honest status `HOLD`.

## Composition check

The summary contains exactly three registered instruments, three failed fixture preflights, zero
model calls, zero replacements, and zero aggregate rescues. Every row links to a canonical raw
record whose hash was recomputed during validation. The panel-level `FAIL` is an accurate
composition of the raw evidence.
