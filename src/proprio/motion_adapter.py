"""Optional procedural motion-twin adapter boundary.

The XRD critical path is fully exercised by Bluesky/Ophyd on CPU. MatteriX is
represented only by this honest conformance boundary in v0.1; no GPU execution
or sim-to-real qualification is claimed.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from proprio.schema import StatusLabel


class MotionTwinResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: str
    operation: str
    status: StatusLabel
    reason: str
    qualification_artifact: str | None = None


class MotionTwinAdapter(Protocol):
    adapter_id: str

    def load_and_align_sample(self, sample_id: str) -> MotionTwinResult: ...


class MatteriXAdapterStub:
    """Fail-closed v0.1 boundary for the optional MatteriX GPU lane."""

    adapter_id = "matterix-gpu-adapter-v0.1"

    def load_and_align_sample(self, sample_id: str) -> MotionTwinResult:
        return MotionTwinResult(
            adapter_id=self.adapter_id,
            operation="load_and_align_sample",
            status=StatusLabel.UNAVAILABLE,
            reason=(
                "MatteriX GPU execution and GB10 ARM64 feasibility are not qualified in v0.1; "
                f"sample {sample_id!r} was not touched"
            ),
        )
