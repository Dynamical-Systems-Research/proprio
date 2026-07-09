# MatteriX adapter status

Proprio v0.1 adopts a fail-closed `MotionTwinAdapter` boundary and does not ship a MatteriX
runtime. The CPU XRD critical path is covered by Bluesky RunEngine and `ophyd.sim`.

`MatteriXAdapterStub.load_and_align_sample` always returns `unavailable`, states that no sample
was touched, and carries no qualification artifact. It cannot be mistaken for a successful
motion-twin run.

The optional GPU lane remains a release-external feasibility task:

1. establish that the MatteriX dependencies build and run on GB10 ARM64;
2. execute the same adapter contract against the GPU runtime;
3. capture per-action status and fault injection;
4. produce a separate qualification artifact before changing `unavailable` to another status.

This lane is not part of the Proprio v0.1 simulation-validation claim.
