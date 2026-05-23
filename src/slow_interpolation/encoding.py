"""Phase D: streaming H.264 encoding.

Wraps `imageio.get_writer` so the Pipeline can append RIFE-interpolated frames
one at a time without buffering the whole sequence in RAM (the legacy script
held 3 GB+ of frames before this was fixed; we keep the streaming approach).
Output is libx264 in yuv420p at 24 fps with a quality slider.

`archive_if_exists` mirrors the legacy behavior: an existing output is moved
to `<output_dir>/archive/<name>_<timestamp>.mp4` rather than overwritten, so a
botched re-render never destroys a good one.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


def archive_if_exists(video_path: Path) -> None:
    """Move an existing MP4 to `<parent>/archive/<stem>_<ts>.mp4`."""
    video_path = Path(video_path)
    if not video_path.exists():
        return
    archive_dir = video_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = archive_dir / f"{video_path.stem}_{ts}{video_path.suffix}"
    shutil.move(str(video_path), str(dest))


class H264StreamWriter:
    """Context-managed streaming writer over imageio + libx264.

    Use as `with H264StreamWriter(path, fps=24) as w: w.append(frame_np)`.
    """

    def __init__(
        self,
        path: Path,
        fps: int = 24,
        quality: int = 5,
        codec: str = "libx264",
        pixelformat: str = "yuv420p",
    ) -> None:
        self.path = Path(path)
        self.fps = fps
        self.quality = quality
        self.codec = codec
        self.pixelformat = pixelformat
        self._writer: Any | None = None
        self.frame_count = 0

    def __enter__(self) -> "H264StreamWriter":
        import imageio

        self.path.parent.mkdir(parents=True, exist_ok=True)
        archive_if_exists(self.path)
        self._writer = imageio.get_writer(
            str(self.path),
            fps=self.fps,
            codec=self.codec,
            quality=self.quality,
            pixelformat=self.pixelformat,
        )
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def append(self, frame: np.ndarray) -> None:
        if self._writer is None:
            raise RuntimeError("H264StreamWriter not opened; use as a context manager")
        self._writer.append_data(frame)
        self.frame_count += 1
