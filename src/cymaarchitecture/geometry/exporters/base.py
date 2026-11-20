"""Exporter contract and length units."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..primitives import GeometryDocument

__all__ = ["LengthUnit", "GeometryExporter", "write_text_file"]


class LengthUnit(Enum):
    """Output length unit: symbol, factor from metres, DXF ``$INSUNITS`` code."""

    METER = ("m", 1.0, 6)
    CENTIMETER = ("cm", 100.0, 5)
    MILLIMETER = ("mm", 1000.0, 4)
    INCH = ("in", 1.0 / 0.0254, 1)

    def __init__(self, symbol: str, per_meter: float, dxf_code: int) -> None:
        self.symbol = symbol
        self.per_meter = per_meter
        self.dxf_code = dxf_code

    def from_meters(self, value: float) -> float:
        return value * self.per_meter


@runtime_checkable
class GeometryExporter(Protocol):
    """Anything that can serialise a :class:`GeometryDocument` to a file."""

    file_extension: str

    def render(self, document: GeometryDocument) -> str:
        """Return the file content as text."""
        ...

    def export(self, document: GeometryDocument, path: str | Path) -> Path:
        """Write the document to ``path`` and return the resolved path."""
        ...


def write_text_file(content: str, path: str | Path, extension: str) -> Path:
    """Write ``content``, adding ``extension`` when missing and creating parents."""
    target = Path(path)
    if target.suffix.lower() != extension.lower():
        target = target.with_name(target.name + extension)
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps the exact line endings produced by the exporter.
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return target.resolve()
