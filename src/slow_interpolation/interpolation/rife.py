"""Phase C: RIFE v4.25 linear-timestep interpolation.

Wraps the vendored Practical-RIFE v4.25 inference code at [../../../vendor/rife_v425/](../../../vendor/rife_v425/).
Two `sys.path` insertions handle the package layout (`from train_log.RIFE_HDv3
import Model` plus internal `from model.X` references). A torchvision
compatibility shim aliases the removed `transforms.functional_tensor` to the
modern `functional` module so the legacy RIFE code keeps importing on current
torchvision.

The interpolator runs in **linear timestep** mode: for each keyframe pair it
issues 63 (= 2^passes - 1) calls to `model.inference(img0, img1, timestep=t)`
at evenly spaced t values, then drops the first and last `skip_boundary`
frames per pair to remove the decelerating boundary zones. This is the path
that fixed the 1.3 s sharpness flash artifact of the rejected recursive
binary-midpoint variant (see `docs/pipeline.md`).

Source keyframes are NOT written to the output ("skip keyframes" recipe); only
the 55 retained interpolated frames per pair go through. The Pipeline layer
appends a wrap-around interpolation between the last and first keyframe for
seamless loop closure.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image


def _prepare_rife_imports(vendor_path: Path) -> None:
    """Insert the vendor paths and the torchvision compat shim."""
    vendor_path = Path(vendor_path).resolve()
    train_log = vendor_path / "train_log"

    for p in (str(vendor_path), str(train_log)):
        if p not in sys.path:
            sys.path.insert(0, p)

    # RIFE v4.25 imports `torchvision.transforms.functional_tensor`, which was
    # removed in modern torchvision. Alias to the replacement.
    try:
        import torchvision.transforms.functional as _F  # noqa: WPS433

        sys.modules.setdefault("torchvision.transforms.functional_tensor", _F)
    except ImportError:
        pass


def load_rife(vendor_path: Path) -> Any:
    """Load the vendored RIFE v4.25 model. Returns a ready-to-call Model."""
    _prepare_rife_imports(vendor_path)

    from train_log.RIFE_HDv3 import Model  # type: ignore[import-not-found]

    model = Model()
    model.load_model(str(Path(vendor_path) / "train_log"), -1)
    model.eval()
    model.device()
    return model


def pil_to_tensor(img: Image.Image) -> torch.Tensor:
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).cuda()


def tensor_to_np(t: torch.Tensor) -> np.ndarray:
    arr = t.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return (arr * 255).astype(np.uint8)


def crop_edges(img_np: np.ndarray, margin: int) -> np.ndarray:
    """Trim `margin` pixels from each side. Removes residual arch artifacts."""
    if margin <= 0:
        return img_np
    return img_np[margin:-margin, margin:-margin].copy()


def linear_interp(
    model: Any,
    img0: torch.Tensor,
    img1: torch.Tensor,
    n_passes: int,
    skip_boundary: int = 0,
    sinusoidal: bool = False,
) -> list[torch.Tensor]:
    """Generate 2^n_passes - 1 intermediate frames at linear (or cosine)
    timesteps between two keyframe tensors. Drops the first/last
    `skip_boundary` frames to remove deceleration zones.
    """
    n_frames = (2**n_passes) - 1
    out: list[torch.Tensor] = []
    for i in range(1, n_frames + 1):
        if sinusoidal:
            t = 0.5 - 0.5 * math.cos(math.pi * i / (n_frames + 1))
        else:
            t = i / (n_frames + 1)

        if skip_boundary > 0 and (i <= skip_boundary or i > n_frames - skip_boundary):
            continue

        out.append(model.inference(img0, img1, timestep=t))
    return out


class RIFEInterpolator:
    """Loads RIFE once, exposes pairwise interpolation against the loaded model.

    Use as a context manager (`with RIFEInterpolator(...) as rife:`) to free
    VRAM when done.
    """

    def __init__(
        self,
        vendor_path: Path,
        n_passes: int = 6,
        skip_boundary: int = 4,
        edge_crop: int = 8,
        sinusoidal: bool = False,
    ) -> None:
        self.vendor_path = vendor_path
        self.n_passes = n_passes
        self.skip_boundary = skip_boundary
        self.edge_crop = edge_crop
        self.sinusoidal = sinusoidal
        self._model: Any | None = None

    def __enter__(self) -> "RIFEInterpolator":
        self._model = load_rife(self.vendor_path)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._model is not None:
            import gc

            del self._model
            self._model = None
            gc.collect()
            torch.cuda.empty_cache()

    def interpolate_pair(self, img0: Image.Image, img1: Image.Image) -> list[np.ndarray]:
        """Return cropped numpy frames between `img0` and `img1` (keyframes
        themselves NOT included)."""
        if self._model is None:
            raise RuntimeError("RIFEInterpolator not loaded; use as a context manager")
        t0 = pil_to_tensor(img0)
        t1 = pil_to_tensor(img1)
        with torch.no_grad():
            tensors = linear_interp(
                self._model,
                t0,
                t1,
                self.n_passes,
                skip_boundary=self.skip_boundary,
                sinusoidal=self.sinusoidal,
            )
        return [crop_edges(tensor_to_np(t), self.edge_crop) for t in tensors]
