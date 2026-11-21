"""Análise espectral (FFT): espectro, picos, fundamental e notas musicais.

Usa ``scipy.fft`` quando está instalado e ``numpy.fft`` caso contrário (a API de
``rfft``/``rfftfreq`` é a mesma), por isso o módulo funciona só com numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

try:  # pragma: no cover - depende do ambiente
    from scipy import fft as _fft

    FFT_BACKEND = "scipy.fft"
except ImportError:  # pragma: no cover
    _fft = np.fft
    FFT_BACKEND = "numpy.fft"

from .loader import AudioSignal

__all__ = [
    "FFT_BACKEND",
    "Spectrum",
    "SpectralPeak",
    "FundamentalEstimate",
    "compute_spectrum",
    "average_spectrum",
    "find_peaks",
    "estimate_fundamental",
    "frequency_to_note",
]

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_MAX_ZERO_PAD = 1 << 20


@dataclass(frozen=True)
class Spectrum:
    """Espectro de amplitude (unilateral). ``magnitudes`` em unidades de amplitude do sinal."""

    frequencies: np.ndarray = field(repr=False)
    magnitudes: np.ndarray = field(repr=False)
    sample_rate: int
    method: str = "fft"

    @property
    def resolution_hz(self) -> float:
        return float(self.frequencies[1] - self.frequencies[0]) if len(self.frequencies) > 1 else 0.0

    def band(self, fmin: float, fmax: float) -> Spectrum:
        mask = (self.frequencies >= fmin) & (self.frequencies <= fmax)
        return Spectrum(self.frequencies[mask], self.magnitudes[mask], self.sample_rate, self.method)

    def normalized(self) -> Spectrum:
        peak = float(np.max(self.magnitudes)) if len(self.magnitudes) else 0.0
        mags = self.magnitudes / peak if peak > 0 else self.magnitudes
        return Spectrum(self.frequencies, mags, self.sample_rate, self.method)

    def decimated(self, max_points: int = 2000, fmin: float = 20.0, fmax: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Versão reduzida para gráficos: máximo por intervalo logarítmico (preserva os picos)."""
        fmax = fmax or self.sample_rate / 2
        spec = self.band(fmin, fmax)
        if len(spec.frequencies) <= max_points:
            return spec.frequencies, spec.magnitudes
        edges = np.geomspace(max(fmin, spec.frequencies[0]), spec.frequencies[-1], max_points + 1)
        idx = np.clip(np.searchsorted(edges, spec.frequencies, side="right") - 1, 0, max_points - 1)
        mags = np.zeros(max_points)
        np.maximum.at(mags, idx, spec.magnitudes)
        freqs = np.sqrt(edges[:-1] * edges[1:])
        used = np.bincount(idx, minlength=max_points) > 0
        return freqs[used], mags[used]


@dataclass(frozen=True)
class SpectralPeak:
    frequency_hz: float
    magnitude: float  # relativa ao maior pico da banda analisada (0..1]
    note: str


@dataclass(frozen=True)
class FundamentalEstimate:
    frequency_hz: float
    note: str
    dominant_peak_hz: float
    confidence: float  # 0..1: 0 = rival igualmente forte, 1 = candidato isolado


def frequency_to_note(frequency_hz: float) -> str:
    """Nome da nota mais próxima (A4 = 440 Hz) com desvio em cents, p.ex. ``'A4 +3¢'``."""
    if frequency_hz <= 0 or not math.isfinite(frequency_hz):
        return "—"
    midi = 69 + 12 * math.log2(frequency_hz / 440.0)
    nearest = int(round(midi))
    cents = int(round((midi - nearest) * 100))
    name = f"{_NOTE_NAMES[nearest % 12]}{nearest // 12 - 1}"
    return name if cents == 0 else f"{name} {cents:+d}¢"


def _samples(signal: AudioSignal | np.ndarray, sample_rate: int | None) -> tuple[np.ndarray, int]:
    if isinstance(signal, AudioSignal):
        return signal.samples.astype(np.float64), signal.sample_rate
    if sample_rate is None:
        raise ValueError("sample_rate é obrigatório quando se passa um array")
    return np.asarray(signal, dtype=np.float64), int(sample_rate)


def compute_spectrum(signal: AudioSignal | np.ndarray, sample_rate: int | None = None, *, zero_pad: int = 4) -> Spectrum:
    """FFT de um trecho com janela de Hann e zero-padding (interpolação espectral)."""
    x, sr = _samples(signal, sample_rate)
    if len(x) < 16:
        raise ValueError("trecho demasiado curto para FFT (mínimo 16 amostras)")
    x = x - x.mean()
    window = np.hanning(len(x))
    n = len(x)
    nfft = 1 << (n - 1).bit_length()
    if nfft * zero_pad <= _MAX_ZERO_PAD:
        nfft *= zero_pad
    nfft = max(nfft, n)
    mags = np.abs(_fft.rfft(x * window, n=nfft)) * 2.0 / window.sum()
    return Spectrum(_fft.rfftfreq(nfft, 1.0 / sr), mags, sr, "fft")


def average_spectrum(
    signal: AudioSignal | np.ndarray,
    sample_rate: int | None = None,
    *,
    frame_size: int = 8192,
    overlap: float = 0.5,
    chunk_frames: int = 128,
) -> Spectrum:
    """Espectro médio (método de Welch): média da potência de janelas sobrepostas.

    Representa a "assinatura" espectral de toda a faixa com memória limitada.
    """
    x, sr = _samples(signal, sample_rate)
    if not 0 <= overlap < 1:
        raise ValueError("overlap deve estar em [0, 1)")
    if len(x) < frame_size:
        return compute_spectrum(x, sr, zero_pad=1)
    hop = max(1, int(frame_size * (1 - overlap)))
    window = np.hanning(frame_size)
    scale = 2.0 / window.sum()
    starts = np.arange(0, len(x) - frame_size + 1, hop)
    power = np.zeros(frame_size // 2 + 1)
    for i in range(0, len(starts), chunk_frames):
        block = np.stack([x[s : s + frame_size] for s in starts[i : i + chunk_frames]])
        block = (block - block.mean(axis=1, keepdims=True)) * window
        power += np.sum(np.abs(_fft.rfft(block, axis=1)) ** 2, axis=0)
    mags = np.sqrt(power / len(starts)) * scale
    return Spectrum(_fft.rfftfreq(frame_size, 1.0 / sr), mags, sr, "welch")


def _refine(freqs: np.ndarray, mags: np.ndarray, i: int) -> float:
    """Interpolação parabólica (em log) do máximo no bin ``i``."""
    if 0 < i < len(mags) - 1:
        a, b, c = np.log(mags[i - 1 : i + 2] + 1e-20)
        denom = a - 2 * b + c
        if denom < 0:
            offset = 0.5 * (a - c) / denom
            return float(freqs[i] + offset * (freqs[1] - freqs[0]))
    return float(freqs[i])


def find_peaks(
    spectrum: Spectrum,
    count: int = 6,
    *,
    fmin: float = 30.0,
    fmax: float = 5000.0,
    min_relative: float = 0.05,
    min_separation_cents: float = 60.0,
) -> list[SpectralPeak]:
    """Picos de maior energia, ordenados por amplitude decrescente.

    Picos a menos de ``min_separation_cents`` de um pico mais forte são ignorados
    (evita contar duas vezes a mesma nota).
    """
    if count < 1:
        raise ValueError("count deve ser >= 1")
    freqs, mags = spectrum.frequencies, spectrum.magnitudes
    lo, hi = np.searchsorted(freqs, fmin), np.searchsorted(freqs, fmax, side="right")
    lo, hi = max(lo, 1), min(hi, len(mags) - 1)
    if hi - lo < 1:
        return []
    band = mags[lo:hi]
    top = float(band.max())
    if top <= 0:
        return []
    left, centre, right = mags[lo - 1 : hi - 1], band, mags[lo + 1 : hi + 1]
    candidates = np.nonzero((centre > left) & (centre >= right) & (centre >= min_relative * top))[0] + lo
    candidates = candidates[np.argsort(mags[candidates])[::-1]]

    df = spectrum.resolution_hz
    chosen: list[SpectralPeak] = []
    for i in candidates:
        f = _refine(freqs, mags, int(i))
        too_close = any(
            abs(1200 * math.log2(f / p.frequency_hz)) < min_separation_cents or abs(f - p.frequency_hz) < 2 * df
            for p in chosen
        )
        if f > 0 and not too_close:
            chosen.append(SpectralPeak(f, float(mags[i] / top), frequency_to_note(f)))
            if len(chosen) == count:
                break
    return chosen


def estimate_fundamental(
    spectrum: Spectrum,
    *,
    fmin: float = 40.0,
    fmax: float = 2000.0,
    harmonics: int = 6,
    bin_cents: float = 10.0,
) -> FundamentalEstimate:
    """Frequência fundamental por soma harmónica ponderada (1/h) num eixo logarítmico.

    Para cada candidato ``f`` soma ``M(h·f)/h`` (h = 1..``harmonics``). É robusto a
    harmónicos fortes (não confunde a oitava superior) e a resoluções FFT muito
    finas (as amplitudes são agrupadas por máximo em intervalos de ``bin_cents``).
    """
    if not 0 < fmin < fmax:
        raise ValueError("é preciso 0 < fmin < fmax")
    freqs, mags = spectrum.frequencies, spectrum.magnitudes
    nyquist = spectrum.sample_rate / 2
    f_top = min(fmax * harmonics, nyquist)
    if f_top <= fmin:
        raise ValueError("banda de análise acima da frequência de Nyquist")

    n_bins = int(math.ceil(1200 * math.log2(f_top / fmin) / bin_cents)) + 1
    centres = fmin * 2 ** (np.arange(n_bins) * bin_cents / 1200)
    sel = (freqs >= fmin) & (freqs <= f_top)
    idx = np.round(1200 * np.log2(freqs[sel] / fmin) / bin_cents).astype(int)
    pooled = np.zeros(n_bins)
    np.maximum.at(pooled, np.clip(idx, 0, n_bins - 1), mags[sel])
    log_mag = np.maximum(pooled, np.interp(centres, freqs, mags))  # preenche bins sem amostras

    n_cand = int(math.floor(1200 * math.log2(min(fmax, f_top) / fmin) / bin_cents)) + 1
    salience = np.zeros(n_cand)
    for h in range(1, harmonics + 1):
        shift = int(round(1200 * math.log2(h) / bin_cents))
        part = log_mag[shift : shift + n_cand]
        salience[: len(part)] += part / h

    best = int(np.argmax(salience))
    coarse = float(centres[best])
    # Refina no espectro original: máximo a ±30 cents do candidato.
    lo, hi = np.searchsorted(freqs, coarse * 2 ** (-30 / 1200)), np.searchsorted(freqs, coarse * 2 ** (30 / 1200))
    if hi - lo >= 1:
        i = lo + int(np.argmax(mags[lo:hi]))
        f0 = _refine(freqs, mags, i)
    else:
        f0 = coarse
    peaks = find_peaks(spectrum, 1, fmin=fmin, fmax=f_top)
    dominant = peaks[0].frequency_hz if peaks else f0
    # Confiança: quão destacado está o vencedor face ao melhor rival (fora de ±50 cents).
    guard = int(round(50 / bin_cents))
    rivals = np.concatenate([salience[: max(0, best - guard)], salience[best + guard + 1 :]])
    top = float(salience[best])
    confidence = 1.0 - float(rivals.max()) / top if top > 0 and len(rivals) else 0.0
    return FundamentalEstimate(
        frequency_hz=f0,
        note=frequency_to_note(f0),
        dominant_peak_hz=dominant,
        confidence=max(0.0, confidence),
    )
