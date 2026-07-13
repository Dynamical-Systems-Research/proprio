# Proprio research handoff

## Decision

The v0.3 cross-family run was stopped on 2026-07-11 with the research lead's approval. The
next method revision must use a minimal persistent agent context across repair and evolution
cycles before the final experiment is frozen and rerun.

Do not resume the stopped process or rewrite its evidence. Treat v0.3 as a bounded baseline.

## Preserved v0.3 state

- Frozen method digest:
  `eef835db9ae74572d027618f19ffd15c0747664d3293204577defbc4114906b1`.
- Panel manifest digest:
  `2a68a79131b0dbdd5333c9c2995baeb1f6a366b5ba51324ec0f49c796d92ab39`.
- Model: `deepseek/deepseek-v4-flash`, resolved as
  `deepseek/deepseek-v4-flash-20260423`.
- Provider allowlist: DeepInfra and GMICloud.
- Stop record: [`run-stop.json`](../artifacts/evidence/generalization-v0.3/run-stop.json).

Binding outcomes at the stop:

| Instrument | Acquisition and locked qualification | Causal repair | Evolution | Status |
| --- | --- | --- | --- | --- |
| North pipette calibration | `ADMIT` / `PASS` | Truthful qualified in 1 episode; no-feedback failed 4 | `REJECTED` after 6 episodes | Complete |
| HELAO Gamry CV | Selected candidate and locked condition passed | Truthful qualified in 1 episode; no-feedback failed 4 | Drift detected; episodes 1 and 2 independently rejected | Stopped before session summary |
| CLSLab light spectrometer | Not run in binding panel | Not run | Not run | Not started |

The earlier engineering cassettes contain at least one executable, locked-condition-qualified
candidate for each family. They are development evidence, not substitutes for the incomplete
binding panel.

## Why the method changes

The current trajectory keeps state within one tool-calling episode, then creates a fresh agent
conversation for the next episode. It carries forward the current candidate and the latest
simulator/verifier suite, but not the prior assistant and tool-result history. That design is a
clean causal baseline, but it makes test-time compute reconstruct diagnoses and can repeat failed
strategies.

The next revision should maintain one persistent context per independent trajectory and causal
arm. The model API may remain stateless; Proprio owns and resends the context.

Persist only the minimal scientific state:

- assistant actions and tool results;
- current candidate and hashes;
- simulator and verifier records;
- a compact repair ledger of failed checks, diagnoses, edits, and outcomes;
- remaining search budget and exact model/provider configuration.

After a rejection, append the verifier record and continue the same agent loop. Branch truthful
and no-feedback arms from the same initial context and keep their histories separate. Compact
older messages only when required by the context budget; retain raw cassettes. Independent
execution, physical-validity, provenance, and locked-condition gates remain the sole promotion
authority.

This should remain a small loop, not a product framework. The relevant reference is the stateful
`AgentContext` plus `agentLoopContinue` pattern in
[`earendil-works/pi`](https://github.com/earendil-works/pi/tree/main/packages/agent).

## Required next experiment

1. Implement persistent context and deterministic checkpoint/resume.
2. Add tests proving rejected attempts and verifier evidence are present in the next model call.
3. Add a regression proving causal arms do not share post-branch history.
4. Measure qualification per model call, per token, repeated-strategy rate, and locked-condition
   success against the v0.3 bounded baseline.
5. Freeze the revised method before the final held-out run.
6. Run one complete session for North, HELAO, and CLSLab without changing the frozen method after
   exposure; report each family independently.

Do not claim a completed v0.3 cross-family binding panel, a 30-session rate estimate, or
cross-family evolution from the stopped evidence.

## Validation at handoff

- `uv run ruff check .`: pass.
- Ruff format check excluding the three byte-frozen v0.3 method sources: pass.
- `uv run pytest -q`: 266 passed.
- Clean-runner sparse checkouts of all three pinned external simulators: 10 generalization tests
  passed.
- Frozen method verification: pass.
- `public/proprio-openflexure-flagship.mp4`: continuous GPT-5.6 Luna full-loop take; H.264 High,
  1920x1080, 30 fps, 1328.967 seconds, decoded end to end. The exact release evidence is bound by
  `cassettes/openflexure-full-loop/session-001/manifest.json`.
