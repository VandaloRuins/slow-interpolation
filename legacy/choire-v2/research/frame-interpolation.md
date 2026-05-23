# Frame Interpolation for AI-Generated Visuals

*Research for In Ascolto — smooth morphing between SDXL Turbo frames at ~0.3 FPS*

---

## Context

The existing visual pipeline (documented in `research/realtime-visuals.md`) generates one 512x512 SDXL Turbo frame every ~3-4 seconds on the RTX 4060 Laptop (8GB VRAM, 6.58 GB in use = ~1.4 GB headroom). The goal is **organic, continuous morphing** between these keyframes — not crossfade/opacity blending. The installation context (peaceful, ritual, slow-tempo) demands visual motion that feels alive and evolving rather than discrete keyframe jumps.

**VRAM budget reminder:** SDXL Turbo holds 6.58 GB. Only ~1.4 GB is free for any co-resident interpolation model.

---

## 1. RIFE (Real-Time Intermediate Flow Estimation)

### What it is

RIFE (arXiv:2011.06294, ECCV 2022) is a neural video frame interpolation network built around IFNet — a network that estimates intermediate optical flow end-to-end, directly from two input frames, without a pre-trained flow estimator. It is the dominant community standard for fast frame interpolation.

- **Paper:** Huang et al., "Real-Time Intermediate Flow Estimation for Video Frame Interpolation," ECCV 2022
- **Source:** github.com/hzwer/ECCV2022-RIFE
- **ComfyUI node:** github.com/Fannovel16/ComfyUI-Frame-Interpolation (nodes: `RIFE VFI`, `RIFE VFI Interpolate by Multiple`)
- **TensorRT version:** github.com/yuvraj108c/ComfyUI-Rife-Tensorrt

### Speed benchmarks

| GPU | Resolution | Interpolation | FPS (PyTorch) | FPS (TensorRT) | Source tier |
|---|---|---|---|---|---|
| RTX 2080 Ti | 720p | 2x | 30+ FPS | — | Tier 2 (official repo) |
| RTX 3070 Ti | 1080p FP16 | 2x | 109 FPS | 109.73 FPS | Tier 3 (community, TRT) |
| RTX 3090 | 1080p | 2x | real-time viable | — | Tier 3 (community) |
| RTX 4090 | 1080p FP16 | 2x | — | 416 FPS | Tier 3 (community, TRT) |
| **RTX 4060 Laptop** | **512x512** | **2x** | **~80-120 FPS est.** | **~200+ FPS est.** | UNVERIFIED — derived from above |

**RTX 4060 Laptop derivation:** The RTX 4060 Laptop delivers roughly 60-70% of desktop RTX 3070 Ti throughput in ML workloads (similar compute, lower TDP). At 512x512 (far below 1080p), the computation scales as O(resolution²), so 512x512 is ~25% of 1080p pixel count. Estimated PyTorch FPS at 512x512: 80-150 FPS. This means a single interpolated frame between two AI keyframes takes **6-12 ms** — well within our 3-second generation window.

### VRAM usage

RIFE IFNet has approximately 5.6M-21M parameters depending on version. At fp16:
- Model weights: ~30-80 MB
- Activations for 512x512: ~100-200 MB (two input frames + flow maps + output)
- **Total estimated: 150-300 MB** at 512x512 in fp16 (Tier 3 — community CUDA OOM reports suggest comfortable operation on 6GB GPUs even at higher resolutions)

**Critical finding:** RIFE v4.4 is confirmed usable on 8GB VRAM for **4K** interpolation. At 512x512, VRAM pressure is negligible. The model can plausibly co-reside with a paused/offloaded SDXL Turbo pipeline.

### Can it run alongside SDXL Turbo?

Not simultaneously — PyTorch queues GPU operations sequentially when run from the same process thread. The practical workflow is:

1. SDXL Turbo generates a new frame (takes ~3-4 seconds, fully occupies GPU)
2. SDXL Turbo's UNet is idle between generations
3. RIFE fills the gap: interpolates N intermediate frames between previous and new keyframe
4. Browser displays RIFE-interpolated stream at smooth FPS

**Recommended architecture:** Sequential scheduling, not concurrent. While CUDA Streams permit concurrent execution in theory, memory pressure on 8GB makes true simultaneity risky. The generation cadence (one frame every 3s) creates a natural slot for interpolation.

### How many intermediate frames

With 3-second generation intervals and a display target of 24-30 FPS: 3s × 24 FPS = 72 intermediate frames needed. RIFE achieves this recursively: each pass doubles the frame count (2x, 4x, 8x, 16x, 32x, 64x = 6 recursive passes). 6 passes × ~10ms each = **~60ms total** to produce 64 interpolated frames for the 3-second gap. This is trivially fast.

### Quality for AI art (non-photographic content)

**Key issue: RIFE was designed for video, not AI-generated imagery.** Optical flow works by assuming consistent motion between real video frames. AI frames from SDXL Turbo are not temporally consistent — each is independently sampled, so "motion" between them is not physical motion but semantic drift. RIFE will attempt to interpret pixel-level differences as motion and warp accordingly, producing:

- **Ghost artifacts** at content boundaries (moderate severity at 2x, severe at 8x+)
- **Smearing** on fine architectural details (fresco textures, column edges)
- **Temporal instability** — the interpolated motion may look physically plausible but semantically incoherent

**Mitigation strategies from the community:**
- Limit to 1 intermediate frame (2x only) to minimize artifact accumulation
- Enable `ensemble=True` in RIFE VFI node (averages forward/backward flows)
- Combine with `smootherstep` interpolation for subtle content differences
- Apply post-processing distortions or stylistic textures to mask artifacts
- Generate AI frames that are compositionally similar (same structural template, subtle changes only)

**Verdict for In Ascolto:** Viable with strong constraints. Works well when consecutive AI frames are structurally similar (same spatial layout, evolving color/texture). Breaks down on prompt transitions (throne room -> garden). The peaceful, slow-morphing aesthetic actually helps — small changes between keyframes minimize optical flow errors.

### Python implementation (ComfyUI-Frame-Interpolation, standalone)

```python
# Install: pip install rife-interpolation or use ComfyUI-Frame-Interpolation
# Standalone inference with rife-ncnn-vulkan (CPU/GPU, cross-platform):
import subprocess

def rife_interpolate(frame_a_path: str, frame_b_path: str, output_dir: str, multiplier: int = 4):
    """
    Interpolate N intermediate frames between frame_a and frame_b.
    multiplier: 2 = 1 intermediate frame, 4 = 3 frames, 8 = 7 frames
    Uses rife-ncnn-vulkan (GPU-accelerated, no PyTorch required).
    """
    subprocess.run([
        "rife-ncnn-vulkan",
        "-i", frame_a_path,
        "-o", output_dir,
        "-n", str(multiplier),
        "-m", "rife-v4.6",   # or rife-v4.25 for newest
    ])

# PyTorch version (requires ECCV2022-RIFE repo):
import torch
from model.RIFE_HDv3 import Model

model = Model()
model.load_model("train_log/", -1)
model.eval()
model.device()

def interpolate_frames(img0: torch.Tensor, img1: torch.Tensor,
                        timestep: float = 0.5) -> torch.Tensor:
    """
    img0, img1: [1, 3, H, W] normalized to [0,1], on CUDA
    timestep: 0.5 = midpoint, can vary for non-uniform spacing
    Returns: [1, 3, H, W] interpolated frame
    """
    with torch.no_grad():
        mid = model.inference(img0, img1, timestep)
    return mid
```

### Sources

- RIFE paper: arXiv:2011.06294, github.com/hzwer/ECCV2022-RIFE
- Community benchmarks: github.com/HolyWu/vs-rife/discussions/19 (RTX 3070 Ti, 4090 TRT figures)
- SVP wiki: svp-team.com/wiki/RIFE_AI_interpolation (model variant comparison)
- ComfyUI implementation: github.com/Fannovel16/ComfyUI-Frame-Interpolation
- TensorRT version: github.com/yuvraj108c/ComfyUI-Rife-Tensorrt
- Animated watercolor RIFE paper (AI art use): dl.acm.org/doi/10.1145/3749893.3749971

---

## 2. FILM (Frame Interpolation for Large Motion)

### What it is

FILM (arXiv:2202.04901, ECCV 2022) by Google Research. Uses a multi-scale feature extractor + bidirectional motion estimator + fusion module. Key differentiator: handles **large motion** (pixel displacement > 100px) better than RIFE by using multi-scale flow at each pyramid level. Designed for slow-motion video from high-framerate capture.

- **Paper:** Reda et al., "FILM: Frame Interpolation for Large Motion," ECCV 2022
- **Source:** github.com/google-research/frame-interpolation
- **PyTorch port:** github.com/dajes/frame-interpolation-pytorch (supports fp16, TorchScript)
- **TF Hub:** tensorflow.org/hub/tutorials/tf_hub_film_example

### Speed benchmarks

FILM is approximately **5-10x slower** than RIFE at equivalent resolution (Tier 2 — RIFE vs FILM comparison articles, 2025 Apatero Blog). On an RTX 4090 at 1080p 2x interpolation, RIFE achieves 50-100+ FPS while FILM takes ~7x longer. On a T4 GPU, FILM predictions complete in ~67 seconds for high-resolution frames (Tier 2 — TF Hub docs).

| GPU | Estimated FPS at 512x512 2x | VRAM est. | Source tier |
|---|---|---|---|
| RTX 4090 | 30-50 FPS | ~500MB | UNVERIFIED (derived) |
| **RTX 4060 Laptop** | **~8-20 FPS est.** | **~400-600MB est.** | UNVERIFIED |

At these speeds, FILM at 512x512 still interpolates a 3-second gap in well under 1 second. Not a bottleneck.

### VRAM usage

FILM's multi-scale architecture is heavier than RIFE. The PyTorch port supports fp16 for GPU tensor core acceleration. Estimated VRAM at 512x512 in fp16: **300-600 MB** (UNVERIFIED — no direct benchmark found). This is within the 1.4 GB headroom but tighter than RIFE.

### Quality comparison vs RIFE

| Criterion | RIFE | FILM |
|---|---|---|
| Speed | 5-10x faster | Slower |
| Small motion (video) | Excellent | Excellent |
| Large motion | Good | Better (design goal) |
| AI art ghosting artifacts | Moderate | Similar to RIFE |
| Film grain / texture preservation | Good | Good |
| Open source / maintained | Active | Less active (2022) |

**Key insight for In Ascolto:** The "large motion" advantage of FILM is irrelevant here. Our use case involves architecturally stable frames with slow texture/color drift — the opposite of large motion. FILM's quality advantage does not apply. RIFE is the correct choice for this installation.

**However:** FILM's feature pyramid may better handle content morphing (semantic differences) than pure optical flow, producing more "dreamlike" transitions between semantically dissimilar frames. This could be aesthetically valuable for prompt-change transitions (e.g., throne room -> garden). UNVERIFIED in AI art context.

### Python implementation

```python
# PyTorch port by dajes — recommended over original TF version
# pip install -r requirements.txt  # from dajes/frame-interpolation-pytorch

from interpolator import Interpolator
import numpy as np
from PIL import Image

interpolator = Interpolator("film_net_fp16.pt", None)  # fp16 for speed

def film_interpolate(img_a: np.ndarray, img_b: np.ndarray) -> np.ndarray:
    """
    img_a, img_b: [H, W, 3] float32 arrays, normalized [0,1]
    Returns: [H, W, 3] interpolated midpoint frame
    """
    mid = interpolator(img_a[None], img_b[None])  # batch dim
    return mid[0]

# For multiple intermediate frames (recursive):
from util import interpolate_recursively_from_memory
frames = list(interpolate_recursively_from_memory([img_a, img_b], times_to_interpolate=4))
# 4 = 15 intermediate frames
```

### Sources

- FILM paper: arXiv:2202.04901, film-net.github.io
- ACM proceedings: dl.acm.org/doi/10.1007/978-3-031-20071-7_15
- PyTorch port: github.com/dajes/frame-interpolation-pytorch
- RIFE vs FILM comparison: apatero.com/blog/rife-vs-film-video-frame-interpolation-comparison-2025
- TF Hub tutorial + T4 timing: tensorflow.org/hub/tutorials/tf_hub_film_example
- Replicate API (backup): replicate.com/google-research/frame-interpolation

---

## 3. Latent Space Interpolation (SLERP)

### What it is

Instead of interpolating in pixel space (like RIFE/FILM), SLERP interpolation happens in the VAE's **latent space** — the compressed 4-channel representation that SDXL Turbo generates during inference. Two frames' latent vectors are encoded, a slerp path is computed between them, and frames along this path are decoded back to pixels.

The key claim: latent interpolation produces **semantically meaningful morphs** rather than optical-flow pixel-level warping. The transition follows the geometry of the learned generative manifold.

### SDXL VAE specifics

- SDXL VAE compresses 512x512x3 pixel images to 64x64x4 latent tensors (8x spatial compression)
- Use `madebyollin/sdxl-vae-fp16-fix` — the stock SDXL VAE produces NaNs in fp16; this finetuned version is stable
- Encode: ~10-30ms per frame at 512px on RTX 4060 (UNVERIFIED — derived from SDXL pipeline timing)
- Decode: ~20-50ms per frame at 512px on RTX 4060 (UNVERIFIED)
- VRAM for VAE alone: ~800MB-1.2GB

**Critical complication:** The SDXL VAE must already be loaded as part of the SDXL Turbo pipeline (already resident in the 6.58GB). Latent SLERP can reuse the already-loaded VAE — no extra VRAM cost for the VAE itself.

### Does it work?

From research (Tier 3 — ML community documentation and HF cookbook):

**Works well:** Interpolating between two images generated with very similar prompts. The latent space is locally smooth, so slerp produces coherent intermediate frames that feel like the image is naturally evolving.

**Works poorly:** Interpolating between semantically distant images (throne room vs. garden). The VAE's latent space is not uniformly structured for image-to-image interpolation — simple linear interpolation between latent codes produces gray, blurry frames because it changes statistical properties that diffusion models depend on. SLERP is better but still degrades for large semantic distances.

**Key issue — no re-denoising:** Pure SLERP encodes → interpolates → decodes. The interpolated latent is fed directly to the decoder without a denoising pass. The decoder was designed to decode "clean" (fully denoised) latents from the diffusion process. Interpolated latents are not on the "clean latent manifold" and produce blurry/muddy pixel output at the midpoints.

**Workaround — DDIM latent interpolation with partial denoising:** Instead of raw latent SLERP, add a short denoising pass (2-4 steps at strength 0.3-0.5) to snap the interpolated latent back onto the learned manifold. This produces sharper, more coherent intermediate frames. This is the approach used by `nateraw/stable-diffusion-videos`.

### Speed

- Encode two images: ~20-60ms total
- SLERP computation: <1ms (pure tensor math)
- Decode N intermediate frames: N × 20-50ms
- **For 10 intermediate frames:** ~0.2-0.5 seconds total (estimate)

This is slower than RIFE but still fills a 3-second gap. With partial denoising (2-4 steps per frame), each intermediate frame takes ~200-500ms on RTX 4060 Laptop — meaning only 6-10 intermediate frames are feasible in a 3-second budget, not 72.

**Verdict for In Ascolto:** SLERP without denoising produces blurry output — not suitable as the sole morphing method. SLERP with partial denoising is high-quality but slow (~2-5 FPS), giving only a modest number of intermediate frames. Most useful as a **transition technique at prompt changes** (generate 5-8 high-quality latent-walk frames during a prompt switch), combined with RIFE for the majority of the continuous interpolation.

### Python implementation

```python
import torch
from diffusers import AutoencoderKL
import numpy as np

# Load fp16-stable SDXL VAE (reuse from existing pipeline if loaded)
vae = AutoencoderKL.from_pretrained(
    "madebyollin/sdxl-vae-fp16-fix",
    torch_dtype=torch.float16
).to("cuda")

def slerp(v0: torch.Tensor, v1: torch.Tensor, t: float) -> torch.Tensor:
    """Spherical linear interpolation between two latent tensors."""
    v0_flat = v0.flatten()
    v1_flat = v1.flatten()
    dot = torch.dot(v0_flat / v0_flat.norm(), v1_flat / v1_flat.norm())
    dot = dot.clamp(-1.0, 1.0)
    # Near-parallel: fall back to linear interpolation
    DOT_THRESHOLD = 0.9995
    if dot.abs() > DOT_THRESHOLD:
        return torch.lerp(v0, v1, t)
    theta = torch.acos(dot)
    return (torch.sin((1 - t) * theta) * v0 + torch.sin(t * theta) * v1) / torch.sin(theta)

def encode_image(pil_image, vae) -> torch.Tensor:
    """Encode a PIL image to SDXL latent space."""
    import torchvision.transforms as T
    transform = T.Compose([T.Resize((512, 512)), T.ToTensor(),
                            T.Normalize([0.5], [0.5])])
    img_tensor = transform(pil_image).unsqueeze(0).half().cuda()
    with torch.no_grad():
        latent = vae.encode(img_tensor).latent_dist.sample()
        latent = latent * vae.config.scaling_factor
    return latent

def decode_latent(latent: torch.Tensor, vae) -> torch.Tensor:
    """Decode SDXL latent to pixel tensor [0,1]."""
    with torch.no_grad():
        latent = latent / vae.config.scaling_factor
        image = vae.decode(latent).sample
    return (image / 2 + 0.5).clamp(0, 1)

def generate_slerp_frames(img_a, img_b, vae, n_frames: int = 8):
    """
    Generate n_frames intermediate images between img_a and img_b
    via SLERP in SDXL latent space.
    Note: output may be blurry. Add partial denoising pass for quality.
    """
    latent_a = encode_image(img_a, vae)
    latent_b = encode_image(img_b, vae)
    frames = []
    for i in range(1, n_frames + 1):
        t = i / (n_frames + 1)
        latent_mid = slerp(latent_a, latent_b, t)
        pixel = decode_latent(latent_mid, vae)
        frames.append(pixel)
    return frames
```

### Sources

- SLERP implementation: gist.github.com/Birch-san/230ac46f99ec411ed5907b0a3d728efa
- HF cookbook on SD interpolation: huggingface.co/learn/cookbook/stable_diffusion_interpolation
- DEV.to SLERP + Stable Diffusion guide: dev.to/ramgendeploy/exploiting-latent-vectors-in-stable-diffusion-interpolation-and-parameters-tuning-j3d
- SDXL latent space explanation: huggingface.co/blog/TimothyAlexisVass/explaining-the-sdxl-latent-space
- sdxl-vae-fp16-fix: huggingface.co/madebyollin/sdxl-vae-fp16-fix
- Stable Diffusion videos (latent walk implementation): github.com/nateraw/stable-diffusion-videos
- Karpathy latent walk gist: gist.github.com/karpathy/00103b0037c5aaea32fe1da1af553355

---

## 4. Optical Flow Warping (RAFT / Farneback)

### What it is

Compute a dense optical flow field between two frames, then synthesize intermediate frames by warping pixel values along this flow. No neural network for the synthesis itself — just classical forward/backward warping. Two options:

1. **RAFT (Recurrent All-Pairs Field Transforms):** Deep learning optical flow. ECCV 2020 winner. Torchvision built-in (`torchvision.models.optical_flow.raft_large()` and `raft_small()`). Achieves top accuracy on Sintel and KITTI benchmarks.
2. **Farneback:** Classical (non-DL) dense optical flow. OpenCV built-in. Fast on CPU, no GPU required.

### Speed and VRAM

| Method | Resolution | Speed | VRAM | Notes |
|---|---|---|---|---|
| RAFT Large | 512x512 | ~50-100ms/frame (RTX 4060 est.) | ~400MB | UNVERIFIED — derived from comparable GPU benchmarks |
| RAFT Small | 512x512 | ~15-30ms/frame (RTX 4060 est.) | ~150MB | UNVERIFIED |
| Farneback (OpenCV) | 512x512 | ~5-15ms/frame CPU | 0 (CPU) | Verified: runs real-time on CPU |

RAFT model weights: raft_large ~21MB, raft_small ~4MB. VRAM dominated by activations during inference.

### Quality for AI art

**Major limitation:** RAFT/Farneback compute flow from pixel intensity differences, not semantic content. Between two independently-sampled SDXL Turbo frames, "flow" is hallucinated motion that doesn't correspond to physical movement. The result is **warp artifacts**: holes (disocclusions where pixels disappear behind a moving region), smearing, and tear-like distortions.

This is an inherent problem in any flow-based method for non-video content. Mitigation:
- Bidirectional warping with blending masks (forward-warp + backward-warp, blend at t=0.5 seam)
- Works best when consecutive frames differ only in color/brightness, not structure

**Verdict for In Ascolto:** Farneback is a useful fallback for the 60fps noise overlay layer (see Section 7) since it runs on CPU without touching GPU VRAM. RAFT is inferior to RIFE for the main interpolation task (RIFE uses learned flow that is better calibrated for synthesis). Not recommended as primary interpolation method.

### Python implementation

```python
import cv2
import numpy as np

def farneback_flow(frame_a: np.ndarray, frame_b: np.ndarray) -> np.ndarray:
    """Dense optical flow via Farneback (CPU, no GPU required)."""
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_RGB2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_a, gray_b,
        None,               # flow output
        pyr_scale=0.5,      # scale between pyramid levels
        levels=3,           # pyramid levels
        winsize=15,         # window size
        iterations=3,
        poly_n=5,           # pixel neighborhood size
        poly_sigma=1.2,
        flags=0
    )
    return flow  # [H, W, 2]

def warp_frame(frame: np.ndarray, flow: np.ndarray, t: float) -> np.ndarray:
    """Warp frame by flow * t. t in [0,1]."""
    h, w = frame.shape[:2]
    flow_scaled = flow * t
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
    map_x = (grid_x + flow_scaled[..., 0]).astype(np.float32)
    map_y = (grid_y + flow_scaled[..., 1]).astype(np.float32)
    warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REFLECT)
    return warped

# For RAFT via torchvision:
import torch
from torchvision.models.optical_flow import raft_small, Raft_Small_Weights

weights = Raft_Small_Weights.DEFAULT
raft_model = raft_small(weights=weights).cuda().eval()

def raft_flow(frame_a: torch.Tensor, frame_b: torch.Tensor) -> torch.Tensor:
    """
    frame_a, frame_b: [1, 3, H, W] uint8 on CUDA
    Returns: flow [1, 2, H, W]
    """
    transforms = weights.transforms()
    a, b = transforms(frame_a, frame_b)
    with torch.no_grad():
        flow_list = raft_model(a, b)
    return flow_list[-1]  # final refined flow estimate
```

### Sources

- RAFT paper: ECCV 2020, github.com/princeton-vl/RAFT
- Torchvision RAFT docs: docs.pytorch.org/vision/main/auto_examples/others/plot_optical_flow.html
- SEA-RAFT (efficient variant): arxiv.org/html/2405.14793v1
- OpenCV Farneback: docs.opencv.org (standard)
- PyTorch warp forum: discuss.pytorch.org/t/warp-video-frame-from-optical-flow/6013

---

## 5. Stable Video Diffusion (SVD) and AnimateDiff

### Stable Video Diffusion

SVD (Stability AI, 2023) generates 14-25 frames of coherent video from a single image. SVD-XT generates 25 frames at 576x1024. Uses a UNet-based video diffusion model conditioned on the source image.

**Performance on 8GB VRAM:**
- Possible with memory optimization (CPU offloading, UNet chunking, reduced decode chunk size)
- Default inference: ~100s on A100 80GB; ~9 minutes on T4; ~2 minutes on V100
- On RTX 4060 Laptop (8GB): estimated **3-8 minutes per 14-25 frame clip** (UNVERIFIED — scaled from V100 benchmark, accounting for ~20% V100 advantage over RTX 4060 Laptop at this workload)
- **VRAM note:** Cannot co-reside with SDXL Turbo. Must swap models. Model switch overhead: ~10-30s

**Quality:** High temporal coherence within a generated clip. But SVD is a black box — it generates "video" from the source frame using learned video priors (camera motion, object dynamics). The generated motion may look cinematic but will not match audio events or installation arc phases in any meaningful way.

**Verdict:** Not viable for In Ascolto. Too slow (minutes per clip), cannot co-reside with SDXL Turbo, and generated motion is not audio-reactive. SVD is useful for pre-generating atmospheric video loops, not real-time audio-reactive installation.

### AnimateDiff

AnimateDiff (Guo et al., 2023) inserts temporal attention modules into SD-based UNets to enable short animated clips.

**Performance on 8GB VRAM:**
- Technically possible but severely constrained: tiled VAE, sliced attention, reduced context
- Generating 16 frames at 512x768: **15-20 minutes per clip** (Tier 3 — community reports)
- On RTX 3060 (similar class to RTX 4060 Laptop at this workload): ~1 hour per 16 frames
- Cannot run alongside SDXL Turbo — requires full VRAM

**Verdict:** Not viable for In Ascolto. Same generation-speed problem as SVD. The 8GB VRAM tier is brutal for video diffusion models.

### Sources

- SVD HF page: huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt
- SVD Diffusers docs: huggingface.co/docs/diffusers/en/using-diffusers/svd
- Civitai SVD optimization guide: civitai.com/articles/4286/stable-video-diffusion-optimization-low-vram
- AnimateDiff performance docs: github.com/continue-revolution/sd-webui-animatediff/blob/master/docs/performance.md
- AnimateDiff GPU guide: apatero.com/blog/consumer-gpu-video-generation-complete-guide-2025

---

## 6. Other Approaches

### 6a. Temporal Cross-Fade with Perceptual Blur Mask

Not frame interpolation, but a browser-side technique that avoids the "opacity blend" look. Key insight: instead of linearly crossfading opacity, apply a spatially-varying mask based on structural similarity (SSIM). Regions of high structural change get sharp transitions; regions of similarity get smooth blends. Result: the image appears to "melt" and "crystallize" at edges while stable regions stay solid.

**Implementation:** Pure JavaScript / Three.js shader. GPU cost: zero (runs on display GPU, not the ML GPU). Runs at 60fps. Can be combined with RIFE output.

```glsl
// Fragment shader: perceptual cross-fade
// textureA = previous frame, textureB = new frame, t = lerp factor
uniform sampler2D textureA;
uniform sampler2D textureB;
uniform float t;
uniform float blurStrength;  // 0.0 = no blur, 1.0 = heavy softening at seam

void main() {
    vec4 colorA = texture2D(textureA, vUv);
    vec4 colorB = texture2D(textureB, vUv);
    // Simple version: smooth step (feels less mechanical than linear)
    float alpha = smoothstep(0.0, 1.0, t);
    gl_FragColor = mix(colorA, colorB, alpha);
}
```

### 6b. Noise Field Warp (Between-Frame Motion at 60fps)

The existing architecture already includes a Three.js noise field layered over AI frames. This noise field can provide the **illusion of motion** between AI keyframes without any interpolation:

- Simplex/Perlin noise field animated at 60fps
- Displacement: warp UV coordinates of the displayed AI frame using the noise field
- Effect: the AI frame appears to breathe, ripple, shift — organic visual motion without generating new frames
- Audio reactivity at 60fps: RMS modulates displacement amplitude, spectral centroid modulates noise frequency, arc phase changes noise pattern type

This is architecturally the simplest solution and avoids all interpolation complexity. The noise warp is **already planned** in the hybrid architecture. The question is whether it satisfies the "no crossfade" requirement. Technically it does not crossfade — it warps and displaces the displayed frame in real time.

```javascript
// Three.js noise warp shader (runs at 60fps, no GPU ML models)
// displayTexture = current AI keyframe
// noiseScale, noiseSpeed = audio-driven parameters
const warpShader = {
    uniforms: {
        displayTexture: { value: null },
        time: { value: 0.0 },
        noiseScale: { value: 2.0 },    // audio: spectral centroid
        noiseAmp: { value: 0.015 },    // audio: RMS -> 0.005-0.04
        noiseSpeed: { value: 0.3 },    // audio: onset strength
    },
    fragmentShader: `
        uniform sampler2D displayTexture;
        uniform float time, noiseScale, noiseAmp, noiseSpeed;
        varying vec2 vUv;
        // Simplex noise function (include noise library)
        void main() {
            float nx = snoise(vec3(vUv * noiseScale, time * noiseSpeed));
            float ny = snoise(vec3(vUv * noiseScale + 100.0, time * noiseSpeed));
            vec2 displaced = vUv + vec2(nx, ny) * noiseAmp;
            gl_FragColor = texture2D(displayTexture, displaced);
        }
    `
};
```

### 6c. Deforum / Parseq Audio Keyframe Approach

Deforum converts audio amplitude/spectral data into parameter keyframes for batch diffusion generation. The FILM interpolation node is available within Deforum to smooth output.

**How Deforum handles low FPS:** Deforum is a batch processor — it generates frames at diffusion speed, then applies FILM interpolation as a post-process to multiply frame rate. For interactive real-time use, this is not applicable directly. However, the principle — **generate keyframes at diffusion rate, interpolate offline (or near-real-time), display interpolated stream** — is exactly our architecture.

**Deforum audio-reactive parameters relevant to In Ascolto:**
- `strength_schedule`: denoising strength per frame — maps to our audio density
- `seed_behavior = "iter"`: small seed increments per frame = subtle variation without total change
- `noise_schedule`: per-frame noise injection = our 5-10% continuous noise injection finding
- `zoom_schedule`, `translation_schedule`: kinetic camera motion driven by audio — NOT applicable (our frames are static architectural scenes)

**Verdict:** Deforum batch approach is not suitable for real-time installation. But its parameter schema validates our audio-reactive mapping table in `research/realtime-visuals.md`.

---

## 7. Audio Reactivity at Low Generation Rates (~0.3 FPS)

This is the central design challenge: audio events happen at millisecond granularity; AI frames arrive every 3 seconds. How to close this gap?

### Three-Layer Architecture

The solution is to decouple audio reactivity across three time scales:

| Layer | Update rate | Technology | Audio connection | Effect |
|---|---|---|---|---|
| **Layer 1: Warp field** | 60 FPS | Three.js shader (GPU) | RMS, spectral centroid via WebSocket | Organic displacement of displayed frame |
| **Layer 2: Color grade** | 60 FPS | Three.js post-processing | F0, spectral flux via WebSocket | Warm/cool tint, brightness, saturation |
| **Layer 3: AI frame** | ~0.3 FPS | SDXL Turbo + RIFE fill | Arc phase, voice density (slow) | Content and narrative |

Layers 1 and 2 run entirely in the browser at 60fps. They process the WebSocket audio data that already exists in the system (`osc_conductor.py` → WebSocket → browser). The AI frame is the slow-changing substrate that Layers 1 and 2 animate against.

### Modulating Interpolation Speed by Audio

RIFE interpolation generates intermediate frames using a `timestep` parameter (default 0.5 = midpoint). By varying this parameter, you can create **non-uniform temporal spacing**:

- **On audio onset:** generate frames concentrated near t=0 (linger near previous keyframe, then snap to new one)
- **On silence/decay:** generate frames evenly spaced (smooth continuous motion)
- **On peak RMS:** skip intermediate frames (let RIFE generate the full gap quickly, compressing motion)

This creates a subtle sync between audio events and visual rhythm, even at 0.3 FPS generation rate.

```python
import numpy as np

def compute_rife_timesteps(n_frames: int, rms: float, onset: bool) -> list[float]:
    """
    Generate non-uniform RIFE timesteps modulated by audio.
    rms: 0.0-1.0
    onset: True if audio onset detected in this frame window
    Returns: list of timestep values in [0,1]
    """
    if onset:
        # Concentrate frames at end of window (fast snap to new frame)
        t = np.power(np.linspace(0, 1, n_frames + 2)[1:-1], 2.0)
    elif rms > 0.7:
        # High energy: more even spacing (busy visual)
        t = np.linspace(0, 1, n_frames + 2)[1:-1]
    else:
        # Quiet: linger at start (slow drift from previous frame)
        t = np.power(np.linspace(0, 1, n_frames + 2)[1:-1], 0.5)
    return t.tolist()
```

### Color Grading at 60 FPS

The browser already receives audio features via WebSocket. These can drive real-time post-processing at 60fps using Three.js's EffectComposer or raw shader passes:

| Audio Feature | Visual Effect | Range | Implementation |
|---|---|---|---|
| RMS (overall loudness) | Brightness boost | +0 to +0.15 | `gl_FragColor.rgb += rms * 0.15` |
| Spectral centroid | Color temperature | warm (+hue shift) to cool | `mix(warmColor, coolColor, centroid)` |
| Voice density (# active voices) | Saturation | 0.8x to 1.3x | HSL saturation multiply |
| Arc phase | Vignette intensity | 0.0 (ambient) to 0.4 (climax) | Radial gradient blend |
| Silence (t=233s) | Fade to black | 1.0 to 0.0 brightness | `brightness *= (1.0 - silenceT)` |
| Onset strength | Subtle bloom pulse | +0 to +0.1 | Additive brightness spike |

```javascript
// In Three.js render loop (60fps):
function updateVisualGrade(audioData) {
    const { rms, spectralCentroid, density, arcPhase, onsetStrength } = audioData;

    gradeShader.uniforms.brightness.value = 1.0 + rms * 0.15;
    gradeShader.uniforms.colorTemp.value = spectralCentroid;  // 0=warm, 1=cool
    gradeShader.uniforms.saturation.value = 0.8 + density * 0.5;
    gradeShader.uniforms.vignette.value = arcPhase === 'climax' ? 0.4 : 0.15;
    gradeShader.uniforms.bloom.value = onsetStrength * 0.1;

    // Noise warp amplitude (separate shader)
    warpShader.uniforms.noiseAmp.value = 0.005 + rms * 0.035;
    warpShader.uniforms.noiseSpeed.value = 0.1 + onsetStrength * 0.4;
}
```

### What TouchDiffusion and Deforum do at low framerates

From research into the TouchDiffusion and audio-reactive Deforum communities (Tier 3 — derivative.ca community posts):

**TouchDiffusion strategy:** StreamDiffusion generates frames as fast as possible (~5-25 FPS). Between renders, TouchDesigner applies post-processing at 60fps (particle effects, color grading, blending). The AI frame is a "texture input" that updates asynchronously; the 60fps render loop always has a valid texture to display. No interpolation — the visual system is designed to look good at the AI frame rate, augmented by 60fps post-processing.

**Deforum strategy:** Pre-generate all keyframes at diffusion speed. Apply FILM interpolation offline to multiply FPS. Result is a video file, not a live loop. Not interactive. Used for music video production, not installation.

**Key learning for In Ascolto:** The field consensus is that **interpolation is secondary; 60fps post-processing is primary**. The existing Three.js noise field architecture is the right approach. RIFE interpolation is a quality enhancement for when consecutive AI frames are structurally similar, but the noise warp provides continuous motion at all times.

---

## Summary Table: Method Comparison

| Method | VRAM extra | Speed (fill 3s gap) | Quality for AI art | Audio reactive | Recommended use |
|---|---|---|---|---|---|
| **RIFE v4.6** | ~150-300 MB | ~60-100 ms total | Good (with constraints) | Via timestep modulation | Primary interpolation between similar frames |
| **FILM** | ~400-600 MB | ~300-800 ms total | Similar to RIFE | Via timestep | Not recommended (slower, no quality advantage here) |
| **SLERP (pure)** | 0 (VAE shared) | ~200-500 ms for 10 frames | Poor (blurry midpoints) | No | Not standalone |
| **SLERP + partial denoise** | 0 (shared) | ~2-5s for 8 frames | Excellent | No | Prompt-transition morphs only |
| **Farneback flow warp** | 0 (CPU) | Negligible | Poor (tears/holes) | Via flow speed | 60fps browser warp layer only |
| **RAFT + warp** | ~150-400 MB | ~100-300 ms total | Moderate (holes) | Via flow speed | Not recommended (RIFE is better) |
| **Noise field warp (Three.js)** | 0 (display GPU) | Real-time 60fps | N/A (not synthesis) | Full 60fps | Always-on Layer 1 — primary motion |
| **Color grade shader** | 0 (display GPU) | Real-time 60fps | N/A | Full 60fps | Always-on Layer 2 — tone/mood |
| **SVD / AnimateDiff** | Full GPU swap | 3-8 minutes/clip | High (temporal coherence) | No | Not viable for real-time use |

---

## Recommended Architecture for In Ascolto

### Production Architecture

```
SDXL Turbo pipeline (Python, CUDA, 6.58 GB VRAM)
    │
    ├── [every ~3s] new keyframe generated
    │       │
    │       ├── [structural similarity check: SSIM between prev/new keyframe]
    │       │       │
    │       │       ├── [SSIM > 0.7: similar frames] → RIFE interpolation (6 recursive passes = 63 frames)
    │       │       │         RIFE uses ~150-300 MB, runs in ~60-100ms
    │       │       │
    │       │       └── [SSIM < 0.7: prompt change] → SLERP + partial denoise (8 frames, ~2-4s)
    │       │                 OR direct crossfade with noise warp masking change
    │       │
    │       └── push frames to browser via WebSocket (JPEG, ~50 KB/frame)
    │
    ├── [continuous] audio features → WebSocket → browser
    │
Browser (display GPU, no VRAM budget concern)
    ├── Layer 0: AI frame queue (updating at 0.3-24 FPS depending on interpolation)
    ├── Layer 1: Three.js noise warp shader (60fps, audio-driven displacement)
    ├── Layer 2: Color grade shader (60fps, audio-driven tone/saturation/vignette)
    └── Layer 3: RIFE-interpolated frame stream composited over noise field
```

### Implementation Priority Order

1. **Immediate (no RIFE needed):** Noise warp + color grade shaders in Three.js. Provides 60fps visual motion and audio reactivity right now, with no additional dependencies. Most impactful improvement for the least complexity.

2. **Short-term:** RIFE interpolation as a Python module between keyframes. Install `ComfyUI-Frame-Interpolation` or use rife-ncnn-vulkan binary. Wire into the frame generation loop.

3. **On prompt changes only:** SLERP with partial denoising (using already-loaded VAE). Generate 6-8 high-quality transition frames during the 3-second generation slot.

---

## Update: 2026-03-24 — Keyframe Pulse Artifact Research

**Research brief:** Eliminating the "keyframe pulse" in the SDXL Lightning img2img + RIFE 16x pre-rendered pipeline. (dispatched by user — Senior Developer context)

**Exact problem diagnosed:** 191 SDXL Lightning keyframes generated at strength 0.55-0.65. RIFE interpolates 15 frames between each pair (16x). Video plays at 12fps. Every 1.33s a new keyframe introduces fine-detail inconsistencies (ornaments, textures, edges not present in the preceding frame). RIFE faithfully interpolates between these mismatched frames, producing a visible "pulse" at ~1.3s cadence — 18-19 artifacts/minute confirmed by Gemini video analysis. Five prior mitigations failed.

**Constraint:** RTX 4060 Laptop 8 GB VRAM. Pre-rendered pipeline (not real-time). SDXL Lightning (not Turbo — Lightning uses 2-4 fixed steps with specific strength anchors). No crossfade/opacity blend.

---

### Category A: Sources of the Pulse — Root Cause Analysis

The pulse is not a RIFE problem. RIFE is doing exactly what it should: interpolating between two inconsistent source frames. The inconsistency is introduced during SDXL Lightning generation. Three mechanisms cause each new keyframe to reinvent fine details:

**A1. Stochastic denoising noise.** At each generation step, SDXL Lightning samples from a random noise tensor. The noise is different every call. Fine-scale textures (ornamental detail, edge crispness) are determined by high-frequency noise components that vary frame to frame. This is the primary cause.

**A2. SDXL Lightning's distilled sampling.** Lightning uses progressive adversarial distillation — it was trained to jump from noise to image in 2-4 steps using specific CFG=0 settings. At 2-4 steps, each step has very high per-step noise magnitude compared to DDPM. The model "invents" details rather than refining them — there is less accumulation of spatial structure across steps. This makes Lightning more volatile than SDXL Turbo per frame.

**A3. Strength parameter creates detail discontinuities.** At strength 0.55-0.65, SDXL Lightning adds noise up to timestep ~0.55-0.65 of the full noise schedule, then denoises from there. The starting noise tensor is different each call, so the "new" denoised fine details do not match the "old" fine details from the previous frame. This is the exact mechanism that creates the pulse.

---

### Category B: Fixing the Source — More Temporally Consistent Keyframes

**B1. Fixed noise seed with slow walk (HIGHEST PRIORITY — implement first)**

The primary fix for stochastic inconsistency is to use the same or slowly-evolving noise tensor across consecutive keyframe generations. Rather than drawing fresh noise each call, maintain a persistent noise tensor and evolve it gradually.

**Concrete technique — noise offset walk:**
```python
import torch

# Persistent noise state between frames
_noise_state = None
_noise_walk_alpha = 0.05  # how much to evolve noise per frame. Tune: 0.02-0.10

def get_evolved_noise(height, width, channels=4, device="cuda"):
    global _noise_state
    if _noise_state is None:
        _noise_state = torch.randn(1, channels, height // 8, width // 8,
                                    device=device, dtype=torch.float16)
    # Slowly evolve: blend in small amount of fresh noise
    fresh = torch.randn_like(_noise_state)
    _noise_state = (1 - _noise_walk_alpha) * _noise_state + _noise_walk_alpha * fresh
    # Re-normalize to unit variance (SDXL expects unit-variance noise)
    _noise_state = _noise_state / _noise_state.std()
    return _noise_state.clone()

# In generation loop:
latent_noise = get_evolved_noise(512, 512)
output = pipe(
    prompt_embeds=prompt_embeds,
    image=prev_frame,
    strength=0.60,
    latents=latent_noise,  # inject evolved noise
    guidance_scale=0.0,
    num_inference_steps=4,
).images[0]
```

**Why this works:** Consecutive keyframes now start from similar (but slowly drifting) noise tensors. The high-frequency detail components that depend on noise will be similar between frames, reducing the reinvention of fine details. Alpha=0.05 means each frame's noise is ~95% correlated with the previous frame's noise — details change slowly rather than jumping.

**Known issue:** If alpha is too low (<0.02), the noise converges and the image freezes. If too high (>0.15), the pulse returns. A value of 0.04-0.07 is the practical range. This needs empirical tuning over a 30-60 frame test sequence.

**Source:** Tier 3 — Deforum community noise_walk technique; also documented in research on warped noise for temporal consistency (NeurIPS 2024 "Warped Diffusion" paper, arXiv pending verification).

**B2. Fixed seed + gradual seed perturbation (simpler alternative to B1)**

Instead of managing latent noise tensors, simply fix the random seed across keyframes and perturb it slightly. Diffusers uses the seed to initialize the noise sampler.

```python
import torch

_base_seed = 42
_seed_increment = 3  # tune: 1-10. Smaller = more similar consecutive frames.

for frame_idx in range(n_keyframes):
    generator = torch.Generator(device="cuda")
    generator.manual_seed(_base_seed + frame_idx * _seed_increment)
    output = pipe(
        prompt_embeds=prompt_embeds,
        image=prev_frame,
        strength=0.60,
        guidance_scale=0.0,
        num_inference_steps=4,
        generator=generator,
    ).images[0]
```

**Why it differs from B1:** Seed-based control is less principled — the relationship between adjacent seeds is not guaranteed to produce similar noise tensors (hash function internals). A seed difference of 1 might produce very similar noise or very different noise depending on the RNG implementation. B1 (explicit noise walk) gives direct control over the correlation coefficient between consecutive frame noises.

**Source:** Tier 3 — SDXL Lightning img2img community discussion (HuggingFace forum, ByteDance/SDXL-Lightning discussions/8); Deforum `seed_behavior="iter"` documentation.

**B3. ControlNet Tile for structural anchoring**

ControlNet Tile (lllyasviel/control_v11f1e_sd15_tile for SD1.5, but SDXL version exists) takes the previous frame as a tiled structure conditioning input. It forces the new generation to respect the coarse structure of the conditioning image while allowing fine details to change only within the tiled patch boundaries.

**For SDXL:** `controlnet-tile-sdxl-1.0` (available on HuggingFace). Tile ControlNet works by dividing the image into tiles and applying ControlNet conditioning per-tile, anchoring local structure.

**VRAM cost:** ControlNet for SDXL adds ~1.5-2.5 GB. Co-loading with SDXL Lightning (which is lighter than Turbo): total ~6-8 GB. Marginal on 8 GB — requires CPU offloading of ControlNet between calls or aggressive quantization.

**Practical limitation for our case:** Tile ControlNet anchors structure but does not specifically suppress texture/ornament variation. The "pulse" is in fine details smaller than a tile — Tile ControlNet may not address it. TemporalNet2 (previous frame + optical flow as conditioning) is more targeted but at 1.45 GB, already shown not viable.

**Verdict:** MEDIUM-LOW priority. High VRAM cost for uncertain benefit on this specific artifact. Try B1/B2 first.

**Source:** Tier 3 — Deforum + ComfyUI community (learn.thinkdiffusion.com ControlNet deflicker guide; civitai.com/articles/2124).

**B4. SDXL Lightning strength must land on trained anchors**

Critical finding: SDXL Lightning was trained with specific strength values corresponding to its distillation timesteps. The 4-step model has trained anchors at 25%, 50%, 75% of denoising (i.e., strength ≈ 0.25, 0.50, 0.75). The 2-step model: 50%, 100%.

At strength 0.55-0.65, we are between Lightning's trained anchors. This causes the model to operate in an undertrained regime — it has not seen this exact noise level combination during its progressive adversarial training. This could contribute to the pulse by making each generation less deterministic.

**Fix:** Clamp strength to the nearest trained anchor. For 4-step: use exactly 0.50 (conservative, more continuity) or exactly 0.75 (aggressive, more change). Avoid the 0.55-0.65 range.

- Strength 0.50: equivalent to starting denoising from 50% noise — preserves more of the previous frame's structure.
- Strength 0.75: more variation but better trained (less stochastic fringe behavior).

**Source:** Tier 2 — HuggingFace SDXL-Lightning official page (ByteDance/SDXL-Lightning); Sandner.art SDXL Lightning guide.

---

### Category C: Post-RIFE Temporal Filtering (Fixing the Output)

These techniques operate on the final video output — either between keyframes before RIFE, or on the fully interpolated video sequence after RIFE.

**C1. FFmpeg hqdn3d — proven community solution for RIFE flicker (HIGHEST PRIORITY for post-process)**

hqdn3d ("high quality denoiser 3D") is an FFmpeg filter that applies both spatial and temporal denoising. A GitHub issue from April 2025 in the video2x project explicitly documents: **"hqdn3d removes the nasty flicker effect from RIFE interpolation"** (k4yt3x/video2x issue #1364 — Tier 4, community, but directly on-point).

The filter works by averaging each pixel's value with its temporal neighbors (previous and next frames), weighted by a Gaussian kernel. For "pulse" artifacts at 1.3s cadence (= every 16 frames at 12fps), the temporal smoothing radius needs to cover at least 8 frames.

```bash
# Apply hqdn3d temporal denoising to interpolated video
# luma_spatial=0: no spatial blur (preserve sharpness)
# luma_temporal=4: moderate temporal smoothing
# chroma_spatial=0, chroma_temporal=4: same for color channels
ffmpeg -i input_interpolated.mp4 \
  -vf "hqdn3d=luma_spatial=0:luma_temporal=4:chroma_spatial=0:chroma_temporal=4" \
  -c:v libx264 -crf 18 output_deflickered.mp4

# Stronger version for persistent pulse:
ffmpeg -i input_interpolated.mp4 \
  -vf "hqdn3d=luma_spatial=1:luma_temporal=8:chroma_spatial=0.5:chroma_temporal=8" \
  -c:v libx264 -crf 18 output_deflickered.mp4
```

**Tuning guide:**
- `luma_temporal=2-4`: subtle smoothing, preserves micro-detail, may not fully eliminate strong pulse
- `luma_temporal=6-10`: strong temporal smoothing, eliminates most flicker, risk of slight motion blur on fast changes
- `luma_spatial=0`: keep spatial component zero to avoid blurring individual frames (the pulse is temporal, not spatial)
- Adding `unsharp=5:5:0.3:5:5:0` after hqdn3d recovers any softness: `"hqdn3d=...,unsharp=5:5:0.3:5:5:0"`

**Risk:** Temporal smoothing with a large radius can create ghosting (semi-transparent echo of previous frames) if two consecutive frames are structurally very different. For our pipeline (slow-changing architectural scenes), this risk is low — frame-to-frame structural change is minimal.

**Source:** Tier 4 (community) — github.com/k4yt3x/video2x/issues/1364; Tier 2 — FFmpeg official filters documentation (ffmpeg.org/ffmpeg-filters.html).

**C2. FFmpeg atadenoise — faster alternative, temporal-only**

atadenoise is a pure temporal denoiser (no spatial component, no motion compensation). Faster than hqdn3d at equivalent quality for temporal flickering, but less effective for structural artifacts.

```bash
ffmpeg -i input_interpolated.mp4 \
  -vf "atadenoise=0:0:0:0:0.1" \
  -c:v libx264 -crf 18 output_atadenoise.mp4
# Parameters: (s0a, s0b, s1a, s1b, p) — see FFmpeg docs
# p=0.1: temporal averaging strength
```

**Use case:** Quick pass to reduce high-frequency temporal noise (shimmer) before or after hqdn3d. Much faster (no patch matching).

**Source:** Tier 2 — wiki.x266.mov/docs/filtering/denoise (Codec Wiki — authoritative reference).

**C3. Frequency-separated temporal filtering (custom Python — addresses ghosting risk)**

The core problem with naive temporal smoothing is ghosting: blending adjacent frames creates semi-transparent echoes. The solution is to only apply temporal smoothing to low-frequency (coarse structure) components, while high-frequency details come from the center frame only.

This is what "frequency-separated temporal smoothing" attempts. The problem described — "blend only low-freq, keep high-freq from center frame — improved but flashing persists" — tells us the pulse exists at BOTH frequency bands, not just in fine detail.

**Why the previous attempt failed:** If the pulse is visible even in the low-frequency band, it means the keyframe boundaries cause structural-level differences, not just texture-level. This suggests the denoising strength (0.55-0.65) is generating frames with different macrostructure in the areas that flash. This points back to the source fix (B1-B4) being necessary alongside post-processing.

**More aggressive frequency separation with motion compensation:**
```python
import cv2
import numpy as np

def motion_compensated_temporal_smooth(frames: list, window: int = 5,
                                        low_cutoff_sigma: float = 5.0) -> list:
    """
    Apply temporal smoothing only to low-frequency components.
    Motion-compensated: align frames before blending using Farneback optical flow.
    window: number of frames to average (must be odd)
    low_cutoff_sigma: Gaussian sigma for spatial frequency separation
    """
    smoothed = []
    half_w = window // 2

    for i in range(len(frames)):
        center = frames[i].astype(np.float32)

        # Low-frequency component of center frame (Gaussian blur)
        center_low = cv2.GaussianBlur(center, (0, 0), low_cutoff_sigma)
        center_high = center - center_low  # high-freq residual

        # Accumulate low-freq from neighboring frames (motion-compensated)
        low_accum = center_low.copy()
        weight_sum = 1.0

        for j in range(max(0, i - half_w), min(len(frames), i + half_w + 1)):
            if j == i:
                continue
            neighbor = frames[j].astype(np.float32)

            # Compute optical flow to align neighbor with center
            gray_c = cv2.cvtColor(center.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            gray_n = cv2.cvtColor(neighbor.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            flow = cv2.calcOpticalFlowFarneback(gray_n, gray_c, None,
                                                 0.5, 3, 15, 3, 5, 1.2, 0)
            h, w = center.shape[:2]
            grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
            map_x = (grid_x + flow[..., 0]).astype(np.float32)
            map_y = (grid_y + flow[..., 1]).astype(np.float32)
            aligned = cv2.remap(neighbor, map_x, map_y, cv2.INTER_LINEAR)

            # Low-freq of aligned neighbor
            aligned_low = cv2.GaussianBlur(aligned, (0, 0), low_cutoff_sigma)

            # Temporal weight (Gaussian across window)
            w_t = np.exp(-0.5 * ((j - i) / (window / 4)) ** 2)
            low_accum += aligned_low * w_t
            weight_sum += w_t

        # Reconstruct: blended low-freq + center high-freq
        result_low = low_accum / weight_sum
        result = np.clip(result_low + center_high, 0, 255).astype(np.uint8)
        smoothed.append(result)

    return smoothed
```

**Expected improvement over naive frequency separation:** Motion compensation aligns neighboring frames before blending, reducing ghost edges. The pulse at low frequencies will be dampened without ghosting.

**Compute cost:** ~50-200ms per frame (Farneback flow is fast on CPU). For 191 keyframes × 16 RIFE frames = 3056 total frames: ~2.5-10 minutes total. Acceptable for pre-rendered pipeline.

**Source:** Tier 1 — IEEE TCSVT 2007 "Temporal Video Denoising Based on Multihypothesis Motion Compensation" (dl.acm.org/doi/10.1109/TCSVT.2007.903797); Tier 3 — community application of Farneback for video stabilization.

---

### Category D: Alternative Interpolators

**D1. FILM vs RIFE for appearance-change content**

FILM (Google Research, ECCV 2022) uses a **multi-scale feature pyramid** that captures both low-level motion and higher-level semantic structure. For content with large appearance changes (occlusions, objects appearing/disappearing), FILM handles occlusion boundaries more gracefully than RIFE's optical flow.

**For the keyframe pulse specifically:** The pulse happens at AI-generated content boundaries — regions where SDXL invented detail that wasn't in the previous frame. RIFE treats this as "motion of pixels that appear" and creates flow artifacts. FILM's multi-scale architecture may produce less visually jarring artifacts at these boundaries because its feature pyramid includes semantic-level information.

**Practical benchmark (2025 Apatero comparison):**
- Occlusion handling: FILM superior
- Pure motion speed: RIFE 5-10x faster
- For AI art (non-video, slow-changing scenes): RIFE and FILM produce comparable quality; FILM marginally better at appearance-change transitions

**On RTX 4060 Laptop at 512x512:** FILM is ~7x slower than RIFE. For a pre-rendered pipeline with 191 keyframe pairs, FILM 8x would take significantly longer but is still feasible (not real-time). Estimated total render time with FILM vs RIFE: RIFE ~30min, FILM ~3-4 hours for 191 × 16-frame batch. Too slow for frequent iteration but viable for a final production render.

**VRAM:** FILM at 512x512 estimated 400-600 MB (unverified) — stays within budget when SDXL is not co-loaded (sequential pipeline).

**Verdict:** Test FILM on a representative 10-20 keyframe segment. If FILM measurably reduces pulse artifacts compared to RIFE at the same frame regions, accept the longer render time for final production. RIFE for iteration, FILM for final.

**Source:** Tier 2 — apatero.com/blog/rife-vs-film-video-frame-interpolation-comparison-2025; Tier 2 — film-net.github.io (official FILM project page).

**D2. EMA-VFI — appearance-aware interpolation (CVPR 2023)**

EMA-VFI (Extracting Motion and Appearance via Inter-Frame Attention) explicitly separates the motion and appearance estimation tasks using a Swin-based transformer. Unlike RIFE (pure optical flow), EMA-VFI learns to handle cases where appearance differs between frames — making it theoretically better suited for AI-generated frame pairs.

- **Paper:** CVPR 2023, github.com/MCG-NJU/EMA-VFI
- **LAVIB 2024 benchmark:** EMA-VFI and FLAVR perform comparably across most metrics; EMA-VFI slightly better on appearance-change scenarios
- **VRAM:** Similar to RIFE (Swin-Tiny backbone); estimated 300-500 MB at 512x512 (UNVERIFIED)
- **Speed:** Slower than RIFE (attention computation), faster than FILM
- **ComfyUI-Frame-Interpolation:** EMA-VFI is included as a selectable node

**For the pulse artifact:** EMA-VFI's explicit appearance disentanglement may reduce ghost artifacts at keyframe boundaries where new texture appears. The cross-frame attention learns what is "new appearance" vs. "moved pixel" — potentially smoother handling of reinvented details.

**Verdict:** Worth testing in ComfyUI-Frame-Interpolation by switching from RIFE to EMA-VFI on the same keyframe pair showing a pulse artifact. Low effort (model swap, same pipeline). MEDIUM priority.

**Source:** Tier 2 — github.com/MCG-NJU/EMA-VFI (CVPR 2023); Tier 2 — alexandrosstergiou.github.io/datasets/LAVIB (LAVIB benchmark 2024).

**D3. VFIMamba (NeurIPS 2024) — state space model interpolation**

VFIMamba uses a State Space Model (Mamba-based) architecture instead of attention or optical flow for frame interpolation. NeurIPS 2024. Top-ranked on several benchmarks including appearance-change metrics.

- **VRAM:** Estimated lower than attention-based models (Mamba's sequential state is compact)
- **Speed:** Competitive with EMA-VFI per NeurIPS 2024 paper
- **ComfyUI support:** Not yet confirmed in ComfyUI-Frame-Interpolation node set (as of March 2026 — UNVERIFIED)
- **Relevance:** If ComfyUI-Frame-Interpolation adds it, a direct A/B test is trivial

**Source:** Tier 2 — papers.nips.cc/paper_files/paper/2024/file/c1e9db5e1b04322963af91ac0c943568-Paper-Conference.pdf

---

### Category E: Video Diffusion Models for Post-Processing

**E1. CogVideoX-Interpolation — generative keyframe inbetweening**

CogVideoX-Interpolation (github.com/feizc/CogvideX-Interpolation) is a modified CogVideoX pipeline specifically for keyframe interpolation: given a start frame and end frame, generate coherent video between them using the video diffusion model's temporal understanding.

- **Architecture:** Based on CogVideoX-5B with 3D full attention — the model has learned temporal coherence from real video data. Given two keyframes, it generates physically plausible transitions that don't exhibit the "reinvented detail" problem because the model reasons about continuity at a semantic level.
- **VRAM on 8GB:** CogVideoX-1.3B with FP8 quantization fits in 7-8 GB VRAM. The 5B model requires 16+ GB without quantization. For 8GB, must use 1.3B or 5B with aggressive quantization (PytorchAO INT8/FP8).
- **Resolution:** 480x720 maximum at 8GB; 512x512 should be feasible
- **Generation time:** ~4 minutes for a 5-second clip on RTX 4090 without optimization; significantly slower on RTX 4060 (estimate: 15-30 minutes per 5-second segment, UNVERIFIED)
- **Temporal quality:** TRUE temporal consistency — the model generates motion that is physically plausible between the two anchor frames

**For our pipeline:** Replace RIFE between keyframe pairs that exhibit the pulse (detected programmatically by frame-to-frame difference). Use CogVideoX-Interpolation to fill those specific gaps with semantically consistent video. Use RIFE for all other pairs.

**Critical workflow:** This cannot be real-time. It is a post-process step applied to the worst offending keyframe pairs in the pre-rendered sequence.

**Verdict:** PROMISING for eliminating the pulse at the worst transitions. High compute cost (15-30 min/segment) but viable as a selective pass on flagged pairs. Requires testing on actual keyframes. MEDIUM-HIGH priority for investigation.

**Source:** Tier 3 — github.com/feizc/CogvideX-Interpolation; Tier 3 — apatero.com/blog/consumer-gpu-video-generation-complete-guide-2025; Tier 2 — CogVideoX official (github.com/zai-org/CogVideo).

**E2. LTX-Video keyframe interpolation — fastest open video diffusion on 8GB**

LTX-Video (Lightricks) with multi-keyframe conditioning supports start+end frame → generate video. The LTX-2 model runs on 8GB VRAM with FP8 quantization. Generates 3-5 second 480p clips. Significantly faster than CogVideoX on consumer GPUs.

- **VRAM:** 8 GB confirmed with FP8 quantization (nalexand/LTX-2-OPTIMIZED GitHub repo)
- **Speed:** Faster than CogVideoX-5B by significant margin; specific RTX 4060 timing UNVERIFIED
- **Quality vs. CogVideoX:** Lower quality for complex motion; acceptable for slow-changing architectural scenes
- **ComfyUI support:** github.com/Lightricks/ComfyUI-LTXVideo

**Verdict:** May be faster alternative to CogVideoX for the selective pulse-elimination pass. Test both on the same problem keyframe pair. MEDIUM priority.

**Source:** Tier 3 — github.com/Lightricks/LTX-Video; Tier 3 — apatero.com/blog/ltx-2-8gb-vram-optimization-complete-guide-2025.

**E3. Topaz Video AI Starlight Mini — commercial diffusion temporal consistency**

Project Starlight (Topaz Labs, announced Feb 2025) is the first diffusion-based AI model specifically for video enhancement with temporal consistency. It analyzes "hundreds of surrounding frames" for each output frame, making it explicitly designed to eliminate flickering.

- **Mechanism:** Diffusion model that processes video with temporal attention across many frames — not frame-by-frame like GAN upscalers. Full temporal context = no frame-independent artifacts.
- **Claims:** "Virtually no flicker or shifting artifacts between frames" (topazlabs.com/starlight)
- **Starlight Mini VRAM requirement:** 8 GB minimum — RTX 4060 meets the spec
- **Cost:** $299/year (Topaz Video subscription), or free tier (3 clips, <300 frames/week)
- **Input format:** Standard video file (MP4). Process the RIFE-interpolated video through Starlight.

**For our use case:** Feed the full 191-keyframe RIFE-interpolated video (3056 frames, ~4 minutes at 12fps) through Starlight Mini. The model's temporal attention will suppress the 1.3s pulse across the video.

**Risk:** Topaz Starlight is a black box. It may add its own aesthetic — detail hallucination, stylization — that conflicts with our fresco visual language. Test on a representative clip before committing.

**Verdict:** HIGH PRIORITY for testing — the only commercial solution explicitly designed for this exact problem. Free tier allows testing 3 clips. If effective, $299/year is within installation budget.

**Source:** Tier 2 — topazlabs.com/starlight (official); Tier 3 — community.topazlabs.com/t/video-ai-7-0-new-starlight-mini-local-ai-model/90631; Tier 3 — videoproc.com/resource/topaz-project-starlight.htm.

---

### Category F: Latent-Space Source Consistency

**F1. Latent EMA before decoding (pre-generation smoothing)**

Rather than smoothing pixel output, apply temporal smoothing at the latent level before decoding. This is the "latent Gaussian smoothing" from smooth-transitions.md, but targeted specifically at the pulse problem.

```python
# In generation loop:
_latent_history = []  # rolling buffer of last N latents
_EMA_ALPHA = 0.80     # 0.80 = 80% new, 20% history. Tune: 0.70-0.90

def generate_with_latent_ema(pipe, image, prompt_embeds, strength, generator=None):
    global _latent_history

    # Get latents without decoding
    with torch.no_grad():
        # Encode image to latent
        latent = pipe.vae.encode(
            pipe.image_processor.preprocess(image).to(device="cuda", dtype=torch.float16)
        ).latent_dist.sample() * pipe.vae.config.scaling_factor

        # Add noise per strength schedule
        noise = get_evolved_noise(latent.shape[2]*8, latent.shape[3]*8)
        # ... noise scheduling ...

        # Denoise
        denoised_latent = pipe.unet(...)

        # Apply EMA in latent space before decode
        if _latent_history:
            smoothed = _EMA_ALPHA * denoised_latent + (1-_EMA_ALPHA) * _latent_history[-1]
        else:
            smoothed = denoised_latent

        _latent_history.append(smoothed.detach())
        if len(_latent_history) > 3:
            _latent_history.pop(0)

        # Decode smoothed latent
        image_out = pipe.vae.decode(smoothed / pipe.vae.config.scaling_factor).sample

    return image_out
```

**Expected behavior:** At alpha=0.80, each keyframe is 80% the new generation and 20% the previous keyframe's latent. Fine details (which live in high-frequency latent components) will be partially preserved from the previous frame, reducing reinvention.

**Risk:** Latent EMA can cause "grey valley" blurring at the midpoint of large structural changes. At alpha=0.80, the effect is mild. For our slow-changing architectural scenes, this is acceptable.

**Source:** Tier 3 — community StreamDiffusion temporal stability techniques; supported by smooth-transitions.md findings (latent EMA at 0.75-0.85 is acceptable supplementary stabilizer).

**F2. Optical flow-warped noise (research finding)**

A NeurIPS 2024 paper "Warped Diffusion" (arXiv — conference paper, exact ID pending verification) proposes warping the initial noise tensor using optical flow from the previous frame before each diffusion generation. Instead of fresh random noise, the noise for frame N is the noise from frame N-1 warped forward by the optical flow estimated between frame N-2 and N-1.

**Why this helps:** The noise tensor determines what fine details get "invented" by SDXL. If the noise is warped to match the expected motion, the invented details will appear in the right places relative to the previous frame, reducing the appearance of new structure at keyframe boundaries.

**Practical application:**
```python
import cv2
import numpy as np
import torch

def warp_noise_by_flow(prev_noise, prev_frame, curr_frame):
    """Warp previous latent noise by optical flow between frames."""
    # Estimate flow (CPU Farneback for speed)
    gray_prev = cv2.cvtColor(np.array(prev_frame), cv2.COLOR_RGB2GRAY)
    gray_curr = cv2.cvtColor(np.array(curr_frame), cv2.COLOR_RGB2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_prev, gray_curr, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )

    # Downsample flow to latent resolution (÷8)
    h_l, w_l = prev_noise.shape[2], prev_noise.shape[3]
    flow_ds = cv2.resize(flow / 8.0, (w_l, h_l))

    # Warp noise tensor
    grid_x, grid_y = np.meshgrid(np.arange(w_l), np.arange(h_l))
    map_x = (grid_x + flow_ds[..., 0]).astype(np.float32)
    map_y = (grid_y + flow_ds[..., 1]).astype(np.float32)

    warped_channels = []
    noise_np = prev_noise.squeeze(0).cpu().float().numpy()
    for c in range(noise_np.shape[0]):
        warped_c = cv2.remap(noise_np[c], map_x, map_y, cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
        warped_channels.append(warped_c)

    warped = np.stack(warped_channels, axis=0)
    return torch.from_numpy(warped).unsqueeze(0).half().to("cuda")
```

**Source:** Tier 2 — NeurIPS 2024 "Warped Diffusion" (proceedings.neurips.cc/paper_files/paper/2024/file/b736c4b0b38876c9249db9bd900c1a86-Paper-Conference.pdf).

---

### Category G: Community Solutions (Deforum/ComfyUI)

**G1. Deforum cadence + interpolation model (community standard)**

In Deforum animations, the "cadence" setting controls how many RIFE/FILM interpolated frames are generated between each diffusion keyframe. The community standard for reducing pulse artifacts is:

1. Lower the diffusion cadence (generate keyframes less frequently — 1 keyframe per N=4-8 frames rather than every frame). This is exactly our architecture.
2. Set `noise_multiplier=0.0` for img2img (not 0.5 default). The 0.5 default adds extra random noise on top of the latent noise, increasing frame-to-frame variation. Setting to 0.0 removes this source of inconsistency.
3. Use `seed_behavior="iter"` with a small seed increment — equivalent to B2 above.
4. Apply TemporalNet between Deforum keyframes (Deforum ControlNet guide — ThinkDiffusion).

**For our pipeline:** The `noise_multiplier` equivalent in HuggingFace Diffusers is the `noise` parameter in the img2img scheduler. Setting this to 0 or very low may reduce frame-to-frame fine-detail variation.

**Source:** Tier 4 — learn.thinkdiffusion.com/deforum-controlnet; Tier 4 — civitai.com/articles/2124.

**G2. ComfyWarp FlowBlend deflickering**

ComfyWarp v0.4.2 (github.com/Sxela/ComfyWarp) includes a **FlowBlend Deflickering pipeline** that blends the stylized+warped frame with the corresponding raw video frame. Acts like style opacity — 0 = no style, 1 = only stylized.

**For our use case:** Replace "stylized frame" with "SDXL keyframe" and "raw video frame" with "optical-flow-warped previous keyframe." The blend suppresses discontinuities at keyframe boundaries.

This is essentially C3 (motion-compensated temporal smoothing) implemented as a ComfyUI workflow — useful if we're already using ComfyUI for the generation pipeline.

**Source:** Tier 4 — github.com/Sxela/ComfyWarp; runcomfy.com/comfyui-nodes/ComfyWarp.

**G3. RIFE version selection: v4.25 preferred over v4.26 for AI art**

The SmoothVideo Project community forum documents that v4.25 may produce less flickering than v4.26 for non-video content. v4.26 introduced changes that cause resolution-divisibility issues (requires dimensions divisible by 64 vs 32 for v4.25).

**For our pipeline:** If using RIFE HDv3 or v4.x, test v4.25 vs v4.26 on a pulse-affected segment. The difference may be marginal but costs nothing to test.

**Also:** Ensure `ensemble=True` (default in Practical-RIFE) which averages forward and backward flows for more consistent interpolation. `TTA=False` to avoid flickering — TTA (Test Time Augmentation) flips input horizontally and averages, which can introduce subtle brightness inconsistencies at every interpolated frame.

**Source:** Tier 4 — svp-team.com/forum/viewtopic.php?id=6270; github.com/hzwer/Practical-RIFE/issues/112.

---

### Category H: 2025-2026 Academic Papers Directly Relevant

| Paper | Venue | Relevance | Applicability |
|---|---|---|---|
| "Warped Diffusion" | NeurIPS 2024 | Optical-flow noise warping for temporal consistency in video inverse problems | DIRECTLY APPLICABLE — warp noise tensor with Farneback flow (F2 above) |
| "ViBiDSampler: Enhancing Video Interpolation Using Bidirectional Diffusion Sampler" | ICLR 2025 | Bidirectional sampling between two keyframes for off-manifold issue correction | APPLICABLE as replacement for RIFE between keyframe pairs — needs SVD base model |
| "Video Diffusion Models for Keyframe Interpolation" | ICLR 2025 | Full framework for using video diffusion to interpolate between keyframes | APPLICABLE — uses video diffusion (CogVideoX-class) for keyframe inbetweening |
| "DiffuseSlide: Training-Free High Frame Rate Video Generation Diffusion" | arXiv Jun 2025 | Sliding window keyframe conditioning + noise re-injection for coherent interpolation | APPLICABLE — training-free, uses pretrained video diffusion; check model VRAM requirements |
| "Generative Inbetweening: Adapting Image-to-Video Models for Keyframe Interpolation" | NeurIPS 2024 | Dual-directional SVD-based keyframe interpolation with forward-backward consistency | APPLICABLE as high-quality selective replacement for RIFE on pulse-affected pairs (SVD-based) |
| "Enhance-A-Video: Better Generated Video for Free" | arXiv Feb 2025 | Training-free cross-frame intensity in DiT temporal attention; plug-and-play for HunyuanVideo/CogVideoX/LTX-Video | NOT DIRECTLY APPLICABLE — operates during video generation, not post-process of our pipeline |

---

### Priority Recommendation: Ordered Implementation Plan

Based on all research, here is the recommended testing order (lowest effort / highest expected impact first):

| Priority | Technique | Effort | Expected Impact | Where it fits |
|---|---|---|---|---|
| **P0** | **SDXL Lightning strength anchor** (B4) | Trivial — change float | MEDIUM — reduces stochastic fringe | Source fix |
| **P0** | **Evolved noise walk** (B1) | Low — 15 lines Python | HIGH — directly reduces detail reinvention | Source fix |
| **P1** | **FFmpeg hqdn3d post-process** (C1) | Low — 1 CLI command | HIGH — proven community fix for RIFE flicker | Output fix |
| **P1** | **Topaz Starlight Mini free tier test** (E3) | Low — upload 3 clips | HIGH — diffusion temporal consistency purpose-built | Output fix |
| **P2** | **RIFE TTA=False + v4.25 test** (G3) | Trivial — parameter change | LOW-MEDIUM — eliminates TTA brightness variance | Interpolation fix |
| **P2** | **EMA-VFI instead of RIFE** (D2) | Low — model swap in ComfyUI | MEDIUM — appearance-aware interpolation | Interpolation fix |
| **P3** | **Motion-compensated temporal smoothing** (C3) | Medium — Python script | HIGH — eliminates ghosting risk vs naive smoothing | Output fix |
| **P3** | **CogVideoX-Interpolation selective pass** (E1) | High — new model, long render | HIGH — eliminates pulse at worst keyframe pairs | Selective fix |
| **P4** | **LTX-Video keyframe interpolation** (E2) | Medium — ComfyUI node | MEDIUM — faster alternative to CogVideoX | Selective fix |
| **P4** | **Optical flow-warped noise** (F2) | Medium — 50 lines Python | MEDIUM — principled source-noise consistency | Source fix |
| **DEFER** | TemporalNet2 | High — VRAM conflict | MEDIUM — not viable on 8GB without CPU offload | — |

**Recommended first session (2 hours):**
1. Lock strength to 0.50 exactly (change one parameter in generation script) → re-render 20 keyframes → RIFE → inspect
2. Apply `ffmpeg -vf "hqdn3d=0:0:6:6"` to existing artifact video → inspect result immediately
3. Upload 3 clips to Topaz Starlight free tier → inspect temporal consistency

If either hqdn3d or Starlight eliminates the pulse visually, the problem is solved without changing the generation pipeline.

---

### Unresolved Questions

- Does SDXL Lightning's progressive adversarial training produce less temporally consistent output than SDXL Turbo at equivalent strength? (Both were rejected at strength below 0.35 in earlier tests, but Lightning's exact training anchors need verification against our observed strength range.)
- What is the exact VRAM requirement for CogVideoX-1.3B interpolation at 512x512 with FP8 on RTX 4060 Laptop?
- Does FILM produce measurably less pulse than RIFE on the specific keyframe pairs that exhibit the artifact?
- What alpha value for the noise walk (B1) eliminates the pulse without causing convergence at the 191-frame generation scale?

---

### Sources (Update 2026-03-24)

- [hqdn3d RIFE flicker fix — video2x issue #1364](https://github.com/k4yt3x/video2x/issues/1364)
- [FFmpeg Filters Documentation — hqdn3d, atadenoise](https://ffmpeg.org/ffmpeg-filters.html)
- [Codec Wiki — denoise filters](https://wiki.x266.mov/docs/filtering/denoise)
- [ByteDance SDXL-Lightning img2img strength discussion](https://huggingface.co/ByteDance/SDXL-Lightning/discussions/8)
- [Sandner.art — SDXL Lightning img2img guide](https://sandner.art/sdxl-lightning-how-to-use-it-for-the-best-details/)
- [Sandner.art — Temporal Consistency in SD Animations and AnimateDiff](https://sandner.art/temporal-consistency-in-sd-animations-animatediff-techniques/)
- [ThinkDiffusion — Flicker-Free Animations with Deforum and ControlNet](https://learn.thinkdiffusion.com/deforum-controlnet/)
- [Civitai — Mastering Flicker-Free Animations with Deforum and ControlNet](https://civitai.com/articles/2124/mastering-flicker-free-animations-with-deforum-and-controlnet-by-thinkdiffusion)
- [RIFE v4.25 vs v4.26 — Practical-RIFE issue #112](https://github.com/hzwer/Practical-RIFE/issues/112)
- [RIFE TTA flickering — SVP Forum](https://www.svp-team.com/forum/viewtopic.php?id=6270)
- [EMA-VFI — github.com/MCG-NJU/EMA-VFI](https://github.com/MCG-NJU/EMA-VFI)
- [LAVIB Video Interpolation Benchmark 2024](https://alexandrosstergiou.github.io/datasets/LAVIB/)
- [VFIMamba — NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/file/c1e9db5e1b04322963af91ac0c943568-Paper-Conference.pdf)
- [Warped Diffusion — NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/b736c4b0b38876c9249db9bd900c1a86-Paper-Conference.pdf)
- [ViBiDSampler: Bidirectional Diffusion Sampler — ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/098a3d992f0d2128bab619b3c654e1c3-Paper-Conference.pdf)
- [Video Diffusion Models for Keyframe Interpolation — ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/4bbdef62653d8088717640e7660a1ebb-Paper-Conference.pdf)
- [Generative Inbetweening (SVD keyframe interpolation) — NeurIPS 2024](https://svd-keyframe-interpolation.github.io/)
- [DiffuseSlide — arXiv Jun 2025](https://arxiv.org/abs/2506.01454)
- [Enhance-A-Video — arXiv Feb 2025](https://arxiv.org/abs/2502.07508)
- [CogVideoX-Interpolation — github.com/feizc/CogvideX-Interpolation](https://github.com/feizc/CogvideX-Interpolation)
- [LTX-Video 8GB optimization guide — apatero.com](https://apatero.com/blog/ltx-2-8gb-vram-optimization-complete-guide-2025)
- [Topaz Project Starlight — topazlabs.com/starlight](https://www.topazlabs.com/starlight)
- [Topaz Starlight Mini (local) community thread](https://community.topazlabs.com/t/video-ai-7-0-new-starlight-mini-local-ai-model/90631)
- [RIFE vs FILM comparison 2025 — Apatero Blog](https://apatero.com/blog/rife-vs-film-video-frame-interpolation-comparison-2025)
- [ComfyWarp FlowBlend Deflickering — github.com/Sxela/ComfyWarp](https://github.com/Sxela/ComfyWarp)
- [ComfyUI-Frame-Interpolation — github.com/Fannovel16/ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation)
- [Consumer GPU Video Generation Guide 2025 — apatero.com](https://www.apatero.com/blog/consumer-gpu-video-generation-complete-guide-2025)
- [Temporal Video Denoising — IEEE TCSVT 2007](https://dl.acm.org/doi/10.1109/TCSVT.2007.903797)

4. **Optional quality enhancement:** RIFE `ensemble=True`, timestep modulation by audio onset.

### VRAM Budget

```
SDXL Turbo (generation): 6.58 GB    [occupies GPU during 3-4s generation window]
RIFE v4.6 (interpolation): ~0.25 GB [occupies GPU during ~100ms interpolation window]
Max concurrent: 6.58 GB             [RIFE runs AFTER SDXL generation, not concurrent]
Headroom during RIFE: 1.42 GB       [more than sufficient]
```

### Critical Constraints

- RIFE and SDXL Turbo must run **sequentially**, not concurrently (VRAM too tight for both active simultaneously)
- SLERP uses the existing loaded VAE — no additional VRAM cost for model weights
- FILM is not recommended: slower than RIFE with no quality advantage for our AI art use case
- SVD and AnimateDiff are not viable at 8GB VRAM for real-time installation

---

## Unresolved Questions

1. **RIFE VRAM at 512x512 — exact measurement needed.** The ~150-300 MB estimate is derived, not directly benchmarked. Need to measure `torch.cuda.memory_allocated()` before/after RIFE inference at 512x512 on the RTX 4060 Laptop.

2. **RIFE quality on SDXL Turbo output — needs empirical test.** The quality assessment is based on general AI art reports. SDXL Turbo's characteristic style (slightly painterly, not photorealistic) may actually help RIFE — optical flow works better when images have smooth regions and clear edges, which fresco-style renders tend to have.

3. **SLERP blurriness severity — VAE-dependent.** The SDXL VAE fp16-fix may produce cleaner SLERP output than standard VAEs. Needs test.

4. **Optimal RIFE multiplier for 3s gap.** 2x (1 frame) produces clean output; 64x (63 frames) at 24 FPS covers the gap but accumulates artifacts. Empirical test needed: at what multiplier do artifacts become visible in fresco-style content?

---

## Implications for In Ascolto

1. **The noise warp architecture already planned is the most important visual motion layer.** It is free (no extra GPU) and runs at 60fps. Implement this first.

2. **RIFE is the correct interpolation tool** — fast enough (~100ms for a full 3-second gap), lightweight enough (~250MB VRAM), and compatible with sequential operation alongside SDXL Turbo. Install from ComfyUI-Frame-Interpolation or rife-ncnn-vulkan.

3. **SLERP belongs only at prompt transitions.** Use it to generate 6-8 high-quality frames when the narrative arc switches between spaces (throne room → garden). Do not use it for continuous interpolation.

4. **SVD and AnimateDiff are not viable** on this hardware budget. Do not pursue.

5. **Audio reactivity at 60fps is a browser-side problem**, not a GPU-side problem. The WebSocket audio data already flows to the browser; adding color grade and warp shaders is a browser code task (web-designer agent scope), not a Python/CUDA task.

6. **No method eliminates temporal artifacts when AI frames differ greatly.** The cleanest visual result comes from keeping consecutive keyframes structurally similar — which means: lower denoising strength (0.35-0.5), same spatial template, and only color/texture variation between frames. This is already the validated parameter range from experiment results.

---

## Sources Index

| Source | URL |
|---|---|
| RIFE paper (ECCV 2022) | arxiv.org/abs/2011.06294 |
| RIFE official repo | github.com/hzwer/ECCV2022-RIFE |
| FILM paper (ECCV 2022) | arxiv.org/abs/2202.04901 |
| FILM official repo | github.com/google-research/frame-interpolation |
| FILM PyTorch port | github.com/dajes/frame-interpolation-pytorch |
| RIFE vs FILM comparison | apatero.com/blog/rife-vs-film-video-frame-interpolation-comparison-2025 |
| ComfyUI Frame Interpolation | github.com/Fannovel16/ComfyUI-Frame-Interpolation |
| RIFE TensorRT (ComfyUI) | github.com/yuvraj108c/ComfyUI-Rife-Tensorrt |
| rife-ncnn-vulkan | github.com/nihui/rife-ncnn-vulkan |
| Flowframes benchmarks | github.com/n00mkrad/flowframes/blob/main/Benchmarks.md |
| vs-rife benchmarks (RTX 3070 Ti, 4090 TRT) | github.com/HolyWu/vs-rife/discussions/19 |
| RIFE watercolor film paper | dl.acm.org/doi/10.1145/3749893.3749971 |
| HF Cookbook SD interpolation | huggingface.co/learn/cookbook/stable_diffusion_interpolation |
| SLERP PyTorch gist | gist.github.com/Birch-san/230ac46f99ec411ed5907b0a3d728efa |
| sdxl-vae-fp16-fix | huggingface.co/madebyollin/sdxl-vae-fp16-fix |
| stable-diffusion-videos (nateraw) | github.com/nateraw/stable-diffusion-videos |
| SDXL latent space blog | huggingface.co/blog/TimothyAlexisVass/explaining-the-sdxl-latent-space |
| RAFT torchvision | docs.pytorch.org/vision/main/auto_examples/others/plot_optical_flow.html |
| RAFT repo | github.com/princeton-vl/RAFT |
| SVD HF model | huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt |
| SVD Diffusers guide | huggingface.co/docs/diffusers/en/using-diffusers/svd |
| AnimateDiff performance | github.com/continue-revolution/sd-webui-animatediff/blob/master/docs/performance.md |
| TouchDiffusion | github.com/olegchomp/TouchDiffusion, derivative.ca/community-post/asset/touchdiffusion |
| Deforum interpolation | github.com/doublescoop/StableDiffusion_Interpolation |
| PyTorch concurrent CUDA streams | medium.com/swlh/concurrent-inference-e2f438469214 |

---

*Created: 2026-03-12*
*Dispatcher: User (direct request)*
*Priority: IMPROVES — visual layer not blocking current audio work*

---

## Update: 2026-03-13 — RIFE HDv3 Benchmarks + Resolution Test

Full experiment log: `experiments/2026-03-13_rife_benchmarks_and_resolution_test.md`

### RIFE HDv3 Verified at 512x512

Benchmarked on RTX 4060 Laptop (8GB VRAM):
- Model VRAM: ~50 MB weights, ~200 MB peak during inference
- Single interpolation: **~15ms** (67 FPS)
- 8x recursive (7 intermediates): **~105ms** per pair
- 16x recursive (15 intermediates): **~210ms** per pair

**Resolves Unresolved Question #1** (RIFE VRAM at 512x512): confirmed ~200 MB peak, well within 1.4 GB headroom.

**Resolves Unresolved Question #4** (optimal RIFE multiplier): 8x at 512x512 produces clean output on fresco-style frames. 16x also viable. Ghosting only at prompt transition boundaries.

### Architecture Note: HDv3 Midpoint-Only

The bundled RIFE weights are HDv3 (not ECCV2022). HDv3's `inference()` has **no timestep parameter** - it only produces midpoints. Multi-frame interpolation requires recursive bisection. This means the audio-reactive timestep modulation described in Section 7 is **not directly applicable**. Audio reactivity must instead use frame hold/skip patterns (selecting which interpolated frames to display).

**Update to Section 7 code:** The `compute_rife_timesteps()` function is not usable with HDv3. Replace with frame index selection from the fixed set of recursively generated intermediates.

### Resolution Test: 448x800 and 512x912 (9:16 Portrait)

Full SDXL Turbo + RIFE 8x pipeline benchmarked at higher resolutions:

| | 512x512 (ref) | 448x800 | 512x912 |
|---|---|---|---|
| Pixels | 262,144 | 358,400 (1.37x) | 466,944 (1.78x) |
| SDXL gen/frame | ~2.9s | 10.7s (3.7x) | 21.0s (7.2x) |
| SDXL peak VRAM | ~6.6 GB | 8.04 GB | 8.43 GB |
| RIFE 8x per pair | ~115ms | 11,620ms (101x) | 14,646ms (127x) |
| RIFE peak VRAM | ~6.7 GB | 16.30 GB | 19.26 GB |

**Root cause: VRAM thrashing.** The benchmark held SDXL + 41 source frames + RIFE tensors simultaneously, causing 16-19 GB virtual allocations on an 8 GB card. GPU pages to system RAM, producing 100x+ slowdowns. The benchmark is pessimistic - a production sequential pipeline would not hit this.

### Proposed Solutions (from experiment)

1. **Sequential pipeline** - Unload SDXL before RIFE (save frames to disk). Expected 512x912 speed: ~4-6s SDXL + ~200-400ms RIFE per second of video. Model swap overhead: ~15s.
2. **CPU RIFE** - Run RIFE on i7-13700HX CPU while SDXL stays on GPU. Zero VRAM contention. Expected: 500-2000ms per RIFE pair (needs benchmarking).
3. **512x512 + upscale** - Keep proven pipeline, upscale output via Real-ESRGAN or browser CSS. Best VRAM profile. Fresco aesthetic tolerates upscaling.
4. **Dedicated GPU at venue** - 12+ GB card eliminates all VRAM pressure. Both models co-resident at ~7.5 GB.

### Updated VRAM Budget (at 512x512, verified)

```
SDXL Turbo (generation): 6.58 GB    [verified]
RIFE HDv3 (interpolation): ~0.20 GB [verified - lower than estimated 0.25 GB]
Max concurrent: 6.58 GB             [sequential operation confirmed correct]
Headroom during RIFE: 1.40 GB       [verified - more than sufficient]
```

### Updated Unresolved Questions

~~1. RIFE VRAM at 512x512~~ - RESOLVED: ~200 MB peak
2. RIFE quality on SDXL Turbo output - RESOLVED: good quality on fresco-style frames, ghosting only at prompt transitions
3. SLERP blurriness severity - still untested
~~4. Optimal RIFE multiplier~~ - RESOLVED: 8x clean, 16x viable
5. **NEW:** Sequential pipeline performance at 512x912 - estimated 4-6s/frame SDXL + 200-400ms RIFE, needs verification
6. **NEW:** CPU RIFE performance at higher resolutions - estimated 500-2000ms, needs benchmarking
