from geodata_catalog.services.layer_filter_service import (
    AttributeSearchFilter,
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)


# ------------------------------------------------------------------ #
# AttributeSearchFilter — build_attribute_expression                  #
# ------------------------------------------------------------------ #

def test_build_attribute_expression_single():
    filters = [AttributeSearchFilter(column="STATUS", value="ACTIVE")]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"STATUS" = \'ACTIVE\''


def test_build_attribute_expression_multiple():
    filters = [
        AttributeSearchFilter(column="STATUS", value="ACTIVE"),
        AttributeSearchFilter(column="TYPE", value="RTE"),
    ]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"STATUS" = \'ACTIVE\' AND "TYPE" = \'RTE\''


def test_build_attribute_expression_multi_value_text_uses_in():
    filters = [AttributeSearchFilter(column="STATUS", value="ACTIVE, PENDING")]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"STATUS" IN (\'ACTIVE\', \'PENDING\')'


def test_build_attribute_expression_multi_value_numeric_uses_in_without_quotes():
    filters = [AttributeSearchFilter(column="FL", value="100, 200", data_type="numeric")]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"FL" IN (100, 200)'


def test_build_attribute_expression_single_numeric_no_quotes():
    filters = [AttributeSearchFilter(column="FL", value="350", data_type="numeric")]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"FL" = 350'


def test_build_attribute_expression_skips_empty_values():
    filters = [
        AttributeSearchFilter(column="STATUS", value="ACTIVE"),
        AttributeSearchFilter(column="TYPE", value=""),
    ]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr == '"STATUS" = \'ACTIVE\''


def test_build_attribute_expression_all_empty_returns_none():
    filters = [AttributeSearchFilter(column="STATUS", value="")]
    expr = LayerFilterService.build_attribute_expression(filters)
    assert expr is None


def test_build_attribute_expression_empty_list_returns_none():
    assert LayerFilterService.build_attribute_expression([]) is None


# ------------------------------------------------------------------ #
# parse_attribute_filters_from_subset                                 #
# ------------------------------------------------------------------ #

def test_parse_attribute_filter_found():
    subset = '"STATUS" = \'ACTIVE\''
    cols = [{"name": "STATUS", "label": "Status"}]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert len(result) == 1
    assert result[0].column == "STATUS"
    assert result[0].value == "ACTIVE"
    assert result[0].label == "Status"


def test_parse_attribute_filter_not_found_gives_empty_value():
    subset = '"FL_LOWER" = \'100\''
    cols = [{"name": "STATUS", "label": "Status"}]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert len(result) == 1
    assert result[0].value == ""


def test_parse_attribute_filter_multiple_columns():
    subset = '"STATUS" = \'ACTIVE\' AND "TYPE" = \'RTE\''
    cols = [
        {"name": "STATUS", "label": "Status"},
        {"name": "TYPE", "label": "Type"},
    ]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert result[0].value == "ACTIVE"
    assert result[1].value == "RTE"


def test_parse_attribute_filter_from_combined_subset():
    subset = (
        '(status = \'BASE\') AND '
        '(CAST("fl_lower" AS INTEGER) >= 100) AND '
        '("STATUS" = \'ACTIVE\')'
    )
    cols = [{"name": "STATUS", "label": "Status"}]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert result[0].value == "ACTIVE"


def test_parse_attribute_filter_in_text_values_roundtrip():
    subset = '"STATUS" IN (\'ACTIVE\', \'PENDING\')'
    cols = [{"name": "STATUS", "label": "Status", "type": "varchar"}]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert result[0].value == "ACTIVE, PENDING"


def test_parse_attribute_filter_in_numeric_values_roundtrip():
    subset = '"FL" IN (100, 200, 300)'
    cols = [{"name": "FL", "label": "Flight Level", "type": "numeric"}]
    result = LayerFilterService.parse_attribute_filters_from_subset(subset, cols)
    assert result[0].value == "100, 200, 300"


# ------------------------------------------------------------------ #
# strip_attribute_filters_from_subset                                 #
# ------------------------------------------------------------------ #

def test_strip_attribute_filter_solo():
    subset = '"STATUS" = \'ACTIVE\''
    result = LayerFilterService.strip_attribute_filters_from_subset(subset, ["STATUS"])
    assert result == ""


def test_strip_attribute_filter_appended_with_parens():
    subset = '(base_filter = 1) AND ("STATUS" = \'ACTIVE\')'
    result = LayerFilterService.strip_attribute_filters_from_subset(subset, ["STATUS"])
    assert result == "base_filter = 1"


def test_strip_attribute_filter_prepended_with_parens():
    subset = '("STATUS" = \'ACTIVE\') AND (base_filter = 1)'
    result = LayerFilterService.strip_attribute_filters_from_subset(subset, ["STATUS"])
    assert result == "base_filter = 1"


def test_strip_attribute_filter_unknown_column_unchanged():
    subset = '"OTHER" = \'VALUE\''
    result = LayerFilterService.strip_attribute_filters_from_subset(subset, ["STATUS"])
    assert result == '"OTHER" = \'VALUE\''


def test_strip_attribute_filter_in_clause():
    subset = '(base_filter = 1) AND ("STATUS" IN (\'ACTIVE\', \'PENDING\'))'
    result = LayerFilterService.strip_attribute_filters_from_subset(subset, ["STATUS"])
    assert result == "base_filter = 1"


# ------------------------------------------------------------------ #
# LayerFilter roundtrip                                               #
# ------------------------------------------------------------------ #

def test_layer_filter_fl_and_attribute_combined():
    """A FL expression and attribute expression can coexist in a subset string."""
    fl = FlightLevelFilter(mode="between", lower=100, upper=350, enabled=True)
    attrs = [AttributeSearchFilter(column="STATUS", value="ACTIVE")]
    layer_filter = LayerFilter(flight_level=fl, attributes=attrs)

    fl_expr = LayerFilterService.build_fl_expression(layer_filter.flight_level)
    attr_expr = LayerFilterService.build_attribute_expression(layer_filter.attributes)

    combined = f"({fl_expr}) AND ({attr_expr})"

    # Parse FL back
    parsed_fl = LayerFilterService.parse_fl_from_subset_string(combined)
    assert parsed_fl is not None
    assert parsed_fl.lower == 100
    assert parsed_fl.upper == 350

    # Parse attr back
    parsed_attrs = LayerFilterService.parse_attribute_filters_from_subset(
        combined, [{"name": "STATUS", "label": "Status"}]
    )
    assert parsed_attrs[0].value == "ACTIVE"
