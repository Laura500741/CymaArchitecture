"""Numerical modal solver (Kirchhoff-Love) and nodal-line extraction.

Contents
--------
KirchhoffLoveSolver
    Finite-difference eigen-solver for a simply supported rectangular plate.
    With Navier conditions (``w = 0`` and ``w'' = 0`` on the edges) the
    biharmonic operator factorises exactly as ``nabla^4 = L @ L`` where ``L`` is
    the Dirichlet Laplacian, which gives an O(h^2) accurate discretisation of

        D nabla^4 phi = rho h omega^2 phi.

    It is used to validate the analytical modes (see ``tests/test_cymatics.py``).
forced_response
    Steady-state harmonic response to a point drive by modal superposition with
    viscous modal damping ``zeta``.
marching_squares
    Iso-contour extraction (with saddle disambiguation) and stitching of the
    segments into continuous polylines.
compute_pattern / pattern_for_mode
    High-level helpers that return :class:`ChladniPattern` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rectangularplate import BoundaryCondition, ChladniPattern, PlateMode, RectangularPlate

__all__ = [
    "ModalSolution",
    "KirchhoffLoveSolver",
    "marching_squares",
    "forced_response",
    "compute_pattern",
    "pattern_for_mode",
]

_MAX_FD_UNKNOWNS = 4000


# --------------------------------------------------------------------------- FD
@dataclass(frozen=True)
class ModalSolution:
    """Eigen-solution of the discretised plate.

    ``mode_shapes[k]`` has shape ``(len(y), len(x))`` on the node grid,
    including the (zero) boundary nodes, normalised to a peak of +1.
    """

    frequencies_hz: np.ndarray
    mode_shapes: np.ndarray = field(repr=False)
    x: np.ndarray = field(repr=False)
    y: np.ndarray = field(repr=False)

    def __len__(self) -> int:
        return len(self.frequencies_hz)


class KirchhoffLoveSolver:
    """Finite-difference modal solver for a simply supported rectangular plate."""

    def __init__(self, plate: RectangularPlate, nx: int = 40, ny: int | None = None) -> None:
        if plate.boundary is not BoundaryCondition.SIMPLY_SUPPORTED:
            raise NotImplementedError(
                "The finite-difference solver supports simply supported plates only; "
                "free plates use the analytical approximation in RectangularPlate."
            )
        if ny is None:
            ny = max(4, round(nx * plate.height / plate.width))
        if nx < 4 or ny < 4:
            raise ValueError("nx and ny must be >= 4")
        if (nx - 1) * (ny - 1) > _MAX_FD_UNKNOWNS:
            raise ValueError(
                f"grid too large for the dense eigen-solver: {(nx - 1) * (ny - 1)} unknowns "
                f"(max {_MAX_FD_UNKNOWNS})"
            )
        self.plate = plate
        self.nx = nx
        self.ny = ny

    @staticmethod
    def _second_difference(n_interior: int, h: float) -> np.ndarray:
        d2 = -2.0 * np.eye(n_interior)
        d2 += np.eye(n_interior, k=1) + np.eye(n_interior, k=-1)
        return d2 / h**2

    def stiffness_operator(self) -> np.ndarray:
        """Discrete biharmonic operator ``L @ L`` on the interior nodes."""
        p = self.plate
        nix, niy = self.nx - 1, self.ny - 1
        d2x = self._second_difference(nix, p.width / self.nx)
        d2y = self._second_difference(niy, p.height / self.ny)
        # Row-major ordering: index = i * nix + j, i -> y, j -> x.
        lap = np.kron(np.eye(niy), d2x) + np.kron(d2y, np.eye(nix))
        return lap @ lap

    def solve(self, num_modes: int = 10) -> ModalSolution:
        p = self.plate
        nix, niy = self.nx - 1, self.ny - 1
        if not 1 <= num_modes <= nix * niy:
            raise ValueError(f"num_modes must be in [1, {nix * niy}]")
        eigenvalues, eigenvectors = np.linalg.eigh(self.stiffness_operator())
        eigenvalues = np.clip(eigenvalues[:num_modes], 0.0, None)
        omega = np.sqrt(eigenvalues * p.flexural_rigidity / p.mass_per_area)

        shapes = np.zeros((num_modes, self.ny + 1, self.nx + 1))
        for k in range(num_modes):
            interior = eigenvectors[:, k].reshape(niy, nix)
            peak = interior.flat[np.argmax(np.abs(interior))]
            shapes[k, 1:-1, 1:-1] = interior / peak
        x = np.linspace(0.0, p.width, self.nx + 1)
        y = np.linspace(0.0, p.height, self.ny + 1)
        return ModalSolution(omega / (2.0 * np.pi), shapes, x, y)


# ------------------------------------------------------------- marching squares
def marching_squares(
    field_values: np.ndarray, x: np.ndarray, y: np.ndarray, level: float = 0.0
) -> list[np.ndarray]:
    """Extract iso-lines ``field == level`` as stitched polylines.

    Parameters
    ----------
    field_values:
        2D array, ``field_values[i, j]`` sampled at ``(x[j], y[i])``.
    x, y:
        Strictly increasing 1D coordinates.

    Returns
    -------
    list of ``(N, 2)`` arrays of ``(x, y)`` points. Closed loops repeat their
    first point at the end.
    """
    f = np.asarray(field_values, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if f.ndim != 2 or f.shape != (len(y), len(x)):
        raise ValueError(f"field shape {f.shape} does not match (len(y), len(x)) = {(len(y), len(x))}")
    if f.shape[0] < 2 or f.shape[1] < 2:
        return []
    if not np.all(np.isfinite(f)):
        raise ValueError("field contains non-finite values")

    inside = f >= level
    ny, nx = f.shape

    def edge_point(edge: tuple[str, int, int]) -> tuple[float, float]:
        kind, i, j = edge
        if kind == "h":  # (i, j) -> (i, j + 1)
            v0, v1 = f[i, j], f[i, j + 1]
            t = (level - v0) / (v1 - v0)
            return (x[j] + t * (x[j + 1] - x[j]), y[i])
        v0, v1 = f[i, j], f[i + 1, j]  # "v": (i, j) -> (i + 1, j)
        t = (level - v0) / (v1 - v0)
        return (x[j], y[i] + t * (y[i + 1] - y[i]))

    # Cases encoded with corners c0=(i,j) c1=(i,j+1) c2=(i+1,j+1) c3=(i+1,j).
    c0 = inside[:-1, :-1]
    c1 = inside[:-1, 1:]
    c2 = inside[1:, 1:]
    c3 = inside[1:, :-1]
    mixed = ~((c0 == c1) & (c1 == c2) & (c2 == c3))

    adjacency: dict[tuple[str, int, int], list[tuple[str, int, int]]] = {}

    def link(e1: tuple[str, int, int], e2: tuple[str, int, int]) -> None:
        adjacency.setdefault(e1, []).append(e2)
        adjacency.setdefault(e2, []).append(e1)

    for i, j in zip(*np.nonzero(mixed)):
        i, j = int(i), int(j)
        b0, b1, b2, b3 = inside[i, j], inside[i, j + 1], inside[i + 1, j + 1], inside[i + 1, j]
        bottom, right = ("h", i, j), ("v", i, j + 1)
        top, left = ("h", i + 1, j), ("v", i, j)
        crossed = []
        if b0 != b1:
            crossed.append(bottom)
        if b1 != b2:
            crossed.append(right)
        if b2 != b3:
            crossed.append(top)
        if b3 != b0:
            crossed.append(left)
        if len(crossed) == 2:
            link(crossed[0], crossed[1])
        elif len(crossed) == 4:  # saddle: decide with the cell-centre value
            centre_inside = 0.25 * (f[i, j] + f[i, j + 1] + f[i + 1, j + 1] + f[i + 1, j]) >= level
            if centre_inside == b0:  # c0 and c2 connected through the centre
                link(bottom, right)
                link(top, left)
            else:
                link(left, bottom)
                link(right, top)

    visited: set[tuple[str, int, int]] = set()
    lines: list[np.ndarray] = []

    def walk(start: tuple[str, int, int]) -> list[tuple[str, int, int]]:
        path = [start]
        visited.add(start)
        current = start
        while True:
            nxt = next((e for e in adjacency[current] if e not in visited), None)
            if nxt is None:
                return path
            visited.add(nxt)
            path.append(nxt)
            current = nxt

    # Open chains first (they start at degree-1 nodes on the domain border) ...
    for edge, neighbours in adjacency.items():
        if edge not in visited and len(neighbours) == 1:
            lines.append(_to_array([edge_point(e) for e in walk(edge)], closed=False))
    # ... then the remaining closed loops.
    for edge in adjacency:
        if edge not in visited:
            path = walk(edge)
            closed = len(path) > 2 and path[0] in adjacency[path[-1]]
            lines.append(_to_array([edge_point(e) for e in path], closed=closed))

    return [line for line in lines if len(line) >= 2]


def _to_array(points: list[tuple[float, float]], closed: bool) -> np.ndarray:
    arr = np.asarray(points, dtype=float)
    if len(arr) > 1:  # drop consecutive duplicates (contour through a grid node)
        keep = np.ones(len(arr), dtype=bool)
        keep[1:] = np.any(np.abs(np.diff(arr, axis=0)) > 1e-12, axis=1)
        arr = arr[keep]
    if closed and len(arr) > 2:
        arr = np.vstack([arr, arr[:1]])
    return arr


# ----------------------------------------------------------- forced response
def forced_response(
    plate: RectangularPlate,
    frequency_hz: float,
    x: np.ndarray,
    y: np.ndarray,
    *,
    max_order: int = 10,
    damping_ratio: float = 0.02,
    drive_point: tuple[float, float] | None = None,
) -> tuple[np.ndarray, PlateMode | None]:
    """Steady-state response to a harmonic point force, by modal superposition.

        W(x) = sum_k phi_k(x) phi_k(x0) / (M_k (omega_k^2 - omega^2 + 2 i zeta omega_k omega))

    The complex field is rotated onto the phase of the dominant modal term so the
    returned real field carries the visible pattern even exactly at resonance.

    Returns ``(field, dominant_mode)`` with the field normalised to peak 1.
    """
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    if damping_ratio <= 0:
        raise ValueError("damping_ratio must be positive")
    if drive_point is None:
        drive_point = (0.5 * plate.width, 0.5 * plate.height)
    x0, y0 = drive_point
    if not (0.0 <= x0 <= plate.width and 0.0 <= y0 <= plate.height):
        raise ValueError("drive_point must lie on the plate")

    X, Y = np.meshgrid(x, y)
    omega = 2.0 * np.pi * frequency_hz
    response = np.zeros(X.shape, dtype=complex)
    best_mode, best_amplitude, best_phase = None, 0.0, 0.0
    px, py = np.array([[x0]]), np.array([[y0]])

    for mode in plate.modes(max_order):
        shape = plate.mode_shape(mode, X, Y)
        rms = float(np.sqrt(np.mean(shape**2)))
        if rms == 0.0:
            continue
        modal_mass = rms**2 * plate.width * plate.height * plate.mass_per_area
        wk = 2.0 * np.pi * mode.frequency_hz
        coefficient = float(plate.mode_shape(mode, px, py)[0, 0]) / (
            modal_mass * (wk**2 - omega**2 + 2j * damping_ratio * wk * omega)
        )
        response += coefficient * shape
        amplitude = abs(coefficient) * rms
        if amplitude > best_amplitude:
            best_mode, best_amplitude, best_phase = mode, amplitude, float(np.angle(coefficient))

    real_field = np.real(response * np.exp(-1j * best_phase))
    peak = float(np.max(np.abs(real_field)))
    if peak > 0:
        real_field = real_field / peak
    return real_field, best_mode


# ---------------------------------------------------------------- high level
def compute_pattern(
    plate: RectangularPlate,
    frequency_hz: float,
    *,
    resolution: int = 200,
    max_order: int = 10,
    damping_ratio: float = 0.02,
    drive_point: tuple[float, float] | None = None,
) -> ChladniPattern:
    """Chladni pattern of a plate driven at ``frequency_hz``."""
    x, y = plate.grid(resolution)
    values, dominant = forced_response(
        plate,
        frequency_hz,
        x,
        y,
        max_order=max_order,
        damping_ratio=damping_ratio,
        drive_point=drive_point,
    )
    lines = tuple(marching_squares(values, x, y))
    return ChladniPattern(plate, float(frequency_hz), x, y, values, lines, dominant)


def pattern_for_mode(plate: RectangularPlate, mode: PlateMode, *, resolution: int = 200) -> ChladniPattern:
    """Pure (single-mode) Chladni pattern at the mode's natural frequency."""
    x, y = plate.grid(resolution)
    X, Y = np.meshgrid(x, y)
    values = plate.mode_shape(mode, X, Y)
    peak = float(np.max(np.abs(values)))
    if peak > 0:
        values = values / peak
    lines = tuple(marching_squares(values, x, y))
    return ChladniPattern(plate, mode.frequency_hz, x, y, values, lines, mode)
