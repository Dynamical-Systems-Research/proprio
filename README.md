# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

[![CI](https://github.com/Dynamical-Systems-Research/proprio/actions/workflows/ci.yml/badge.svg)](https://github.com/Dynamical-Systems-Research/proprio/actions/workflows/ci.yml)

Point an agent at an instrument's documentation. Proprio gives it a persistent simulator loop for
drafting an operating skill, executing it, inspecting the evidence, and repairing what failed.
Independent execution and physical checks decide what enters the skill library.

Verified in simulation. Hardware validation remains separate.

[Technical report](https://dynamicalsystems.ai/blog/simulator-verified-skill-acquisition) ·
[Skill catalog](catalog.json) ·
[Published skills](skills) ·
[OpenFlexure full-loop demo](public/proprio-demo.mp4) ·
[Video evidence manifest](public/proprio-demo.json)

[![The OpenFlexure full-loop agent demo](docs/assets/proprio-demo-poster.jpg)](public/proprio-demo.mp4)

The demo shows a persistent GPT-5.6 Luna agent reading the development source in a live terminal while
the native OpenFlexure microscope simulator runs beside it. A fresh execution is rejected on its
acquisition-time budget, the agent repairs the skill to an admitted parent, a registered drift breaks
it, a first evolution proposal is rejected, and a corrected proposal is staged. This is a
development-trial demonstration, not a published OpenFlexure skill. Its
[evidence manifest](public/proprio-demo.json) binds the agent session, fresh simulator executions,
candidate hashes, verifier records, and media identity.

## Published skills

Every published package contains a `SKILL.md`, bounded control code where required, provenance hashes,
and a link to the record that admitted it. [`catalog.json`](catalog.json) binds each skill, source
bundle, control implementation, verifier, and admission record by hash.

| Instrument | Skill | Verification record |
| --- | --- | --- |
| 2D powder XRD | [XRD reference](skills/xrd-reference/SKILL.md) | [Composition record](artifacts/evidence/composition/summary.json) |
| Keithley 2450-style SMU | [Current measurement](skills/keithley-2450/SKILL.md) | [Admission record](artifacts/evidence/skill-admission/summary.json) |
| North Cytation | [Pipette calibration](skills/external/north-pipette-calibration/SKILL.md) | [Session record](cassettes/cross-family/north-pipette-calibration/session-000/summary.json) |
| HELAO Gamry | [Cyclic voltammetry](skills/external/helao-gamry-cv/SKILL.md) | [Session record](cassettes/cross-family/helao-gamry-cv/session-000/summary.json) |
| CLSLab | [Light spectroscopy](skills/external/clslab-light-spectrometer/SKILL.md) | [Session record](cassettes/cross-family/clslab-light-spectrometer/session-000/summary.json) |

## Quickstart

This takes one instrument source through drafting, visible simulator execution, evidence-guided
repair, and locked verification. You finish with a complete verification record and an ADMIT, REJECT,
or HOLD decision.

### 1. Install

```bash
git clone https://github.com/Dynamical-Systems-Research/proprio.git
cd proprio
uv sync --locked --extra dev --extra simulators
```

### 2. Install the example simulator

The adapter expects the pinned checkout under `/tmp/proprio-candidates`.

```bash
mkdir -p /tmp/proprio-candidates
git clone --filter=blob:none --no-checkout \
  https://github.com/AccelerationConsortium/North-Cytation \
  /tmp/proprio-candidates/North-Cytation
git -C /tmp/proprio-candidates/North-Cytation sparse-checkout set \
  sdl_pipette_calibration/protocols
git -C /tmp/proprio-candidates/North-Cytation checkout \
  3f49b5faba803a4a5d22544aa2ea5923ec513e20
```

### 3. Give the source to your agent

Any agent that can edit files and run commands can use Proprio. Inspect the source bundle, then ask
the agent to draft a skill from it alone.

```bash
mkdir -p runs/candidate
uv run proprio inspect-source \
  --instrument north-pipette-calibration > runs/source.json
```

> Read `runs/source.json`. Using only that source and its controller contract, create
> `runs/candidate/SKILL.md` and `runs/candidate/skill.py`. The Python entry point must be
> `run(controller)`. Do not inspect existing skills, cassettes, verifier code, or locked conditions.

### 4. Execute, inspect, and repair

```bash
uv run proprio execute-candidate \
  --instrument north-pipette-calibration \
  --candidate-dir runs/candidate \
  --output-dir runs/attempt-001
uv run proprio read-visible-evidence \
  --run-dir runs/attempt-001 > runs/attempt-001/evidence.json
```

If the decision is REJECT or HOLD, keep the same agent context and ask it to diagnose the failed
checks from `runs/attempt-001/evidence.json` and update only the candidate. Every attempt is
immutable; increment the attempt number for further repairs.

### 5. Run locked verification

Once a visible attempt returns ADMIT, run the independently held conditions. The agent does not see
these during drafting or repair.

```bash
uv run proprio verify-locked \
  --instrument north-pipette-calibration \
  --candidate-dir runs/candidate \
  --output-dir runs/locked
```

ADMIT means the candidate passed the registered simulation checks. Real hardware still requires
site-specific validation.

## Stage a skill evolution

After simulated deployment drift, stage a proposal only if it passes the changed condition and
replays the behavior that admitted its parent.

```bash
uv run proprio stage-evolution \
  --instrument north-pipette-calibration \
  --parent-dir runs/admitted \
  --candidate-dir runs/proposal \
  --output-dir runs/evolution
```

These operations are also importable from [`proprio.interface`](src/proprio/interface.py) as
`inspect_source`, `execute_candidate`, `read_visible_evidence`, `verify_locked`, and
`stage_evolution`. The agent owns its context; Proprio owns execution records and promotion.

## Reference verification

XRD is the reference instrument, using Bluesky and Ophyd for execution and an independent pyFAI-based
verifier. The Keithley example is the compact admission proof: circuit-law checks admit the correct
skill and reject a plausible wrong-range procedure the model accepted.

```bash
uv run proprio metrology --cases-per-class 300 --output-dir runs/metrology
uv run proprio composition-battery --output-dir runs/xrd-reference
uv run proprio skill-admission \
  --cassette-dir cassettes/skill-admission \
  --output-dir runs/skill-admission
```

## Repository map

- [`src/proprio`](src/proprio) contains the persistent agent, bounded runtime, adapters, and gates.
- [`sources`](sources) contains the documentation shown to the model.
- [`skills`](skills) contains the published skill packages.
- [`cassettes`](cassettes) contains raw model and execution records.
- [`artifacts/evidence`](artifacts/evidence) contains metrology and verification evidence.
- [`catalog.json`](catalog.json) is the content-addressed skill catalog.

## License and citation

Proprio is released under the [Apache License 2.0](LICENSE). Citation metadata is in
[`CITATION.cff`](CITATION.cff), and contribution requirements are in [`CONTRIBUTING.md`](CONTRIBUTING.md).
