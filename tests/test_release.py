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


def test_evidence_manifest_includes_model_cassettes(tmp_path) -> None:
    root = tmp_path / "repo"
    cassette = root / "cassettes/cross-family/instrument/session-000"
    cassette.mkdir(parents=True)
    (cassette / "summary.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    output = root / "artifacts/evidence/manifest.json"
    manifest = build_evidence_manifest(root, output)
    assert [row["path"] for row in manifest["artifacts"]] == [
        "cassettes/cross-family/instrument/session-000/summary.json"
    ]
