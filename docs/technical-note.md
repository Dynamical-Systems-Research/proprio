# Proprio v0.1: a self-observing instrument-operation substrate

## Claim

Proprio v0.1 is a **simulation-validated pre-deployment instrument-operation substrate**.
It does not establish that a policy can operate an unsupervised real instrument safely or
correctly. Fixture-specific tolerances, interlocks, radiation safety, failure recovery, and
operator sign-off remain part of a separate real-hardware qualification.

Within Dynamical's measure → train → deploy arc, the judgment line asks whether a policy can
make evidence-conditioned scientific decisions; the public
[`training-scientific-judgment`](https://github.com/Dynamical-Systems-Research/training-scientific-judgment)
release is the adjacent policy surface. Proprio supplies the operation-and-observability half
of deployment. v0.1 intentionally imports neither that checkpoint's training distribution nor
XRD-RL/VOE-Bench data. Its live policy call uses DSV4 as an explicitly untrained baseline, and
the future trained-policy binding remains a typed support hook.

The generalized skill-acquisition protocol is likewise independent of the judgment-policy
work: it uses public instrument source bundles, synthetic execution traces, and deterministic
physical-verifier records only. XRD is the reference operation, not training data, an
evaluation distribution, or a prerequisite for adding another instrument family.

## The composed gap

The ingredients are established, but serve different purposes. Bluesky documents both plan
introspection and execution with the real RunEngine over simulated hardware
([Bluesky simulation documentation](https://nsls-ii.github.io/bluesky/simulation.html));
Ophyd provides a hardware abstraction commonly paired with the RunEngine
([Ophyd repository](https://github.com/bluesky/ophyd)). pyFAI calibrates area-detector
geometry from reference compounds and performs signal-conserving azimuthal integration
([pyFAI documentation](https://pyfai.readthedocs.io/)). gpCAM addresses autonomous data
acquisition, uncertainty quantification, and next-measurement selection through Gaussian
processes ([LBNL gpCAM](https://gpcam.lbl.gov/)). MatteriX supplies a GPU-accelerated digital
twin for robotics-assisted chemistry workflows
([MatteriX paper](https://arxiv.org/abs/2601.13232)).

Proprio does not replace those systems. Its contribution is the end-to-end composition of:

1. procedural success;
2. physics-grounded evidence validity;
3. declared-distribution support;
4. a separately stored policy judgment;

plus a skill-admission mechanism that treats simulator and physics checks—not the drafting
model's own confidence—as authority.

## Reference instrument and firewall

The anchor is one Cu Kα, two-dimensional area-detector powder-XRD geometry using LaB6 as the
primary calibrant. A synthetic forward model produces raw frames from analytic Bragg-ring
geometry. The verifier uses pyFAI for integration and separate detector-telemetry,
peak-alignment, ring-fidelity, and calibrated statistical checks. The generator and verifier
share declared geometry, wavelength, and certified calibrant provenance, but do not share
image-generation or integration code. That remaining common provenance is an explicit
correlated-oracle risk.

Indexing, Rwp-like fit checks, and the lower-tail chi-squared check are restricted in code to
`calibrant_qc`. On an unknown sample, Validity verification may check acquisition and preprocessing integrity
but may not infer whether a phase model is correct. The canonical operation schema rejects
judgment and decision keys; DSV4 output is stored in a separate judgment record. The firewall
regression is in [`tests/test_schema.py`](../tests/test_schema.py).

The chi-squared check is not the invalid rule “χ² < 1 means bad.” It is a preregistered
lower-tail probability test conditioned on degrees of freedom and the calibrated uncertainty
model, and it runs only on calibrant/QC evidence. All operating points are frozen in
[`metrology-preregistration.yaml`](../src/proprio/data/metrology-preregistration.yaml).

## Results

Procedural verification runs Bluesky's RunEngine over `ophyd.sim` and injects motor stall, timeout, aborted
plan, dropped frame, and unreachable setpoint. All five classes are detected; the dropped
frame remains procedurally completed at the RunEngine level but is honestly labeled
`degraded` by frame-shape validation
([procedural artifact](../artifacts/evidence/procedural/summary.json)). The optional MatteriX adapter
is a fail-closed `unavailable` stub, not a clean pass.

Validity verification evaluates 300 valid controls and 300 cases for each of nine invalid classes. It records
0 false rejects and 0 observed false-valid results in every invalid class. The always-valid bot
has 0/2700 exploits. The sample-displacement target check misses direct attribution in 19/300
cases (AUROC 0.943); adjacent shift/indexing checks still reject every case. This is adequate
for the preregistered release-level false-valid bar, but the attribution result is weaker than
the other individual postconditions
([metrology report](../artifacts/evidence/metrology/report.md),
[raw cases](../artifacts/evidence/metrology/scored_cases.jsonl)).

Support verification is calibrated against the synthetic substrate support, not a policy's training data.
Across 300 in-support cases and 500 out-of-support cases, it records 0 false alarms and 100%
detection. Out classes include novel calibrants, wavelength excursions, non-finite input,
negative intensity, and unsupported shape
([support artifact](../artifacts/evidence/support/summary.json)). These results exceed the frozen
90% detection / 10% false-alarm bar on this synthetic battery; they do not measure OOD
detection against a trained judgment checkpoint.

The composed path produces a schema-validated record with a linked raw Bluesky stream and a
byte-deterministic canonical record. The adversarial trajectory is procedurally successful but
contains a saturated frame: Procedural verification succeeds, Validity verification fails, and Support verification remains a separate
support result ([composition artifact](../artifacts/evidence/composition/summary.json)). A live
DSV4 call consumed a valid record and returned `evidence_gate=proceed`, labeled
`untrained_baseline` ([judgment artifact](../artifacts/evidence/xrd-live/judgment/judgment.json)).

## Self-verifying skill acquisition

Voyager introduced an executable skill library and iterative improvement using environment
feedback, execution errors, and self-verification
([Voyager paper](https://arxiv.org/abs/2305.16291)). Hermes exposes `/learn` to draft a
`SKILL.md` from a directory, URL, workflow, or notes
([Hermes slash-command reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)).
Proprio adopts the learn-from-sources interface and changes the admission authority.

Two 2026 instrument-agent demonstrations sharpen the boundary. The agentic X-ray scientist
developed a sample-alignment workflow in a six-circle virtual beamline and then relayed its
commands through a human safety intermediary at SSRL
([Chen et al.](https://www.nature.com/articles/s42256-026-01261-5)). Vriza et al. describe a
human-in-the-loop, multi-agent pipeline for an X-ray nanoprobe and autonomous robotic station,
including iterative learning and code writer/reviewer roles
([Vriza et al.](https://www.nature.com/articles/s41524-026-02005-0)). Proprio does not claim a
stronger hardware result; it contributes a different simulator-only result: source-to-skill
acquisition, causal repair from execution evidence, independent physical admission, and
staged evolution under one reproducible protocol across instrument families.

Hermes `/learn` demonstrates open-ended skill authoring from local directories, URLs, prior
workflow, or notes, while Microsoft SkillOpt optimizes reusable text skills behind validation
gates ([Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#learning-a-skill-from-sources-learn),
[SkillOpt](https://github.com/microsoft/SkillOpt)). Proprio uses the same procedural-knowledge
shape but makes simulator execution, physical postconditions, provenance, and historical replay
the promotion authority for instrument-control code.

DSV4 drafted two Keithley 2450-style skills from supplied driver and fixture documents, then
self-judged both `ACCEPT`. The correct revision uses a 1 kΩ fixture at 1 V with 2 mA compliance
and a 10 mA range. A plausible stale worksheet instead specifies a 100 kΩ fixture, 200 µA
compliance, and a 100 µA range. PyVISA-sim supports YAML-defined simulated instruments and
their commands/properties
([PyVISA-sim documentation](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html));
Proprio executes both drafts against that transport and independently checks the current
against the 1 kΩ circuit law and the active range/compliance contract. The correct skill is
simulation-qualified; the self-accepted stale skill is rejected on range and compliance
([skill-admission artifact](../artifacts/evidence/skill-admission/summary.json),
[captured DSV4 cassettes](../cassettes/dsv4/)).

That Keithley result is a development case, not the generalization result. An initial
eight-instrument diagnostic panel spanning liquid handling, batteries, additive manufacturing,
and quantum transport showed that a hidden executor grammar was the dominant failure mode.
After the executor contract, historical replay, simulator-information firewall, and locked
validation protocol were fixed, those instruments remained method-development evidence and
were excluded from the confirmatory claim.

The separate confirmatory panel contains six source bundles across optical measurement,
calibrated delivery, and thermal control. These families were absent from method development.
The frozen method uses only public instrument sources, simulated execution state, and
deterministic physical records; it uses no XRD-RL data, VOE-Bench data, trained judgment
checkpoint, or external policy-training distribution. No claim is made about model pretraining.
DSV4 produced an executable nominal skill for all six instruments. Under a paired intervention
from the same initial draft, truthful simulator feedback produced 6/6 qualified repairs while
the no-feedback arm produced 0/6; the paired uplift was 1.0 with a bootstrap 95% interval of
[1.0, 1.0]. Every truthful repair preserved nominal behavior and passed 50 sealed conditions
that were unavailable during repair. The deterministic replay regenerated all 12 arm episodes,
including 600 locked-condition results, byte-identically with reset/idempotence intact
([confirmatory cassette](../cassettes/confirmatory-dsv4/summary.json),
[replay artifact](../artifacts/evidence/confirmatory-replay/summary.json)).

Independent verifier metrology generated 9,000 labeled simulations: 1,800 valid cases and
7,200 invalid cases covering wrong order, unsafe setting, wrong physical target, and omitted
cleanup for every confirmatory instrument. It observed zero false admissions and zero false
rejections. Thirty records selected by a fixed index rule were read individually; every trace,
telemetry record, failed check, and verdict matched its analytic label
([metrology artifact](../artifacts/evidence/confirmatory-metrology/summary.json),
[manual inspection](../artifacts/evidence/confirmatory-metrology/manual-inspection.md)).

The repair agent must inspect simulator output before editing, cite evidence identifiers that
actually appeared in the trace, and replay after the edit. A successful patch with fabricated
provenance is ineligible for packaging. The supplemental stateful agent judge can inspect
sources, diffs, traces, and replay, but it may only veto or hold; it cannot rescue a deterministic
failure. Invalidated judge-calibration runs are retained rather than folded into pass metrics
([protocol amendments](protocol-amendments.md)). This separation follows the debug-versus-locked
validation discipline of [NVIDIA ASPIRE](https://research.nvidia.com/labs/gear/aspire/) while
making instrument-specific execution and physical postconditions the admission authority.

The judge prompt was calibrated only on the diagnostic panel, then frozen. Its final battery
used 24 previously unseen semantic-mutation cases on the six confirmatory instruments. It
recorded 100% critical-defect recall, 0% false alarms on valid repairs, 100% honest `HOLD`
decisions for unavailable target execution, and zero hard-gate overrides. DSV4 serving as both
drafter and reviewer remains correlated secondary evidence; the deterministic simulator,
physical checks, provenance gate, and locked replay remain promotion authority
([judge metrology](../cassettes/judge-metrology-confirmatory/summary.json)).

Alternative-model runs were diagnostic, not confirmatory. On the shared eight-instrument
failure set, Qwen 3.7 Plus repaired all target failures but preserved history in only 6/8;
DeepSeek V4 Pro repaired and preserved 6/8. DSV4 Flash with the disclosed executor contract
repaired all eight and preserved 7/8. All three therefore failed the frozen zero-regression
gate, which is why the method added historical replay and why none of those runs supports the
final generalization claim. Qwen 3.6 Flash was stopped incomplete once DSV4 passed the separate
confirmatory panel; its partial artifacts are excluded from comparisons
([model-ablation cassettes](../cassettes/model-ablations/)).

## Simulation-valid skill evolution

The evolution study starts from eight history-safe parent skills in the diagnostic panel. A
versioned simulator change makes every parent fail under a new operating condition. DSV4 must
inspect the failure, cite its evidence, submit a bounded edit, replay the changed condition,
replay nominal and prior-repair history, and stop without seeing the locked validation set.
All eight evolved candidates passed nominal, prior-repair, drift, and 50 sealed conditions;
the stateful reviewer accepted all eight after receiving the complete intermediate event chain.
The proposals were staged with parent, rollback, evidence, simulator, verifier, and validation
hashes plus `hardware_gate_required=true`. None replaced its parent or crossed the hardware
gate. Offline replay regenerated all eight proposal statuses byte-identically with zero unsafe
promotions ([evolution result](../cassettes/dsv4-evolution/summary.json),
[replay](../artifacts/evidence/evolution-replay/summary.json)).

The first two additive-manufacturing reviews had falsely rejected real intermediate evidence
because their review tool exposed only the endpoint gates. Those reviews are preserved; the
replacement reviews received the same complete event closure as the deterministic provenance
gate, while candidate code and locked results remained unchanged
([protocol amendments](protocol-amendments.md)).

Hosted generation is not treated as byte-deterministic. CI deterministically replays the
captured drafts and verifies admission; fresh DSV4 generation is a separate release gate.
Reasoning fields are preserved in the raw assistant message even when the endpoint returns
`null` for these non-tool calls.

## What remains before hardware

The v0.1 evidence closes the simulation gates only. A real-instrument deployment still needs
qualified motion and detector adapters, hardware-specific fault injection, calibrant scans on
the target geometry, uncertainty and drift studies, interlock validation, reset/recovery tests,
and independent diffraction-expert sign-off. The raw synthetic inspection is recorded in
[`manual-inspection.md`](../artifacts/evidence/metrology/manual-inspection.md); the v0.1 human
countersignature is a release approval, not a substitute for the later independent expert.

## Reproduction

The complete hardware-free gate is encoded in [CI](../.github/workflows/ci.yml). It installs
from the lock file, runs lint and tests, regenerates the 300-per-class metrology battery, and
replays the procedural, support, composition, and skill-admission gates. All random cases use pinned seeds;
all release skills are hash-bound to [`catalog.json`](../catalog.json).
