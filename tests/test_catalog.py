from pathlib import Path

import pytest

from proprio.catalog import parse_skill_markdown, validate_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_release_catalog_is_evidence_bound() -> None:
    # 2d-flake-search is wired ahead of full catalog publication: its provider,
    # controller.md, and discrimination-gate tests exist and run against the live
    # provider (tests/test_flake_search_provider.py), but the catalog.json entry is a
    # later task. See tests/test_skill_publication.py's STAGED_PACKAGES for the same
    # exclusion; remove both once 2d-flake-search joins the catalog.
    catalog = validate_catalog(ROOT, staged=frozenset({"2d-flake-search"}))
    assert {entry.status for entry in catalog.skills} == {
        "simulation_qualified",
        "simulation_staged",
    }
    assert len(catalog.skills) == 12
    assert all(entry.hardware_qualification_required for entry in catalog.skills)


def test_skill_markdown_requires_closed_frontmatter_and_body() -> None:
    with pytest.raises(ValueError, match="closed YAML frontmatter"):
        parse_skill_markdown("---\nname: broken\ndescription: no closing delimiter")
    with pytest.raises(ValueError, match="instruction body"):
        parse_skill_markdown("---\nname: empty\ndescription: empty\n---\n")
    with pytest.raises(ValueError, match=r"unsupported.*workflow"):
        parse_skill_markdown(
            "---\nname: bad-fields\ndescription: invalid\nworkflow: {}\n---\n# Run\n"
        )
