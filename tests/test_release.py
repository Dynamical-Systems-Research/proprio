from proprio.release import build_evidence_manifest, verify_evidence_manifest


def test_evidence_manifest_is_content_addressed(tmp_path) -> None:
    root = tmp_path / "repo"
    evidence = root / "artifacts/evidence"
    evidence.mkdir(parents=True)
    (evidence / "proof.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    output = evidence / "manifest.json"
    manifest = build_evidence_manifest(root, output)
    assert manifest["artifact_count"] == 1
    assert verify_evidence_manifest(root, manifest) == []
    (evidence / "proof.json").write_text('{"verdict":"FAIL"}\n', encoding="utf-8")
    assert verify_evidence_manifest(root, manifest) == [
        "hash mismatch: artifacts/evidence/proof.json"
    ]


def test_evidence_manifest_excludes_run_logs(tmp_path) -> None:
    root = tmp_path / "repo"
    run_log = root / "runs/session-000"
    run_log.mkdir(parents=True)
    (run_log / "summary.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    output = root / "artifacts/evidence/manifest.json"
    manifest = build_evidence_manifest(root, output)
    assert manifest["artifacts"] == []
    assert manifest["verdict"] == "FAIL"


def test_evidence_manifest_is_independent_of_output_location(tmp_path) -> None:
    root = tmp_path / "repo"
    evidence = root / "artifacts/evidence"
    evidence.mkdir(parents=True)
    (evidence / "proof.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    (evidence / "manifest.json").write_text('{"stale":true}\n', encoding="utf-8")

    checked_in = build_evidence_manifest(root, evidence / "manifest.json")
    external = build_evidence_manifest(root, tmp_path / "external-manifest.json")

    assert external == checked_in
    assert [artifact["path"] for artifact in external["artifacts"]] == [
        "artifacts/evidence/proof.json"
    ]
