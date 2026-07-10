# Proprio

Proprio is an open-source method for qualifying AI-generated scientific-instrument skills in
simulation before they are allowed near real hardware. It answers three separate questions:

1. Did the control procedure execute?
2. Did it produce physically usable evidence?
3. Is that evidence inside a declared operating support?

The resulting self-observation record is provenance-complete and firewalled from scientific
judgment. `simulation_qualified` means that a skill passed the released execution, physical,
provenance, regression, and locked-validation gates. It does **not** mean that the skill is
qualified for unsupervised use on a physical instrument. Real-hardware qualification remains a
separate, required gate.

## What v0.1 establishes

DeepSeek V4 Flash (DSV4) can acquire runnable instrument procedures from source bundles, use
simulator evidence to repair some failed drafts, and submit those repairs to an admission
system it cannot overrule. The strongest systematic result remains the frozen six-instrument
panel: 60/60 independent generations qualified across optical measurement, calibrated
delivery, and thermal control.

The harder external-simulator test did **not** clear the preregistered generalization bar.
Against a pinned OpenFlexure microscope server, all 10 drafts executed, but only 4/10 repaired
candidates passed target replay, history, provenance, terminal-status, and all locked physical
checks. The frozen requirement was at least 8/10 for every instrument. Proprio rejected the
other six and did not add a microscope skill to the public catalog.

Across the full 70-generation panel:

| Claim | Result | Frozen gate | Evidence |
| --- | ---: | ---: | --- |
| Initial code executed | 68/70 (97.1%; Wilson 95% CI 90.2–99.2%) | at least 75% per instrument | [`summary.json`](cassettes/replication-dsv4/summary.json) |
| Initial measurement was physically valid | 61/70 (87.1%) | reported separately | [`summary.json`](cassettes/replication-dsv4/summary.json) |
| Candidate fully qualified | 64/70 (91.4%; Wilson 95% CI 82.5–96.0%) | at least 80% per instrument | **FAIL**: OpenFlexure was 4/10 |
| Unqualified candidate promoted | 0/6 | zero | PASS |
| Original six-instrument panel | 60/60 qualified | at least 80% per instrument | PASS |

This is a held-out-method result, not a claim about model pretraining. These experiments
use no XRD-RL or VOE-Bench data, trained judgment checkpoint, or external policy-training
distribution. XRD remains a reference instrument, not the dataset against which generalization is
claimed.

## The proof ladder

Proprio advances one claim at a time. A later claim cannot pass when an earlier gate fails.

| Question | Evidence |
| --- | --- |
| Can DSV4 draft executable skills? | 68/70 independent drafts executed. |
| Can independent checks separate execution from valid evidence? | OpenFlexure produced 10/10 executable drafts but only 3/10 initially valid measurements; the gate preserved that distinction. |
| Did simulator feedback cause repair on the frozen panel? | From byte-identical drafts, truthful feedback qualified 6/6 while no feedback qualified 0/6; paired uplift 1.0, bootstrap 95% interval [1.0, 1.0]. |
| Does the method replicate across held-out families? | Yes for the original three reduced-order families (60/60); no for the external OpenFlexure family (4/10). |
| Can a model promote its own mistake? | No observed promotion: locked-validation failures and `MAX_TURNS` episodes remained rejected. |
| Can an admitted skill evolve under simulated drift? | 8/8 reduced-order development cases staged regression-safe proposals. The external OpenFlexure evolution attempt failed its hard gate and was not staged. |

Raw DSV4 messages, reasoning state, tool calls, simulator records, seeds, provider route, and
usage are retained under [`cassettes/replication-dsv4/`](cassettes/replication-dsv4/). The 70
generations used unique panel-global seeds, temperature 0.7, top-p 0.95, the pinned GMICloud
route, and 2,527,902 total tokens. The inspected sample includes one replicate from every
instrument and every failed microscope candidate.

## How qualification works

```text
instrument sources
      |
      v
draft skill -> execute in simulator -> inspect physical evidence -> repair and replay
                                                           |
                                                           v
                  provenance + history + locked conditions + semantic veto
                                                           |
                                      simulation-qualified or rejected
```

1. The agent reads an instrument source bundle and drafts `SKILL.md` plus executable control
   code.
2. The draft runs against a simulator with explicit state, failure semantics, and
   instrument-specific physical postconditions.
3. A repair must cite evidence identifiers actually exposed by the failed run, then replay the
   changed condition and prior behavior.
4. A locked condition set is revealed only after candidate selection. The agent cannot edit
   after seeing it.
5. A stateful semantic reviewer may inspect sources, diffs, traces, and fresh replay. It may
   veto or hold, but cannot rescue a deterministic failure.
6. A qualifying package is content-addressed and marked
   `hardware_qualification_required=true`.

Hosted generation is not assumed to be byte-deterministic. CI replays captured candidates and
canonical evidence; fresh hosted generation is a separate release experiment.

## External OpenFlexure stress test

The additional confirmatory family uses the
[OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server)
at revision `d26b93e1be1093e9d696b634dd1f7dde3bb7142a`, run as an external GPL-3.0 process through
its public LabThings/FastAPI interface. Proprio redistributes no OpenFlexure source. The model
received only the frozen instrument source bundle and public controller contract.

The physical verifier never imports the simulator's focus score. It checks public stage state,
frame integrity, calibrated focus position, normalized FFT high-frequency energy, and an
alternate SciPy Laplacian implementation. Both image checks must pass.

| OpenFlexure verifier result | Value |
| --- | ---: |
| Labeled cases | 2,700 |
| Invalid classes | 8 |
| False-valid | 0 |
| False-reject | 1/300 valid cases (0.33%) |
| Valid-case FFT/Laplacian concordance | 99.67% |
| Overall agreement | 90.59% |

The two image metrics share the exported frame and are therefore not statistically
independent. They use different domains, neither reads simulator internals, and public stage
position provides a third calibrated reference. The residual correlation is reported rather
than claimed away. See the [metrology record](artifacts/evidence/microscopy/locked/metrology/summary.json)
and [manual frame inspection](artifacts/evidence/microscopy/locked/manual-inspection.md).

The 4/10 qualification rate exposes two failure modes that a single demonstration would hide:

- four agents exhausted the turn budget without a terminal candidate;
- two plausible candidates passed the visible repair case but failed locked offsets.

One of those locked failures was a strict false rejection consistent with the measured
non-zero valid-case false-reject rate. The other was a fixture-specific repair. Both correctly
remained outside the catalog.

## Independent semantic review

Qwen 3.7 Plus served as a separately prompted, stateful reviewer. Its frozen rubric covers
provenance, hard-evidence consistency, API grounding, causal correspondence, regression and
cleanup, the simulation/hardware claim boundary, and honest uncertainty. The reviewer reads
sources, both skill versions, their diff, the complete execution record, and fresh replay. It
can reject or hold; deterministic gates remain authoritative.

The reviewer passed all 56 diagnostic calibration cases and all 42 cases on the original six
confirmatory instruments. The full 49-case confirmatory panel nevertheless failed two frozen
bars:

- the OpenFlexure `valid-repair` case was expected to be accepted, but fresh nominal replay
  failed FFT focus and regression checks, so Qwen correctly rejected the hard failure;
- the OpenFlexure `unavailable-evidence` case was expected to be held, but the captured fixture
  had silently changed the skill despite no repair submission, and fresh replay failed, so
  Qwen correctly rejected the unsupported change.

The raw result is therefore 47/49 label matches, 100% critical-defect recall, 14.3% valid-case
false alarm against the preregistered labels, 85.7% unavailable-label accuracy, and zero hard-
gate overrides. The semantic-review confirmatory verdict is **FAIL**, not a post-hoc pass. The
released fixture builder corrects the unavailable-case construction for future use, but the
captured result is unchanged.

On the 24 original cases shared with the DSV4 reviewer, exact agreement was 100% and Cohen's
κ was 1.0. That measures correlation; it does not make two agent judgments independent
physical evidence. See the [study summary](cassettes/independent-review/summary.json) and
[raw inspection](cassettes/independent-review/manual-inspection.md).

## XRD reference implementation

Powder X-ray diffraction is the reference because operation quality and evidence quality are
tightly coupled. The hardware-free implementation uses Bluesky RunEngine and `ophyd.sim` for
procedural execution, an analytic NumPy forward model for Cu Kα LaB6 area-detector frames,
and pyFAI plus separate telemetry and statistical checks for verification. The generator and
verifier are intentionally different implementations.

The validity battery covers geometry miscalibration, zero shift, sample displacement,
detector saturation, dead-time distortion, insufficient counting statistics, cake-integration
failure, unindexed peaks, and an implausible lower tail of reduced chi-squared. Fit checks are
restricted to calibrant or quality-control scans. Unknown samples are checked for acquisition
and preprocessing integrity, never phase-model correctness.

| XRD check | Result | Evidence |
| --- | --- | --- |
| Procedural fault injection | 5/5 classes detected; dropped frame labeled `degraded` | [`summary.json`](artifacts/evidence/procedural/summary.json) |
| Valid calibrant controls | 0/300 false rejections | [`report.md`](artifacts/evidence/metrology/report.md) |
| Invalid calibrant measurements | 0 observed false-valids in 300 cases for each of 9 classes | [`summary.json`](artifacts/evidence/metrology/summary.json) |
| Always-valid adversary | 2,700/2,700 invalid cases rejected | [`summary.json`](artifacts/evidence/metrology/summary.json) |
| Declared-support battery | 100% detection; 0% false alarms | [`report.md`](artifacts/evidence/support/report.md) |
| Composed record | Valid path passed; procedurally successful saturated frame failed validity | [`summary.json`](artifacts/evidence/composition/summary.json) |

The sample-displacement attribution check missed its specific label in 19/300 injected cases,
although adjacent shift or indexing checks still rejected every affected measurement. The
false-valid gate passes; the weaker attribution result remains visible.

## Engineering burden

Instrument-specific verification is real work. Proprio measures nonblank source lines,
declared checks, labeled failure classes, and external dependencies; it does not infer person-
hours from Git history.

| Family | Simulator / adapter LOC | Verifier LOC | Source-bundle LOC | Physical checks | Invalid classes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Optical measurement (2 instruments) | 130 | 107 | 30 | 7 each | 4 |
| Calibrated delivery (2 instruments) | 113 | 80 | 24 | 5 / 6 | 4 |
| Thermal control (2 instruments) | 100 | 50 | 24 | 7 each | 4 |
| OpenFlexure microscopy (external simulator) | 333 adapter | 162 | 32 | 10 | 8 |

The microscopy integration also required a 185-line metrology harness. Person-hours are
unavailable because prospective labor logging was not active. See the
[burden manifest](artifacts/evidence/engineering-burden/summary.json).

## Relationship to prior work

[Chen et al.](https://www.nature.com/articles/s42256-026-01261-5) directly demonstrate
iterative interaction with a virtual six-circle X-ray beamline and adaptation to an
approximately 1.22° motor offset on a real beamline. Their simulation benchmark used ten
independent runs per model; the authors explicitly state that the limited real-beamline trials
do not statistically establish the offset capability.

[Liu et al.](https://www.nature.com/articles/s41524-026-02005-0) demonstrate real scientific-
instrument operation and reusable memory from human feedback. That is operational
teachability, not simulator-grounded autonomous skill repair.

Proprio does not claim those systems lack adaptation, memory, simulation, or instrument
control. Its narrower contribution is a reproducible source-to-skill protocol in which
execution, physical validity, provenance, regression, and locked checks—not the drafting
model's confidence—control promotion. The protocol also adopts ASPIRE's separation between
debug feedback and locked validation while using instrument-specific physical postconditions
as authority ([ASPIRE](https://research.nvidia.com/labs/gear/aspire/)).

## Reproduce the hardware-free evidence

Requirements: Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Dynamical-Systems-Research/proprio.git
cd proprio
uv sync --locked --extra dev

uv run proprio composition-battery \
  --output-dir artifacts/generated/composition

uv run proprio confirmatory-study-replay \
  --cassette-dir cassettes/confirmatory-dsv4 \
  --output-dir artifacts/generated/confirmatory-replay

uv run proprio replication-study-summary \
  --cassette-dir cassettes/replication-dsv4
```

Run XRD and cross-family metrology with:

```bash
uv run proprio metrology \
  --cases-per-class 300 \
  --output-dir artifacts/generated/metrology

uv run proprio confirmatory-metrology \
  --cases-per-class 300 \
  --output-dir artifacts/generated/confirmatory-metrology

uv run proprio microscopy-metrology \
  --reference-dir artifacts/evidence/microscopy/locked/reference \
  --output-dir artifacts/generated/microscopy-metrology \
  --cases-per-class 300
```

Live generation is a separate, intentional gate:

```bash
OPENAI_API_KEY="$OPENROUTER_API_KEY" \
OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
MODEL=deepseek/deepseek-v4-flash \
OPENROUTER_PROVIDER=GMICloud \
DSV4_REASONING_EFFORT=high \
  uv run proprio replication-study-live \
    --output-dir artifacts/live/replication
```

## Add an instrument

- Begin with [`skills/xrd-reference/SKILL.md`](skills/xrd-reference/SKILL.md) and the packaged
  examples under [`skills/simulated/`](skills/simulated/).
- Define honest `succeeded`, `failed`, `degraded`, and `unavailable` outcomes.
- Separate simulator implementation from physical verification wherever possible; document
  residual shared assumptions.
- Author labeled valid and invalid batteries before model generation, then freeze thresholds,
  prompts, provider route, support, and locked conditions.
- Use [`schemas/skill.schema.json`](schemas/skill.schema.json), capture raw event provenance,
  and require historical replay before staging evolution.
- Keep operation records free of phase assignments, decisions, or other scientific-judgment
  claims.

The optional MatteriX adapter remains honestly `unavailable`; see
[`docs/matterix-adapter.md`](docs/matterix-adapter.md). GSAS-II and xrayutilities remain behind
external adapters that preserve their upstream licenses.

## Scope and limitations

Proprio v0.1 supports a rigorous simulation-only qualification method. It does not establish
safe autonomous operation on physical hardware. Deployment still requires hardware adapters,
interlock and recovery tests, reference measurements on the target geometry, uncertainty and
drift studies, supervised canaries, and instrument-expert sign-off.

The reduced-order panel demonstrates repeatable acquisition and causal repair within three
families; it is not universal generalization. The external OpenFlexure result is deliberately
reported as a failed breadth gate. Simulator–verifier independence is imperfect, model
generation remains stochastic, and per-instrument physical contracts require specialist
engineering. These are the research boundary, not release footnotes.

See the [technical note](docs/technical-note.md), [research protocol](docs/research-agenda.md),
[protocol amendments](docs/protocol-amendments.md), and
[release status](docs/release-status.md). Every released skill remains hash-bound in
[`catalog.json`](catalog.json); every evidence artifact is bound in
[`artifacts/evidence/manifest.json`](artifacts/evidence/manifest.json).

## Repository map

| Path | Contents |
| --- | --- |
| [`src/proprio/`](src/proprio/) | simulators, verifiers, agent loop, replay, and CLI |
| [`skills/`](skills/) | XRD reference, Keithley development case, and qualified skills |
| [`sources/`](sources/) | model-visible instrument source bundles |
| [`cassettes/`](cassettes/) | raw model messages, tool calls, reviews, and deterministic results |
| [`artifacts/evidence/`](artifacts/evidence/) | metrology, raw samples, canonical records, and manifest |
| [`artifacts/invalidated/`](artifacts/invalidated/) | excluded protocol runs retained for audit |
| [`docs/`](docs/) | technical note, protocol, amendments, and release status |

Proprio is Apache-2.0 licensed. External simulators retain their upstream licenses. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CITATION.cff`](CITATION.cff).
