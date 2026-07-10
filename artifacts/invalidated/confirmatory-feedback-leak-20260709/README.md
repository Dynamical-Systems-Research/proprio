# Invalidated partial confirmatory run

This partial capture is excluded from every result and public claim.

Cause: `run_history` exposed the `repair` scenario while `repair` was the causal target, so
the no-feedback arm could inspect target-equivalent evidence. The run was stopped immediately
after detection. The corrected runner rejects target/history overlap and exposes nominal
history only during this comparison. See
`tests/test_instrument_agent.py::test_history_tool_rejects_target_scenario_leakage`.
