from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_generalization_protocol_has_no_judgment_dataset_dependency() -> None:
    prereg = yaml.safe_load(
        (ROOT / "src/proprio/data/confirmatory-preregistration.yaml").read_text(encoding="utf-8")
    )
    assert prereg["data_policy"] == {
        "xrd_rl_dataset": "not_used",
        "voe_bench_dataset": "not_used",
        "trained_judgment_checkpoint": "not_used",
        "external_policy_training_distribution": "not_used",
        "allowed_inputs": [
            "public instrument source bundles",
            "synthetic simulator state and traces",
            "deterministic execution and physical verifier records",
        ],
    }


def test_public_docs_state_xrd_is_reference_not_generalization_data() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    note = (ROOT / "docs/technical-note.md").read_text(encoding="utf-8")
    assert "use no XRD-RL or VOE-Bench data" in readme
    assert "XRD remains a reference instrument" in readme
    assert "XRD is the reference operation, not training data" in note
