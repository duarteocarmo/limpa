# /// script
# requires-python = "==3.12.6"
# dependencies = [
#     "nemo_toolkit[asr]",
#     "torch",
#     "lightning",
#     "omegaconf",
# ]
# ///
"""
ASR transcription with word-level timestamps using NeMo.

Usage:
    uv run transcribe_timestamps.py audio.mp3
"""

import sys
import os
import torch
import nemo.collections.asr as nemo_asr


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run transcribe_timestamps.py <audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]
    if not os.path.exists(audio_file):
        print(f"File not found: {audio_file}")
        sys.exit(1)

    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    print(f"Using device: {device}")

    torch.set_grad_enabled(False)
    torch.set_default_dtype(torch.float32)

    asr_model = nemo_asr.models.ASRModel.from_pretrained(
        model_name="nvidia/parakeet-tdt-0.6b-v2",
    )
    asr_model.to(device)
    asr_model.to(dtype=torch.bfloat16)

    # for long-form audio
    asr_model.change_attention_model(
        self_attention_model="rel_pos_local_attn",
        att_context_size=[256, 256],
    )

    asr_model.eval()

    with (
        torch.autocast("mps", enabled=False, dtype=torch.bfloat16),
        torch.inference_mode(),
        torch.no_grad(),
    ):
        output = asr_model.transcribe([audio_file], timestamps=True)

    print("\n--- Full Transcription ---")
    print(output[0].text)

    print("\n--- Segment Timestamps ---")
    for stamp in output[0].timestamp["segment"]:
        print(f"{stamp['start']:.2f}s - {stamp['end']:.2f}s : {stamp['segment']}")

    print("\n--- Word Timestamps ---")
    for stamp in output[0].timestamp["word"]:
        print(f"{stamp['start']:.2f}s - {stamp['end']:.2f}s : {stamp['word']}")


if __name__ == "__main__":
    main()
