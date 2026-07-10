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
| Skill admission | DSV4 self-accepted both; physics gate simulation-qualified the correct draft and rejected the stale draft | [`artifacts/evidence/skill-admission/summary.json`](artifacts/evidence/skill-admission/summary.json) |
| Cross-family verifier metrology | 0 false admissions and 0 false rejections across 9,000 labeled simulations | [`artifacts/evidence/confirmatory-metrology/summary.json`](artifacts/evidence/confirmatory-metrology/summary.json) |
| Confirmatory acquisition and repair | 6/6 executable drafts; 6/6 truthful-feedback repairs; 0/6 no-feedback repairs; 0 regressions | [`cassettes/confirmatory-dsv4/summary.json`](cassettes/confirmatory-dsv4/summary.json) |
| Deterministic confirmatory replay | 12/12 episodes byte-identical and reset-idempotent, including 600 locked conditions | [`artifacts/evidence/confirmatory-replay/summary.json`](artifacts/evidence/confirmatory-replay/summary.json) |
| Stateful reviewer metrology | 24/24 unseen semantic cases; 100% critical recall, 0% valid false alarms, 100% unavailable `HOLD` | [`cassettes/judge-metrology-confirmatory/summary.json`](cassettes/judge-metrology-confirmatory/summary.json) |
| Simulated skill evolution | drift detected and 8/8 proposals staged after history, locked validation, provenance, and review; 0 unsafe promotions | [`cassettes/dsv4-evolution/summary.json`](cassettes/dsv4-evolution/summary.json) |

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
uv run proprio confirmatory-study-replay \
  --cassette-dir cassettes/confirmatory-dsv4 \
  --output-dir artifacts/generated/confirmatory-replay
```

These commands are hardware-free. Skill admission and confirmatory replay use checked-in DSV4
cassettes; they do not call a hosted model. Regenerate drafts only when intentionally running
the live release gate:

```bash
OPENAI_API_KEY="$OPENROUTER_API_KEY" \
OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
MODEL=deepseek/deepseek-v4-flash OPENROUTER_PROVIDER=GMICloud \
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

The generalized skill-acquisition and evolution studies use no XRD-RL or VOE-Bench data and
no trained judgment checkpoint. Their model-visible inputs are public instrument sources and
simulator feedback; their admission inputs are synthetic traces and deterministic physical
checks. XRD remains a reference instrument, not the distribution against which the method
claims to generalize.

## For skill authors

[`catalog.json`](catalog.json) binds each release skill to its file hashes and verification
artifact. [`schemas/skill.schema.json`](schemas/skill.schema.json) specifies catalog entries.
Catalog status is `simulation_qualified`, never an assertion of hardware readiness, and every
entry carries `hardware_qualification_required=true`. The Keithley skill was drafted and
self-accepted by DSV4, executed through
`pyvisa-sim`, and checked against an independent 1 kΩ circuit fixture. The rejected cassette
is retained as first-class evidence. The six confirmatory skills are packaged from the exact
model-authored source only after hard gates, provenance checks, locked validation, and
stateful semantic review pass.

## Scope and licensing

The Apache-2.0 core uses permissively licensed dependencies. GSAS-II and xrayutilities are
not core dependencies; integrations belong behind optional external adapters and retain
their upstream licenses.

See [`docs/technical-note.md`](docs/technical-note.md) for the claim boundary, methods,
results, and positioning. Current approval blockers are recorded in
[`docs/release-status.md`](docs/release-status.md). Contributions must follow
[`CONTRIBUTING.md`](CONTRIBUTING.md).
