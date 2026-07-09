# Proprio

Proprio is a simulation-validated pre-deployment substrate for operating scientific
instruments and observing whether the evidence they produced is trustworthy enough to hand
to a policy. Real-hardware qualification is a separate, required deployment gate.

The v0.1 reference chain is:

```text
operate -> procedural status -> measurement validity -> declared support -> judge
```

Proprio emits the three middle results as one provenance-complete self-observation record.
The operation record is firewalled from scientific judgment: it can report execution,
validity, and support, but cannot claim that a phase assignment or scientific decision is
correct.

## Evidence at a glance

| Gate | Release result | Artifact |
| --- | --- | --- |
| Procedural faults | 5/5 injected failure classes detected; dropped frame labeled `degraded` | [`artifacts/evidence/procedural/summary.json`](artifacts/evidence/procedural/summary.json) |
| Valid controls | 0/300 false rejects | [`artifacts/evidence/metrology/report.md`](artifacts/evidence/metrology/report.md) |
| Invalid measurements | 0 observed false-valid in 300 cases for each of 9 classes | [`artifacts/evidence/metrology/summary.json`](artifacts/evidence/metrology/summary.json) |
| Adversarial validity | always-valid bot rejected on 2700/2700 invalid cases | [`artifacts/evidence/metrology/summary.json`](artifacts/evidence/metrology/summary.json) |
| Substrate support | 100% detection, 0% false alarms on the labeled battery | [`artifacts/evidence/support/report.md`](artifacts/evidence/support/report.md) |
| Composed trajectory | valid path passes; procedurally successful saturation fails validity | [`artifacts/evidence/composition/summary.json`](artifacts/evidence/composition/summary.json) |
| Skill admission | DSV4 self-accepted both; physics gate admitted the correct draft and rejected the stale draft | [`artifacts/evidence/skill-admission/summary.json`](artifacts/evidence/skill-admission/summary.json) |

The sample-displacement target check missed attribution in 19/300 injected cases. Every one
was still rejected by an adjacent shift/indexing check, so the release-level false-valid bar
is closed; the attribution weakness is reported rather than hidden. Simulation does not
cover fixture tolerances, hardware interlocks, radiation controls, or other real-instrument
qualification.

## Run the worked example

Requires Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Dynamical-Systems-Research/proprio.git
cd proprio
uv sync --locked --extra dev
uv run proprio composition-battery --output-dir artifacts/generated/composition
uv run proprio skill-admission \
  --cassette-dir cassettes/dsv4 \
  --output-dir artifacts/generated/skill-admission
```

Both commands are hardware-free. The Skill acquisition command replays checked-in DSV4 drafts; it does
not call a hosted model. Regenerate drafts only when intentionally running the live release
gate:

```bash
OPENAI_BASE_URL=http://100.70.91.108:8000/v1 MODEL=dsv4 \
  uv run proprio draft-skills --cassette-dir artifacts/live/dsv4
```

Run the full preregistered metrology battery with:

```bash
uv run proprio metrology \
  --cases-per-class 300 \
  --output-dir artifacts/generated/metrology
```

## For instrument operators

Start with [`skills/xrd-reference/SKILL.md`](skills/xrd-reference/SKILL.md). The canonical
record and raw Bluesky stream are linked but separate: wall-clock timestamps and RunEngine
UIDs stay in the raw stream, while logical time and content-addressed IDs make canonical
replay byte-identical.

The optional MatteriX boundary is intentionally `unavailable`; see
[`docs/matterix-adapter.md`](docs/matterix-adapter.md). It is not a simulated pass.

## For verifier authors

Thresholds are frozen in
[`src/proprio/data/metrology-preregistration.yaml`](src/proprio/data/metrology-preregistration.yaml).
The generator is an analytic NumPy Bragg-ring model; verification uses pyFAI integration plus
separate detector-telemetry, peak, and statistical checks. Do not tune thresholds against
the battery. The residual shared geometry, wavelength, and calibrant provenance is documented
in the metrology report.

Rwp, indexing, and the lower-tail chi-squared check are legal only for calibrant/QC scans.
Unknown-sample Validity verification checks are limited to acquisition and preprocessing integrity.

## For policy authors

Support verification implements `DistributionSupportHook`. v0.1 binds it to the synthetic substrate's
support—not DSV4's training distribution and not the XRD-RL/VOE-Bench corpus. The live demo
calls DSV4 only to prove that a real baseline policy can consume the record; the output is
honestly labeled `untrained_baseline` and stored separately under
[`artifacts/evidence/xrd-live/judgment/`](artifacts/evidence/xrd-live/judgment/).

## For skill authors

[`catalog.json`](catalog.json) binds each release skill to its file hashes and verification
artifact. [`schemas/skill.schema.json`](schemas/skill.schema.json) specifies catalog entries.
The admitted Keithley skill was drafted and self-accepted by DSV4, executed through
`pyvisa-sim`, and checked against an independent 1 kΩ circuit fixture. The rejected cassette
is retained as first-class evidence.

## Scope and licensing

The Apache-2.0 core uses permissively licensed dependencies. GSAS-II and xrayutilities are
not core dependencies; integrations belong behind optional external adapters and retain
their upstream licenses.

See [`docs/technical-note.md`](docs/technical-note.md) for the claim boundary, methods,
results, and positioning. Current approval blockers are recorded in
[`docs/release-status.md`](docs/release-status.md). Contributions must follow
[`CONTRIBUTING.md`](CONTRIBUTING.md).
