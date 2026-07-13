from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_method_has_no_judgment_dataset_dependency() -> None:
    method = (ROOT / "src/proprio/data/method.yaml").read_text(encoding="utf-8")
    assert "XRD-RL" not in method
    assert "VOE-Bench" not in method
    assert "trained checkpoint" not in method
