from proprio.adaptive_microscopy_metrology import (
    EXPECTED_CHECK,
    MicroscopyFault,
    _evaluate_case,
)


def test_independent_generator_passes_valid_and_detects_each_fault() -> None:
    valid = _evaluate_case(MicroscopyFault.VALID, 1, 0)
    assert valid["observed_valid"]
    assert valid["failed_checks"] == []
    for index, fault in enumerate(MicroscopyFault):
        if fault is MicroscopyFault.VALID:
            continue
        row = _evaluate_case(fault, 100 + index, index)
        assert not row["observed_valid"], fault
        assert EXPECTED_CHECK[fault] in row["failed_checks"]
        assert row["expected_check_detected"]
