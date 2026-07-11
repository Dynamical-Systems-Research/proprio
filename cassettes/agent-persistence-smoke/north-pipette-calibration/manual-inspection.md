# Persistent-context live smoke: raw manual inspection

Inspection date: 2026-07-11. Inspector: Claude (research engineering session); human
countersignature pending. Evidence role: engineering smoke; not binding evidence.

## What was inspected

All sixteen raw files under `cassettes/agent-persistence-smoke/north-pipette-calibration/`:
six `raw-*.json` chat completions, nine `step-*.json` state checkpoints, and
`smoke-summary.json`.

## Findings

1. **Persisted history is resent.** The final checkpoint's message sequence is
   `system, user, user(verifier record), assistant, tool, tool, assistant, tool, assistant,
   tool, assistant, tool, user(verifier record), assistant, tool, assistant, tool`.
   Verifier records sit at message indexes 2 and 12; six assistant turns follow the first
   evidence message. Every model request after the first therefore contained the earlier
   assistant turns, tool results, and verifier evidence verbatim.
2. **Context growth matches persistence.** Per-call total tokens grow monotonically:
   15,620 → 18,971 → 27,701 → 29,253 → 38,654 → 46,724. No call shrank the context; no
   compaction was applied.
3. **Transport provenance is clean.** All six completions resolved to
   `deepseek/deepseek-v4-flash-20260423` on `GMICloud`, inside the DeepInfra/GMICloud
   allowlist. Usage and cost fields are present on every completion.
4. **Reasoning is preserved.** Every completion carries a populated
   `preserved_assistant_message` with reasoning content. The final call's reasoning
   reconciles both registered conditions, distinguishing preserved nominal behavior
   (`water-50ul`, unchanged) from the repaired condition (`glycerol-delivery-drift`,
   admitted after iterative correction) before finishing as `CANDIDATE`.
5. **The repair ledger is coherent.** One entry: diagnosis attributes the failure to fixed
   nominal overaspiration under `delivery_scale=0.8`, cites exactly the three exposed
   `debug:glycerol-delivery-drift:*:volume-accuracy` failure references, and the submitted
   change implements measured-relative-error compensation. Post-edit replay admitted; the
   entry's outcome is `CANDIDATE` and the summary verdict is `PASS`.

## Conclusion

The live transcript demonstrates the persistent agent context on real transport: earlier
tool results and verifier records appear in later model requests, reasoning survives the
round trip, and the provider contract held. This satisfies the pre-freeze live-persistence
gate for the v0.4 method.
