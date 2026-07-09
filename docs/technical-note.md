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

DSV4 drafted two Keithley 2450-style skills from supplied driver and fixture documents, then
self-judged both `ACCEPT`. The correct revision uses a 1 kΩ fixture at 1 V with 2 mA compliance
and a 10 mA range. A plausible stale worksheet instead specifies a 100 kΩ fixture, 200 µA
compliance, and a 100 µA range. PyVISA-sim supports YAML-defined simulated instruments and
their commands/properties
([PyVISA-sim documentation](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html));
Proprio executes both drafts against that transport and independently checks the current
against the 1 kΩ circuit law and the active range/compliance contract. The correct skill is
admitted; the self-accepted stale skill is rejected on range and compliance
([skill-admission artifact](../artifacts/evidence/skill-admission/summary.json),
[captured DSV4 cassettes](../cassettes/dsv4/)).

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
