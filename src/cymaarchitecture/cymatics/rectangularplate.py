"""Physical models: rectangular Kirchhoff-Love plate and Chladni patterns.

Physics
-------
Free transverse vibration of a thin, isotropic, homogeneous plate
(Kirchhoff-Love theory) is governed by

    D * nabla^4 w + rho * h * d^2 w / dt^2 = 0,     D = E h^3 / (12 (1 - nu^2))

with ``D`` the flexural rigidity, ``rho`` the density and ``h`` the thickness.

* **Simply supported** (Navier) rectangular plate ``a x b``: exact modes

      w_mn(x, y) = sin(m pi x / a) sin(n pi y / b),   m, n >= 1
      omega_mn   = pi^2 * sqrt(D / (rho h)) * ((m/a)^2 + (n/b)^2)

* **Free** plate (the classical Chladni experiment): no closed-form solution
  exists. We use the classical Rayleigh/Ritz-style approximation with cosine
  beam functions,

      w_mn = cos(m pi x / a) cos(n pi y / b)   (rectangular plates)

  and, for *square* plates, the degenerate-pair superposition that reproduces
  Chladni's figures

      w_mn^(+/-) = cos(m pi x/a) cos(n pi y/a) +/- cos(n pi x/a) cos(m pi y/a)

  with the same frequency estimate as above. Frequencies of free-plate modes are
  therefore *approximate* (typically within ~10-20 % of measured values); the
  nodal topology is qualitatively correct.

Coordinates are SI (metres), origin at the lower-left corner of the plate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

__all__ = [
    "BoundaryCondition",
    "PlateMode",
    "RectangularPlate",
    "ChladniPattern",
]


class BoundaryCondition(str, Enum):
    """Edge support condition of the plate."""

    SIMPLY_SUPPORTED = "simply_supported"
    FREE = "free"


@dataclass(frozen=True, order=True)
class PlateMode:
    """A single vibration mode ``(m, n)``.

    ``symmetry`` is ``+1``/``-1`` for the symmetric/antisymmetric superposition
    used for free square plates and ``0`` for a plain separable mode.
    Ordering is by frequency first, so ``sorted(modes)`` sorts by frequency.
    """

    frequency_hz: float
    m: int
    n: int
    symmetry: int = 0

    @property
    def label(self) -> str:
        sign = {1: "+", -1: "-", 0: ""}[self.symmetry]
        return f"({self.m},{self.n}){sign}"


@dataclass(frozen=True)
class RectangularPlate:
    """Thin isotropic rectangular plate.

    Defaults correspond to a 1 mm brass plate, a classic Chladni setup.
    """

    width: float = 0.24  # a  [m]  (x direction)
    height: float = 0.24  # b  [m]  (y direction)
    thickness: float = 0.001  # h  [m]
    youngs_modulus: float = 100e9  # E  [Pa]
    density: float = 8500.0  # rho [kg/m^3]
    poisson_ratio: float = 0.33  # nu [-]
    boundary: BoundaryCondition = BoundaryCondition.FREE

    def __post_init__(self) -> None:
        for name in ("width", "height", "thickness", "youngs_modulus", "density"):
            value = getattr(self, name)
            if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
                raise ValueError(f"{name} must be a positive finite number, got {value!r}")
        if not (-1.0 < self.poisson_ratio < 0.5):
            raise ValueError(f"poisson_ratio must lie in (-1, 0.5), got {self.poisson_ratio!r}")
        # Accept plain strings such as "free".
        object.__setattr__(self, "boundary", BoundaryCondition(self.boundary))
        if self.thickness >= 0.1 * min(self.width, self.height):
            raise ValueError("thickness must be < 10% of the smallest side (thin-plate theory)")

    # ------------------------------------------------------------------ physics
    @property
    def flexural_rigidity(self) -> float:
        """D = E h^3 / (12 (1 - nu^2))  [N m]."""
        return self.youngs_modulus * self.thickness**3 / (12.0 * (1.0 - self.poisson_ratio**2))

    @property
    def mass_per_area(self) -> float:
        """rho * h  [kg/m^2]."""
        return self.density * self.thickness

    @property
    def is_square(self) -> bool:
        return math.isclose(self.width, self.height, rel_tol=1e-9)

    def angular_frequency(self, m: int, n: int) -> float:
        """omega_mn = pi^2 sqrt(D / rho h) ((m/a)^2 + (n/b)^2)  [rad/s]."""
        k2 = (m / self.width) ** 2 + (n / self.height) ** 2
        return math.pi**2 * math.sqrt(self.flexural_rigidity / self.mass_per_area) * k2

    def natural_frequency(self, m: int, n: int) -> float:
        """Natural frequency in Hz (exact for simply supported, approximate for free)."""
        return self.angular_frequency(m, n) / (2.0 * math.pi)

    def modes(self, max_order: int = 8) -> list[PlateMode]:
        """All modes with ``m, n <= max_order``, sorted by frequency."""
        if max_order < 1:
            raise ValueError("max_order must be >= 1")
        result: list[PlateMode] = []
        if self.boundary is BoundaryCondition.SIMPLY_SUPPORTED:
            for m in range(1, max_order + 1):
                for n in range(1, max_order + 1):
                    result.append(PlateMode(self.natural_frequency(m, n), m, n))
        elif self.is_square:
            for m in range(0, max_order + 1):
                for n in range(m, max_order + 1):
                    if m + n < 2:  # (0,0) rigid translation, (0,1) ~ rigid tilt
                        continue
                    f = self.natural_frequency(m, n)
                    if m == n:
                        result.append(PlateMode(f, m, n, +1))
                    else:
                        result.append(PlateMode(f, m, n, +1))
                        result.append(PlateMode(f, m, n, -1))
        else:
            for m in range(0, max_order + 1):
                for n in range(0, max_order + 1):
                    if m + n < 2:
                        continue
                    result.append(PlateMode(self.natural_frequency(m, n), m, n))
        return sorted(result)

    def mode_shape(self, mode: PlateMode, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Evaluate the (unnormalised, peak ~1) mode shape on a meshgrid ``x, y``."""
        a, b = self.width, self.height
        m, n = mode.m, mode.n
        if self.boundary is BoundaryCondition.SIMPLY_SUPPORTED:
            return np.sin(m * np.pi * x / a) * np.sin(n * np.pi * y / b)
        base = np.cos(m * np.pi * x / a) * np.cos(n * np.pi * y / b)
        if mode.symmetry == 0 or m == n:
            return base
        swapped = np.cos(n * np.pi * x / a) * np.cos(m * np.pi * y / b)
        return 0.5 * (base + mode.symmetry * swapped)

    def grid(self, resolution: int) -> tuple[np.ndarray, np.ndarray]:
        """Cell-centred sampling coordinates (1D ``x``, ``y``).

        Cell-centred samples avoid evaluating exactly on the simply supported
        edges (where ``w == 0`` identically) and keep the aspect ratio.
        """
        if resolution < 4:
            raise ValueError("resolution must be >= 4")
        longest = max(self.width, self.height)
        nx = max(4, round(resolution * self.width / longest))
        ny = max(4, round(resolution * self.height / longest))
        x = (np.arange(nx) + 0.5) * self.width / nx
        y = (np.arange(ny) + 0.5) * self.height / ny
        return x, y


@dataclass(frozen=True)
class ChladniPattern:
    """Result of a cymatic simulation: displacement field and its nodal lines.

    ``displacement[i, j]`` is the (normalised) displacement at ``(x[j], y[i])``. ``nodal_lines`` is a
    tuple of ``(N, 2)`` arrays of ``(x, y)`` points in metres - the curves where
    sand accumulates on a Chladni plate.
    """

    plate: RectangularPlate
    frequency_hz: float
    x: np.ndarray = field(repr=False)
    y: np.ndarray = field(repr=False)
    displacement: np.ndarray = field(repr=False)
    nodal_lines: tuple[np.ndarray, ...] = field(repr=False)
    dominant_mode: PlateMode | None = None

    @property
    def nodal_line_count(self) -> int:
        return len(self.nodal_lines)

    @property
    def total_nodal_length(self) -> float:
        """Total length of all nodal lines in metres."""
        return float(
            sum(np.linalg.norm(np.diff(line, axis=0), axis=1).sum() for line in self.nodal_lines)
        )
