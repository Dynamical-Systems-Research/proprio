from __future__ import annotations

from proprio.flagship_demo import BRAND_CSS, HTML, load_demo_evidence, static_bindings


def test_flagship_evidence_is_bound_to_release_artifacts() -> None:
    evidence = load_demo_evidence()

    assert evidence["causal"]["pairs"] == 18
    assert evidence["causal"]["truthful_successes"] == 14
    assert evidence["development"]["confirmatory_status"] == "NOT_ESTABLISHED"
    assert evidence["evolution"]["status"] == "REJECTED"
    assert "fast_autofocus(4000)" in evidence["initial_skill"]
    assert "fast_autofocus(8000)" in evidence["final_skill"]


def test_flagship_bindings_keep_simulation_and_model_provenance() -> None:
    evidence = load_demo_evidence()
    bindings = static_bindings(
        evidence,
        simulator_url="http://127.0.0.1:5122",
        simulator_entropy="123",
    )

    assert bindings["model_resolved"] == "deepseek/deepseek-v4-flash-20260423"
    assert bindings["simulator"]["rng_entropy"] == "123"
    assert len(bindings["captured_repair"]["sha256"]) == 64


def test_flagship_uses_dynamical_brand_contract() -> None:
    assert "#fafaf8" in BRAND_CSS
    assert "#3d5a80" in BRAND_CSS
    assert 'font-family: "Source Sans 3"' in BRAND_CSS
    assert "Dynamical Systems" in HTML
    assert "START TRACE" in HTML
    assert "methodFlow" not in HTML
