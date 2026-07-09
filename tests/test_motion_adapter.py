from proprio.motion_adapter import MatteriXAdapterStub
from proprio.schema import StatusLabel


def test_unqualified_motion_adapter_fails_closed() -> None:
    result = MatteriXAdapterStub().load_and_align_sample("lab6-srm-660c")
    assert result.status is StatusLabel.UNAVAILABLE
    assert result.qualification_artifact is None
    assert "not qualified" in result.reason
