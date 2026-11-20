"""Execução integrada da pipeline CymaArchitecture.

    física (placa Kirchhoff-Love) -> padrão de Chladni (marching squares)
        -> geometria neutra (adaptador) -> SVG + DXF em ./saida

Uso:
    python main.py [--resolucao 200] [--modos 6] [--varredura 4] [--saida saida]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))  # permite executar sem instalar o pacote

from cymaarchitecture.cymatics import (  # noqa: E402
    BatchGenerator,
    BoundaryCondition,
    ChladniPattern,
    KirchhoffLoveSolver,
    RectangularPlate,
)
from cymaarchitecture.geometry import (  # noqa: E402
    DxfExporter,
    LengthUnit,
    SvgExporter,
    geometry_from_chladni_pattern,
)


def validate_solver() -> float:
    """Compara o solver numérico (diferenças finitas) com a solução analítica."""
    plate = RectangularPlate(width=0.30, height=0.20, boundary=BoundaryCondition.SIMPLY_SUPPORTED)
    numeric = KirchhoffLoveSolver(plate, nx=48).solve(num_modes=6).frequencies_hz
    analytic = [m.frequency_hz for m in plate.modes(6)[:6]]
    print("\n[1] Validação do solver modal (placa apoiada 300x200x1 mm, latão)")
    print("     modo   analítico [Hz]   numérico [Hz]   erro [%]")
    worst = 0.0
    for k, (fa, fn) in enumerate(zip(analytic, numeric), start=1):
        err = abs(fn - fa) / fa * 100
        worst = max(worst, err)
        print(f"     {k:>4}   {fa:>14.2f}   {fn:>13.2f}   {err:>8.3f}")
    print(f"     pior erro: {worst:.3f} %")
    return worst


def export(pattern: ChladniPattern, stem: str, out_dir: Path) -> tuple[Path, Path]:
    doc = geometry_from_chladni_pattern(pattern, min_length=0.002, simplify_tolerance=2e-4)
    svg = SvgExporter(unit=LengthUnit.MILLIMETER).export(doc, out_dir / f"{stem}.svg")
    dxf = DxfExporter(unit=LengthUnit.MILLIMETER).export(doc, out_dir / f"{stem}.dxf")
    return svg, dxf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline CymaArchitecture")
    parser.add_argument("--resolucao", type=int, default=200)
    parser.add_argument("--modos", type=int, default=6)
    parser.add_argument("--varredura", type=int, default=4)
    parser.add_argument("--saida", type=Path, default=ROOT / "saida")
    args = parser.parse_args(argv)
    out_dir: Path = args.saida
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    print("=== CymaArchitecture: pipeline integrada ===")
    worst = validate_solver()

    plate = RectangularPlate()  # latão 240x240x1 mm, bordas livres (Chladni clássico)
    print(
        f"\n[2] Placa: {plate.width * 1e3:.0f}x{plate.height * 1e3:.0f}x{plate.thickness * 1e3:.1f} mm, "
        f"D = {plate.flexural_rigidity:.3f} N·m, contorno = {plate.boundary.value}"
    )
    generator = BatchGenerator(plate, resolution=args.resolucao, max_order=8)

    files: list[Path] = []
    print(f"\n[3] Padrões ressonantes (primeiros {args.modos} modos)")
    for k, pattern in enumerate(generator.resonant(args.modos), start=1):
        stem = f"modo_{k:02d}_{pattern.dominant_mode.m}{pattern.dominant_mode.n}_{pattern.frequency_hz:.0f}Hz"
        files += export(pattern, stem, out_dir)
        print(
            f"     {pattern.dominant_mode.label:<8} {pattern.frequency_hz:>8.1f} Hz  "
            f"{pattern.nodal_line_count:>3} linhas nodais, {pattern.total_nodal_length * 1e3:>7.1f} mm"
        )

    if args.varredura > 0:
        modes = plate.modes(8)
        f_lo, f_hi = modes[0].frequency_hz * 0.9, modes[min(len(modes) - 1, 11)].frequency_hz * 1.05
        print(f"\n[4] Varredura forçada {f_lo:.0f}-{f_hi:.0f} Hz ({args.varredura} passos, excitação central)")
        for k, pattern in enumerate(generator.iter_sweep(f_lo, f_hi, args.varredura), start=1):
            stem = f"varredura_{k:02d}_{pattern.frequency_hz:.0f}Hz"
            files += export(pattern, stem, out_dir)
            dominant = pattern.dominant_mode.label if pattern.dominant_mode else "-"
            print(f"     {pattern.frequency_hz:>8.1f} Hz  modo dominante {dominant:<8} {pattern.nodal_line_count:>3} linhas")

    print(f"\n[5] {len(files)} arquivos exportados em {out_dir}")
    print(f"    tempo total: {time.perf_counter() - t0:.2f} s")
    return 0 if worst < 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
