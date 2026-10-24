"""PyTorch backend: Baidu's original model code via transformers. Used on NVIDIA GPUs (CUDA),
and as a fallback on Apple Silicon (MPS) or the CPU when MLX is not installed."""

from __future__ import annotations

import tempfile
from pathlib import Path

import torch

MODEL_ID = "baidu/Unlimited-OCR"
# Pinned: the model ships its own Python code (trust_remote_code) and the MPS fixes below
# were verified against this revision.
MODEL_REVISION = "8249d20b2822a7d8a4c22c8d8c9069b5ac36bda3"
# The repo also carries a duplicate copy of the weights, a wheel and a PDF that are not needed.
IGNORE_PATTERNS = ["model-00001-of-*", "wheel/*", "*.pdf", "assets/*"]

# Prompts and decoding settings from the official model card.
MAX_LENGTH = 32768
NGRAM_SIZE = 35


def pick_device(requested: str | None = None) -> str:
    if requested:
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _redirect_cuda_calls(device: str) -> None:
    """The model's remote code hardcodes .cuda() and autocast("cuda"); send both to `device`."""
    if device == "cuda":
        return

    torch.Tensor.cuda = lambda self, *args, **kwargs: self.to(device)

    original_autocast = torch.autocast

    class _Autocast(original_autocast):
        def __init__(self, device_type, *args, **kwargs):
            if device_type == "cuda":
                device_type = device
                # transformers' RoPE only opts out of CPU autocast when on MPS, so an active MPS
                # autocast computes rotary angles in bf16 and corrupts positions. Weights are
                # already bf16, so autocast is unnecessary here.
                if device == "mps":
                    kwargs["enabled"] = False
            super().__init__(device_type, *args, **kwargs)

    torch.autocast = _Autocast

    if device == "mps":
        _fix_mps_masked_scatter()


def _fix_mps_masked_scatter() -> None:
    """masked_scatter_ silently writes wrong values on MPS (torch 2.10), which scrambles the
    image embeddings and makes the model return nothing. Use index_copy_ for row masks."""
    original = torch.Tensor.masked_scatter_

    def masked_scatter_(self, mask, source):
        if self.device.type != "mps":
            return original(self, mask, source)
        if mask.shape[-1] == 1 and self.is_contiguous():
            rows = mask.expand(*self.shape[:-1], 1).reshape(-1).nonzero().squeeze(1)
            src = source.reshape(-1, self.shape[-1])[: rows.numel()].to(self.dtype)
            self.view(-1, self.shape[-1]).index_copy_(0, rows, src)
            return self
        return self.copy_(original(self.cpu(), mask.cpu(), source.cpu()))

    torch.Tensor.masked_scatter_ = masked_scatter_


class TorchBackend:
    def __init__(self, path: str, device: str | None = None):
        """`path`: local snapshot of MODEL_ID (see weights.ensure_weights)."""
        from transformers import AutoModel, AutoTokenizer

        self.device = pick_device(device)
        self.name = f"PyTorch on {self.device}"
        _redirect_cuda_calls(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
        model = AutoModel.from_pretrained(path, trust_remote_code=True, use_safetensors=True, dtype=torch.bfloat16)
        self.model = model.eval().to(self.device)
        self._scratch = tempfile.TemporaryDirectory(prefix="unlimited_ocr_")  # the model insists on an output dir

    def parse_single(self, page: Path) -> str:
        # "Gundam" mode: global view plus 640px tiles; best quality for one page.
        return self.model.infer(
            self.tokenizer,
            prompt="<image>document parsing.",
            image_file=str(page),
            output_path=self._scratch.name,
            base_size=1024,
            image_size=640,
            crop_mode=True,
            max_length=MAX_LENGTH,
            no_repeat_ngram_size=NGRAM_SIZE,
            ngram_window=128,
            eval_mode=True,
        )

    def parse_multi(self, pages: list[Path]) -> str:
        raw, _ = self.model.infer_multi(
            self.tokenizer,
            prompt="<image>Multi page parsing.",
            image_files=[str(p) for p in pages],
            output_path=self._scratch.name,
            image_size=1024,
            max_length=MAX_LENGTH,
            no_repeat_ngram_size=NGRAM_SIZE,
            ngram_window=1024,
        )
        return raw
