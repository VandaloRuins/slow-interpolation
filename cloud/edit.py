"""Open-weight instruction image editors on Modal (the nano-banana replacement probe).

Why this module exists: `tools/banana_keyframes.py` authors every keyframe in the
edit-model loop through Google's `gemini-3.1-flash-image`. That endpoint is metered,
it depleted mid-production on 2026-08-13, and it costs 0.067 USD per image. This app
hosts the three open-weight candidates from
`docs/findings/image-edit-model-alternatives.md` so the bake-off can be run entirely
on rented GPUs at full precision, which removes the quantisation-degradation risk
class that dominates any 8 GB local analysis.

Three candidates, three classes, one method signature. `tools/edit_keyframes.py` is
the drop-in caller and never has to know which one it is talking to.

    CANDIDATE   model                            GPU          weights
    klein       black-forest-labs/FLUX.2-klein-4B  L40S        23.7 GB
    firered     FireRedTeam/FireRed-Image-Edit-1.1 A100-80GB   57.7 GB
    mageflow    mage-flow-community/Mage-Flow-Edit-Turbo  L40S 17.5 GB

Three deviations from the kickoff sketch, each measured rather than assumed:

1. **FireRed does NOT fit L40S 48 GB.** The finding recorded "20B, ~30 GB"; the
   actual repo is 40.86 GB of transformer plus 16.58 GB of text encoder = 57.7 GB
   in bf16. The 30 GB figure on the model card is the *quantised* acceleration
   suite. It is bound to A100-80GB here, because CPU offload on L40S would shuttle
   40 GB across PCIe on every call and we would be measuring the offload.

2. **Weights land on a dedicated `slow-interp-edit-cache` volume**, not the shared
   `slow-interp-hf-cache`. Roughly 100 GB of candidate weights is bake-off scratch;
   on its own volume it can be deleted in one command when the verdict is in,
   without disturbing the SDXL/RIFE cache the render path depends on.

3. **Mage-Flow runs the SDPA attention backend**, not flash-attn. Its README
   installs `flash-attn==2.8.3` from source with build isolation off, which is a
   30-60 minute CUDA compile inside an image build. `mage_flow.models.modules
   ._attn_backend.set_attn_backend("sdpa")` is a supported first-party path and
   costs only speed, which is not what the bake-off is measuring.

Each class holds the pipeline resident via `@modal.enter()`, so a 9-edit chain pays
the model load ONCE. With `@app.function` the load is per edit and the cost model
collapses.
"""

from __future__ import annotations

import io
import time

import modal

# ---------------------------------------------------------------------------
# Volumes. See deviation 2 above.
# ---------------------------------------------------------------------------

HF_CACHE = "/root/.cache/huggingface"
edit_cache = modal.Volume.from_name("slow-interp-edit-cache", create_if_missing=True)
VOLUMES = {HF_CACHE: edit_cache}

app = modal.App("slow-interp-edit")


# ---------------------------------------------------------------------------
# Images.
#
# `diffusers_image` serves klein and FireRed: both are diffusers-native
# (`Flux2KleinPipeline`, `QwenImageEditPlusPipeline`) and both need diffusers
# from git, because the released wheel predates Flux2.
#
# `mage_image` is separate and NOT mergeable: Mage-Flow pins torch 2.13 /
# transformers 5.5 / diffusers 0.38, and ships its own `mage_flow` package with
# custom transformer and VAE classes. transformers 5.x is above the ceiling the
# other two are tested against.
# ---------------------------------------------------------------------------

diffusers_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.7.1",
        "torchvision==0.22.1",
        extra_index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install(
        "accelerate",
        "safetensors",
        "pillow",
        "numpy",
        "sentencepiece",
        "protobuf",
        # transformers must be 5.x here, not the 4.57 the kickoff sketch implies.
        # diffusers main pulls huggingface-hub>=1.23, and every transformers 4.57.x
        # caps huggingface-hub<1.0, so the 4.x pin is unresolvable. Ceiling at 5.6
        # for the same reason Mage-Flow does: 5.6 dropped the `input_embeds` kwarg
        # of `create_causal_mask` that the Qwen text encoders call.
        "transformers>=5.5,<5.6",
        "hf_transfer",
        "git+https://github.com/huggingface/diffusers.git",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HOME": HF_CACHE})
)

mage_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.13.0",
        "torchvision==0.28.0",
        extra_index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install(
        "diffusers==0.38.0",
        "transformers==5.5.0",
        "accelerate==1.13.0",
        "safetensors>=0.8.0",
        "einops",
        "pydantic",
        "pillow",
        "numpy",
        "loguru",
        "huggingface_hub>=0.20",
        "hf_transfer",
    )
    .run_commands(
        "pip install --no-deps 'git+https://github.com/microsoft/Mage.git"
        "#subdirectory=mage_flow'"
    )
    # Mage-Flow has TWO independent attention paths and skipping either one
    # re-introduces the flash-attn build. `set_attn_backend` covers only the DiT;
    # the Qwen3-VL text encoder is constructed by transformers with
    # `attn_implementation="flash_attention_2"` hard-coded, and VF_HF_ATTN_IMPL is
    # the first-party override for exactly that (its docstring names "forcing sdpa
    # on machines without flash-attn" as the use case).
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_HOME": HF_CACHE,
        "VF_HF_ATTN_IMPL": "sdpa",
    })
)


TIMEOUT = 60 * 60
SCALEDOWN = 300


def _to_pil(blobs: list[bytes]):
    from PIL import Image

    return [Image.open(io.BytesIO(b)).convert("RGB") for b in blobs]


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ping(pipe) -> dict:
    """What actually loaded, and how much of the card it took.

    Reported rather than assumed because the finding's VRAM figures were wrong
    for FireRed by 27 GB; a resident-memory number is the only honest answer to
    "does it fit".
    """
    import torch

    free, total = torch.cuda.mem_get_info()
    return {
        "device": torch.cuda.get_device_name(0),
        "vram_total_gb": round(total / 1e9, 1),
        "vram_resident_gb": round((total - free) / 1e9, 1),
        "torch": torch.__version__,
        "pipeline": type(pipe).__name__,
    }


def _result(img, seconds: float, note: str = "") -> dict:
    """Uniform return. Size travels WITH the bytes so Q2 never rests on a
    caller-side assumption about what was requested."""
    return {
        "png": _to_png(img),
        "width": img.size[0],
        "height": img.size[1],
        "seconds": seconds,
        "note": note,
    }


# ---------------------------------------------------------------------------
# 1. FLUX.2 [klein] 4B -- Apache 2.0, distilled, 4 steps, guidance 1.0.
# ---------------------------------------------------------------------------


@app.cls(
    image=diffusers_image,
    gpu="L40S",
    volumes=VOLUMES,
    timeout=TIMEOUT,
    scaledown_window=SCALEDOWN,
)
class KleinEditor:
    MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"

    @modal.enter()
    def load(self):
        import torch
        from diffusers import Flux2KleinPipeline

        t0 = time.perf_counter()
        self.pipe = Flux2KleinPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=torch.bfloat16
        ).to("cuda")
        print(f"[klein] loaded in {time.perf_counter() - t0:.1f}s")

    @modal.method()
    def ping(self) -> dict:
        return _ping(self.pipe)

    @modal.method()
    def edit(
        self,
        images: list[bytes],
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int = 4,
        seed: int = 1087,
        guidance: float = 1.0,
    ) -> dict:
        import torch

        refs = _to_pil(images)
        t0 = time.perf_counter()
        out = self.pipe(
            image=refs if len(refs) > 1 else (refs[0] if refs else None),
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        return _result(out, time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# 2. FireRed-Image-Edit 1.1 -- Apache 2.0, QwenImageEditPlusPipeline, 20B.
#
# true_cfg_scale > 1 needs a negative prompt and runs BOTH branches, doubling
# the compute per step. The Qwen-family default is 4.0 and preservation is the
# thing under test, so the probe does not economise here.
# ---------------------------------------------------------------------------


@app.cls(
    image=diffusers_image,
    gpu="A100-80GB",
    volumes=VOLUMES,
    timeout=TIMEOUT,
    scaledown_window=SCALEDOWN,
)
class FireRedEditor:
    MODEL_ID = "FireRedTeam/FireRed-Image-Edit-1.1"

    @modal.enter()
    def load(self):
        import torch
        from diffusers import QwenImageEditPlusPipeline

        t0 = time.perf_counter()
        self.pipe = QwenImageEditPlusPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=torch.bfloat16
        ).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        print(f"[firered] loaded in {time.perf_counter() - t0:.1f}s")

    @modal.method()
    def ping(self) -> dict:
        return _ping(self.pipe)

    @modal.method()
    def edit(
        self,
        images: list[bytes],
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int = 24,
        seed: int = 1087,
        guidance: float = 4.0,
        negative_prompt: str = " ",
    ) -> dict:
        import torch

        refs = _to_pil(images)
        t0 = time.perf_counter()
        out = self.pipe(
            image=refs,
            prompt=prompt,
            negative_prompt=negative_prompt,
            true_cfg_scale=guidance,
            width=width,
            height=height,
            num_inference_steps=steps,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        return _result(out, time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# 3. Mage-Flow-Edit-Turbo 4B -- MIT, 4 steps, cfg 1.0.
#
# The one candidate that does NOT downsample the VAE conditioning path to a
# 1 MP budget: `vl_cond_long_edge` caps only the reference fed to the VL text
# encoder. That is the whole reason it is in the bake-off.
#
# Weights come from a community mirror. `microsoft/Mage-Flow*` returns 404 even
# with a valid token, and `Comfy-Org/Mage-Flow` is single-file ComfyUI format
# with no diffusers `model_index.json`. The mirror is a byte re-upload of the
# MIT release referenced by `base_model: microsoft/Mage-Flow`; provenance is
# weaker than a first-party repo and is flagged in the finding.
# ---------------------------------------------------------------------------


@app.cls(
    image=mage_image,
    gpu="L40S",
    volumes=VOLUMES,
    timeout=TIMEOUT,
    scaledown_window=SCALEDOWN,
)
class MageFlowEditor:
    MODEL_ID = "mage-flow-community/Mage-Flow-Edit-Turbo"

    @modal.enter()
    def load(self):
        from mage_flow import MageFlowPipeline
        from mage_flow.models.modules._attn_backend import set_attn_backend

        t0 = time.perf_counter()
        self.pipe = MageFlowPipeline.from_pretrained(self.MODEL_ID, device="cuda")
        # AFTER the load, not before. `MageFlowModel.__init__` calls
        # `set_attn_backend(config.attn_type)` itself and the repo config says
        # flash2, so a pre-load call is silently overwritten. Nothing attends
        # during construction, and the shim resolves its kernel lazily on first
        # use, so setting it here is what actually takes effect.
        set_attn_backend("sdpa")
        print(f"[mageflow] loaded in {time.perf_counter() - t0:.1f}s")

    @modal.method()
    def ping(self) -> dict:
        return _ping(self.pipe)

    @modal.method()
    def edit(
        self,
        images: list[bytes],
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int = 4,
        seed: int = 1087,
        guidance: float = 1.0,
    ) -> dict:
        refs = _to_pil(images)
        kw = dict(steps=steps, cfg=guidance, seeds=[seed])
        if width and height:
            kw["heights"] = [height]
            kw["widths"] = [width]
        t0 = time.perf_counter()
        out = self.pipe.edit([prompt], [refs if len(refs) > 1 else refs[0]], **kw)[0]
        return _result(out, time.perf_counter() - t0)


EDITORS = {
    "klein": KleinEditor,
    "firered": FireRedEditor,
    "mageflow": MageFlowEditor,
}

# Per-candidate sampler defaults. The caller may override, but these are the
# card-documented settings and are what the bake-off numbers were taken at.
DEFAULTS = {
    "klein": {"steps": 4, "guidance": 1.0},
    "firered": {"steps": 24, "guidance": 4.0},
    "mageflow": {"steps": 4, "guidance": 1.0},
}


@app.local_entrypoint()
def smoke(candidate: str = "klein"):
    """Load one candidate and report what it landed on. No sampling.

    The cheapest possible proof that the image builds, the weights download and
    the pipeline instantiates, before a probe spends real money on samples. An
    exit code proves nothing here: run it, read the printed dict.

        env PYTHONIOENCODING=utf-8 PYTHONUTF8=1 \\
            modal run cloud/edit.py::smoke --candidate klein
    """
    print(EDITORS[candidate]().ping.remote())
