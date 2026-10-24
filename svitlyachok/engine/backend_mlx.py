"""MLX backend for Apple Silicon: the mlx-vlm port of Unlimited-OCR. Much faster than PyTorch
on MPS, whose per-operation overhead dominates decoding for a model this small."""

from __future__ import annotations

from pathlib import Path

import mlx.core as mx
from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

MODEL_ID = "mlx-community/Unlimited-OCR-bf16"  # same bf16 weights as baidu/Unlimited-OCR
MODEL_REVISION = "6d9f675e3fa73dd49cd03f630868b1941c72803f"  # pinned: the revision tested here
IGNORE_PATTERNS: list[str] = []

# Prompts and decoding settings from the official model card.
MAX_TOKENS = 30000
NGRAM_SIZE = 35


def ngram_blocker(n: int, window: int):
    """Logits processor matching the model's SlidingWindowNoRepeatNgramProcessor: ban any token
    that would repeat an n-gram seen in the last `window` generated tokens. mlx-vlm does not
    enable it by default, and without it long documents can loop."""

    def process(tokens: mx.array, logits: mx.array) -> mx.array:
        seg = tokens[max(0, tokens.shape[0] - window) :]
        if seg.shape[0] < n:
            return logits
        grams = seg[mx.arange(seg.shape[0] - n + 1)[:, None] + mx.arange(n)[None, :]]  # [positions, n]
        if n == 1:
            match = mx.ones(grams.shape[0], dtype=mx.bool_)
        else:
            prefix = tokens[tokens.shape[0] - (n - 1) :]  # the n-1 most recent tokens
            match = mx.all(grams[:, :-1] == prefix[None, :], axis=1)
        hits = mx.zeros((logits.shape[-1],), dtype=mx.int32).at[grams[:, -1]].add(match.astype(mx.int32))
        return mx.where(hits[None, :] > 0, -mx.inf, logits)

    return process


class MLXBackend:
    name = "MLX on Apple GPU"

    def __init__(self, path: str):
        """`path`: local snapshot of MODEL_ID (see weights.ensure_weights)."""
        self.model, self.processor = load(path)
        self.config = load_config(path)

    def _generate(self, task: str, pages: list[Path], window: int, **processor_kwargs) -> str:
        prompt = apply_chat_template(self.processor, self.config, task, num_images=1)  # one <image> for all pages
        result = generate(
            self.model,
            self.processor,
            prompt,
            image=[str(p) for p in pages],
            max_tokens=MAX_TOKENS,
            temperature=0.0,
            logits_processors=[ngram_blocker(NGRAM_SIZE, window)],
            skip_special_tokens=False,  # keep the layout tags and <PAGE> markers
            **processor_kwargs,
        )
        return result.text

    def parse_single(self, page: Path) -> str:
        # "Gundam" mode (mlx-vlm's default): global view plus 640px tiles.
        return self._generate("document parsing.", [page], window=128)

    def parse_multi(self, pages: list[Path]) -> str:
        return self._generate("Multi page parsing.", pages, window=1024, cropping=False, image_size=1024)
