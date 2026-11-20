"""CymaArchitecture — interface web (Streamlit), responsiva para computador e telemóvel.

Executar:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import numpy as np
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cymaarchitecture.cymatics import (  # noqa: E402
    BoundaryCondition,
    RectangularPlate,
    compute_pattern,
    pattern_for_mode,
)
from cymaarchitecture.geometry import (  # noqa: E402
    NODAL_LAYER,
    DxfExporter,
    LengthUnit,
    SvgExporter,
    geometry_from_chladni_pattern,
)

# Propriedades típicas (isotrópicas). E [Pa], densidade [kg/m3], Poisson [-]
MATERIAIS: dict[str, tuple[float, float, float]] = {
    "Latão": (100e9, 8500.0, 0.33),
    "Alumínio": (69e9, 2700.0, 0.33),
    "Aço": (200e9, 7850.0, 0.30),
    "Madeira (contraplacado)": (11e9, 600.0, 0.30),
}

CONTORNOS = {
    "Livre (Chladni clássico)": BoundaryCondition.FREE,
    "Simplesmente apoiada": BoundaryCondition.SIMPLY_SUPPORTED,
}

UNIDADES = {
    "Milímetros (mm)": LengthUnit.MILLIMETER,
    "Centímetros (cm)": LengthUnit.CENTIMETER,
    "Polegadas (in)": LengthUnit.INCH,
}

MAX_ORDEM = 8

st.set_page_config(page_title="CymaArchitecture", page_icon="〰️", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1200px;}
      .cyma-preview {background: #ffffff; border: 1px solid #ddd; border-radius: 8px; padding: 8px;}
      .cyma-preview img {width: 100%; height: auto; display: block;}
      div[data-testid="stDownloadButton"] button {width: 100%;}
      @media (max-width: 640px) {
        .block-container {padding-left: 0.8rem; padding-right: 0.8rem;}
        h1 {font-size: 1.6rem !important;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------- cálculo
def criar_placa(largura_mm, altura_mm, espessura_mm, material, contorno) -> RectangularPlate:
    e, rho, nu = MATERIAIS[material]
    return RectangularPlate(
        width=largura_mm / 1000,
        height=altura_mm / 1000,
        thickness=espessura_mm / 1000,
        youngs_modulus=e,
        density=rho,
        poisson_ratio=nu,
        boundary=CONTORNOS[contorno],
    )


@st.cache_data(show_spinner=False, max_entries=64)
def listar_modos(largura_mm, altura_mm, espessura_mm, material, contorno, quantidade=24):
    placa = criar_placa(largura_mm, altura_mm, espessura_mm, material, contorno)
    return [(m.label, m.frequency_hz) for m in placa.modes(MAX_ORDEM)[:quantidade]]


@st.cache_data(show_spinner=False, max_entries=64)
def gerar(largura_mm, altura_mm, espessura_mm, material, contorno, modo_idx, frequencia, resolucao, unidade):
    """Corre a pipeline completa e devolve SVG, DXF, campo e estatísticas."""
    placa = criar_placa(largura_mm, altura_mm, espessura_mm, material, contorno)
    if modo_idx is not None:
        padrao = pattern_for_mode(placa, placa.modes(MAX_ORDEM)[modo_idx], resolution=resolucao)
    else:
        padrao = compute_pattern(placa, frequencia, resolution=resolucao, max_order=MAX_ORDEM)

    doc = geometry_from_chladni_pattern(padrao, min_length=0.002, simplify_tolerance=1e-4)
    un = UNIDADES[unidade]
    svg = SvgExporter(unit=un).render(doc)
    dxf = DxfExporter(unit=un).render(doc)
    estatisticas = {
        "frequencia": padrao.frequency_hz,
        "modo": padrao.dominant_mode.label if padrao.dominant_mode else "—",
        "linhas": len(doc.layer(NODAL_LAYER)),
        "comprimento_mm": sum(pl.length for pl in doc.layer(NODAL_LAYER).polylines) * 1000,
        "rigidez": placa.flexural_rigidity,
    }
    return svg, dxf, padrao.displacement, estatisticas


def campo_para_imagem(campo: np.ndarray) -> np.ndarray:
    """Mapa divergente azul-branco-vermelho (RGB uint8), com y para cima."""
    v = np.clip(campo, -1.0, 1.0)[::-1]
    pos, neg = np.clip(v, 0, 1), np.clip(-v, 0, 1)
    r = 1.0 - 0.75 * neg
    g = 1.0 - 0.75 * (pos + neg)
    b = 1.0 - 0.75 * pos
    img = (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)
    fator = max(1, -(-640 // max(img.shape[:2])))  # amplia para ~640 px (encolhe no telemóvel)
    return np.repeat(np.repeat(img, fator, axis=0), fator, axis=1)


# ---------------------------------------------------------------- interface
st.title("〰️ CymaArchitecture")
st.caption(
    "Padrões de Chladni a partir da física de placas finas (Kirchhoff-Love), "
    "exportados em SVG e DXF prontos para corte laser/CNC."
)

col_placa, col_excitacao = st.columns(2, gap="large")

with col_placa:
    st.subheader("1 · Placa")
    c1, c2, c3 = st.columns(3)
    largura = c1.number_input("Largura (mm)", min_value=20.0, max_value=3000.0, value=240.0, step=10.0)
    altura = c2.number_input("Altura (mm)", min_value=20.0, max_value=3000.0, value=240.0, step=10.0)
    espessura = c3.number_input("Espessura (mm)", min_value=0.1, max_value=50.0, value=1.0, step=0.1, format="%.1f")
    material = st.selectbox("Material", list(MATERIAIS))
    contorno = st.radio("Condição de contorno", list(CONTORNOS), horizontal=True)

with col_excitacao:
    st.subheader("2 · Excitação")
    tipo = st.radio(
        "Tipo de excitação",
        ["Modo ressonante", "Frequência livre (Hz)"],
        horizontal=True,
        help="Modo ressonante: padrão puro de um modo. Frequência livre: resposta forçada "
        "com excitação no centro da placa (sobreposição modal com amortecimento).",
    )
    erro_placa = None
    try:
        modos = listar_modos(largura, altura, espessura, material, contorno)
    except ValueError as exc:
        modos, erro_placa = [], str(exc)

    modo_idx, frequencia = None, None
    if modos and tipo == "Modo ressonante":
        modo_idx = st.selectbox(
            "Modo",
            range(len(modos)),
            format_func=lambda i: f"{i + 1:>2}. {modos[i][0]} — {modos[i][1]:,.1f} Hz",
        )
    elif modos:
        frequencia = st.number_input(
            "Frequência (Hz)",
            min_value=1.0,
            max_value=50000.0,
            value=float(round(modos[min(5, len(modos) - 1)][1], 1)),
            step=10.0,
        )
    c4, c5 = st.columns(2)
    resolucao = c4.select_slider("Resolução", options=[80, 120, 160, 200, 260, 320], value=200)
    unidade = c5.selectbox("Unidade dos ficheiros", list(UNIDADES))

if erro_placa:
    st.error(f"Parâmetros inválidos: {erro_placa}")
    st.stop()

with st.spinner("A calcular o padrão…"):
    svg, dxf, campo, info = gerar(
        largura, altura, espessura, material, contorno, modo_idx, frequencia, resolucao, unidade
    )

st.divider()
st.subheader("3 · Resultado")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Frequência", f"{info['frequencia']:,.1f} Hz")
m2.metric("Modo dominante", info["modo"])
m3.metric("Linhas nodais", info["linhas"])
m4.metric("Comprimento de corte", f"{info['comprimento_mm']:,.0f} mm")

tab_svg, tab_campo = st.tabs(["Linhas nodais (SVG)", "Campo de deslocamento"])
with tab_svg:
    svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    st.markdown(
        f'<div class="cyma-preview"><img alt="Padrão de Chladni" src="data:image/svg+xml;base64,{svg_b64}"/></div>',
        unsafe_allow_html=True,
    )
with tab_campo:
    st.image(campo_para_imagem(campo),
             caption="Vermelho/azul: fases opostas de vibração · branco: linhas nodais (onde a areia se acumula)")

nome = f"chladni_{largura:.0f}x{altura:.0f}mm_{info['frequencia']:.0f}Hz"
d1, d2 = st.columns(2)
d1.download_button("⬇️ Descarregar SVG", svg, file_name=f"{nome}.svg", mime="image/svg+xml")
d2.download_button("⬇️ Descarregar DXF", dxf, file_name=f"{nome}.dxf", mime="application/dxf")

with st.expander("Notas técnicas"):
    st.markdown(
        f"""
- Rigidez à flexão **D = {info['rigidez']:.4g} N·m**.
- Placa **simplesmente apoiada**: modos e frequências exatos; o solver numérico coincide com a solução
  analítica com erro < 0,5 % (ver `main.py`).
- Placa **livre**: aproximação clássica — a forma das linhas nodais é correta, mas as frequências
  podem desviar ~10–20 % de medições reais.
- Madeira é tratada como isotrópica (aproximação).
- O DXF (AutoCAD 2000, camadas `PLATE_OUTLINE` e `NODAL_LINES`) deve ser testado no seu CAD/CAM antes de produção.
"""
    )
