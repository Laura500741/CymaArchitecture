"""CymaArchitecture — interface web (Streamlit), responsiva para computador e telemóvel.

Modos (barra lateral):
    * Manual (Chladni): modo ressonante ou frequência livre.
    * Áudio / acorde específico: FFT de um trecho -> fundamental -> solver.
    * Assinatura média da obra: picos de maior energia da faixa -> padrão composto.

Executar:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from audio_module import (  # noqa: E402
    FFT_BACKEND,
    AudioDecodeError,
    average_spectrum,
    compute_spectrum,
    estimate_fundamental,
    find_peaks,
    frequency_to_note,
    load_audio,
)
from cymaarchitecture.cymatics import (  # noqa: E402
    BoundaryCondition,
    RectangularPlate,
    compute_composite_pattern,
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

MODO_MANUAL = "🎛️ Manual (Chladni)"
MODO_AUDIO = "🎵 Áudio / acorde específico"
MODO_OBRA = "📊 Assinatura média da obra"

MAX_ORDEM = 8          # modos listados no modo manual
ORDEM_AUDIO = 12       # base modal mais rica para frequências vindas de áudio
JANELA_MAX_S = 30.0    # trecho máximo analisado no modo "acorde"
MIME_AUDIO = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}

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
def gerar(largura_mm, altura_mm, espessura_mm, material, contorno, excitacao, resolucao, unidade):
    """Corre a pipeline completa e devolve SVG, DXF, campo e estatísticas.

    ``excitacao``: ("modo", índice) | ("freq", Hz) | ("audio", Hz) | ("composto", ((Hz, peso), ...)).
    """
    placa = criar_placa(largura_mm, altura_mm, espessura_mm, material, contorno)
    tipo, valor = excitacao
    if tipo == "modo":
        padrao = pattern_for_mode(placa, placa.modes(MAX_ORDEM)[valor], resolution=resolucao)
    elif tipo in ("freq", "audio"):
        ordem = MAX_ORDEM if tipo == "freq" else ORDEM_AUDIO
        padrao = compute_pattern(placa, valor, resolution=resolucao, max_order=ordem)
    else:
        padrao = compute_composite_pattern(placa, valor, resolution=resolucao, max_order=ORDEM_AUDIO)

    doc = geometry_from_chladni_pattern(padrao, min_length=0.002, simplify_tolerance=1e-4)
    un = UNIDADES[unidade]
    estatisticas = {
        "frequencia": padrao.frequency_hz,
        "modo": padrao.dominant_mode.label if padrao.dominant_mode else "—",
        "linhas": len(doc.layer(NODAL_LAYER)),
        "comprimento_mm": sum(pl.length for pl in doc.layer(NODAL_LAYER).polylines) * 1000,
        "rigidez": placa.flexural_rigidity,
    }
    return SvgExporter(unit=un).render(doc), DxfExporter(unit=un).render(doc), padrao.displacement, estatisticas


@st.cache_data(show_spinner=False, max_entries=8)
def carregar_audio(dados: bytes, nome: str):
    return load_audio(dados, nome)


@st.cache_data(show_spinner=False, max_entries=32)
def analisar_trecho(dados: bytes, nome: str, inicio: float, fim: float):
    sinal = carregar_audio(dados, nome).segment(inicio, fim)
    espectro = compute_spectrum(sinal).band(20.0, 8000.0)
    return espectro, find_peaks(espectro, 6, fmin=30.0, fmax=5000.0), estimate_fundamental(espectro)


@st.cache_data(show_spinner=False, max_entries=16)
def analisar_obra(dados: bytes, nome: str, n_picos: int, fmin: float, fmax: float):
    espectro = average_spectrum(carregar_audio(dados, nome)).band(20.0, 8000.0)
    return espectro, find_peaks(espectro, n_picos, fmin=fmin, fmax=fmax)


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


def grafico_espectro(espectro, picos, destaque_hz=None, fmin=30.0, fmax=5000.0) -> None:
    """Espectro (Hz x amplitude relativa, eixo log) com os picos assinalados."""
    banda = espectro.band(fmin, fmax)
    topo = float(banda.magnitudes.max()) if len(banda.magnitudes) else 1.0
    freqs, mags = banda.decimated(1500, fmin=fmin, fmax=fmax)
    df = pd.DataFrame({"Frequência (Hz)": freqs, "Amplitude": mags / (topo or 1.0)})
    eixo_x = alt.X("Frequência (Hz):Q", scale=alt.Scale(type="log", domain=[fmin, fmax]))
    eixo_y = alt.Y("Amplitude:Q", title="Amplitude relativa", scale=alt.Scale(domain=[0, 1.12]))
    camadas = [alt.Chart(df).mark_line(color="#4c78a8", strokeWidth=1.2).encode(eixo_x, eixo_y)]
    if picos:
        pk = pd.DataFrame(
            {
                "Frequência (Hz)": [p.frequency_hz for p in picos],
                "Amplitude": [p.magnitude for p in picos],
                "Nota": [p.note for p in picos],
                "Hz": [f"{p.frequency_hz:.1f}" for p in picos],
            }
        )
        dica = ["Hz", "Nota", alt.Tooltip("Amplitude:Q", format=".2f")]
        camadas.append(alt.Chart(pk).mark_point(color="#d62728", filled=True, size=70).encode(eixo_x, eixo_y, tooltip=dica))
        camadas.append(
            alt.Chart(pk).mark_text(dy=-11, color="#d62728", fontSize=11, fontWeight="bold").encode(eixo_x, eixo_y, text="Nota")
        )
    if destaque_hz:
        regra = pd.DataFrame({"Frequência (Hz)": [destaque_hz]})
        camadas.append(alt.Chart(regra).mark_rule(color="#2ca02c", strokeDash=[5, 3], strokeWidth=2).encode(eixo_x))
    st.altair_chart(alt.layer(*camadas).properties(height=280))


# ---------------------------------------------------------------- interface
modo = st.sidebar.radio("Modo de análise", [MODO_MANUAL, MODO_AUDIO, MODO_OBRA])
st.sidebar.caption(
    "**Manual**: escolha um modo ou frequência.\n\n"
    "**Áudio / acorde**: a fundamental de um trecho é injetada no solver.\n\n"
    "**Assinatura da obra**: os picos de maior energia da faixa geram um padrão composto.\n\n"
    f"Motor FFT: `{FFT_BACKEND}`"
)

st.title("〰️ CymaArchitecture")
st.caption(
    "Padrões de Chladni a partir da física de placas finas (Kirchhoff-Love), "
    "exportados em SVG e DXF prontos para corte laser/CNC."
    + ("" if modo == MODO_MANUAL else f" · Modo: **{modo}**")
)
st.caption("📱 No telemóvel, toque em **›** (canto superior esquerdo) para mudar de modo.")

col_placa, col_excitacao = st.columns(2, gap="large")

with col_placa:
    st.subheader("1 · Placa")
    c1, c2, c3 = st.columns(3)
    largura = c1.number_input("Largura (mm)", min_value=20.0, max_value=3000.0, value=240.0, step=10.0)
    altura = c2.number_input("Altura (mm)", min_value=20.0, max_value=3000.0, value=240.0, step=10.0)
    espessura = c3.number_input("Espessura (mm)", min_value=0.1, max_value=50.0, value=1.0, step=0.1, format="%.1f")
    material = st.selectbox("Material", list(MATERIAIS))
    contorno = st.radio("Condição de contorno", list(CONTORNOS), horizontal=True)
    c4, c5 = st.columns(2)
    resolucao = c4.select_slider("Resolução", options=[80, 120, 160, 200, 260, 320], value=200)
    unidade = c5.selectbox("Unidade dos ficheiros", list(UNIDADES))

try:
    modos = listar_modos(largura, altura, espessura, material, contorno)
except ValueError as exc:
    st.error(f"Parâmetros inválidos: {exc}")
    st.stop()

excitacao = None
audio_ctx = None  # dados para o gráfico de espectro

with col_excitacao:
    st.subheader("2 · Excitação")

    if modo == MODO_MANUAL:
        tipo = st.radio(
            "Tipo de excitação",
            ["Modo ressonante", "Frequência livre (Hz)"],
            horizontal=True,
            help="Modo ressonante: padrão puro de um modo. Frequência livre: resposta forçada "
            "com excitação no centro da placa (sobreposição modal com amortecimento).",
        )
        if tipo == "Modo ressonante":
            idx = st.selectbox(
                "Modo",
                range(len(modos)),
                format_func=lambda i: f"{i + 1:>2}. {modos[i][0]} — {modos[i][1]:,.1f} Hz",
            )
            excitacao = ("modo", int(idx))
        else:
            freq = st.number_input(
                "Frequência (Hz)", min_value=1.0, max_value=50000.0,
                value=float(round(modos[min(5, len(modos) - 1)][1], 1)), step=10.0,
            )
            excitacao = ("freq", float(freq))

    else:
        ficheiro = st.file_uploader("Ficheiro de áudio (.wav, .mp3, .ogg)", type=["wav", "mp3", "ogg"])
        if ficheiro is None:
            st.info("Carregue um ficheiro de áudio para começar.")
            st.stop()
        dados, nome = ficheiro.getvalue(), ficheiro.name
        try:
            with st.spinner("A descodificar o áudio…"):
                sinal = carregar_audio(dados, nome)
        except AudioDecodeError as exc:
            st.error(str(exc))
            st.stop()
        st.audio(dados, format=MIME_AUDIO.get(Path(nome).suffix.lower(), "audio/wav"))
        st.caption(f"{sinal.duration:.1f} s · {sinal.sample_rate} Hz · {sinal.channels_in_source} canal(is)")
        oitavas = st.select_slider(
            "Transpor (oitavas)", options=[-3, -2, -1, 0, 1, 2, 3], value=0,
            help="Multiplica as frequências por 2^n antes de as injetar na placa.",
        )
        fator = 2.0**oitavas

        if modo == MODO_AUDIO:
            duracao = sinal.duration
            fim_padrao = min(duracao, 2.0)
            inicio, fim = st.slider(
                "Trecho a analisar (s)", min_value=0.0, max_value=float(round(duracao, 2)),
                value=(0.0, float(round(fim_padrao, 2))), step=0.05,
            )
            if fim - inicio > JANELA_MAX_S:
                fim = inicio + JANELA_MAX_S
                st.warning(f"Trecho limitado a {JANELA_MAX_S:.0f} s ({inicio:.2f}–{fim:.2f} s).")
            if fim - inicio < 0.05:
                st.error("Selecione um trecho com pelo menos 0,05 s.")
                st.stop()
            metodo = st.radio(
                "Frequência a usar", ["Fundamental (soma harmónica)", "Pico dominante"], horizontal=True,
                help="Fundamental: a nota-base do som (robusta a harmónicos). "
                "Pico dominante: a frequência com mais energia no trecho.",
            )
            espectro, picos, f0 = analisar_trecho(dados, nome, float(inicio), float(fim))
            base_hz = f0.frequency_hz if metodo.startswith("Fundamental") else f0.dominant_peak_hz
            freq_final = base_hz * fator
            excitacao = ("audio", float(freq_final))
            m1, m2, m3 = st.columns(3)
            m1.metric("Detetado", f"{base_hz:,.1f} Hz", frequency_to_note(base_hz), delta_color="off")
            m2.metric(
                "Confiança", f"{f0.confidence:.0%}",
                help="Quanto o candidato vencedor se destaca do melhor rival (p.ex. a oitava acima). "
                "Valores baixos não significam erro; indicam que há outra frequência quase tão provável.",
            )
            m3.metric("Injetado na placa", f"{freq_final:,.1f} Hz")
            audio_ctx = (espectro, picos, base_hz, "Espectro do trecho selecionado")

        else:  # MODO_OBRA
            n_picos = st.slider("Número de picos", min_value=2, max_value=8, value=5)
            fmin, fmax = st.select_slider(
                "Banda de análise (Hz)", options=[20, 30, 50, 80, 120, 200, 400, 800, 1600, 3200, 5000, 8000],
                value=(50, 3200),
            )
            with st.spinner("A calcular o espectro médio da obra…"):
                espectro, picos = analisar_obra(dados, nome, int(n_picos), float(fmin), float(fmax))
            if not picos:
                st.error("Não foram encontrados picos nesta banda.")
                st.stop()
            excitacao = ("composto", tuple((float(p.frequency_hz * fator), float(p.magnitude)) for p in picos))
            audio_ctx = (espectro, picos, None, "Assinatura espectral média da obra (Welch)")

if audio_ctx is not None:
    espectro, picos, destaque, titulo = audio_ctx
    st.divider()
    st.subheader("Espectro de frequências")
    st.caption(f"{titulo} · picos a vermelho" + (" · linha verde: frequência escolhida" if destaque else ""))
    grafico_espectro(espectro, picos, destaque)
    with st.expander("Picos detetados", expanded=(modo == MODO_OBRA)):
        st.dataframe(
            pd.DataFrame(
                {
                    "Frequência (Hz)": [round(p.frequency_hz, 2) for p in picos],
                    "Nota": [p.note for p in picos],
                    "Energia relativa": [round(p.magnitude, 3) for p in picos],
                    "Injetado (Hz)": [round(p.frequency_hz * fator, 2) for p in picos],
                }
            ),
            hide_index=True,
        )

with st.spinner("A calcular o padrão…"):
    svg, dxf, campo, info = gerar(largura, altura, espessura, material, contorno, excitacao, resolucao, unidade)

st.divider()
st.subheader("3 · Resultado")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Frequência" + (" principal" if excitacao[0] == "composto" else ""), f"{info['frequencia']:,.1f} Hz")
m2.metric("Modo dominante", info["modo"])
m3.metric("Linhas nodais", info["linhas"])
m4.metric("Comprimento de corte", f"{info['comprimento_mm']:,.0f} mm")
if excitacao[0] == "composto":
    st.caption(
        "Padrão composto: soma das respostas da placa a cada pico, ponderada pela energia espectral. "
        "É uma síntese visual da assinatura da obra, não uma única vibração física estacionária."
    )

tab_svg, tab_campo = st.tabs(["Linhas nodais (SVG)", "Campo de deslocamento"])
with tab_svg:
    svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    st.markdown(
        f'<div class="cyma-preview"><img alt="Padrão de Chladni" src="data:image/svg+xml;base64,{svg_b64}"/></div>',
        unsafe_allow_html=True,
    )
with tab_campo:
    st.image(
        campo_para_imagem(campo),
        caption="Vermelho/azul: fases opostas de vibração · branco: linhas nodais (onde a areia se acumula)",
    )

sufixo = {"modo": "", "freq": "", "audio": "_audio", "composto": "_composto"}[excitacao[0]]
nome_ficheiro = f"chladni_{largura:.0f}x{altura:.0f}mm_{info['frequencia']:.0f}Hz{sufixo}"
d1, d2 = st.columns(2)
d1.download_button("⬇️ Descarregar SVG", svg, file_name=f"{nome_ficheiro}.svg", mime="image/svg+xml")
d2.download_button("⬇️ Descarregar DXF", dxf, file_name=f"{nome_ficheiro}.dxf", mime="application/dxf")

with st.expander("Notas técnicas"):
    st.markdown(
        f"""
- Rigidez à flexão **D = {info['rigidez']:.4g} N·m**.
- Placa **simplesmente apoiada**: modos e frequências exatos; o solver numérico coincide com a solução
  analítica com erro < 0,5 % (ver `main.py`).
- Placa **livre**: aproximação clássica — a forma das linhas nodais é correta, mas as frequências
  podem desviar ~10–20 % de medições reais.
- Madeira é tratada como isotrópica (aproximação).
- Áudio: FFT com janela de Hann (`{FFT_BACKEND}`); fundamental por soma harmónica; assinatura média
  pelo método de Welch. MP3/OGG requerem o pacote `soundfile`.
- O DXF (AutoCAD 2000, camadas `PLATE_OUTLINE` e `NODAL_LINES`) deve ser testado no seu CAD/CAM antes de produção.
"""
    )
