"""Adapter: physics (:class:`ChladniPattern`) -> neutral geometry (:class:`GeometryDocument`)."""

from __future__ import annotations

from ...cymatics.rectangularplate import ChladniPattern
from ..primitives import GeometryDocument, GeometryLayer, Point2D, Polyline2D

__all__ = ["geometry_from_chladni_pattern", "OUTLINE_LAYER", "NODAL_LAYER"]

OUTLINE_LAYER = "PLATE_OUTLINE"
NODAL_LAYER = "NODAL_LINES"


def geometry_from_chladni_pattern(
    pattern: ChladniPattern,
    *,
    include_outline: bool = True,
    min_length: float = 0.0,
    simplify_tolerance: float = 0.0,
    outline_color: str = "#000000",
    nodal_color: str = "#c0392b",
) -> GeometryDocument:
    """Convert a Chladni pattern into a geometry document (units: metres).

    Parameters
    ----------
    min_length:
        Discard nodal lines shorter than this (metres) - removes numerical specks.
    simplify_tolerance:
        Ramer-Douglas-Peucker tolerance in metres (0 disables simplification).
    """
    plate = pattern.plate
    a, b = plate.width, plate.height

    nodal: list[Polyline2D] = []
    for line in pattern.nodal_lines:
        if len(line) < 2:
            continue
        try:
            polyline = Polyline2D.from_coordinates(line)
        except ValueError:  # degenerate after de-duplication
            continue
        if simplify_tolerance > 0:
            polyline = polyline.simplified(simplify_tolerance)
        if polyline.length >= min_length and polyline.length > 0:
            nodal.append(polyline)

    layers = []
    if include_outline:
        outline = Polyline2D((Point2D(0, 0), Point2D(a, 0), Point2D(a, b), Point2D(0, b)), closed=True)
        layers.append(GeometryLayer(OUTLINE_LAYER, (outline,), outline_color))
    layers.append(GeometryLayer(NODAL_LAYER, tuple(nodal), nodal_color))

    metadata = {
        "source": "cymaarchitecture.chladni",
        "frequency_hz": f"{pattern.frequency_hz:.6g}",
        "boundary": plate.boundary.value,
        "plate_width_m": f"{a:.6g}",
        "plate_height_m": f"{b:.6g}",
        "plate_thickness_m": f"{plate.thickness:.6g}",
    }
    if pattern.dominant_mode is not None:
        metadata["mode"] = pattern.dominant_mode.label
    return GeometryDocument(a, b, tuple(layers), metadata)
