---
name: xrd-operate-observe
description: >
  Run the Proprio simulated LaB6 XRD reference operation and interpret its composed
  self-observation record. Use for pre-deployment execution and evidence-validity checks;
  never use it to claim a phase assignment or scientific decision is correct.
version: 0.1.0
---

# XRD Operate and Observe

## Preconditions

- Use the pinned Proprio environment.
- Treat this as simulation validation only. Real hardware requires a separate qualification.
- Use `calibrant_qc` for indexing and goodness-of-fit checks. Unknown-sample records may only
  check acquisition and preprocessing integrity.

## Run

```bash
uv run proprio xrd-reference --output-dir artifacts/generated/xrd-reference
```

Read `self-observation.json` before any policy call. Require explicit statuses for procedural
execution, measurement validity, and substrate support. A
`degraded` or `unavailable` status is not a pass.

## Failure handling

- Stop before judgment if Procedural verification failed or degraded.
- Stop before judgment if Validity verification failed, degraded, or unavailable.
- Do not reinterpret a Support verification out-of-support result as evidence invalidity; it means this
  support contract does not cover the evidence.
- Keep judgment output separate from the self-observation record.

## Evidence

The release proof is `artifacts/evidence/composition/summary.json`. validity verification thresholds and
metrology live under `artifacts/evidence/metrology/`.
