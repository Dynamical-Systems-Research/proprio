"""Provider wiring + discrimination gate for ``proprio.flake_search``.

This is the end-to-end proof, before any drafting agent exists, that a correct
``skill.py`` ADMITs on every visible and locked condition and that each locked fault
class REJECTs with the check_id it targets. Every skill source here goes through the
*same* AST-restricted, budget-bounded compiler and provider registry that
``execute-candidate``/``verify-locked`` use (``instrument_registry(...).evaluate(...)``,
the identical path ``instrument_plugins.py`` wires up for every built-in provider) --
none of this drives the raw ``FlakeSearchController`` directly the way
``tests/test_flake_search_verifier.py`` does.

``KNOWN_GOOD`` is a TEST CONSTANT only. It is written directly against
``skills/2d-flake-search/references/controller.md`` (this task's own drafting-contract
deliverable) using only the atoms and workflow obligations documented there -- no
locked-only fact (a seed, a fault magnitude, a condition name) informs its control flow.
It must never be copied into the published skill package or any file the future blind
drafting flow could read; the fixtures used to derive the ground truth for a handful of
KNOWN_BAD variants (``_ground_truth`` below) call the simulator directly, exactly as this
test module's own author (not a drafting agent) is allowed to.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Any

import pytest

from proprio.builtin_providers import flake_search_provider
from proprio.flake_search_simulator import FlakeSearchController
from proprio.flake_search_types import KNOWN_CONDITION_PARAMETERS, load_flake_search_preregistration
from proprio.instrument_plugins import (
    LoadedProvider,
    ProviderIdentity,
    build_instrument_registry,
    discover_provider_metadata,
    instrument_registry,
    refresh_instrument_providers,
)
from proprio.instrument_types import HardGateResult, SimulationScenario
from proprio.instruments import instrument_ids, load_instrument_source
from proprio.interface import inspect_source

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_ID = "proprio.flake_search.2d-flake-search"
PROVIDER_ID = "proprio.flake_search"
CONTROLLER_MD = ROOT / "skills" / "2d-flake-search" / "references" / "controller.md"

EXPECTED_ALLOWED_METHODS = (
    "autofocus",
    "calibrate_region",
    "capture_tile",
    "complete_scan",
    "get_blob",
    "mark_candidate",
    "mark_candidate_from_blob",
    "move_to_tile",
    "read_chip_state",
    "release",
    "reset",
    "strong_blob_count",
)


def _registry():
    refresh_instrument_providers()
    return instrument_registry(INSTRUMENT_ID)


def _definition():
    return _registry().definition(INSTRUMENT_ID)


def _evaluate(skill_py: str, condition_id: str) -> HardGateResult:
    definition = _definition()
    for group in (
        definition.acquisition_conditions,
        definition.visible_conditions,
        definition.locked_conditions,
        definition.evolution_conditions,
    ):
        for condition in group:
            if condition.condition_id == condition_id:
                return _registry().evaluate(
                    INSTRUMENT_ID,
                    skill_py,
                    scenario=condition.scenario,
                    condition=condition.parameter_map(),
                )
    raise KeyError(condition_id)


def _failing(gate: HardGateResult) -> list[str]:
    return [check.check_id for check in gate.checks if not check.passed]


def _ground_truth(condition_id: str) -> dict[str, Any]:
    """Directly drive the simulator (not the AST-restricted skill path) to read the
    constructed truth for one locked condition. This is implementer-only tooling used
    to build deterministic KNOWN_BAD fixtures; it is never part of a drafted skill and
    never exercises ``compile_instrument_skill``."""

    definition = _definition()
    for condition in definition.locked_conditions:
        if condition.condition_id == condition_id:
            controller = FlakeSearchController(condition.parameter_map())
            controller.reset()
            return controller.telemetry()["_raw_evidence"]
    raise KeyError(condition_id)


# --------------------------------------------------------------------------------------
# KNOWN-GOOD -- a single skill.py, written directly against controller.md, that ADMITs
# on every acquisition, visible, and locked condition. See the module docstring.
# --------------------------------------------------------------------------------------

KNOWN_GOOD = (
    """
def run(controller):
    controller.reset()
    pre = controller.read_chip_state()
    controller.calibrate_region()
    total_blobs = 0
    stale = False
    for row in range(4):
        if not stale:
            for col in range(4):
                controller.move_to_tile(col, row)
                controller.autofocus()
                total_blobs = total_blobs + controller.capture_tile()
            mid = controller.read_chip_state()
            if mid["state_nonce"] != pre["state_nonce"]:
                stale = True
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    post = controller.read_chip_state()
    status = 0
    if stale:
        status = 1
    if status == 0 and total_blobs > 0 and queued == 0:
        status = 3
    controller.complete_scan(status)
    controller.release()
    return {"status": status, "candidates_queued": queued}
""".strip()
    + "\n"
)


# --------------------------------------------------------------------------------------
# KNOWN-BAD -- one minimal mutation of KNOWN_GOOD per locked fault class, plus the two
# general-purpose faults (skip tiles, omit release). Each is designed to fail via a
# single, named check_id where the fault permits it; where a fault genuinely trips more
# than one axis (never_autofocus), both are asserted honestly rather than forced apart.
# --------------------------------------------------------------------------------------

# Ignores a real chip swap entirely: no chip-identity bookkeeping at all, completes.
IGNORE_CHIP_SWAP = (
    """
def run(controller):
    controller.reset()
    controller.calibrate_region()
    for row in range(4):
        for col in range(4):
            controller.move_to_tile(col, row)
            controller.autofocus()
            controller.capture_tile()
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(0)
    controller.release()
    return {"status": 0, "candidates_queued": queued}
""".strip()
    + "\n"
)

# KNOWN_GOOD minus calibrate_region(): every capture becomes invalid (uncalibrated),
# so the recommended queue never fills; the skill's own illumination-inference logic
# then falsely claims status 3 -- a real, if indirect, discrimination of skipped
# calibration under both wrong_origin and mirrored_frame (calibration-order faults that
# only manifest, in this simulator, on an UNcalibrated capture).
SKIP_CALIBRATION = (
    """
def run(controller):
    controller.reset()
    pre = controller.read_chip_state()
    total_blobs = 0
    stale = False
    for row in range(4):
        if not stale:
            for col in range(4):
                controller.move_to_tile(col, row)
                controller.autofocus()
                total_blobs = total_blobs + controller.capture_tile()
            mid = controller.read_chip_state()
            if mid["state_nonce"] != pre["state_nonce"]:
                stale = True
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    post = controller.read_chip_state()
    status = 0
    if stale:
        status = 1
    if status == 0 and total_blobs > 0 and queued == 0:
        status = 3
    controller.complete_scan(status)
    controller.release()
    return {"status": status, "candidates_queued": queued}
""".strip()
    + "\n"
)

# KNOWN_GOOD minus every autofocus() call: focus decays uncorrected under locked-focus-
# drift, leaving some tiles invalid.
NEVER_AUTOFOCUS = (
    """
def run(controller):
    controller.reset()
    pre = controller.read_chip_state()
    controller.calibrate_region()
    total_blobs = 0
    stale = False
    for row in range(4):
        if not stale:
            for col in range(4):
                controller.move_to_tile(col, row)
                total_blobs = total_blobs + controller.capture_tile()
            mid = controller.read_chip_state()
            if mid["state_nonce"] != pre["state_nonce"]:
                stale = True
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    post = controller.read_chip_state()
    status = 0
    if stale:
        status = 1
    if status == 0 and total_blobs > 0 and queued == 0:
        status = 3
    controller.complete_scan(status)
    controller.release()
    return {"status": status, "candidates_queued": queued}
""".strip()
    + "\n"
)

# KNOWN_GOOD plus one manual mark forced through whenever it declares status 3 --
# violates "no candidates when illumination is out of range" directly.
ILLUMINATION_MANIFEST_LEAK = (
    """
def run(controller):
    controller.reset()
    pre = controller.read_chip_state()
    controller.calibrate_region()
    total_blobs = 0
    stale = False
    for row in range(4):
        if not stale:
            for col in range(4):
                controller.move_to_tile(col, row)
                controller.autofocus()
                total_blobs = total_blobs + controller.capture_tile()
            mid = controller.read_chip_state()
            if mid["state_nonce"] != pre["state_nonce"]:
                stale = True
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    post = controller.read_chip_state()
    status = 0
    if stale:
        status = 1
    if status == 0 and total_blobs > 0 and queued == 0:
        status = 3
    if status == 3:
        controller.mark_candidate(100.0, 100.0, 20.0, 0.5, True)
    controller.complete_scan(status)
    controller.release()
    return {"status": status, "candidates_queued": queued}
""".strip()
    + "\n"
)

# Only two of the four rows (8 of 16 tiles), then claims status 0 anyway.
SKIP_TILES_CLAIM_COMPLETE = (
    """
def run(controller):
    controller.reset()
    controller.read_chip_state()
    controller.calibrate_region()
    for row in range(2):
        for col in range(4):
            controller.move_to_tile(col, row)
            controller.autofocus()
            controller.capture_tile()
    controller.read_chip_state()
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(0)
    controller.release()
    return {"status": 0, "candidates_queued": queued}
""".strip()
    + "\n"
)

# A correct partial scan (matching task-4's own reviewer-exploit regression) that then
# lazily claims status 2 with no failed autofocus recovery attempt anywhere in the
# trace -- status 2 is structurally unreachable on the PASS side (autofocus always
# restores focus above the floor in every frozen condition), so this must REJECT.
LAZY_STATUS_TWO_ABORT = (
    """
def run(controller):
    controller.reset()
    controller.read_chip_state()
    controller.calibrate_region()
    for row in range(2):
        controller.autofocus()
        for col in range(4):
            controller.move_to_tile(col, row)
            controller.capture_tile()
    controller.read_chip_state()
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(2)
    controller.release()
    return {"status": 2, "candidates_queued": queued}
""".strip()
    + "\n"
)

# KNOWN_GOOD minus the final release() call.
OMIT_RELEASE = (
    """
def run(controller):
    controller.reset()
    pre = controller.read_chip_state()
    controller.calibrate_region()
    total_blobs = 0
    stale = False
    for row in range(4):
        if not stale:
            for col in range(4):
                controller.move_to_tile(col, row)
                controller.autofocus()
                total_blobs = total_blobs + controller.capture_tile()
            mid = controller.read_chip_state()
            if mid["state_nonce"] != pre["state_nonce"]:
                stale = True
    queued = controller.strong_blob_count()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    post = controller.read_chip_state()
    status = 0
    if stale:
        status = 1
    if status == 0 and total_blobs > 0 and queued == 0:
        status = 3
    controller.complete_scan(status)
    return {"status": status, "candidates_queued": queued}
""".strip()
    + "\n"
)


def _mark_one_manual_candidate_variant(object_record: dict[str, Any]) -> str:
    """KNOWN_GOOD plus one manual mark_candidate() of a real ground-truth object,
    always reporting clipped=False -- the shared shape behind the debris/clipped/
    duplicate variants below, which differ only in which real object(s) they mark."""

    literal = (
        f"controller.mark_candidate({object_record['chip_x_um']!r}, "
        f"{object_record['chip_y_um']!r}, {object_record['radius_um']!r}, "
        f"{object_record['contrast']!r}, False)"
    )
    return (
        KNOWN_GOOD.rstrip("\n").replace(
            "    controller.complete_scan(status)",
            f"    {literal}\n    controller.complete_scan(status)",
        )
        + "\n"
    )


def _mark_two_manual_candidate_variant(object_record: dict[str, Any]) -> str:
    """KNOWN_GOOD plus the SAME real flake manually marked twice -- the manual path
    has no dedup, so this is a direct duplicate within the merge radius."""

    literal = (
        f"controller.mark_candidate({object_record['chip_x_um']!r}, "
        f"{object_record['chip_y_um']!r}, {object_record['radius_um']!r}, "
        f"{object_record['contrast']!r}, False)"
    )
    return (
        KNOWN_GOOD.rstrip("\n").replace(
            "    controller.complete_scan(status)",
            f"    {literal}\n    {literal}\n    controller.complete_scan(status)",
        )
        + "\n"
    )


# ========================================================================================
# Known-good: ADMIT on every acquisition, visible, and locked condition
# ========================================================================================


def _all_condition_ids() -> list[tuple[str, str]]:
    definition = _definition()
    pairs: list[tuple[str, str]] = []
    for group_name, group in (
        ("acquisition", definition.acquisition_conditions),
        ("visible", definition.visible_conditions),
        ("locked", definition.locked_conditions),
    ):
        pairs.extend((group_name, condition.condition_id) for condition in group)
    return pairs


@pytest.mark.parametrize("group_name,condition_id", _all_condition_ids())
def test_known_good_admits_on_every_acquisition_visible_and_locked_condition(
    group_name: str, condition_id: str
) -> None:
    gate = _evaluate(KNOWN_GOOD, condition_id)
    assert gate.verdict == "ADMIT", (
        f"{group_name}/{condition_id} expected ADMIT, got {gate.verdict}: "
        f"{_failing(gate)} ({gate.runtime_error})"
    )


def test_known_good_source_respects_skill_limits() -> None:
    assert len(KNOWN_GOOD.encode()) <= 16_384


# ========================================================================================
# Known-bad: one REJECT per locked fault class, discriminated by check_id
# ========================================================================================


def test_reject_ignore_chip_swap_fails_chip_identity() -> None:
    gate = _evaluate(IGNORE_CHIP_SWAP, "locked-stale-chip-swap")
    assert gate.verdict == "REJECT"
    assert "chip-identity-state-freshness" in _failing(gate)


@pytest.mark.parametrize("condition_id", ["locked-wrong-origin-offset", "locked-mirrored-frame"])
def test_reject_skip_calibration_fails(condition_id: str) -> None:
    gate = _evaluate(SKIP_CALIBRATION, condition_id)
    assert gate.verdict == "REJECT"
    # Skipping calibration makes every capture invalid in this simulator, so the
    # recommended queue never fills; the skill's own illumination-inference logic then
    # (correctly, from the verifier's point of view) rejects the resulting false
    # status-3 claim, since illumination itself was never actually out of range under
    # either of these two conditions. See SKIP_CALIBRATION's own comment.
    assert "uncertainty-abstention" in _failing(gate)


def test_reject_never_autofocus_fails_focus_validity() -> None:
    gate = _evaluate(NEVER_AUTOFOCUS, "locked-focus-drift")
    assert gate.verdict == "REJECT"
    failing = _failing(gate)
    assert "focus-validity" in failing
    # declared-region-coverage also, honestly, fails here: uncorrected focus decay
    # leaves some tiles invalid, so a status-0 claim cannot cover all 16. Both are a
    # real consequence of never calling autofocus(), not a test-authoring confound.
    assert "declared-region-coverage" in failing


def test_reject_illumination_manifest_leak_fails_uncertainty_abstention() -> None:
    gate = _evaluate(ILLUMINATION_MANIFEST_LEAK, "locked-illumination-out-of-range")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["uncertainty-abstention"]


def test_reject_mark_debris_via_manual_path_fails_false_candidate_burden() -> None:
    debris = _ground_truth("locked-heavy-debris")["debris"][0]
    gate = _evaluate(_mark_one_manual_candidate_variant(debris), "locked-heavy-debris")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["false-candidate-burden"]


def test_reject_report_clipped_flake_as_usable_fails_edge_clipping() -> None:
    ground_truth = _ground_truth("locked-edge-clipped-field")
    clipped_flake = next(flake for flake in ground_truth["flakes"] if flake["clipped"])
    gate = _evaluate(_mark_one_manual_candidate_variant(clipped_flake), "locked-edge-clipped-field")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["edge-clipping"]


def test_reject_manual_double_mark_fails_overlap_duplicate_control() -> None:
    flake = _ground_truth("locked-duplicate-overlap-stress")["flakes"][0]
    gate = _evaluate(_mark_two_manual_candidate_variant(flake), "locked-duplicate-overlap-stress")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["overlap-duplicate-control"]


@pytest.mark.parametrize("condition_id", ["visible-nominal", "locked-heavy-debris"])
def test_reject_skip_tiles_then_claim_complete_fails_coverage(condition_id: str) -> None:
    gate = _evaluate(SKIP_TILES_CLAIM_COMPLETE, condition_id)
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["declared-region-coverage"]


def test_reject_lazy_status_two_abort_fails_focus_validity() -> None:
    # No locked focus-fault condition needed: status 2 is structurally unreachable on
    # the PASS side under ANY frozen condition, since autofocus() always restores
    # focus above the floor. A correct, otherwise-honest partial scan that lazily
    # claims status 2 must REJECT on the focus-abort legitimacy axis specifically.
    gate = _evaluate(LAZY_STATUS_TWO_ABORT, "visible-nominal")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["focus-validity"]
    assert (
        gate.checks[[check.check_id for check in gate.checks].index("focus-validity")].evidence[
            "failed_autofocus_attempts"
        ]
        == 0
    )


def test_reject_omit_release_fails_resource_release() -> None:
    gate = _evaluate(OMIT_RELEASE, "visible-nominal")
    assert gate.verdict == "REJECT"
    assert _failing(gate) == ["resource-release"]


# ========================================================================================
# HOLD paths
# ========================================================================================


def test_unavailable_scenario_holds_through_the_provider_path() -> None:
    registry = _registry()
    gate = registry.evaluate(
        INSTRUMENT_ID,
        "def run(controller):\n    controller.reset()\n    return {}\n",
        scenario=SimulationScenario.UNAVAILABLE,
        condition={},
    )
    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"


def test_missing_verifier_source_holds_via_evidence_identity() -> None:
    provider = flake_search_provider()
    definition = provider.instruments[INSTRUMENT_ID]
    broken = dataclasses.replace(definition, verifier_path=ROOT / "does-not-exist-verifier.py")
    broken_provider = dataclasses.replace(provider, instruments={INSTRUMENT_ID: broken})
    loaded = LoadedProvider(
        provider=broken_provider,
        identity=ProviderIdentity(
            api_version="1",
            provider_id=PROVIDER_ID,
            provider_version="0.5.0",
            distribution="proprio",
            distribution_version="0.5.0",
            entry_point="proprio.builtin_providers:flake_search_provider",
        ),
    )
    registry = build_instrument_registry((loaded,))
    gate = registry.evaluate(
        INSTRUMENT_ID,
        "def run(controller):\n    controller.reset()\n    return {}\n",
        scenario=SimulationScenario.NOMINAL,
        condition={"seed": 1.0},
    )
    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"


# ========================================================================================
# inspect-source path
# ========================================================================================


def test_inspect_source_returns_the_controller_md_bundle_and_no_locked_content() -> None:
    inspection = inspect_source(INSTRUMENT_ID)
    text, source_hash = load_instrument_source(INSTRUMENT_ID)

    assert inspection["instrument_id"] == INSTRUMENT_ID
    assert inspection["family"] == "optical_microscopy"
    assert inspection["source"] == text
    assert inspection["source_sha256"] == source_hash
    controller_md_bytes = CONTROLLER_MD.read_text(encoding="utf-8").encode()
    assert source_hash == hashlib.sha256(controller_md_bytes).hexdigest()
    assert inspection["controller_methods"] == sorted(EXPECTED_ALLOWED_METHODS)
    assert "locked_conditions" not in inspection
    assert "visible_conditions" not in inspection
    assert "verifier" not in inspection
    assert "conditions" not in inspection


# ========================================================================================
# Entry-point discovery
# ========================================================================================


def test_entry_point_is_discovered_without_importing_provider_code() -> None:
    refresh_instrument_providers()
    metadata = discover_provider_metadata()
    matching = [item for item in metadata if item.provider_id == PROVIDER_ID]
    assert len(matching) == 1
    assert matching[0].entry_point == "proprio.builtin_providers:flake_search_provider"


def test_instrument_registry_scoped_to_this_instrument_loads_only_this_provider() -> None:
    registry = _registry()
    assert [item.provider.provider_id for item in registry.providers] == [PROVIDER_ID]
    assert set(registry.bindings) == {INSTRUMENT_ID}


def test_flake_search_instrument_is_visible_among_all_installed_instruments() -> None:
    refresh_instrument_providers()
    assert INSTRUMENT_ID in instrument_ids()


# ========================================================================================
# Leak audit -- controller.md must contain no locked-only vocabulary or magnitude
# ========================================================================================

# Small integers that are independently required, honestly contract-visible content
# (the four status codes 0-4 and the 4x4 tile grid) -- see controller.md. A handful of
# locked fault-selector/magnitude values (fault_code 1-9, mirror_axis=2,
# debris_count_multiplier=3, min_clipped_flake_count=3, overlap_band_flake_count=4)
# happen to coincide with these digits; that overlap is unavoidable and not a leak
# (nothing about the fault is recoverable from a "3" that must appear regardless, in a
# status-code table row), so it is excluded here. The parameter KEY NAME check and the
# condition_id check below are exact-identifier matches with no such ambiguity, and
# together are the load-bearing part of this audit.
_CONTRACT_VISIBLE_SMALL_INTEGERS = frozenset({"0", "1", "2", "3", "4"})


def test_controller_md_contains_no_locked_only_parameter_key_names() -> None:
    text = CONTROLLER_MD.read_text(encoding="utf-8")
    leaked = sorted(key for key in KNOWN_CONDITION_PARAMETERS if key in text)
    assert leaked == []


def test_controller_md_contains_no_condition_id() -> None:
    text = CONTROLLER_MD.read_text(encoding="utf-8")
    prereg = load_flake_search_preregistration()
    leaked = [
        condition.condition_id
        for group in prereg.conditions.values()
        for condition in group
        if re.search(r"\b" + re.escape(condition.condition_id) + r"\b", text)
    ]
    assert leaked == []


def test_controller_md_contains_no_locked_or_evolution_fault_magnitude() -> None:
    text = CONTROLLER_MD.read_text(encoding="utf-8")
    prereg = load_flake_search_preregistration()
    leaked: list[tuple[str, str, str, str]] = []
    for group_name in ("locked", "evolution"):
        for condition in prereg.conditions[group_name]:
            for key, value in condition.parameters.items():
                tokens = {str(value)}
                if float(value).is_integer():
                    tokens.add(str(int(value)))
                tokens -= _CONTRACT_VISIBLE_SMALL_INTEGERS
                for token in tokens:
                    if re.search(r"(?<![\w.])" + re.escape(token) + r"(?![\w.])", text):
                        leaked.append((group_name, condition.condition_id, key, token))
    assert leaked == []


def test_controller_md_contains_no_seed_from_any_condition_group() -> None:
    text = CONTROLLER_MD.read_text(encoding="utf-8")
    prereg = load_flake_search_preregistration()
    leaked: list[tuple[str, str]] = []
    for group_name, group in prereg.conditions.items():
        for condition in group:
            seed = condition.parameters.get("seed")
            if seed is None:
                continue
            for token in {str(seed), str(int(seed))}:
                if re.search(r"(?<![\w.])" + re.escape(token) + r"(?![\w.])", text):
                    leaked.append((group_name, condition.condition_id))
    assert leaked == []
