# Invalidated semantic-judge run

This partial run is excluded from all reported metrics. The stateful semantic reviewer accepted
a fabricated-evidence case because the final code replayed successfully, despite noting that the
cited evidence was circular and ungrounded. Execution correctness and evidence provenance are
conjunctive admission requirements. The run was stopped, quarantined, and replaced only after a
deterministic provenance gate and regression test were added.
