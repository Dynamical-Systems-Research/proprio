from proprio.engineering_burden import measure_engineering_burden


def test_engineering_burden_separates_external_simulator_and_adapter_work() -> None:
    result = measure_engineering_burden()
    microscopy = result["families"]["optical_microscopy"]
    assert microscopy["instrument_specific_simulator_loc"] == 0
    assert microscopy["external_simulator_loc_authored"] == 0
    assert microscopy["instrument_specific_adapter_loc"] > 0
    assert microscopy["instrument_specific_verifier_loc"] > 0
    assert microscopy["person_hours"] == "unavailable"
    assert result["prospective_execution_window"]["elapsed_minutes"] > 0


def test_engineering_burden_reports_each_confirmatory_family() -> None:
    result = measure_engineering_burden()
    assert set(result["families"]) == {
        "optical_measurement",
        "calibrated_delivery",
        "thermal_control",
        "optical_microscopy",
    }
    assert all(family["labeled_invalid_classes"] >= 4 for family in result["families"].values())
