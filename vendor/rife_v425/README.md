# RIFE v4.25 (vendored)

Vendored copy of the inference-side of Practical-RIFE v4.25, used by Phase C
of the pipeline (`docs/pipeline.md`). Upstream: https://github.com/hzwer/Practical-RIFE.

## Provenance

Copied on 2026-05-14 from the author's local working copy of the upstream
release. Only the inference assets needed by the pipeline were vendored:

- `train_log/RIFE_HDv3.py` (was `train_log/train_log/RIFE_HDv3.py` in source, doubly-nested)
- `train_log/IFNet_HDv3.py`
- `train_log/refine.py`
- `train_log/flownet.pkl` (24 MB)
- `model/warplayer.py`
- `model/loss.py`
- `model/pytorch_msssim/`
- `LICENSE`

The original source has `train_log/train_log/` nesting (from the upstream zip
extraction). This vendor layout is flattened to a single `train_log/` level,
so the legacy `sys.path.insert(rife_repo); sys.path.insert(rife_train_log)`
dance collapses to one insertion plus `from train_log.RIFE_HDv3 import Model`.

## Why v4.25 specifically

- v4.25 is the first RIFE release with explicit arbitrary-timestep support,
  which is what `linear_interp` in the pipeline uses to eliminate the binary-
  midpoint sharpness flash that plagued v3 / HDv3.
- v4.26 introduced resolution-divisible-by-64 requirements (v4.25 only needs
  32) and shows marginally worse non-video flicker per the SmoothVideo community
  (see `docs/pipeline.md` for the rationale; the original frame-interpolation
  research log is under `legacy/`).

## License

MIT, see LICENSE. Original work by Zhewei Huang et al., Practical-RIFE project.

## Usage from this repo

The Python wrapper at `src/slow_interpolation/interpolation/rife.py` (Phase 2C)
handles `sys.path` insertion, the torchvision `functional_tensor` compatibility
shim, and provides the `RIFEInterpolator` class. Direct use from elsewhere in
the package is not expected.
