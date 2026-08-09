"""Top-level Pipeline orchestrator.

`Pipeline` composes the four phases of the slow-interpolation technique:

- Phase A   (`generate_keyframes`):  SDXL Lightning img2img chain
- Phase A.5 (`smooth_keyframes`):    frequency-separated temporal smoothing
- Phase C   (`interpolate_and_encode`): RIFE v4.25 64x linear + streaming H.264
                                        + wrap-around loop closure
- Phase D                              is folded into Phase C as the encode path.

`render()` runs all phases in sequence. Phase outputs land under
`config.output_dir / "staging" / output_name /` (keyframes PNGs) and
`config.output_dir / f"{output_name}.mp4"` (final video).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .config import PipelineConfig
from .encoding import H264StreamWriter
from .interpolation import RIFEInterpolator
from .keyframes import (
    expected_keyframe_count,
    generate_keyframes,
    load_sdxl_pipeline,
    unload_sdxl_pipeline,
)
from .noise import NoiseSource, build_noise_source
from .smoothing import temporal_smooth_keyframes


class Pipeline:
    """Slow-interpolation pipeline orchestrator."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._sdxl = None
        self._noise_walker: NoiseSource | None = None

    # ------------------------------------------------------------------ paths

    @property
    def output_name(self) -> str:
        return self.config.output_name or self.config.subject.name

    @property
    def staging_dir(self) -> Path:
        return self.config.output_dir / "staging" / self.output_name

    @property
    def keyframes_dir(self) -> Path:
        return self.staging_dir / "keyframes"

    @property
    def output_path(self) -> Path:
        return self.config.output_dir / f"{self.output_name}.mp4"

    # ------------------------------------------------------------------ phases

    def generate_keyframes(self) -> Path:
        """Phase A: render the keyframe PNG sequence. Returns its directory."""
        kf_dir = self.keyframes_dir
        kf_dir.mkdir(parents=True, exist_ok=True)
        self._noise_walker = build_noise_source(self.config)

        if self._sdxl is None:
            self._sdxl = load_sdxl_pipeline(self.config)

        generate_keyframes(
            self._sdxl,
            self.config,
            output_dir=kf_dir,
            noise_walker=self._noise_walker,
            guidance_scale=self.config.sampling.guidance_scale,
            num_inference_steps=self.config.sampling.num_inference_steps,
        )

        unload_sdxl_pipeline(self._sdxl)
        self._sdxl = None
        return kf_dir

    def smooth_keyframes(self) -> Path:
        """Phase A.5: in-place frequency-separated temporal smoothing."""
        r = self.config.render
        temporal_smooth_keyframes(
            self.keyframes_dir,
            sigma=r.smoothing_sigma,
            window=r.smoothing_window,
            blur_radius=r.smoothing_blur_radius,
        )
        return self.keyframes_dir

    def interpolate_and_encode(self) -> Path:
        """Phase C + D: RIFE 64x linear interpolation streamed to H.264.

        Reads keyframes from `self.keyframes_dir`, writes the MP4 to
        `self.output_path`. The wrap-around interpolation between the last and
        first keyframe (minus the final t=1 frame) is appended for seamless
        loop closure.
        """
        kf_paths = sorted(self.keyframes_dir.glob("*.png"))
        if len(kf_paths) < 2:
            raise RuntimeError(
                f"Need at least 2 keyframes in {self.keyframes_dir}, found {len(kf_paths)}"
            )

        rife_cfg = self.config.rife
        enc = self.config.encoding

        first_img: Image.Image | None = None
        prev_img: Image.Image | None = None

        with (
            RIFEInterpolator(
                vendor_path=rife_cfg.vendor_path,
                n_passes=rife_cfg.passes,
                skip_boundary=rife_cfg.skip_boundary,
                edge_crop=rife_cfg.edge_crop,
                sinusoidal=rife_cfg.sinusoidal,
            ) as rife,
            H264StreamWriter(
                self.output_path,
                fps=enc.fps,
                quality=enc.quality,
                codec=enc.codec,
                pixelformat=enc.pixelformat,
            ) as writer,
        ):
            for i, path in enumerate(kf_paths):
                img = Image.open(path).convert("RGB")
                if i == 0:
                    first_img = img
                else:
                    for frame in rife.interpolate_pair(prev_img, img):
                        writer.append(frame)
                prev_img = img

            # Wrap-around: interpolate from last keyframe back to first for
            # seamless loop closure. Drop the final frame (it equals first_img).
            wrap_frames = rife.interpolate_pair(prev_img, first_img)
            for frame in wrap_frames[:-1] if wrap_frames else []:
                writer.append(frame)

        return self.output_path

    def render(self) -> Path:
        """Run all phases sequentially. Returns the final MP4 path."""
        self.generate_keyframes()
        self.smooth_keyframes()
        return self.interpolate_and_encode()

    # ----------------------------------------------------------------- helpers

    def expected_keyframe_count(self) -> int:
        return expected_keyframe_count(self.config)
