"""Image-derived noise as a NoiseSource.

The noise tensor is computed from a reference image rather than from a random
generator. The diffusion model is biased toward the reference's texture
statistics without that texture entering the prompt path. Useful for: "drift
the Renoir floral toward a specific painting's brushwork", "carry a
photograph's grain into a fresco-styled generation".

Two computation paths, both produce a static (per-shape) texture that is
cached for the lifetime of the source:

- CPU (default): resize the reference to the target shape, optionally subtract
  a Gaussian low-pass to keep only the high-frequency residual, normalize to
  zero mean and unit variance.
- VAE (opt-in, `use_vae=True`): roundtrip the reference through TAESD on CUDA
  and use the decoded result as the texture. This captures the "VAE-encodable
  shape" of the reference and is what SDXL's denoising actually sees. Falls
  back to the CPU path silently if CUDA or diffusers are unavailable.

The texture is static across frames by design (a reference image does not
evolve). Combine with the structured sources via `FrequencyBandedNoise` if you
want temporal life in some bands while a still texture dominates another.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ._filters import gaussian_blur_2d
from .base import NoiseSource


class ImageDerivedNoise(NoiseSource):
    """Static noise tensor derived from a reference image."""

    def __init__(
        self,
        source_image: str | Path | Image.Image,
        high_freq_only: bool = True,
        high_pass_sigma: float = 16.0,
        use_vae: bool = False,
        pixel_spread: float = 40.0,
        pixel_center: float = 128.0,
    ) -> None:
        if isinstance(source_image, (str, Path)):
            self._source = Image.open(Path(source_image)).convert("RGB")
        else:
            self._source = source_image.convert("RGB")
        self.high_freq_only = high_freq_only
        self.high_pass_sigma = float(high_pass_sigma)
        self.use_vae = use_vae
        self.pixel_spread = float(pixel_spread)
        self.pixel_center = float(pixel_center)

        self._noise: np.ndarray | None = None
        self._shape: tuple[int, ...] | None = None
        self._vae = None  # lazily loaded if use_vae

    def reset(self) -> None:
        self._noise = None
        self._shape = None

    def blend(self, img: Image.Image, blend_pct: float = 0.08) -> Image.Image:
        arr = np.array(img).astype(np.float32)
        if self._noise is None or self._shape != arr.shape:
            self._noise = self._compute_texture(arr.shape)
            self._shape = arr.shape

        noise_pixels = (self._noise * self.pixel_spread + self.pixel_center).clip(0, 255)
        blended = arr * (1.0 - blend_pct) + noise_pixels * blend_pct
        return Image.fromarray(blended.clip(0, 255).astype(np.uint8))

    # ----------------------------------------------------------------- helpers

    def _compute_texture(self, shape: tuple[int, ...]) -> np.ndarray:
        height, width = shape[0], shape[1]
        raw = self._vae_texture(height, width) if self.use_vae else None
        if raw is None:
            raw = self._cpu_texture(height, width)

        arr = raw.astype(np.float32)
        if self.high_freq_only and self.high_pass_sigma > 0:
            low = gaussian_blur_2d(arr, self.high_pass_sigma)
            arr = arr - low
        arr = arr - arr.mean()
        std = arr.std()
        if std > 0:
            arr = arr / std

        # Match the input channel count (grayscale reference -> tile to RGB).
        target_c = shape[2] if len(shape) == 3 else 1
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], target_c, axis=-1)
        elif arr.shape[-1] != target_c:
            if arr.shape[-1] == 1:
                arr = np.repeat(arr, target_c, axis=-1)
            else:
                arr = arr[..., :target_c]
        return arr.astype(np.float32)

    def _cpu_texture(self, height: int, width: int) -> np.ndarray:
        resized = self._source.resize((width, height), Image.LANCZOS)
        return np.array(resized).astype(np.float32)

    def _vae_texture(self, height: int, width: int) -> np.ndarray | None:
        """Roundtrip through TAESD on CUDA. Returns None if unavailable."""
        try:
            import torch
            from diffusers import AutoencoderTiny
        except ImportError:
            return None
        if not torch.cuda.is_available():
            return None

        if self._vae is None:
            self._vae = AutoencoderTiny.from_pretrained(
                "madebyollin/taesdxl", torch_dtype=torch.float16
            ).to("cuda")

        # TAESD operates on multiples of 8; round up and crop back.
        h8 = ((height + 7) // 8) * 8
        w8 = ((width + 7) // 8) * 8
        resized = self._source.resize((w8, h8), Image.LANCZOS)
        tensor = (
            torch.from_numpy(np.array(resized))
            .permute(2, 0, 1)
            .unsqueeze(0)
            .float()
            .to("cuda", dtype=torch.float16)
            / 255.0
        )
        tensor = tensor * 2.0 - 1.0  # TAESD expects [-1, 1]
        with torch.no_grad():
            latent = self._vae.encode(tensor).latents
            decoded = self._vae.decode(latent).sample
        decoded = ((decoded + 1.0) / 2.0).clamp(0, 1)
        decoded = decoded.cpu().float().squeeze(0).permute(1, 2, 0).numpy() * 255.0
        return decoded[:height, :width].astype(np.float32)
