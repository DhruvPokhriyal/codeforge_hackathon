import time
import torch
import torchaudio
from pathlib import Path
from denoiser.pretrained import master64

NOISY_INPUT_DIR = "./noisy_input"
DENOISED_OUTPUT_DIR = "./denoised_output"
SUPPORTED_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def load_audio(file_path: Path) -> torch.Tensor:
    wav, sr = torchaudio.load(str(file_path))
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    return wav


def denoise_all():
    input_dir = Path(NOISY_INPUT_DIR)
    output_dir = Path(DENOISED_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files = [
        f for f in input_dir.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS
    ]

    if not audio_files:
        print(f"No supported audio files found in '{input_dir}'")
        return

    print("Loading model...")
    model = master64()
    model.eval()

    print(f"Found {len(audio_files)} file(s). Starting denoising...\n")

    for file_path in sorted(audio_files):
        try:
            wav = load_audio(file_path)
            duration = wav.shape[-1] / 16000
            wav_input = wav.unsqueeze(0)

            t0 = time.perf_counter()
            with torch.no_grad():
                enhanced = model(wav_input)[0]
            elapsed = time.perf_counter() - t0

            out_path = output_dir / (file_path.stem + ".wav")
            torchaudio.save(str(out_path), enhanced.cpu(), 16000)
            print(
                f"  [OK] {file_path.name} | audio: {duration:.2f}s | denoised in: {elapsed:.2f}s -> {out_path}"
            )

        except Exception as e:
            print(f"  [FAIL] {file_path.name}: {e}")

    print(f"\nDone. Denoised files saved to '{output_dir}'")


if __name__ == "__main__":
    denoise_all()
