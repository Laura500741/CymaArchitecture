"""Neutral, immutable 2D geometric primitives.

These types know nothing about physics or file formats. Coordinates are in
*model units* (metres throughout CymaArchitecture); exporters convert to the
output :class:`~cymaarchitecture.geometry.exporters.base.LengthUnit`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np

__all__ = ["Point2D", "Polyline2D", "GeometryLayer", "GeometryDocument", "Bounds"]

Bounds = tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        if not (math.isfinite(self.x) and math.isfinite(self.y)):
            raise ValueError(f"Point2D coordinates must be finite, got ({self.x}, {self.y})")

    def distance_to(self, other: Point2D) -> float:
        return math.hypot(other.x - self.x, other.y - self.y)

    def translated(self, dx: float, dy: float) -> Point2D:
        return Point2D(self.x + dx, self.y + dy)

    def scaled(self, factor: float) -> Point2D:
        return Point2D(self.x * factor, self.y * factor)


@dataclass(frozen=True)
class Polyline2D:
    """Ordered sequence of points; ``closed`` adds an implicit last->first segment.

    A closed polyline does *not* store its first point twice.
    """

    points: tuple[Point2D, ...]
    closed: bool = False

    def __post_init__(self) -> None:
        pts = tuple(self.points)
        if len(pts) < 2:
            raise ValueError("a Polyline2D needs at least 2 points")
        if not all(isinstance(p, Point2D) for p in pts):
            raise TypeError("points must be Point2D instances")
        if self.closed and len(pts) < 3:
            raise ValueError("a closed Polyline2D needs at least 3 points")
        object.__setattr__(self, "points", pts)

    # --------------------------------------------------------------- builders
    @classmethod
    def from_coordinates(cls, coords: Iterable[tuple[float, float]] | np.ndarray, closed: bool | None = None) -> Polyline2D:
        """Build from ``(x, y)`` pairs.

        With ``closed=None`` the polyline is closed automatically when the first
        and last points coincide (the duplicate is dropped).
        """
        pts = [Point2D(float(x), float(y)) for x, y in coords]
        repeats = len(pts) > 3 and pts[0].distance_to(pts[-1]) <= 1e-12
        if closed is None:
            closed = repeats
        if closed and repeats:
            pts = pts[:-1]
        return cls(tuple(pts), closed)

    def to_array(self) -> np.ndarray:
        return np.array([(p.x, p.y) for p in self.points], dtype=float)

    # ------------------------------------------------------------- queries
    def __len__(self) -> int:
        return len(self.points)

    def segments(self) -> list[tuple[Point2D, Point2D]]:
        pts = self.points
        segs = list(zip(pts[:-1], pts[1:]))
        if self.closed:
            segs.append((pts[-1], pts[0]))
        return segs

    @property
    def length(self) -> float:
        return sum(a.distance_to(b) for a, b in self.segments())

    @property
    def bounds(self) -> Bounds:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    # ----------------------------------------------------------- transforms
    def translated(self, dx: float, dy: float) -> Polyline2D:
        return Polyline2D(tuple(p.translated(dx, dy) for p in self.points), self.closed)

    def scaled(self, factor: float) -> Polyline2D:
        return Polyline2D(tuple(p.scaled(factor) for p in self.points), self.closed)

    def simplified(self, tolerance: float) -> Polyline2D:
        """Ramer-Douglas-Peucker simplification (endpoints preserved)."""
        if tolerance <= 0 or len(self.points) <= 2:
            return self
        arr = self.to_array()
        if self.closed:
            arr = np.vstack([arr, arr[:1]])
        keep = _rdp_mask(arr, tolerance)
        kept = arr[keep]
        if self.closed:
            kept = kept[:-1]
            if len(kept) < 3:
                return self
        return Polyline2D(tuple(Point2D(x, y) for x, y in kept), self.closed)


def _rdp_mask(arr: np.ndarray, tolerance: float) -> np.ndarray:
    keep = np.zeros(len(arr), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(arr) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = arr[start], arr[end]
        seg = b - a
        seg_len = float(np.hypot(*seg))
        rel = arr[start + 1 : end] - a
        if seg_len == 0.0:
            dist = np.hypot(rel[:, 0], rel[:, 1])
        else:
            dist = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / seg_len
        idx = int(np.argmax(dist))
        if dist[idx] > tolerance:
            mid = start + 1 + idx
            keep[mid] = True
            stack.append((start, mid))
            stack.append((mid, end))
    return keep


@dataclass(frozen=True)
class GeometryLayer:
    """Named group of polylines with a display colour (``#rrggbb``)."""

    name: str
    polylines: tuple[Polyline2D, ...] = ()
    color: str = "#000000"

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("layer name must not be empty")
        if any(ch in self.name for ch in '<>/\\":;?*|=`'):
            raise ValueError(f"layer name contains characters invalid for CAD: {self.name!r}")
        color = self.color.lower()
        if len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdef" for c in color[1:]):
            raise ValueError(f"color must be '#rrggbb', got {self.color!r}")
        object.__setattr__(self, "color", color)
        object.__setattr__(self, "polylines", tuple(self.polylines))

    def __len__(self) -> int:
        return len(self.polylines)

    @property
    def bounds(self) -> Bounds | None:
        if not self.polylines:
            return None
        return _merge_bounds(pl.bounds for pl in self.polylines)

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (int(self.color[1:3], 16), int(self.color[3:5], 16), int(self.color[5:7], 16))


@dataclass(frozen=True)
class GeometryDocument:
    """A drawing: canvas size (model units), layers and free-form metadata."""

    width: float
    height: float
    layers: tuple[GeometryLayer, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (self.width > 0 and self.height > 0):
            raise ValueError("document width and height must be positive")
        layers = tuple(self.layers)
        names = [layer.name for layer in layers]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate layer names: {names}")
        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "metadata", MappingProxyType({str(k): str(v) for k, v in self.metadata.items()}))

    def layer(self, name: str) -> GeometryLayer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise KeyError(name)

    @property
    def polyline_count(self) -> int:
        return sum(len(layer) for layer in self.layers)

    @property
    def bounds(self) -> Bounds | None:
        boxes = [b for b in (layer.bounds for layer in self.layers) if b is not None]
        return _merge_bounds(boxes) if boxes else None


def _merge_bounds(boxes: Iterable[Bounds]) -> Bounds:
    boxes = list(boxes)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
