# Proprio

Proprio is an open-source method for qualifying AI-generated scientific-instrument skills in
simulation before they are allowed near real hardware. It records whether an operation ran,
whether the resulting evidence is physically usable, and whether that evidence lies within a
declared support boundary. Real-hardware qualification remains a separate, required gate.

`simulation_qualified` means that a skill passed the released simulator, physical
postconditions, provenance checks, and locked validation set. It does not mean that the skill
is safe or qualified for an unsupervised physical instrument.

## Result

DeepSeek V4 Flash (DSV4) generated executable skills for six instruments across optical
measurement, calibrated delivery, and thermal control—three families held out from method
development. Starting from the same initial draft, truthful simulator feedback produced 6/6
qualified repairs; a no-feedback control produced 0/6. Every accepted repair preserved prior
behavior and passed 50 conditions that were hidden during repair. Independent verifier
metrology observed zero false admissions and zero false rejections across 9,000 labeled
simulations.

This is a held-out-method result, not a claim about the model's pretraining data. The
generalized skill-acquisition and evolution studies use no XRD-RL or VOE-Bench data, no trained
judgment checkpoint, and no external policy-training distribution.
XRD remains a reference instrument, not the distribution against which the method claims to
generalize.

| Question | Result | Evidence |
| --- | --- | --- |
| Can DSV4 draft runnable skills? | 6/6 initial drafts executed | [`cassettes/confirmatory-dsv4/summary.json`](cassettes/confirmatory-dsv4/summary.json) |
| Did simulator feedback cause the repairs? | 6/6 with truthful feedback versus 0/6 without feedback; paired uplift 1.0, bootstrap 95% interval [1.0, 1.0] | [`cassettes/confirmatory-dsv4/summary.json`](cassettes/confirmatory-dsv4/summary.json) |
| Did the independent gates separate valid from invalid operations? | 0 false admissions and 0 false rejections across 9,000 labeled simulations | [`artifacts/evidence/confirmatory-metrology/summary.json`](artifacts/evidence/confirmatory-metrology/summary.json) |
| Is the result reproducible without a hosted model? | 12/12 episodes replayed byte-identically and reset-idempotently, including 600 locked conditions | [`artifacts/evidence/confirmatory-replay/summary.json`](artifacts/evidence/confirmatory-replay/summary.json) |
| Could an agent reviewer override a physical failure? | No; 24/24 semantic cases passed with zero hard-gate overrides | [`cassettes/judge-metrology-confirmatory/summary.json`](cassettes/judge-metrology-confirmatory/summary.json) |
| Can an existing skill be updated after simulated drift? | 8/8 proposals were validated and staged; 0 unsafe promotions | [`cassettes/dsv4-evolution/summary.json`](cassettes/dsv4-evolution/summary.json) |

The six confirmatory skills are:

| Instrument family | Simulation-qualified skills |
| --- | --- |
| Optical measurement | absorbance plate read; fluorescence plate read |
| Calibrated delivery | calibrated pump dose; dual-pump blend |
| Thermal control | isothermal hold; thermal cycle |

They are packaged under [`skills/simulated/`](skills/simulated/) and bound to their source,
code, verifier, and evidence hashes in [`catalog.json`](catalog.json).

## Why instrument operation needs observability

An instrument can execute every command and still produce unusable evidence. A detector can
saturate, a sample can be displaced, a calibration can be stale, or an integration can fail.
Passing a command-level check is therefore necessary but insufficient for a scientific agent.

Proprio evaluates the complete path:

```text
operate -> procedural status -> measurement validity -> declared support -> judge
```

- **Procedural status** records whether the plan completed, degraded, failed, or was
  unavailable.
- **Measurement validity** checks acquisition and preprocessing against simulator state and
  instrument-specific physical postconditions.
- **Declared support** reports whether the evidence is within the operating domain declared by
  the consuming policy or substrate.

These results form one provenance-complete self-observation record. The record is deliberately
firewalled from scientific judgment: it may say that a diffraction pattern is valid evidence,
but it may not say that a phase assignment or scientific decision is correct.

## How a generated skill is qualified

1. The agent reads an instrument source bundle and drafts `SKILL.md` plus executable control
   code.
2. The draft runs against a simulator with explicit execution state and physical
   postconditions.
3. If the draft fails, the agent must inspect the simulator record before editing, cite the
   evidence identifiers it used, and replay the revised skill.
4. Deterministic gates check execution, physical validity, provenance, prior behavior, and a
   locked validation set that the agent cannot inspect during repair.
5. A stateful semantic reviewer may inspect sources, diffs, traces, and simulator state. It may
   veto or hold a candidate, but it cannot rescue a deterministic failure.
6. Only a qualifying candidate is added to the catalog, with exact hashes and
   `hardware_qualification_required=true`.

Hosted generation is not assumed to be byte-deterministic. The release stores raw model
messages, reasoning state, tool calls, simulator records, and validation results as cassettes;
CI replays the captured candidates deterministically.

## XRD reference implementation

Powder X-ray diffraction is the reference instrument because operation quality and evidence
quality are tightly coupled. The hardware-free reference uses Bluesky RunEngine and
`ophyd.sim` for procedural execution, an analytic NumPy forward model for Cu Kα LaB6 area-
detector frames, and pyFAI plus separate telemetry and statistical checks for verification.
The generator and verifier are intentionally different implementations.

The validity battery covers geometry miscalibration, zero shift, sample displacement,
detector saturation, dead-time distortion, insufficient counting statistics, cake-integration
failure, unindexed peaks, and an implausible lower tail of reduced chi-squared. Rietveld-style
fit checks are permitted only for calibrant or quality-control scans; unknown samples are
checked for acquisition and preprocessing integrity, not phase-model agreement.

| XRD check | Release result | Evidence |
| --- | --- | --- |
| Procedural fault injection | 5/5 failure classes detected; dropped frame labeled `degraded` | [`artifacts/evidence/procedural/summary.json`](artifacts/evidence/procedural/summary.json) |
| Valid calibrant controls | 0/300 false rejections | [`artifacts/evidence/metrology/report.md`](artifacts/evidence/metrology/report.md) |
| Invalid calibrant measurements | 0 observed false-valid results in 300 cases for each of 9 classes | [`artifacts/evidence/metrology/summary.json`](artifacts/evidence/metrology/summary.json) |
| Always-valid adversary | 2,700/2,700 invalid cases rejected | [`artifacts/evidence/metrology/summary.json`](artifacts/evidence/metrology/summary.json) |
| Declared-support battery | 100% out-of-support detection; 0% false alarms | [`artifacts/evidence/support/report.md`](artifacts/evidence/support/report.md) |
| Composed record | Valid path passed; a procedurally successful saturated frame failed validity | [`artifacts/evidence/composition/summary.json`](artifacts/evidence/composition/summary.json) |

The sample-displacement attribution check missed its specific label in 19/300 injected cases,
although every affected case was still rejected by an adjacent shift or indexing check. The
release-level false-valid requirement is closed; the attribution limitation is retained in the
report.

## Skill evolution under simulated drift

The evolution study begins with eight history-safe skills spanning liquid handling, battery
cycling, additive manufacturing, and quantum-transport measurements. After a versioned
simulator change, DSV4 must inspect the new failure, submit a bounded repair, replay the changed
condition, replay prior history, and pass 50 locked conditions. All eight proposals passed and
were staged with immutable parent, rollback, evidence, simulator, verifier, and validation
hashes. Staging does not replace the parent and does not cross the hardware gate.

The diagnostic model ablations and invalidated protocol runs are preserved under
[`cassettes/model-ablations/`](cassettes/model-ablations/) and
[`artifacts/invalidated/`](artifacts/invalidated/). They are not included in the confirmatory
generalization result.

## Reproduce the released evidence

Requirements: Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/). These commands require
no hardware and make no hosted-model calls.

```bash
git clone https://github.com/Dynamical-Systems-Research/proprio.git
cd proprio
uv sync --locked --extra dev

uv run proprio composition-battery \
  --output-dir artifacts/generated/composition

uv run proprio skill-admission \
  --cassette-dir cassettes/dsv4 \
  --output-dir artifacts/generated/skill-admission

uv run proprio confirmatory-study-replay \
  --cassette-dir cassettes/confirmatory-dsv4 \
  --output-dir artifacts/generated/confirmatory-replay
```

Run the full XRD and cross-family metrology batteries with:

```bash
uv run proprio metrology \
  --cases-per-class 300 \
  --output-dir artifacts/generated/metrology

uv run proprio confirmatory-metrology \
  --cases-per-class 300 \
  --output-dir artifacts/generated/confirmatory-metrology
```

Live generation is a separate release gate. To intentionally regenerate the development
skills through OpenRouter:

```bash
OPENAI_API_KEY="$OPENROUTER_API_KEY" \
OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
MODEL=deepseek/deepseek-v4-flash \
OPENROUTER_PROVIDER=GMICloud \
  uv run proprio draft-skills --cassette-dir artifacts/live/dsv4
```

## Integrating a policy or instrument

- Start with the complete XRD reference skill at
  [`skills/xrd-reference/SKILL.md`](skills/xrd-reference/SKILL.md).
- Implement the typed support boundary in `DistributionSupportHook`; v0.1 binds the reference
  to synthetic-substrate support, not DSV4's training distribution.
- Preserve the raw Bluesky event stream separately from the canonical record. The raw stream
  retains wall-clock timestamps and UIDs; the canonical record uses logical time,
  content-addressed IDs, and normalized values for byte-identical replay.
- Treat `failed`, `degraded`, and `unavailable` as distinct outcomes. A missing simulator or
  adapter is never a clean pass.
- Use [`schemas/skill.schema.json`](schemas/skill.schema.json) and the packaged confirmatory
  skills as the reusable template for another instrument family.

The optional MatteriX adapter remains honestly `unavailable`; see
[`docs/matterix-adapter.md`](docs/matterix-adapter.md). GSAS-II and xrayutilities are not core
dependencies and belong behind external adapters that retain their upstream licenses.

## Scope and limitations

Proprio v0.1 establishes a reproducible pre-deployment qualification method within the released
simulators. It does not establish safe autonomous operation on physical hardware. A real
deployment still requires instrument-specific adapters, interlock validation, real calibrant or
reference measurements, uncertainty and drift studies, reset and recovery testing, and an
independent instrument expert's sign-off.

The confirmatory panel contains six instruments and reduced-order simulators. It supports a
cross-family existence and replication claim, not universal generalization across scientific
instrumentation. DSV4 also served as the stateful semantic reviewer, so that reviewer is
correlated evidence; deterministic execution and physical gates remain the promotion authority.

See the [technical note](docs/technical-note.md) for methods, related work, model ablations,
protocol amendments, and the complete claim boundary. Release status and approvals are recorded
in [`docs/release-status.md`](docs/release-status.md), and every evidence artifact is bound in
[`artifacts/evidence/manifest.json`](artifacts/evidence/manifest.json).

## Repository map

| Path | Contents |
| --- | --- |
| [`src/proprio/`](src/proprio/) | simulators, verifiers, agent loop, replay, and CLI |
| [`skills/`](skills/) | XRD reference, Keithley development case, and simulation-qualified skills |
| [`sources/`](sources/) | model-visible instrument source bundles |
| [`cassettes/`](cassettes/) | captured model messages, tool calls, reviews, and deterministic results |
| [`artifacts/evidence/`](artifacts/evidence/) | release metrology, raw samples, records, and manifest |
| [`artifacts/invalidated/`](artifacts/invalidated/) | superseded or invalidated protocol evidence retained for audit |
| [`docs/`](docs/) | technical note, research protocol, amendments, and release status |

Proprio is licensed under Apache-2.0. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development and
validation requirements and [`CITATION.cff`](CITATION.cff) for citation metadata.
