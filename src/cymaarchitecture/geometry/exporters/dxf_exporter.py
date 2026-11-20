"""DXF exporter: AutoCAD 2000 (``AC1015``) ASCII, polylines as ``LWPOLYLINE``.

The writer emits the sections an R2000 reader expects - HEADER, CLASSES,
TABLES (VPORT, LTYPE, LAYER, STYLE, VIEW, UCS, APPID, DIMSTYLE, BLOCK_RECORD),
BLOCKS (``*Model_Space``/``*Paper_Space``), ENTITIES and OBJECTS (root
dictionary + ``ACAD_GROUP``) - with unique hexadecimal handles, owner pointers
(group 330) and subclass markers (group 100). Each geometry layer becomes a DXF
layer whose colour is the nearest AutoCAD Color Index (ACI) colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..primitives import GeometryDocument, GeometryLayer
from .base import LengthUnit, write_text_file

__all__ = ["DxfExporter", "nearest_aci"]

_ACI_RGB = {
    1: (255, 0, 0),
    2: (255, 255, 0),
    3: (0, 255, 0),
    4: (0, 255, 255),
    5: (0, 0, 255),
    6: (255, 0, 255),
    7: (0, 0, 0),  # "white/black": rendered with contrast to the background
    8: (128, 128, 128),
    9: (192, 192, 192),
}


def nearest_aci(rgb: tuple[int, int, int]) -> int:
    """Nearest basic AutoCAD Color Index (1-9) to an RGB triple."""
    return min(_ACI_RGB, key=lambda k: sum((a - b) ** 2 for a, b in zip(_ACI_RGB[k], rgb)))


class _DxfBuilder:
    def __init__(self, fmt) -> None:
        self._next = 1
        self.lines: list[str] = []
        self.fmt = fmt

    def handle(self) -> str:
        value = f"{self._next:X}"
        self._next += 1
        return value

    @property
    def seed(self) -> str:
        return f"{self._next:X}"

    def tag(self, code: int, value: object) -> None:
        if isinstance(value, float):
            value = self.fmt(value)
        self.lines.append(f"{code:>3}")
        self.lines.append(str(value))

    def tags(self, *pairs: tuple[int, object]) -> None:
        for code, value in pairs:
            self.tag(code, value)


@dataclass(frozen=True)
class DxfExporter:
    """Write a :class:`GeometryDocument` as an AutoCAD 2000 ASCII DXF."""

    unit: LengthUnit = LengthUnit.MILLIMETER
    precision: int = 6
    file_extension: str = ".dxf"

    def _fmt(self, value: float) -> str:
        text = f"{value:.{self.precision}f}"
        return "0.0" if float(text) == 0.0 else text

    # ---------------------------------------------------------------- render
    def render(self, document: GeometryDocument) -> str:
        u = self.unit.from_meters
        width, height = u(document.width), u(document.height)
        layers: list[GeometryLayer] = [layer for layer in document.layers if layer.name != "0"]

        # Tables/blocks/entities/objects are written first so $HANDSEED is known.
        b = body = _DxfBuilder(self._fmt)

        # ------------------------------------------------------ TABLES
        h_root_dict = b.handle()
        h_group_dict = b.handle()
        h_ms_record = b.handle()
        h_ps_record = b.handle()

        body.tags((0, "SECTION"), (2, "TABLES"))

        def table(name: str, count: int, extra: tuple[tuple[int, object], ...] = ()) -> str:
            h = b.handle()
            body.tags((0, "TABLE"), (2, name), (5, h), (330, "0"), (100, "AcDbSymbolTable"), (70, count), *extra)
            return h

        # VPORT
        t = table("VPORT", 1)
        body.tags(
            (0, "VPORT"), (5, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
            (100, "AcDbViewportTableRecord"), (2, "*Active"), (70, 0),
            (10, 0.0), (20, 0.0), (11, 1.0), (21, 1.0),
            (12, width / 2), (22, height / 2), (13, 0.0), (23, 0.0), (14, 1.0), (24, 1.0),
            (15, 0.0), (25, 0.0), (16, 0.0), (26, 0.0), (36, 1.0), (17, 0.0), (27, 0.0), (37, 0.0),
            (40, height * 1.1), (41, max(width / height, 1e-6)), (42, 50.0), (43, 0.0), (44, 0.0),
            (50, 0.0), (51, 0.0), (71, 0), (72, 100), (73, 1), (74, 3), (75, 0), (76, 0), (77, 0), (78, 0),
        )
        body.tag(0, "ENDTAB")

        # LTYPE
        t = table("LTYPE", 3)
        for name, desc in (("ByBlock", ""), ("ByLayer", ""), ("Continuous", "Solid line")):
            body.tags(
                (0, "LTYPE"), (5, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
                (100, "AcDbLinetypeTableRecord"), (2, name), (70, 0), (3, desc), (72, 65), (73, 0), (40, 0.0),
            )
        body.tag(0, "ENDTAB")

        # LAYER
        t = table("LAYER", len(layers) + 1)
        for name, color in [("0", 7)] + [(layer.name, nearest_aci(layer.rgb)) for layer in layers]:
            body.tags(
                (0, "LAYER"), (5, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
                (100, "AcDbLayerTableRecord"), (2, name), (70, 0), (62, color), (6, "Continuous"), (370, -3),
            )
        body.tag(0, "ENDTAB")

        # STYLE
        t = table("STYLE", 1)
        body.tags(
            (0, "STYLE"), (5, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
            (100, "AcDbTextStyleTableRecord"), (2, "Standard"), (70, 0), (40, 0.0), (41, 1.0), (50, 0.0),
            (71, 0), (42, 2.5), (3, "txt"), (4, ""),
        )
        body.tag(0, "ENDTAB")

        # VIEW, UCS (empty)
        table("VIEW", 0)
        body.tag(0, "ENDTAB")
        table("UCS", 0)
        body.tag(0, "ENDTAB")

        # APPID
        t = table("APPID", 1)
        body.tags(
            (0, "APPID"), (5, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
            (100, "AcDbRegAppTableRecord"), (2, "ACAD"), (70, 0),
        )
        body.tag(0, "ENDTAB")

        # DIMSTYLE (records use group 105 for their handle)
        t = table("DIMSTYLE", 1, ((100, "AcDbDimStyleTable"), (71, 1)))
        body.tags(
            (0, "DIMSTYLE"), (105, b.handle()), (330, t), (100, "AcDbSymbolTableRecord"),
            (100, "AcDbDimStyleTableRecord"), (2, "Standard"), (70, 0),
        )
        body.tag(0, "ENDTAB")

        # BLOCK_RECORD
        t = table("BLOCK_RECORD", 2)
        for h, name in ((h_ms_record, "*Model_Space"), (h_ps_record, "*Paper_Space")):
            body.tags(
                (0, "BLOCK_RECORD"), (5, h), (330, t), (100, "AcDbSymbolTableRecord"),
                (100, "AcDbBlockTableRecord"), (2, name),
            )
        body.tag(0, "ENDTAB")
        body.tag(0, "ENDSEC")

        # ------------------------------------------------------ BLOCKS
        body.tags((0, "SECTION"), (2, "BLOCKS"))
        for owner, name, paper in ((h_ms_record, "*Model_Space", False), (h_ps_record, "*Paper_Space", True)):
            body.tags((0, "BLOCK"), (5, b.handle()), (330, owner), (100, "AcDbEntity"))
            if paper:
                body.tag(67, 1)
            body.tags(
                (8, "0"), (100, "AcDbBlockBegin"), (2, name), (70, 0),
                (10, 0.0), (20, 0.0), (30, 0.0), (3, name), (1, ""),
            )
            body.tags((0, "ENDBLK"), (5, b.handle()), (330, owner), (100, "AcDbEntity"))
            if paper:
                body.tag(67, 1)
            body.tags((8, "0"), (100, "AcDbBlockEnd"))
        body.tag(0, "ENDSEC")

        # ------------------------------------------------------ ENTITIES
        body.tags((0, "SECTION"), (2, "ENTITIES"))
        for layer in document.layers:
            for polyline in layer.polylines:
                body.tags(
                    (0, "LWPOLYLINE"), (5, b.handle()), (330, h_ms_record), (100, "AcDbEntity"),
                    (8, layer.name), (100, "AcDbPolyline"), (90, len(polyline.points)),
                    (70, 1 if polyline.closed else 0), (43, 0.0),
                )
                for p in polyline.points:
                    body.tags((10, u(p.x)), (20, u(p.y)))
        body.tag(0, "ENDSEC")

        # ------------------------------------------------------ OBJECTS
        body.tags(
            (0, "SECTION"), (2, "OBJECTS"),
            (0, "DICTIONARY"), (5, h_root_dict), (330, "0"), (100, "AcDbDictionary"), (281, 1),
            (3, "ACAD_GROUP"), (350, h_group_dict),
            (0, "DICTIONARY"), (5, h_group_dict), (330, h_root_dict), (100, "AcDbDictionary"), (281, 1),
            (0, "ENDSEC"),
        )
        body.tag(0, "EOF")

        # ------------------------------------------------------ HEADER (+ CLASSES)
        head = _DxfBuilder(self._fmt)
        head.tags(
            (0, "SECTION"), (2, "HEADER"),
            (9, "$ACADVER"), (1, "AC1015"),
            (9, "$DWGCODEPAGE"), (3, "ANSI_1252"),
            (9, "$HANDSEED"), (5, b.seed),
            (9, "$INSUNITS"), (70, self.unit.dxf_code),
            (9, "$MEASUREMENT"), (70, 0 if self.unit is LengthUnit.INCH else 1),
            (9, "$EXTMIN"), (10, 0.0), (20, 0.0), (30, 0.0),
            (9, "$EXTMAX"), (10, width), (20, height), (30, 0.0),
            (9, "$LIMMIN"), (10, 0.0), (20, 0.0),
            (9, "$LIMMAX"), (10, width), (20, height),
            (0, "ENDSEC"),
            (0, "SECTION"), (2, "CLASSES"), (0, "ENDSEC"),
        )
        comments = [f"999\n{k}={v}" for k, v in sorted(document.metadata.items()) if "\n" not in k + v]
        return "\n".join(comments + head.lines + body.lines) + "\n"

    def export(self, document: GeometryDocument, path: str | Path) -> Path:
        return write_text_file(self.render(document), path, self.file_extension)
