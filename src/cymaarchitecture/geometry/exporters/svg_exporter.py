"""SVG exporter (SVG 1.1, physical size in real units, one ``<g>`` per layer)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..primitives import GeometryDocument, Polyline2D
from .base import LengthUnit, write_text_file

__all__ = ["SvgExporter"]

# SVG has no "m" unit: metres are written as centimetres (same physical size).
_SVG_UNIT = {
    LengthUnit.METER: ("cm", 100.0),
    LengthUnit.CENTIMETER: ("cm", 1.0),
    LengthUnit.MILLIMETER: ("mm", 1.0),
    LengthUnit.INCH: ("in", 1.0),
}


@dataclass(frozen=True)
class SvgExporter:
    """Write a :class:`GeometryDocument` as SVG.

    The SVG user coordinate system equals ``unit`` (``viewBox`` in that unit) and
    the y axis is flipped so the drawing keeps the mathematical orientation
    (origin at the lower-left corner).
    """

    unit: LengthUnit = LengthUnit.MILLIMETER
    stroke_width: float | None = None  # in `unit`; default: 0.25 % of the largest side
    precision: int = 4
    background: str | None = "#ffffff"
    file_extension: str = ".svg"

    def _fmt(self, value: float) -> str:
        text = f"{value:.{self.precision}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text

    def render(self, document: GeometryDocument) -> str:
        u = self.unit.from_meters
        width, height = u(document.width), u(document.height)
        svg_unit, factor = _SVG_UNIT[self.unit]
        stroke = self.stroke_width if self.stroke_width is not None else 0.0025 * max(width, height)

        def coords(polyline: Polyline2D) -> str:
            return " ".join(f"{self._fmt(u(p.x))},{self._fmt(height - u(p.y))}" for p in polyline.points)

        out = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{self._fmt(width * factor)}{svg_unit}" height="{self._fmt(height * factor)}{svg_unit}" '
            f'viewBox="0 0 {self._fmt(width)} {self._fmt(height)}">',
        ]
        title = document.metadata.get("mode") or document.metadata.get("source", "CymaArchitecture")
        out.append(f"  <title>{escape(title)}</title>")
        if document.metadata:
            desc = "; ".join(f"{k}={v}" for k, v in sorted(document.metadata.items()))
            out.append(f"  <desc>{escape(desc)}</desc>")
        if self.background:
            out.append(
                f'  <rect x="0" y="0" width="{self._fmt(width)}" height="{self._fmt(height)}" '
                f'fill={quoteattr(self.background)} stroke="none"/>'
            )
        for layer in document.layers:
            out.append(
                f"  <g id={quoteattr(layer.name)} fill=\"none\" stroke={quoteattr(layer.color)} "
                f'stroke-width="{self._fmt(stroke)}" stroke-linecap="round" stroke-linejoin="round">'
            )
            for polyline in layer.polylines:
                tag = "polygon" if polyline.closed else "polyline"
                out.append(f'    <{tag} points="{coords(polyline)}"/>')
            out.append("  </g>")
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def export(self, document: GeometryDocument, path: str | Path) -> Path:
        return write_text_file(self.render(document), path, self.file_extension)
