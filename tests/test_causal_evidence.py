from pathlib import Path

from proprio.causal_evidence import summarize_accumulated_causal_evidence

ROOT = Path(__file__).resolve().parents[1]


def test_accumulated_causal_evidence_preserves_claim_boundary(tmp_path: Path) -> None:
    summary = summarize_accumulated_causal_evidence(
        tmp_path,
        confirmatory_path=ROOT / "cassettes/confirmatory-dsv4/summary.json",
        diagnostic_path=ROOT / "cassettes/dsv4-skill-evolution/summary.json",
        openflexure_lock_path=(
            ROOT / "artifacts/generated/adaptive-microscopy-causal-development/summary.json"
        ),
    )
    assert summary["pairs"] == 18
    assert summary["truthful_successes"] == 14
    assert summary["none_successes"] == 0
    assert summary["mcnemar"]["one_sided_exact_p"] < 0.001
    assert summary["broad_mechanism_claim"] == "ESTABLISHED"
    assert summary["single_protocol_openflexure_30_trial_claim"] == "NOT_ESTABLISHED"
