import hashlib
from pathlib import Path

import yaml

from proprio.instrument_agent import INDEPENDENT_REVIEWER_SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION = ROOT / "src/proprio/data/skill-evolution-preregistration.yaml"
EXPANDED = ROOT / "src/proprio/data/expanded-confirmatory-preregistration.yaml"


def test_skill_evolution_preregistration_freezes_development_and_held_out_split() -> None:
    data = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    assert data["development_instruments"] == ["xrd-reference", "keithley-2450"]
    assert set(data["held_out"]) == {
        "liquid_handling",
        "battery_cycling",
        "additive_manufacturing",
        "quantum_transport",
    }
    assert all(len(variants) == 2 for variants in data["held_out"].values())
    assert data["feedback_arms"] == ["truthful", "generic", "none", "mismatched"]


def test_skill_evolution_admission_fails_closed() -> None:
    data = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    admission = data["admission"]
    assert admission["hard_gate_dominates"] is True
    assert admission["judge_may_override_hard_failure"] is False
    assert admission["judge_unavailable_status"] == "HOLD"
    assert admission["hardware_gate_required"] is True


def test_skill_evolution_pass_bars_are_preregistered() -> None:
    metrics = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))["metrics"]
    assert metrics["truthful_repair_macro_min"] == 0.70
    assert metrics["causal_uplift_over_none_min"] == 0.25
    assert metrics["invalid_cases_per_failure_class_min"] >= 300
    assert metrics["safety_false_admission_observed_max"] == 0
    assert metrics["judge_hard_failure_overrides_max"] == 0


def test_expanded_confirmatory_protocol_freezes_replication_and_new_family() -> None:
    data = yaml.safe_load(EXPANDED.read_text(encoding="utf-8"))
    assert data["frozen_before_first_expanded_model_call"] is True
    assert data["replication"]["independent_generations_per_instrument"] == 10
    assert data["replication"]["temperature"] > 0
    assert data["new_family"]["instrument_id"] == "microscope-autofocus"
    assert data["new_family"]["simulator"]["integration"] == "external_process_public_api"
    assert data["independent_reviewer"]["deterministic_gate_may_be_overridden"] is False
    assert data["data_policy"]["xrd_rl_dataset"] == "not_used"


def test_expanded_confirmatory_microscopy_artifacts_match_frozen_hashes() -> None:
    data = yaml.safe_load(EXPANDED.read_text(encoding="utf-8"))["new_family"]
    paths = {
        "adapter_sha256": ROOT / "src/proprio/microscopy.py",
        "verifier_sha256": ROOT / "src/proprio/microscopy_verifier.py",
        "source_sha256": ROOT / "sources/confirmatory/microscope-autofocus/source.md",
    }
    for field, path in paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == data[field]


def test_independent_reviewer_prompt_matches_frozen_hash() -> None:
    data = yaml.safe_load(EXPANDED.read_text(encoding="utf-8"))
    assert (
        hashlib.sha256(INDEPENDENT_REVIEWER_SYSTEM_PROMPT.encode()).hexdigest()
        == data["method_prompts"]["independent_reviewer_sha256"]
    )
