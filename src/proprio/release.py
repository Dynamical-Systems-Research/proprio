"""Release-evidence manifest generation and verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proprio.artifacts import file_sha256, write_canonical_json


def build_evidence_manifest(root: Path, output: Path) -> dict[str, Any]:
    evidence_root = root / "artifacts/evidence"
    excluded = output.resolve()
    artifacts = []
    for path in sorted(item for item in evidence_root.rglob("*") if item.is_file()):
        if path.resolve() == excluded:
            continue
        artifacts.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "proprio.evidence_manifest.v0.1",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "verdict": "PASS" if artifacts else "FAIL",
    }
    write_canonical_json(output, manifest)
    return manifest


def verify_evidence_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors = []
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        if not path.is_file():
            errors.append(f"missing: {artifact['path']}")
        elif file_sha256(path) != artifact["sha256"]:
            errors.append(f"hash mismatch: {artifact['path']}")
    return errors
