"""Cymatics: thin-plate (Kirchhoff-Love) physics and Chladni pattern generation."""

from .batch_generator import BatchGenerator, frequency_range
from .rectangularplate import BoundaryCondition, ChladniPattern, PlateMode, RectangularPlate
from .solver import (
    KirchhoffLoveSolver,
    ModalSolution,
    compute_composite_pattern,
    compute_pattern,
    forced_response,
    marching_squares,
    pattern_for_mode,
)

__all__ = [
    "BatchGenerator",
    "BoundaryCondition",
    "ChladniPattern",
    "KirchhoffLoveSolver",
    "ModalSolution",
    "PlateMode",
    "RectangularPlate",
    "compute_composite_pattern",
    "compute_pattern",
    "forced_response",
    "frequency_range",
    "marching_squares",
    "pattern_for_mode",
]
