# Invalidated held-repair promotion leak

DSV4 returned HOLD after its five-frame repair failed the post-edit debug suite. A later single
stochastic replay admitted that code, and the archive incorrectly selected it because promotion
did not also require the captured agent terminal status. This run is excluded. Search now requires
both an independently admitting suite and `agent_status == CANDIDATE`; the uncertainty condition
also uses three independent skill executions.
