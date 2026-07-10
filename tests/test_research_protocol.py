from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION = ROOT / "src/proprio/data/skill-evolution-preregistration.yaml"


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
