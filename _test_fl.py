import sys, os, importlib.util

spec = importlib.util.spec_from_file_location(
    "geodata_catalog.services.flightlevel_filter_service",
    os.path.join(os.path.dirname(__file__), "geodata_catalog", "services", "flightlevel_filter_service.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
FlightLevelFilterService = mod.FlightLevelFilterService
FlightLevelFilter = mod.FlightLevelFilter

# Test parse BETWEEN
s1 = 'CAST("fl_lower" AS INTEGER) <= 355 AND CAST("fl_upper" AS INTEGER) >= 265'
r = FlightLevelFilterService.parse_from_subset_string(s1)
print("parse BETWEEN:", r)
assert r.mode == "between" and r.lower == 265 and r.upper == 355

# Test parse ABOVE
s2 = 'CAST("fl_lower" AS INTEGER) >= 240'
r = FlightLevelFilterService.parse_from_subset_string(s2)
print("parse ABOVE:", r)
assert r.mode == "above" and r.lower == 240

# Test parse BELOW
s3 = 'CAST("fl_upper" AS INTEGER) <= 400'
r = FlightLevelFilterService.parse_from_subset_string(s3)
print("parse BELOW:", r)
assert r.mode == "below" and r.upper == 400

# Test parse None for unrelated
r = FlightLevelFilterService.parse_from_subset_string("status = 'ACTIVE'")
print("parse None:", r)
assert r is None

# Test strip standalone BETWEEN
stripped = FlightLevelFilterService.strip_from_subset_string(s1)
print("strip standalone:", repr(stripped))
assert stripped == ""

# Test strip combined
combined = "(status = 'ACTIVE') AND (CAST(\"fl_lower\" AS INTEGER) <= 355 AND CAST(\"fl_upper\" AS INTEGER) >= 265)"
stripped = FlightLevelFilterService.strip_from_subset_string(combined)
print("strip combined:", repr(stripped))
assert stripped == "status = 'ACTIVE'", f"Got: {stripped!r}"

# Test strip unrelated unchanged
unchanged = FlightLevelFilterService.strip_from_subset_string("status = 'ACTIVE'")
print("strip unrelated:", repr(unchanged))
assert unchanged == "status = 'ACTIVE'"

print("ALL TESTS PASSED")
