from pathlib import Path

import pytest

from proprio.catalog import parse_skill_markdown, validate_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_release_catalog_is_evidence_bound() -> None:
    catalog = validate_catalog(ROOT)
    assert {entry.status for entry in catalog.skills} == {"reference", "admitted"}


def test_skill_markdown_requires_closed_frontmatter_and_body() -> None:
    with pytest.raises(ValueError, match="closed YAML frontmatter"):
        parse_skill_markdown("---\nname: broken\ndescription: no closing delimiter")
    with pytest.raises(ValueError, match="instruction body"):
        parse_skill_markdown("---\nname: empty\ndescription: empty\n---\n")
    with pytest.raises(ValueError, match=r"unsupported.*workflow"):
        parse_skill_markdown(
            "---\nname: bad-fields\ndescription: invalid\nworkflow: {}\n---\n# Run\n"
        )
