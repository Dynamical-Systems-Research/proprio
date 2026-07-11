# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

Proprio turns instrument documentation into executable skills, tests those skills against a
simulator and an independent physical contract, and admits only candidates that pass. The model
can inspect execution evidence and repair its work, but it cannot promote its own mistakes.

This is a pre-deployment qualification method. A simulation-qualified skill still requires a
separate real-hardware qualification before operating an instrument without supervision.

![The agent-to-instrumentation gap](docs/assets/agent-to-instrumentation-gap.png)

## How it works

```text
instrument sources
      ↓
persistent agent context
      ↓
draft → execute → inspect evidence → repair
      ↓
independent execution and physical qualification
      ↓
locked replay → ADMIT / REJECT / HOLD
      ↓
deployment drift → validated evolution proposal
```

The agent owns the skill and its working context. Proprio owns the simulator interface,
qualification contract, locked conditions, and promotion decision. Each trajectory is checkpointed
after tool results and verifier records, so interrupted work can resume without repeating completed
model calls. The complete method contract is in
[`method.yaml`](src/proprio/data/method.yaml).

## Cross-family result

The binding panel used one frozen method across three external simulator families. Each initial
skill executed but failed physical qualification, giving the agent a real repair problem rather
than a syntax-only task.

| Instrument | Family | Qualified after feedback | Locked replay | Drift evolution staged |
| --- | --- | ---: | ---: | ---: |
| North Cytation pipette calibration | calibrated liquid delivery | yes | pass | yes |
| HELAO Gamry cyclic voltammetry | electrochemical measurement | yes | pass | yes |
| CLSLab light spectrometer | spectral measurement | yes | pass | yes |

All three sessions passed the complete protocol, with zero invalid promotions. The truthful
feedback arm qualified in 3/3 families; the no-feedback comparison qualified in 1/3. With one
session per family, that comparison is descriptive rather than a rate estimate. Raw model messages,
tool results, simulator records, selection seals, and summaries are in
[`cassettes/cross-family`](cassettes/cross-family), and the admitted skills are in
[`skills/external`](skills/external).

The panel used `deepseek/deepseek-v4-flash` through OpenRouter. The three external families were
screened for executable simulator access before model use; they are not claimed as untouched
first-exposure families. The binding evidence is byte-bound to commit
[`c2cd6be`](https://github.com/Dynamical-Systems-Research/proprio/tree/c2cd6be). This release removes
superseded study code and preserves the original evidence through that pinned commit.

## Install

```bash
git clone https://github.com/Dynamical-Systems-Research/proprio.git
cd proprio
uv sync --locked --extra dev --extra simulators
```

The cross-family adapters expect these pinned simulator checkouts under
`/tmp/proprio-candidates`:

```bash
mkdir -p /tmp/proprio-candidates

git clone --filter=blob:none --no-checkout \
  https://github.com/AccelerationConsortium/North-Cytation \
  /tmp/proprio-candidates/North-Cytation
git -C /tmp/proprio-candidates/North-Cytation sparse-checkout set \
  sdl_pipette_calibration/protocols
git -C /tmp/proprio-candidates/North-Cytation checkout \
  3f49b5faba803a4a5d22544aa2ea5923ec513e20

git clone --filter=blob:none --no-checkout \
  https://github.com/helgestein/helao-pub \
  /tmp/proprio-candidates/helao-pub
git -C /tmp/proprio-candidates/helao-pub sparse-checkout set driver
git -C /tmp/proprio-candidates/helao-pub checkout \
  d644716e17c40c2bdfce74d5ebe82a04ff70cc6a

git clone --filter=blob:none --no-checkout \
  https://github.com/sparks-baird/self-driving-lab-demo \
  /tmp/proprio-candidates/self-driving-lab-demo
git -C /tmp/proprio-candidates/self-driving-lab-demo sparse-checkout set src
git -C /tmp/proprio-candidates/self-driving-lab-demo checkout \
  34e4e8cd880bc7b788109d8a56da3f6fae978518
```

Set an OpenAI-compatible model endpoint, freeze the complete method, then run a session or the full
panel:

```bash
export OPENAI_API_KEY="$OPENROUTER_API_KEY"
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export MODEL=deepseek/deepseek-v4-flash
export OPENROUTER_PROVIDER=DeepInfra,GMICloud
export DSV4_REASONING_EFFORT=high

uv run proprio cross-family-freeze --output-dir runs/method-freeze
uv run proprio cross-family-session \
  --instrument north-pipette-calibration \
  --freeze runs/method-freeze/manifest.json \
  --output-dir runs/north-pipette-calibration
```

The simulator and qualification gates, not the model's self-judgment, determine the final status.
Unavailable or ambiguous evidence produces `HOLD`; a failed execution, physical check, provenance
check, or locked replay produces `REJECT`.

## XRD reference workflow

XRD is the reference instrument because it connects Proprio to Dynamical's earlier physical-
judgment work. The reference workflow uses Bluesky and Ophyd for procedural execution, an
independent synthetic LaB6/Si generator and verifier for measurement validity, and a typed support
check before evidence reaches a policy. It does not use XRD-RL or VOE-Bench data.

```bash
uv run proprio procedural-battery --output-dir runs/procedural
uv run proprio metrology --cases-per-class 300 --output-dir runs/metrology
uv run proprio support-battery --output-dir runs/support
uv run proprio composition-battery --output-dir runs/xrd-reference
```

The Keithley 2450 example provides the compact admission proof: a correct drafted skill is admitted,
while a plausible wrong-range skill that the model accepted is rejected by circuit-law checks.

```bash
uv run proprio skill-admission \
  --cassette-dir cassettes/dsv4 \
  --output-dir runs/skill-admission
```

## Repository map

- [`src/proprio`](src/proprio): persistent agent, bounded skill runtime, simulators, and gates
- [`sources/instruments`](sources/instruments): instrument source bundles used by the model
- [`skills`](skills): reference and simulation-qualified skill packages
- [`cassettes`](cassettes): raw model and qualification records
- [`artifacts/evidence`](artifacts/evidence): metrology, freeze, and composition evidence
- [`catalog.json`](catalog.json): content-addressed skill catalog

The [OpenFlexure demo](public/proprio-openflexure-flagship.mp4) illustrates the same
documentation-to-simulation repair loop used during method development.

## License and citation

Proprio is released under the [Apache License 2.0](LICENSE). See
[`CITATION.cff`](CITATION.cff) for citation metadata and [`CONTRIBUTING.md`](CONTRIBUTING.md) for
development and verification requirements.
