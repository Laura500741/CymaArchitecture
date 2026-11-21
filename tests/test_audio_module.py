import io
import importlib.util
import wave

import numpy as np
import pytest

from audio_module import (
    AudioDecodeError,
    AudioSignal,
    average_spectrum,
    compute_spectrum,
    estimate_fundamental,
    find_peaks,
    frequency_to_note,
    load_audio,
)
from cymaarchitecture.cymatics import RectangularPlate, compute_composite_pattern, compute_pattern

SR = 22050


def tone(freqs, duration=1.0, amps=None, sr=SR):
    t = np.arange(int(duration * sr)) / sr
    amps = amps or [1.0] * len(freqs)
    x = sum(a * np.sin(2 * np.pi * f * t) for f, a in zip(freqs, amps))
    return (0.8 * x / np.max(np.abs(x))).astype(np.float64)


def wav_bytes(x, sr=SR, width=2, channels=1):
    data = np.repeat(x[:, None], channels, axis=1).reshape(-1)
    if width == 1:
        pcm = np.clip(data * 127 + 128, 0, 255).astype(np.uint8).tobytes()
    elif width == 2:
        pcm = (data * 32767).astype("<i2").tobytes()
    elif width == 3:
        ints = (data * (2**23 - 1)).astype(np.int32)
        b = ints.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]
        pcm = b.tobytes()
    else:
        pcm = (data * (2**31 - 1)).astype("<i4").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(sr)
        wf.writeframes(pcm)
    return buf.getvalue()


# ----------------------------------------------------------------- loader
@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_load_wav_pcm_widths(width):
    x = tone([440.0], 0.5)
    sig = load_audio(wav_bytes(x, width=width), "a.wav")
    assert sig.sample_rate == SR and len(sig.samples) == len(x)
    tol = 0.02 if width == 1 else 1e-3
    assert np.max(np.abs(sig.samples - x)) < tol


def test_load_stereo_downmix_and_file_like(tmp_path):
    path = tmp_path / "s.wav"
    path.write_bytes(wav_bytes(tone([220.0], 0.3), channels=2))
    sig = load_audio(path)
    assert sig.channels_in_source == 2 and sig.samples.ndim == 1
    with open(path, "rb") as fh:
        assert len(load_audio(fh, "s.wav").samples) == len(sig.samples)


def test_load_rejects_bad_input():
    with pytest.raises(AudioDecodeError):
        load_audio(b"", "x.wav")
    with pytest.raises(AudioDecodeError):
        load_audio(wav_bytes(tone([440.0], 0.1)), "x.flac")


@pytest.mark.skipif(importlib.util.find_spec("soundfile") is not None, reason="soundfile instalado")
def test_mp3_without_soundfile_gives_clear_message():
    with pytest.raises(AudioDecodeError, match="soundfile"):
        load_audio(b"ID3" + b"\x00" * 200, "musica.mp3")


def test_segment():
    sig = AudioSignal(np.zeros(SR * 2, dtype=np.float32), SR)
    part = sig.segment(0.5, 1.5)
    assert part.duration == pytest.approx(1.0)
    assert sig.segment(1.5, 99).duration == pytest.approx(0.5)
    with pytest.raises(ValueError):
        sig.segment(1.0, 1.0)


# --------------------------------------------------------------- analysis
def test_spectrum_peak_precision():
    spec = compute_spectrum(tone([440.0], 0.5), SR)
    peaks = find_peaks(spec, 1)
    assert peaks[0].frequency_hz == pytest.approx(440.0, abs=0.5)
    assert peaks[0].note == "A4"


def test_chord_peaks_detected():
    c_major = [261.63, 329.63, 392.00]
    spec = compute_spectrum(tone(c_major, 1.0, [1.0, 0.8, 0.6]), SR)
    peaks = find_peaks(spec, 3)
    found = sorted(p.frequency_hz for p in peaks)
    assert np.allclose(found, c_major, atol=1.0)
    assert peaks[0].frequency_hz == pytest.approx(261.63, abs=1.0)  # mais forte primeiro
    assert {p.note.split()[0] for p in peaks} == {"C4", "E4", "G4"}


def test_fundamental_of_harmonic_tone_not_octave_error():
    # 110 Hz com harmónicos, o 2.º harmónico mais forte que a fundamental.
    x = tone([110, 220, 330, 440, 550], 1.0, [0.6, 1.0, 0.7, 0.5, 0.3])
    est = estimate_fundamental(compute_spectrum(x, SR))
    assert est.frequency_hz == pytest.approx(110.0, abs=0.5)
    assert est.dominant_peak_hz == pytest.approx(220.0, abs=0.5)
    assert est.note.startswith("A2")
    assert 0.0 <= est.confidence <= 1.0


def test_fundamental_pure_tone_with_fine_resolution():
    est = estimate_fundamental(compute_spectrum(tone([196.0], 4.0), SR))  # resolução muito fina
    assert est.frequency_hz == pytest.approx(196.0, abs=0.3)


def test_average_spectrum_signature():
    x = np.concatenate([tone([440.0], 1.0), tone([660.0], 1.0, [0.5])])
    spec = average_spectrum(x, SR, frame_size=4096)
    assert spec.method == "welch"
    peaks = find_peaks(spec, 2)
    assert [round(p.frequency_hz / 10) * 10 for p in peaks] == [440, 660]


def test_decimated_preserves_peak():
    spec = compute_spectrum(tone([1000.0], 2.0), SR)
    f, m = spec.decimated(500)
    assert len(f) <= 500
    assert f[np.argmax(m)] == pytest.approx(1000, rel=0.01)


@pytest.mark.parametrize(
    "freq,note", [(440.0, "A4"), (261.63, "C4"), (27.5, "A0"), (446.0, "A4 +23¢"), (0, "—")]
)
def test_frequency_to_note(freq, note):
    assert frequency_to_note(freq) == note


# ------------------------------------------------------- bridge to physics
def test_composite_pattern():
    plate = RectangularPlate()
    single = compute_pattern(plate, 400.0, resolution=60, max_order=6)
    same = compute_composite_pattern(plate, [(400.0, 1.0)], resolution=60, max_order=6)
    assert np.allclose(single.displacement, same.displacement)
    mixed = compute_composite_pattern(plate, [(300.0, 0.4), (700.0, 1.0)], resolution=60, max_order=6)
    assert mixed.frequency_hz == 700.0 and mixed.nodal_line_count >= 1
    with pytest.raises(ValueError):
        compute_composite_pattern(plate, [(300.0, 0.0)])
