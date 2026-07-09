from __future__ import annotations

import ast
import inspect

import pytest

import proprio.xrd_generator as generator_module
from proprio.schema import StatusLabel
from proprio.xrd_generator import generate_calibrant_frame
from proprio.xrd_types import ValidityFault
from proprio.xrd_verifier import verify_calibrant_frame


def test_generator_is_independent_of_pyfai() -> None:
    tree = ast.parse(inspect.getsource(generator_module))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.lower().startswith("pyfai") for name in imports)


@pytest.mark.parametrize("calibrant", ["lab6", "si"])
def test_valid_calibrant_frame_passes(calibrant: str) -> None:
    case = generate_calibrant_frame(calibrant=calibrant, seed=11)
    result = verify_calibrant_frame(case)
    assert result.record.status is StatusLabel.SUCCEEDED, {
        check.check_id: check.metric_value
        for check in result.record.checks
        if check.status is StatusLabel.FAILED
    }


@pytest.mark.parametrize(
    "fault",
    [
        ValidityFault.GEOMETRY_MISCALIBRATION,
        ValidityFault.ZERO_SHIFT,
        ValidityFault.SAMPLE_DISPLACEMENT,
        ValidityFault.SATURATION,
        ValidityFault.DEAD_TIME,
        ValidityFault.INSUFFICIENT_COUNTS,
        ValidityFault.CAKE_INTEGRATION_FAILURE,
        ValidityFault.UNINDEXED_PEAK,
        ValidityFault.CHI2_LOWER_TAIL,
    ],
)
def test_invalid_calibrant_frame_fails(fault: ValidityFault) -> None:
    case = generate_calibrant_frame(fault=fault, seed=22)
    result = verify_calibrant_frame(case)
    assert result.record.status is StatusLabel.FAILED, fault
