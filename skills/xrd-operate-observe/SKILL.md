---
name: xrd-operate-observe
description: Run Proprio's simulated LaB6 XRD reference operation and interpret its composed self-observation record. Use for pre-deployment execution and evidence-validity checks; never use it to claim that a phase assignment or scientific decision is correct.
---

# XRD Operate and Observe

## Overview

Generate and inspect the procedural, measurement-validity, and support records for the simulated
LaB6 XRD reference workflow. This is a reference skill, not an admitted scientific judgment policy.

## Requirements

- Use the pinned Proprio environment.
- Treat the workflow as simulation validation only.
- Use `calibrant_qc` for indexing and goodness-of-fit checks. Unknown samples may only check
  acquisition and preprocessing integrity.

## Workflow

Run:

```bash
uv run proprio xrd-reference --output-dir artifacts/generated/xrd-reference
```

Read `self-observation.json` before any policy call. Require explicit procedural, validity, and
support statuses. Stop before judgment when procedural or validity verification is failed,
degraded, or unavailable. Treat an out-of-support result as a scope boundary, not invalid evidence.

## Verification

Read [`references/verification.json`](references/verification.json) for the composition evidence
binding and hardware claim boundary.

## Common mistakes

- Do not merge scientific judgment into the self-observation record.
- Do not interpret `degraded` or `unavailable` as passing.
- Do not treat reference execution as hardware qualification.
