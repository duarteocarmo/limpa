# /// script
# requires-python = "==3.12.6"
# dependencies = [
#     "nemo_toolkit[asr]",
#     "torch",
#     "lightning",
#     "omegaconf",
#     "tqdm",
# ]
# ///
"""
Streaming ASR inference using NeMo RNNT models.

Usage:
    uv run nemo_streaming_asr.py audio.mp3
"""

import copy
import os
import sys

# print python version
print(f"Python version: {sys.version}")


alloc_conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if "expandable_segments" not in alloc_conf:
    if len(alloc_conf) > 0:
        alloc_conf += ",expandable_segments:True"
    else:
        alloc_conf = "expandable_segments:True"
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = alloc_conf

import torch
from omegaconf import OmegaConf
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

from nemo.collections.asr.models import EncDecHybridRNNTCTCModel, EncDecRNNTModel
from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTDecodingConfig
from nemo.collections.asr.parts.submodules.transducer_decoding.label_looping_base import (
    GreedyBatchedLabelLoopingComputerBase,
)
from nemo.collections.asr.parts.utils.rnnt_utils import (
    BatchedHyps,
    batched_hyps_to_hypotheses,
)
from nemo.collections.asr.parts.utils.streaming_utils import (
    AudioBatch,
    ContextSize,
    SimpleAudioDataset,
    StreamingBatchedAudioBuffer,
)
from nemo.utils import logging


def make_divisible_by(num, factor: int) -> int:
    return (num // factor) * factor


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run nemo_streaming_asr.py <audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]
    if not os.path.exists(audio_file):
        print(f"File not found: {audio_file}")
        sys.exit(1)

    pretrained_name = "nvidia/parakeet-tdt-0.6b-v2"
    chunk_secs = 2.0
    left_context_secs = 10.0
    right_context_secs = 2.0
    batch_size = 32

    torch.set_grad_enabled(False)
    torch.set_float32_matmul_precision("high")

    device = get_device()
    logging.info(f"Using device: {device}")

    asr_model = EncDecRNNTModel.from_pretrained(
        model_name=pretrained_name, map_location=device
    )

    # set attention for long-form audio
    asr_model.change_attention_model(
        self_attention_model="rel_pos_local_attn", att_context_size=[256, 256]
    )

    model_cfg = copy.deepcopy(asr_model._cfg)
    OmegaConf.set_struct(model_cfg.preprocessor, False)
    model_cfg.preprocessor.dither = 0.0
    model_cfg.preprocessor.pad_to = 0
    OmegaConf.set_struct(model_cfg.preprocessor, True)

    asr_model.freeze()
    asr_model = asr_model.to(device)

    decoding_cfg = RNNTDecodingConfig()
    decoding_cfg.strategy = "greedy_batch"
    decoding_cfg.greedy.loop_labels = True
    decoding_cfg.greedy.preserve_alignments = False
    decoding_cfg.fused_batch_size = -1
    decoding_cfg.beam.return_best_hypothesis = True

    if isinstance(asr_model, EncDecRNNTModel):
        asr_model.change_decoding_strategy(decoding_cfg)
    elif isinstance(asr_model, EncDecHybridRNNTCTCModel) and hasattr(
        asr_model, "cur_decoder"
    ):
        asr_model.change_decoding_strategy(decoding_cfg, decoder_type="rnnt")

    asr_model.preprocessor.featurizer.dither = 0.0
    asr_model.preprocessor.featurizer.pad_to = 0
    asr_model.eval()

    decoding_computer: GreedyBatchedLabelLoopingComputerBase = (
        asr_model.decoding.decoding.decoding_computer
    )

    audio_sample_rate = model_cfg.preprocessor["sample_rate"]
    feature_stride_sec = model_cfg.preprocessor["window_stride"]
    features_per_sec = 1.0 / feature_stride_sec
    encoder_subsampling_factor = asr_model.encoder.subsampling_factor

    features_frame2audio_samples = make_divisible_by(
        int(audio_sample_rate * feature_stride_sec), factor=encoder_subsampling_factor
    )
    encoder_frame2audio_samples = (
        features_frame2audio_samples * encoder_subsampling_factor
    )

    context_encoder_frames = ContextSize(
        left=int(left_context_secs * features_per_sec / encoder_subsampling_factor),
        chunk=int(chunk_secs * features_per_sec / encoder_subsampling_factor),
        right=int(right_context_secs * features_per_sec / encoder_subsampling_factor),
    )
    context_samples = ContextSize(
        left=context_encoder_frames.left
        * encoder_subsampling_factor
        * features_frame2audio_samples,
        chunk=context_encoder_frames.chunk
        * encoder_subsampling_factor
        * features_frame2audio_samples,
        right=context_encoder_frames.right
        * encoder_subsampling_factor
        * features_frame2audio_samples,
    )

    logging.info(
        f"Contexts (sec): Left {context_samples.left / audio_sample_rate:.2f}, "
        f"Chunk {context_samples.chunk / audio_sample_rate:.2f}, "
        f"Right {context_samples.right / audio_sample_rate:.2f}"
    )

    audio_dataset = SimpleAudioDataset(
        audio_filenames=[audio_file], sample_rate=audio_sample_rate
    )
    audio_dataloader = DataLoader(
        dataset=audio_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=AudioBatch.collate_fn,
        drop_last=False,
    )

    with torch.no_grad(), torch.inference_mode():
        all_hyps = []
        for audio_data in tqdm(audio_dataloader):
            audio_batch = audio_data.audio_signals.to(device=device)
            audio_batch_lengths = audio_data.audio_signal_lengths.to(device=device)
            batch_size_actual = audio_batch.shape[0]

            current_batched_hyps: BatchedHyps | None = None
            state = None
            left_sample = 0
            right_sample = min(
                context_samples.chunk + context_samples.right, audio_batch.shape[1]
            )
            buffer = StreamingBatchedAudioBuffer(
                batch_size=batch_size_actual,
                context_samples=context_samples,
                dtype=audio_batch.dtype,
                device=device,
            )
            rest_audio_lengths = audio_batch_lengths.clone()

            while left_sample < audio_batch.shape[1]:
                chunk_length = min(right_sample, audio_batch.shape[1]) - left_sample
                is_last_chunk_batch = chunk_length >= rest_audio_lengths
                is_last_chunk = right_sample >= audio_batch.shape[1]
                chunk_lengths_batch = torch.where(
                    is_last_chunk_batch,
                    rest_audio_lengths,
                    torch.full_like(rest_audio_lengths, fill_value=chunk_length),
                )
                buffer.add_audio_batch_(
                    audio_batch[:, left_sample:right_sample],
                    audio_lengths=chunk_lengths_batch,
                    is_last_chunk=is_last_chunk,
                    is_last_chunk_batch=is_last_chunk_batch,
                )

                encoder_output, encoder_output_len = asr_model(
                    input_signal=buffer.samples,
                    input_signal_length=buffer.context_size_batch.total(),
                )
                encoder_output = encoder_output.transpose(1, 2)
                encoder_context = buffer.context_size.subsample(
                    factor=encoder_frame2audio_samples
                )
                encoder_context_batch = buffer.context_size_batch.subsample(
                    factor=encoder_frame2audio_samples
                )
                encoder_output = encoder_output[:, encoder_context.left :]

                chunk_batched_hyps, _, state = decoding_computer(
                    x=encoder_output,
                    out_len=torch.where(
                        is_last_chunk_batch,
                        encoder_output_len - encoder_context_batch.left,
                        encoder_context_batch.chunk,
                    ),
                    prev_batched_state=state,
                )
                if current_batched_hyps is None:
                    current_batched_hyps = chunk_batched_hyps
                else:
                    current_batched_hyps.merge_(chunk_batched_hyps)

                rest_audio_lengths -= chunk_lengths_batch
                left_sample = right_sample
                right_sample = min(
                    right_sample + context_samples.chunk, audio_batch.shape[1]
                )

            all_hyps.extend(
                batched_hyps_to_hypotheses(
                    current_batched_hyps, None, batch_size=batch_size_actual
                )
            )

    for hyp in all_hyps:
        hyp.text = asr_model.tokenizer.ids_to_text(hyp.y_sequence.tolist())
        print(hyp.text)


if __name__ == "__main__":
    main()
