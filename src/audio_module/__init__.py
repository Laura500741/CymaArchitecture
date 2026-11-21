"""Módulo de análise de áudio (FFT) do CymaArchitecture.

Isolado do motor físico: depende apenas de numpy (``scipy.fft`` e ``soundfile``
são usados quando estão instalados). Produz frequências em Hz que a aplicação
injeta no solver Kirchhoff-Love.

Exemplo::

    from audio_module import load_audio, compute_spectrum, estimate_fundamental
    sinal = load_audio("acorde.wav")
    f0 = estimate_fundamental(compute_spectrum(sinal.segment(1.0, 2.5)))
    print(f0.frequency_hz, f0.note)
"""

from .analysis import (
    FFT_BACKEND,
    FundamentalEstimate,
    SpectralPeak,
    Spectrum,
    average_spectrum,
    compute_spectrum,
    estimate_fundamental,
    find_peaks,
    frequency_to_note,
)
from .loader import MAX_DURATION_S, SUPPORTED_EXTENSIONS, AudioDecodeError, AudioSignal, load_audio

__all__ = [
    "FFT_BACKEND",
    "MAX_DURATION_S",
    "SUPPORTED_EXTENSIONS",
    "AudioDecodeError",
    "AudioSignal",
    "FundamentalEstimate",
    "SpectralPeak",
    "Spectrum",
    "average_spectrum",
    "compute_spectrum",
    "estimate_fundamental",
    "find_peaks",
    "frequency_to_note",
    "load_audio",
]
