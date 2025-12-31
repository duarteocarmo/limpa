# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "modal",
# ]
# ///
"""
Transcribe audio files using NVIDIA Parakeet on Modal.

Usage:
    uv run transcribe_modal.py audio.wav
    uv run transcribe_modal.py audio.mp3
"""

import sys
from pathlib import Path
import modal

MODAL_APP_NAME = "transcriber"
MODAL_GPU = "L40S"
MODEL_ID = "nvidia/parakeet-tdt-0.6b-v2"
DEFAULT_BATCH_SIZE = 128

model_volume = modal.Volume.from_name("transcription-models", create_if_missing=True)
MODELS_VOLPATH = "/models"

transcription_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04",
        add_python="3.12",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HOME": MODELS_VOLPATH,
            "CXX": "g++",
            "CC": "g++",
        }
    )
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.7.1",
        "evaluate==0.4.3",
        "librosa==0.11.0",
        "hf_transfer==0.1.9",
        "huggingface_hub[hf-xet]==0.32.4",
        "cuda-python==12.8.0",
        "nemo_toolkit[asr]==2.3.1",
    )
    .entrypoint([])
)

app = modal.App(MODAL_APP_NAME, image=transcription_image)


@app.cls(
    gpu=MODAL_GPU,
    timeout=600,
    volumes={MODELS_VOLPATH: model_volume},
)
class Transcriber:
    use_greedy_batch: bool = modal.parameter(default=True)

    @modal.enter()
    def setup(self):
        import logging
        import nemo.collections.asr as nemo_asr
        import torch

        logging.getLogger("nemo_logger").setLevel(logging.CRITICAL)

        self.asr_model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL_ID)
        self.asr_model.change_attention_model(
            self_attention_model="rel_pos_local_attn",
            att_context_size=[256, 256],
        )
        self.asr_model.to(torch.bfloat16)
        self.asr_model.eval()

        if self.use_greedy_batch and self.asr_model.cfg.decoding.strategy != "beam":
            self.asr_model.cfg.decoding.strategy = "greedy_batch"
            self.asr_model.change_decoding_strategy(self.asr_model.cfg.decoding)

    @modal.method()
    def transcribe(self, audio_bytes: bytes, filename: str) -> dict:
        from pathlib import Path
        import torch
        from pydub import AudioSegment

        input_path = Path(f"/tmp/{filename}")
        input_path.write_bytes(audio_bytes)

        audio = AudioSegment.from_file(str(input_path))
        if audio.channels > 1:
            audio = audio.set_channels(1)
            audio.export(str(input_path), format=input_path.suffix.lstrip("."))

        with torch.inference_mode(), torch.no_grad():
            output = self.asr_model.transcribe(
                [str(input_path)],
                batch_size=DEFAULT_BATCH_SIZE,
                timestamps=True,
            )

        result = output[0]
        return {
            "text": result.text,
            "segments": result.timestamp.get("segment", []),
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run transcribe_modal.py <audio_file>")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"Error: File not found: {audio_path}")
        sys.exit(1)

    if audio_path.suffix.lower() not in (".wav", ".mp3", ".flac"):
        print("Error: Only .wav, .mp3, and .flac files are supported")
        sys.exit(1)

    print(f"Transcribing: {audio_path}")
    audio_bytes = audio_path.read_bytes()

    with modal.enable_output():
        with app.run():



            transcriber = Transcriber()
            result = transcriber.transcribe.remote(audio_bytes, audio_path.name)

    # print("\n--- Transcription ---")
    # print(result["text"])

    print("\n--- Segments ---")
    for seg in result["segments"]:
        print(f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['segment']}")


if __name__ == "__main__":
    main()
