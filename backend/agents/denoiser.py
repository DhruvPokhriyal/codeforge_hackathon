# backend/agents/denoiser.py
# STEP 2 — Audio Denoiser
#
# Strips crowd noise, alarms, rain, and crackling phone audio from .wav files.
# Supports two backends selected via config.py → DENOISER flag:
#   "noisereduce" — stationary spectral subtraction (CPU-only, fast, default)
#   "facebook"    — Facebook DNS64 deep-learning model (CPU, higher quality)
#
# Public interface:
#   denoise(input_path: str, output_path: str) -> str
#     · input_path  — path to raw/noisy .wav file
#     · output_path — path where clean .wav will be written
#     · returns     — output_path (passthrough, for pipeline chaining)

import numpy as np
import scipy.io.wavfile as wav

from config import DENOISER


def denoise_noisereduce(input_path: str, output_path: str) -> str:
    """Option A: noisereduce — stationary noise reduction at 85% strength."""
    import noisereduce as nr

    rate, data = wav.read(input_path)
    if data.ndim == 2:
        data = data.mean(axis=1).astype(np.int16)
    cleaned = nr.reduce_noise(
        y=data.astype(np.float32),
        sr=rate,
        stationary=True,
        prop_decrease=0.85,
    )
    wav.write(output_path, rate, cleaned.astype(np.int16))
    return output_path


def denoise_facebook(input_path: str, output_path: str) -> str:
    """Option B: Facebook Denoiser (dns64) — deep-learning based denoising."""
    import torch
    import torchaudio
    from denoiser import pretrained
    from denoiser.dsp import convert_audio

    model = pretrained.dns64()
    model.eval()
    wav_tensor, sr = torchaudio.load(input_path)
    wav_tensor = convert_audio(wav_tensor, sr, model.sample_rate, model.chin)
    with torch.no_grad():
        denoised = model(wav_tensor[None])[0]
    torchaudio.save(output_path, denoised, model.sample_rate)
    return output_path


def denoise(input_path: str, output_path: str) -> str:
    """
    Config-driven entry point.
    Routes to denoise_noisereduce() or denoise_facebook() based on config.py.
    """
    if DENOISER == "facebook":
        return denoise_facebook(input_path, output_path)
    return denoise_noisereduce(input_path, output_path)
