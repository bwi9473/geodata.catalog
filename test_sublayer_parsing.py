#!/usr/bin/env python3
"""Quick test to verify sublayer parsing logic without QGIS dependency."""


def _parse_sublayer_entry(entry: str) -> dict[str, str | None]:
    """Standalone version of KmlConnector._parse_sublayer_entry for testing."""
    tokens = [token.strip() for token in entry.split("!!::!!") if token is not None]
    if len(tokens) < 2:
        return {"name": entry.strip(), "layer_id": None}

    # OGR can emit either "id!!::!!name..." or "name!!::!!id...".
    first, second = tokens[0], tokens[1]
    if first.isdigit():
        return {"name": second, "layer_id": first}
    if second.isdigit():
        return {"name": first, "layer_id": second}

    # Fallback for providers that don't include a numeric layer id.
    return {"name": second, "layer_id": None}


# Simulate real OGR sublayer entry formats that QGIS returns for KML
test_cases = [
    # Common OGR format: id!!::!!name!!::!!geometry_type!!::!!geometry_dimension
    "1!!::!!Aerodromes!!::!!Point!!::!!Point25D",
    "0!!::!!Network!!::!!Polygon!!::!!PolygonM",
    # Alternative order (name first)
    "Aerodromes!!::!!1!!::!!Point!!::!!Point25D",
    # Simple name (no sublayers)
    "Aerodromes",
    # Edge case: just numeric id
    "1",
]

print("Testing KML sublayer parsing:")
print("-" * 60)

for entry in test_cases:
    parsed = _parse_sublayer_entry(entry)
    print(f"Entry:     {entry!r}")
    print(f"  → name:     {parsed['name']!r}")
    print(f"  → layer_id: {parsed['layer_id']!r}")
    print()

# Test the URI construction
print("\nURIs constructed for each case:")
print("-" * 60)

for entry in test_cases:
    parsed = _parse_sublayer_entry(entry)
    path = "C:/tmp/aerodromes_sample.kml"
    uri = (
        f"{path}|layerid={parsed['layer_id']}"
        if parsed["layer_id"] is not None
        else f"{path}|layername={parsed['name']}"
    )
    print(f"Sublayer: {parsed['name']!r}")
    print(f"  → URI:  {uri}")
    print()
