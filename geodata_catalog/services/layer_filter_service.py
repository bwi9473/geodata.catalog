from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class FlightLevelFilter:
    mode: str
    lower: int
    upper: int
    enabled: bool
    lower_field: str = "fl_lower"
    upper_field: str = "fl_upper"


@dataclass(slots=True)
class AttributeSearchFilter:
    """Equality filter on a text or categorical attribute column."""

    column: str
    value: str
    label: str = ""
    data_type: str = "varchar"


@dataclass
class LayerFilter:
    """Combined filter: flight-level range plus optional attribute searches."""

    flight_level: FlightLevelFilter
    attributes: list[AttributeSearchFilter] = field(default_factory=list)


class LayerFilterService:
    """Builds and parses QGIS subset-string expressions for all filter types."""

    MODE_BETWEEN = "between"
    MODE_ABOVE = "above"
    MODE_BELOW = "below"
    MODE_NONE = "none"

    _NUMERIC_TYPES = {
        "int",
        "integer",
        "smallint",
        "bigint",
        "number",
        "numeric",
        "decimal",
        "float",
        "double",
        "real",
    }

    _NUMERIC_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

    # -- Flight-level expression building --

    @staticmethod
    def build_fl_expression(flight_filter: FlightLevelFilter) -> str | None:
        if not flight_filter.enabled:
            return None
        lower = flight_filter.lower
        upper = flight_filter.upper
        lower_field = flight_filter.lower_field
        upper_field = flight_filter.upper_field
        if flight_filter.mode == LayerFilterService.MODE_BETWEEN:
            return (
                f'CAST("{lower_field}" AS INTEGER) <= {upper} AND '
                f'CAST("{upper_field}" AS INTEGER) >= {lower}'
            )
        if flight_filter.mode == LayerFilterService.MODE_ABOVE:
            return f'CAST("{lower_field}" AS INTEGER) >= {lower}'
        if flight_filter.mode == LayerFilterService.MODE_BELOW:
            return f'CAST("{upper_field}" AS INTEGER) <= {upper}'
        return None

    @classmethod
    def build_expression(cls, flight_filter: FlightLevelFilter) -> str | None:
        """Legacy alias for build_fl_expression."""
        return cls.build_fl_expression(flight_filter)

    # -- Attribute-filter expression building --

    @staticmethod
    def build_attribute_expression(filters: list[AttributeSearchFilter]) -> str | None:
        """Build a combined expression for all non-empty attribute filters.

        - Multiple comma-separated values become an IN clause.
        - Numeric column types are emitted without quotes.
        - Text-like column types are single-quoted and SQL-escaped.
        """
        parts = []
        for f in filters:
            clause = LayerFilterService._build_attribute_clause(f)
            if clause:
                parts.append(clause)
        return " AND ".join(parts) if parts else None

    @staticmethod
    def _build_attribute_clause(filter_item: AttributeSearchFilter) -> str | None:
        values = LayerFilterService._split_filter_values(filter_item.value)
        if not values:
            return None

        is_numeric = LayerFilterService._is_numeric_type(filter_item.data_type)
        if is_numeric:
            numeric_values = [
                val for val in values if LayerFilterService._NUMERIC_VALUE_RE.match(val)
            ]
            if not numeric_values:
                return None
            literals = numeric_values
        else:
            literals = [
                f"'{LayerFilterService._escape_sql_string(val)}'"
                for val in values
            ]

        if len(literals) == 1:
            return f'"{filter_item.column}" = {literals[0]}'
        return f'"{filter_item.column}" IN ({", ".join(literals)})'

    @staticmethod
    def _split_filter_values(raw_value: str) -> list[str]:
        return [part.strip() for part in raw_value.split(",") if part.strip()]

    @staticmethod
    def _escape_sql_string(value: str) -> str:
        return value.replace("'", "''")

    @classmethod
    def _is_numeric_type(cls, data_type: str | None) -> bool:
        return (data_type or "varchar").strip().lower() in cls._NUMERIC_TYPES

    # -- Regex patterns for flight-level expressions --

    _PAT_BETWEEN = re.compile(
        r'CAST\("([^"]+)"\s+AS\s+INTEGER\)\s*<=\s*(\d+)\s+AND\s+CAST\("([^"]+)"\s+AS\s+INTEGER\)\s*>=\s*(\d+)',
        re.IGNORECASE,
    )
    _PAT_ABOVE = re.compile(
        r'CAST\("([^"]+)"\s+AS\s+INTEGER\)\s*>=\s*(\d+)',
        re.IGNORECASE,
    )
    _PAT_BELOW = re.compile(
        r'CAST\("([^"]+)"\s+AS\s+INTEGER\)\s*<=\s*(\d+)',
        re.IGNORECASE,
    )
    _PAT_ANY_FL = re.compile(
        r'(?:'
        r'CAST\("[^"]+"\s+AS\s+INTEGER\)\s*<=\s*\d+\s+AND\s+CAST\("[^"]+"\s+AS\s+INTEGER\)\s*>=\s*\d+'
        r'|CAST\("[^"]+"\s+AS\s+INTEGER\)\s*>=\s*\d+'
        r'|CAST\("[^"]+"\s+AS\s+INTEGER\)\s*<=\s*\d+'
        r')',
        re.IGNORECASE,
    )

    # -- Flight-level parsing --

    @staticmethod
    def parse_fl_from_subset_string(subset_string: str) -> FlightLevelFilter | None:
        """Parse a FlightLevelFilter from a QGIS subset string.

        Returns None when no flight level expression is found.
        """
        if not subset_string:
            return None

        m = LayerFilterService._PAT_BETWEEN.search(subset_string)
        if m:
            return FlightLevelFilter(
                mode=LayerFilterService.MODE_BETWEEN,
                lower=int(m.group(4)),
                upper=int(m.group(2)),
                enabled=True,
                lower_field=m.group(1),
                upper_field=m.group(3),
            )

        m = LayerFilterService._PAT_ABOVE.search(subset_string)
        if m:
            return FlightLevelFilter(
                mode=LayerFilterService.MODE_ABOVE,
                lower=int(m.group(2)),
                upper=600,
                enabled=True,
                lower_field=m.group(1),
                upper_field="fl_upper",
            )

        m = LayerFilterService._PAT_BELOW.search(subset_string)
        if m:
            return FlightLevelFilter(
                mode=LayerFilterService.MODE_BELOW,
                lower=0,
                upper=int(m.group(2)),
                enabled=True,
                lower_field="fl_lower",
                upper_field=m.group(1),
            )

        return None

    @classmethod
    def parse_from_subset_string(cls, subset_string: str) -> FlightLevelFilter | None:
        """Legacy alias for parse_fl_from_subset_string."""
        return cls.parse_fl_from_subset_string(subset_string)

    # -- Attribute-filter parsing --

    @staticmethod
    def parse_attribute_filters_from_subset(
        subset_string: str,
        searchable_columns: list[dict[str, str]],
    ) -> list[AttributeSearchFilter]:
        """Return one AttributeSearchFilter per column with its value from the subset string.

        Columns for which no expression is found in the subset get an empty value,
        so the dialog always shows all configured search fields.
        """
        result: list[AttributeSearchFilter] = []
        for col_def in searchable_columns:
            col_name = col_def.get("name", "")
            label = col_def.get("label", col_name)
            data_type = col_def.get("type", "varchar")
            if not col_name:
                continue
            value = LayerFilterService._parse_column_value_from_subset(
                subset_string,
                col_name,
                data_type,
            )
            result.append(
                AttributeSearchFilter(
                    column=col_name,
                    value=value,
                    label=label,
                    data_type=data_type,
                )
            )
        return result

    @staticmethod
    def _parse_column_value_from_subset(
        subset_string: str,
        column_name: str,
        data_type: str,
    ) -> str:
        col_escaped = re.escape(column_name)

        in_pattern = re.compile(
            rf'"{col_escaped}"\s+IN\s*\(([^)]*)\)',
            re.IGNORECASE,
        )
        in_match = in_pattern.search(subset_string)
        if in_match:
            parsed = LayerFilterService._parse_in_values(in_match.group(1), data_type)
            return ", ".join(parsed)

        eq_pattern = re.compile(
            rf'"{col_escaped}"\s*=\s*(\'[^\']*(?:\'\'[^\']*)*\'|-?\d+(?:\.\d+)?)',
            re.IGNORECASE,
        )
        eq_match = eq_pattern.search(subset_string)
        if not eq_match:
            return ""

        token = eq_match.group(1).strip()
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1].replace("''", "'")
        return token

    @staticmethod
    def _parse_in_values(raw_values: str, data_type: str) -> list[str]:
        if LayerFilterService._is_numeric_type(data_type):
            return [
                val.strip()
                for val in raw_values.split(",")
                if val.strip()
            ]

        return [
            match.group(1).replace("''", "'")
            for match in re.finditer(r"'((?:''|[^'])*)'", raw_values)
        ]

    # -- Stripping FL expressions --

    @staticmethod
    def strip_fl_from_subset_string(subset_string: str) -> str:
        """Remove any flight level expression from a QGIS subset string."""
        if not subset_string:
            return ""

        s = subset_string.strip()
        pat = LayerFilterService._PAT_ANY_FL.pattern

        # Remove "AND ({fl_expression})" anywhere (FL appended to combined expr)
        s = re.sub(r'\s+AND\s+\(' + pat + r'\)', "", s, flags=re.IGNORECASE).strip()

        # Remove "({fl_expression}) AND" anywhere (FL prepended)
        s = re.sub(r'\(' + pat + r'\)\s+AND\s+', "", s, flags=re.IGNORECASE).strip()

        # Remove bare FL expression when it is the entire remaining string
        if re.fullmatch(r'\s*(?:' + pat + r')\s*', s, flags=re.IGNORECASE):
            return ""

        # Remove one layer of outer parens left around the base filter
        return LayerFilterService._strip_outer_parens(s)

    @classmethod
    def strip_from_subset_string(cls, subset_string: str) -> str:
        """Legacy alias for strip_fl_from_subset_string."""
        return cls.strip_fl_from_subset_string(subset_string)

    # -- Stripping attribute expressions --

    @staticmethod
    def strip_attribute_filters_from_subset(
        subset_string: str,
        columns: list[str],
    ) -> str:
        """Remove equality expressions for the given columns from a subset string."""
        if not subset_string or not columns:
            return subset_string or ""

        s = subset_string.strip()
        for col in columns:
            pat_eq = rf'"{re.escape(col)}"\s*=\s*(?:\'[^\']*(?:\'\'[^\']*)*\'|-?\d+(?:\.\d+)?)'
            pat_in = rf'"{re.escape(col)}"\s+IN\s*\([^)]*\)'
            pat_inner = rf'(?:{pat_eq}|{pat_in})'

            # Remove "AND (col = 'val')" — filter was appended with parens
            s = re.sub(r'\s+AND\s+\(' + pat_inner + r'\)', "", s, flags=re.IGNORECASE).strip()

            # Remove "(col = 'val') AND" — filter was prepended with parens
            s = re.sub(r'\(' + pat_inner + r'\)\s+AND\s+', "", s, flags=re.IGNORECASE).strip()

            # Bare expression as entire string (with parens)
            if re.fullmatch(r'\s*\(' + pat_inner + r'\)\s*', s, flags=re.IGNORECASE):
                return ""

            # Remove "AND col = 'val'" without parens (fallback for edge cases)
            s = re.sub(r'\s+AND\s+' + pat_inner, "", s, flags=re.IGNORECASE).strip()

            # Remove "col = 'val' AND" without parens (fallback)
            s = re.sub(pat_inner + r'\s+AND\s+', "", s, flags=re.IGNORECASE).strip()

            # Bare expression as entire string (without parens)
            if re.fullmatch(r'\s*' + pat_inner + r'\s*', s, flags=re.IGNORECASE):
                return ""

        return LayerFilterService._strip_outer_parens(s.strip())

    @staticmethod
    def _strip_outer_parens(s: str) -> str:
        """Remove exactly one layer of matching outer parentheses, if present."""
        if not (s.startswith("(") and s.endswith(")")):
            return s
        depth = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s
        return s[1:-1].strip()
