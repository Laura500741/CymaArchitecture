"""Leitura de áudio (.wav, .mp3, .ogg) para um sinal mono normalizado.

* WAV PCM (8/16/24/32 bits) é lido com a biblioteca padrão (``wave``), sem dependências.
* MP3, OGG e WAV em vírgula flutuante usam ``soundfile`` (libsndfile >= 1.1),
  se estiver instalado. Sem ele, é levantado :class:`AudioDecodeError` com instruções.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import numpy as np

__all__ = ["AudioSignal", "AudioDecodeError", "load_audio", "SUPPORTED_EXTENSIONS", "MAX_DURATION_S"]

SUPPORTED_EXTENSIONS = (".wav", ".mp3", ".ogg")
MAX_DURATION_S = 20 * 60  # proteção de memória (Streamlit Cloud ~1 GB)


class AudioDecodeError(ValueError):
    """O ficheiro não pôde ser descodificado."""


@dataclass(frozen=True)
class AudioSignal:
    """Sinal mono em float32 no intervalo [-1, 1]."""

    samples: np.ndarray = field(repr=False)
    sample_rate: int
    channels_in_source: int = 1

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate deve ser positivo")
        if np.ndim(self.samples) != 1:
            raise ValueError("samples deve ser um array 1D (mono)")

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate

    def segment(self, start_s: float, end_s: float) -> AudioSignal:
        """Trecho entre ``start_s`` e ``end_s`` (segundos, limitado à duração)."""
        start = int(round(max(0.0, start_s) * self.sample_rate))
        end = int(round(min(self.duration, end_s) * self.sample_rate))
        if end - start < 2:
            raise ValueError("o trecho selecionado é demasiado curto")
        return AudioSignal(self.samples[start:end], self.sample_rate, self.channels_in_source)


def _read_bytes(source: bytes | bytearray | str | Path | BinaryIO) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    data = source.read()
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("o ficheiro deve ser aberto em modo binário")
    return bytes(data)


def _to_mono(data: np.ndarray, channels: int) -> np.ndarray:
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data.astype(np.float32, copy=False)


def _decode_wav_pcm(raw: bytes) -> AudioSignal:
    with wave.open(io.BytesIO(raw), "rb") as wf:
        channels, width, rate, frames = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
        if frames / max(rate, 1) > MAX_DURATION_S:
            raise AudioDecodeError(f"áudio com mais de {MAX_DURATION_S // 60} minutos")
        pcm = wf.readframes(frames)
    if width == 1:  # 8 bits: sem sinal
        data = (np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(pcm, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        data = ints.astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(pcm, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise AudioDecodeError(f"largura de amostra WAV não suportada: {width} bytes")
    return AudioSignal(_to_mono(data, channels), rate, channels)


def _decode_with_soundfile(raw: bytes, extension: str) -> AudioSignal:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise AudioDecodeError(
            f"Para ler ficheiros {extension or 'deste tipo'} instale o pacote 'soundfile' "
            "(pip install soundfile). Ficheiros WAV PCM funcionam sem ele."
        ) from exc
    try:
        info = sf.info(io.BytesIO(raw))
        if info.duration > MAX_DURATION_S:
            raise AudioDecodeError(f"áudio com mais de {MAX_DURATION_S // 60} minutos")
        data, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    except AudioDecodeError:
        raise
    except Exception as exc:  # libsndfile levanta vários tipos
        raise AudioDecodeError(f"não foi possível descodificar o áudio: {exc}") from exc
    channels = data.shape[1]
    return AudioSignal(_to_mono(data.reshape(-1), channels), int(rate), channels)


def load_audio(source: bytes | bytearray | str | Path | BinaryIO, filename: str | None = None) -> AudioSignal:
    """Carrega áudio de bytes, caminho ou ficheiro binário e devolve um sinal mono.

    ``filename`` (ou o caminho) indica a extensão; sem ela, o formato é detetado
    pelo cabeçalho.
    """
    if filename is None and isinstance(source, (str, Path)):
        filename = str(source)
    raw = _read_bytes(source)
    if len(raw) < 44:
        raise AudioDecodeError("ficheiro vazio ou demasiado pequeno")

    extension = Path(filename).suffix.lower() if filename else ""
    if extension and extension not in SUPPORTED_EXTENSIONS:
        raise AudioDecodeError(f"formato {extension} não suportado; use {', '.join(SUPPORTED_EXTENSIONS)}")

    is_wav = raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    if is_wav:
        try:
            signal = _decode_wav_pcm(raw)
        except wave.Error:  # p.ex. WAV em vírgula flutuante (formato 3)
            signal = _decode_with_soundfile(raw, ".wav")
    else:
        signal = _decode_with_soundfile(raw, extension)

    if len(signal.samples) < 2:
        raise AudioDecodeError("o áudio não contém amostras")
    peak = float(np.max(np.abs(signal.samples)))
    if peak > 1.0:
        signal = AudioSignal(signal.samples / peak, signal.sample_rate, signal.channels_in_source)
    return signal
