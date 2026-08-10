from geodata_catalog.services.layer_filter_service import (
    FlightLevelFilter,
    LayerFilterService as FlightLevelFilterService,
)


def test_build_expression_between():
    flight_filter = FlightLevelFilter(mode="between", lower=265, upper=355, enabled=True)

    expression = FlightLevelFilterService.build_expression(flight_filter)

    assert expression == 'CAST("fl_lower" AS INTEGER) <= 355 AND CAST("fl_upper" AS INTEGER) >= 265'


def test_build_expression_above():
    flight_filter = FlightLevelFilter(mode="above", lower=240, upper=400, enabled=True)

    expression = FlightLevelFilterService.build_expression(flight_filter)

    assert expression == 'CAST("fl_lower" AS INTEGER) >= 240'


def test_build_expression_below():
    flight_filter = FlightLevelFilter(mode="below", lower=240, upper=400, enabled=True)

    expression = FlightLevelFilterService.build_expression(flight_filter)

    assert expression == 'CAST("fl_upper" AS INTEGER) <= 400'


def test_build_expression_disabled_returns_none():
    flight_filter = FlightLevelFilter(mode="between", lower=265, upper=355, enabled=False)

    expression = FlightLevelFilterService.build_expression(flight_filter)

    assert expression is None


# --- parse_from_subset_string ---

def test_parse_between_from_subset():
    subset = 'CAST("fl_lower" AS INTEGER) <= 355 AND CAST("fl_upper" AS INTEGER) >= 265'
    result = FlightLevelFilterService.parse_from_subset_string(subset)

    assert result is not None
    assert result.mode == FlightLevelFilterService.MODE_BETWEEN
    assert result.lower == 265
    assert result.upper == 355
    assert result.lower_field == "fl_lower"
    assert result.upper_field == "fl_upper"


def test_parse_above_from_subset():
    subset = 'CAST("fl_lower" AS INTEGER) >= 240'
    result = FlightLevelFilterService.parse_from_subset_string(subset)

    assert result is not None
    assert result.mode == FlightLevelFilterService.MODE_ABOVE
    assert result.lower == 240
    assert result.lower_field == "fl_lower"


def test_parse_below_from_subset():
    subset = 'CAST("fl_upper" AS INTEGER) <= 400'
    result = FlightLevelFilterService.parse_from_subset_string(subset)

    assert result is not None
    assert result.mode == FlightLevelFilterService.MODE_BELOW
    assert result.upper == 400
    assert result.upper_field == "fl_upper"


def test_parse_returns_none_for_unrelated_filter():
    subset = "status = 'ACTIVE'"
    result = FlightLevelFilterService.parse_from_subset_string(subset)

    assert result is None


def test_parse_from_combined_subset():
    # Simulate a subset produced by the plugin when a base filter was present.
    subset = "(status = 'ACTIVE') AND (CAST(\"fl_lower\" AS INTEGER) <= 355 AND CAST(\"fl_upper\" AS INTEGER) >= 265)"
    result = FlightLevelFilterService.parse_from_subset_string(subset)

    assert result is not None
    assert result.mode == FlightLevelFilterService.MODE_BETWEEN
    assert result.lower == 265
    assert result.upper == 355


# --- strip_from_subset_string ---

def test_strip_standalone_between():
    subset = 'CAST("fl_lower" AS INTEGER) <= 355 AND CAST("fl_upper" AS INTEGER) >= 265'
    assert FlightLevelFilterService.strip_from_subset_string(subset) == ""


def test_strip_standalone_above():
    subset = 'CAST("fl_lower" AS INTEGER) >= 240'
    assert FlightLevelFilterService.strip_from_subset_string(subset) == ""


def test_strip_standalone_below():
    subset = 'CAST("fl_upper" AS INTEGER) <= 400'
    assert FlightLevelFilterService.strip_from_subset_string(subset) == ""


def test_strip_combined_returns_base_filter():
    subset = "(status = 'ACTIVE') AND (CAST(\"fl_lower\" AS INTEGER) <= 355 AND CAST(\"fl_upper\" AS INTEGER) >= 265)"
    result = FlightLevelFilterService.strip_from_subset_string(subset)

    assert result == "status = 'ACTIVE'"


def test_strip_unrelated_filter_unchanged():
    subset = "status = 'ACTIVE'"
    assert FlightLevelFilterService.strip_from_subset_string(subset) == "status = 'ACTIVE'"


def test_strip_empty_returns_empty():
    assert FlightLevelFilterService.strip_from_subset_string("") == ""
