from __future__ import annotations

import base64
import binascii
import posixpath
import re
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree

from geodata_catalog.exceptions import ConfigurationException

try:
    from qgis.core import QgsApplication
except ImportError:  # pragma: no cover
    QgsApplication = None


def is_embedded_svg(reference: str) -> bool:
    return reference.startswith(("base64:", "data:image/svg+xml;base64,"))


def _svg_file(reference: str) -> Path:
    normalized = posixpath.normpath(reference.replace("\\", "/"))
    path = Path(normalized)
    if path.is_file():
        return path

    # Old configurations may refer to another QGIS installation, including
    # Windows short paths such as PROGRA~1/QGIS42~1.2/apps/qgis/./svg//...
    qgis_match = re.search(r"(?:^|/)qgis(?:-[^/]+)?/svg/(.+)$", normalized, re.IGNORECASE)
    relative = qgis_match.group(1) if qgis_match else normalized
    if not Path(relative).is_absolute() and not PureWindowsPath(relative).is_absolute():
        if QgsApplication is not None:
            for root in QgsApplication.svgPaths():
                candidate = Path(root) / relative
                if candidate.is_file():
                    return candidate

    plugin_match = re.search(
        r"(?:^|/)geodata_catalog/resources/aviation_symbols/(.+)$",
        normalized,
        re.IGNORECASE,
    )
    if plugin_match:
        candidate = Path(__file__).parent / "resources" / "aviation_symbols" / plugin_match.group(1)
        if candidate.is_file():
            return candidate
    raise ConfigurationException(
        f"SVG marker file not found: {reference}. Select the SVG again on this computer."
    )


def _validate_svg(data: bytes) -> None:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ConfigurationException(f"Invalid SVG marker: {exc}") from exc
    if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
        raise ConfigurationException("The marker file is not an SVG document.")
    for element in root.iter():
        for name, value in element.attrib.items():
            if name.rsplit("}", 1)[-1] == "href" and value.strip():
                if not value.strip().startswith(("#", "data:")):
                    raise ConfigurationException(
                        "The SVG marker uses an external resource. Embed linked images or files in the SVG first."
                    )
        for value in [*element.attrib.values(), element.text or ""]:
            if "@import" in value.casefold():
                raise ConfigurationException("The SVG marker must not import external stylesheets.")
            for target in re.findall(r"url\((.*?)\)", value, re.IGNORECASE | re.DOTALL):
                if not target.strip(" \t\r\n'\"").startswith(("#", "data:")):
                    raise ConfigurationException(
                        "The SVG marker uses an external resource. Embed linked images or files in the SVG first."
                    )


def portable_svg_reference(reference: str | None) -> str | None:
    """Return a validated, self-contained QGIS SVG reference for JSON storage."""
    if reference is None:
        return None
    if not isinstance(reference, str):
        raise ConfigurationException("The SVG marker reference must be a string.")
    if not reference.strip():
        return None
    reference = reference.strip()
    if is_embedded_svg(reference):
        encoded = reference.split(",", 1)[1] if reference.startswith("data:") else reference[7:]
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigurationException("The embedded SVG marker has invalid base64 data.") from exc
    else:
        try:
            data = _svg_file(reference).read_bytes()
        except OSError as exc:
            raise ConfigurationException(f"Unable to read SVG marker '{reference}': {exc}") from exc
    _validate_svg(data)
    return "base64:" + base64.b64encode(data).decode("ascii")
