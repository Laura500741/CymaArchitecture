"""Batch generation of Chladni patterns: frequency sweeps and resonant series."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .rectangularplate import ChladniPattern, RectangularPlate
from .solver import compute_pattern, pattern_for_mode

__all__ = ["frequency_range", "BatchGenerator"]


def frequency_range(f_start: float, f_stop: float, steps: int, spacing: str = "linear") -> np.ndarray:
    """Frequencies for a sweep. ``spacing`` is ``"linear"`` or ``"log"``."""
    if steps < 1:
        raise ValueError("steps must be >= 1")
    if f_start <= 0 or f_stop <= 0:
        raise ValueError("frequencies must be positive")
    if f_stop < f_start:
        raise ValueError("f_stop must be >= f_start")
    if spacing == "linear":
        return np.linspace(f_start, f_stop, steps)
    if spacing == "log":
        return np.geomspace(f_start, f_stop, steps)
    raise ValueError(f"unknown spacing {spacing!r}; use 'linear' or 'log'")


@dataclass(frozen=True)
class BatchGenerator:
    """Generates series of patterns for one plate with shared numerical settings."""

    plate: RectangularPlate
    resolution: int = 200
    max_order: int = 10
    damping_ratio: float = 0.02
    drive_point: tuple[float, float] | None = None

    def iter_sweep(
        self, f_start: float, f_stop: float, steps: int, spacing: str = "linear"
    ) -> Iterator[ChladniPattern]:
        """Lazily yield driven patterns over a frequency range."""
        for f in frequency_range(f_start, f_stop, steps, spacing):
            yield compute_pattern(
                self.plate,
                float(f),
                resolution=self.resolution,
                max_order=self.max_order,
                damping_ratio=self.damping_ratio,
                drive_point=self.drive_point,
            )

    def sweep(self, f_start: float, f_stop: float, steps: int, spacing: str = "linear") -> list[ChladniPattern]:
        """Driven patterns over a frequency range (eager)."""
        return list(self.iter_sweep(f_start, f_stop, steps, spacing))

    def resonant(self, count: int) -> list[ChladniPattern]:
        """Pure modal patterns of the ``count`` lowest modes."""
        if count < 1:
            raise ValueError("count must be >= 1")
        modes = self.plate.modes(self.max_order)[:count]
        return [pattern_for_mode(self.plate, mode, resolution=self.resolution) for mode in modes]
