"""
generate_videos.py -- Offline batch generation of seamless-loop MP4 videos
for each curated reading excerpt.

Four-phase sequential pipeline (no VRAM contention):
  Phase A: SDXL Lightning 4-step (TAESD, 768x1344 portrait) -> keyframe PNGs
  Phase B: Real-ESRGAN x2 (576x1024 -> 1152x2048) -> upscaled PNGs
  Phase C: RIFE HDv3 8x (at 1152x2048) -> interpolated frames
  Phase D: H.264 encoding -> final MP4

Usage:
    python generate_videos.py --all                  # Generate all 54 videos
    python generate_videos.py --excerpt E12           # Single excerpt
    python generate_videos.py --section III           # All excerpts in section
    python generate_videos.py --resume                # Skip completed phases
    python generate_videos.py --phase A               # Run only keyframe generation
    python generate_videos.py --phase B               # Run only ESRGAN upscale
    python generate_videos.py --phase C               # Run only RIFE interpolation
    python generate_videos.py --phase D               # Run only video encoding
    python generate_videos.py --no-rife               # Skip RIFE (phases A+B+D)
    python generate_videos.py --no-esrgan             # Skip ESRGAN (576px output)
    python generate_videos.py --no-lora               # Skip LoRA loading
    python generate_videos.py --preview               # Quick: fewer frames per segment
    python generate_videos.py --benchmark             # VRAM test (3 frames, then exit)
    python generate_videos.py --quality 7             # Encoding quality (0-10, default 5)
"""

import sys
import os
os.environ['PYTHONUNBUFFERED'] = '1'

import argparse
import gc
import json
import math
import time
import traceback
from pathlib import Path

import numpy as np

# Add project root to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# RIFE path — v4.25 with arbitrary timestep support (replaces HDv3)
V1_VISUALS = BASE_DIR.parent / "Choire" / "visuals"
RIFE_DIR = V1_VISUALS / "rife_v425" / "train_log"
RIFE_TRAIN_LOG = RIFE_DIR / "train_log"

# Cross-venv path for realesrgan/basicsr (installed in visuals venv)
VISUALS_VENV_PACKAGES = V1_VISUALS / ".venv-sd" / "Lib" / "site-packages"

LORA_CANDIDATES = [
    V1_VISUALS / "lora_weights" / "SDXL CASA DEL SUONO_epoch_4.safetensors",
    V1_VISUALS / "lora_weights" / "SDXL CASA DEL SUONO_epoch_3.safetensors",
]

# ---------------------------------------------------------------------------
# Generation parameters
# ---------------------------------------------------------------------------

GEN_WIDTH = 768                 # Official SDXL training bucket portrait (4:7)
GEN_HEIGHT = 1344               # Native portrait — no off-grid border artifacts
FPS = 24                        # smooth playback with 64x RIFE
LORA_SCALE = 0.35

# SDXL Lightning 4-step inference
NUM_INFERENCE_STEPS = 4         # Lightning trained for 4-step inference
GUIDANCE_SCALE = 1.5            # CFG re-enabled (Turbo was 0.0 — root cause of subject collapse)

# SDXL micro-conditioning — simulate center crop to suppress frame/border bias
CROPS_COORDS_TOP_LEFT = (256, 256)  # non-zero = "zoomed in crop" in training data = no frame
ORIGINAL_SIZE = (1024, 1024)
TARGET_SIZE = (GEN_WIDTH, GEN_HEIGHT)

# Per-segment parameters (segments: A, B, C, return-to-A)
STEADY_FRAMES = 54              # steady-state keyframes per prompt segment
TRANSITION_FRAMES = 6           # SLERP blended keyframes between segments
RETURN_FRAMES = 16              # extended return transition for seamless loop
WARMUP_FRAMES = 3               # discard initial noise-to-image frames

# Denoising — proven values from successful E15 generation (pre-meditative attempt)
STEADY_STRENGTHS = [0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]  # slightly reduced for temporal consistency
NOISE_BLEND_CENTER = 0.08       # proven noise level
NOISE_BLEND_EDGE = 0.08         # uniform (no edge weighting — was causing frame artifacts)
EDGE_NOISE_BORDER = 64          # unused (edge == center)
NOISE_BLEND_TRANSITION = 0.15   # proven transition noise
STRUCTURAL_DECAY_RADIUS = 2     # proven blur radius

# Transition denoising ramp — proven values
TRANSITION_STRENGTHS = [0.65, 0.72, 0.80, 0.80, 0.72, 0.65]
# Noise ramp during transitions: proven peak at 35%
TRANSITION_NOISE_RAMP = [0.15, 0.25, 0.35, 0.35, 0.25, 0.15]

# Return-to-anchor segment
ANCHOR_RETURN_STRENGTH = 0.75

STYLE_PREFIX = "Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, "
STYLE_SUFFIX = ""

RIFE_PASSES = 6     # 2^6 = 64x — meditative pace with linear timestep
EDGE_CROP = 8       # pixels trimmed from each edge after RIFE (removes arch artifacts)

# ESRGAN
ESRGAN_SCALE = 2                # x2 upscale (768x1344 -> 1536x2688)
ESRGAN_TILE = 384
ESRGAN_TILE_PAD = 10
FINAL_WIDTH = GEN_WIDTH * ESRGAN_SCALE      # 1536
FINAL_HEIGHT = GEN_HEIGHT * ESRGAN_SCALE    # 2688

# Encoding
DEFAULT_QUALITY = 5

# Preview mode: smaller segments for fast testing
PREVIEW_STEADY = 4
PREVIEW_TRANSITION = 3

VIDEOS_DIR = BASE_DIR / "videos"
STAGING_DIR = VIDEOS_DIR / "staging"
ARCHIVE_DIR = VIDEOS_DIR / "archive"
MANIFEST_PATH = VIDEOS_DIR / "manifest.json"


def archive_if_exists(video_path):
    """Move existing video to archive/ with timestamp. Never overwrite previous work."""
    if not video_path.exists():
        return
    import shutil
    from datetime import datetime
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{stem}_{ts}{video_path.suffix}"
    dest = ARCHIVE_DIR / archive_name
    shutil.move(str(video_path), str(dest))
    print(f"  Archived previous: {dest.name}")


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

# Temporally coherent noise generator (replaces random pixel noise)
NOISE_LO_W = 128                # low-res noise width (bicubic upscaled to target)
NOISE_LO_H = 224                # low-res noise height (matches 9:16 aspect)
NOISE_SPATIAL_SCALE = 0.02      # simplex spatial frequency
NOISE_TIME_SCALE = 0.08         # simplex temporal evolution — proven value
NOISE_OCTAVES = 3               # proven fractal detail

_noise_gen = None

def _get_noise_gen():
    global _noise_gen
    if _noise_gen is None:
        from opensimplex import OpenSimplex
        _noise_gen = OpenSimplex(seed=42)
    return _noise_gen


def coherent_noise_image(w, h, t):
    """Generate temporally coherent simplex noise at low-res, upscale to target.

    Creates organic flowing blobs like varnish on canvas — large smooth masses
    that drift and merge frame-to-frame, giving RIFE consistent motion to track.
    Uses vectorized opensimplex for speed (~5ms vs ~5s per frame).
    """
    from PIL import Image
    from opensimplex import noise3array

    lo_w, lo_h = NOISE_LO_W, NOISE_LO_H
    # Create coordinate grids
    xs = np.arange(lo_w, dtype=np.float64)
    ys = np.arange(lo_h, dtype=np.float64)

    arr = np.zeros((lo_h, lo_w, 3), dtype=np.float32)
    for octave in range(NOISE_OCTAVES):
        freq = NOISE_SPATIAL_SCALE * (2 ** octave)
        amp = 1.0 / (1.5 ** octave)
        for c in range(3):
            z_val = t * NOISE_TIME_SCALE + c * 100.0
            # noise3array expects (z, y, x) coordinate arrays
            z_arr = np.full(1, z_val)
            noise_2d = noise3array(xs * freq, ys * freq, z_arr)
            # noise3array returns shape (len(z), len(y), len(x)), squeeze z dim
            arr[:, :, c] += amp * noise_2d[0].astype(np.float32)

    # Normalize to 0-255
    arr = ((arr + 1.0) * 0.5 * 255.0).clip(0, 255).astype(np.uint8)
    # Bicubic upscale to target resolution — creates smooth organic blobs
    noise_img = Image.fromarray(arr).resize((w, h), Image.BICUBIC)
    return noise_img


def temporal_noise_blend(img, frame_idx, blend_pct=0.06):
    """Blend image with temporally coherent noise (replaces random pixel noise)."""
    noise_img = coherent_noise_image(img.width, img.height, float(frame_idx))
    arr = np.array(img).astype(np.float32)
    noise = np.array(noise_img).astype(np.float32)
    blended = arr * (1 - blend_pct) + noise * blend_pct
    from PIL import Image as PILImage
    return PILImage.fromarray(blended.clip(0, 255).astype(np.uint8))


def edge_weighted_noise_blend(img, center_pct=NOISE_BLEND_CENTER,
                               edge_pct=NOISE_BLEND_EDGE, border=EDGE_NOISE_BORDER):
    """Blend noise with edge-weighted mask: strong at borders, gentle at center.
    Prevents frame/arch artifacts from locking in at image edges."""
    from PIL import Image as PILImage
    arr = np.array(img).astype(np.float32)
    noise = np.random.randint(0, 256, arr.shape).astype(np.float32)
    h, w = arr.shape[:2]
    # Build gradient mask: 1.0 at edges, 0.0 at center
    mask = np.zeros((h, w, 1), dtype=np.float32)
    for i in range(min(border, h // 2, w // 2)):
        val = 1.0 - (i / border)
        mask[i, :] = np.maximum(mask[i, :], val)
        mask[h - 1 - i, :] = np.maximum(mask[h - 1 - i, :], val)
        mask[:, i] = np.maximum(mask[:, i], val)
        mask[:, w - 1 - i] = np.maximum(mask[:, w - 1 - i], val)
    # Interpolate blend: center_pct at center, edge_pct at edges
    blend = center_pct + mask * (edge_pct - center_pct)
    blended = arr * (1.0 - blend) + noise * blend
    return PILImage.fromarray(blended.clip(0, 255).astype(np.uint8))


def random_noise_image(w=GEN_WIDTH, h=GEN_HEIGHT):
    arr = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    from PIL import Image
    return Image.fromarray(arr)


def structural_decay(img, blur_radius=2):
    if blur_radius <= 0:
        return img
    from PIL import ImageFilter
    return img.filter(ImageFilter.GaussianBlur(radius=blur_radius))


# ---------------------------------------------------------------------------
# Latent edge suppression callback (prevents frame/border artifacts)
# ---------------------------------------------------------------------------

EDGE_SUPPRESS_PX = 3            # latent pixels (~24px in pixel space at 8x VAE scale)
EDGE_SUPPRESS_STRENGTH = 0.3    # blend factor: 0=no effect, 1=full replacement

def edge_suppression_callback(pipe, step, timestep, callback_kwargs):
    """Gently nudge outer latent border toward mirrored interior content.

    Uses mirror-padding from interior (not global mean) as replacement source,
    and a soft blend factor to avoid introducing flat-color border tint.
    Quadratic feather ramp for smoother falloff.
    """
    import torch
    latents = callback_kwargs["latents"]
    B, C, H, W = latents.shape

    ep = EDGE_SUPPRESS_PX
    # Build feathered mask: 1.0 = keep original, 0.0 = maximum suppression zone
    mask = torch.ones(1, 1, H, W, device=latents.device, dtype=latents.dtype)
    for i in range(ep):
        val = (i / max(1, ep)) ** 2  # quadratic: gentler at extreme edge
        mask[:, :, i, :] = torch.minimum(mask[:, :, i, :], torch.tensor(val))
        mask[:, :, H - 1 - i, :] = torch.minimum(mask[:, :, H - 1 - i, :], torch.tensor(val))
        mask[:, :, :, i] = torch.minimum(mask[:, :, :, i], torch.tensor(val))
        mask[:, :, :, W - 1 - i] = torch.minimum(mask[:, :, :, W - 1 - i], torch.tensor(val))

    # Scale by strength: at mask=0 (edge), apply EDGE_SUPPRESS_STRENGTH
    blend_mask = (1.0 - mask) * EDGE_SUPPRESS_STRENGTH

    # Mirror-pad from interior as replacement source (preserves local texture)
    interior = latents.clone()
    interior[:, :, :ep, :] = torch.flip(latents[:, :, ep:2*ep, :], dims=[2])
    interior[:, :, -ep:, :] = torch.flip(latents[:, :, -2*ep:-ep, :], dims=[2])
    interior[:, :, :, :ep] = torch.flip(latents[:, :, :, ep:2*ep], dims=[3])
    interior[:, :, :, -ep:] = torch.flip(latents[:, :, :, -2*ep:-ep], dims=[3])

    callback_kwargs["latents"] = latents * (1.0 - blend_mask) + interior * blend_mask
    return callback_kwargs


# ---------------------------------------------------------------------------
# SDXL embedding helpers
# ---------------------------------------------------------------------------

def slerp_embeddings(embed_a, embed_b, t, dot_threshold=0.9995):
    import torch
    a_flat = embed_a.reshape(-1).float()
    b_flat = embed_b.reshape(-1).float()
    dot = torch.dot(a_flat, b_flat) / (torch.norm(a_flat) * torch.norm(b_flat))
    if abs(dot.item()) > dot_threshold:
        result = (1 - t) * embed_a + t * embed_b
    else:
        theta_0 = torch.acos(dot.clamp(-1, 1))
        sin_theta_0 = torch.sin(theta_0)
        theta_t = theta_0 * t
        s0 = torch.sin(theta_0 - theta_t) / sin_theta_0
        s1 = torch.sin(theta_t) / sin_theta_0
        result = s0 * embed_a + s1 * embed_b
    return result.to(embed_a.dtype)


def encode_prompt(pipe, prompt_text, neg_text=""):
    use_cfg = GUIDANCE_SCALE > 1.0
    (prompt_embeds, neg_embeds,
     pooled_prompt_embeds, neg_pooled) = pipe.encode_prompt(
        prompt=prompt_text, prompt_2=prompt_text,
        device=pipe.device, num_images_per_prompt=1,
        do_classifier_free_guidance=use_cfg,
        negative_prompt=neg_text if neg_text else None,
    )
    if use_cfg:
        return prompt_embeds, pooled_prompt_embeds, neg_embeds, neg_pooled
    return prompt_embeds, pooled_prompt_embeds, None, None


# ---------------------------------------------------------------------------
# RIFE helpers
# ---------------------------------------------------------------------------

def load_rife():
    import torch
    # RIFE v4.25 needs three paths:
    # - repo root (for model.warplayer, model.loss)
    # - train_log parent (for from train_log.RIFE_HDv3)
    # - train_log itself (for internal imports)
    rife_repo = str(RIFE_DIR.parent)  # rife_v425/
    rife_str = str(RIFE_DIR)          # rife_v425/train_log/
    rife_tl_str = str(RIFE_TRAIN_LOG) # rife_v425/train_log/train_log/
    for p in [rife_repo, rife_str, rife_tl_str]:
        if p not in sys.path:
            sys.path.insert(0, p)

    # Torchvision monkeypatch for RIFE
    try:
        import torchvision.transforms.functional as _F
        sys.modules['torchvision.transforms.functional_tensor'] = _F
    except ImportError:
        pass

    from train_log.RIFE_HDv3 import Model
    model = Model()
    model.load_model(str(RIFE_TRAIN_LOG), -1)
    model.eval()
    model.device()
    return model


def pil_to_tensor(img):
    import torch
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).cuda()


def tensor_to_np(t):
    arr = t.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return (arr * 255).astype(np.uint8)


def recursive_interp(model, img0, img1, n_passes):
    """Legacy recursive binary interpolation — kept for reference."""
    if n_passes == 0:
        return []
    mid = model.inference(img0, img1)
    if n_passes == 1:
        return [mid]
    left = recursive_interp(model, img0, mid, n_passes - 1)
    right = recursive_interp(model, mid, img1, n_passes - 1)
    return left + [mid] + right


def linear_interp(model, img0, img1, n_passes, skip_boundary=0, sinusoidal=False):
    """Generate intermediate frames with evenly-spaced or sinusoidal timesteps.

    Eliminates binary-tree midpoint artifact by calling RIFE directly
    at linear (or sinusoidal) t values instead of recursive binary splitting.
    All frames generated from the same (img0, img1) pair — no error cascade.
    Requires RIFE v4.x+ with timestep parameter support.

    skip_boundary: drop first/last N frames per pair (removes boundary deceleration)
    sinusoidal: use cosine spacing (more time in middle, less at boundaries)
    """
    import math
    n_frames = (2 ** n_passes) - 1  # 63 for n_passes=6, 15 for n_passes=4
    frames = []
    for i in range(1, n_frames + 1):
        if sinusoidal:
            # Ease-in-ease-out: spends more time mid-transition, rushes boundaries
            t = 0.5 - 0.5 * math.cos(math.pi * i / (n_frames + 1))
        else:
            t = i / (n_frames + 1)

        # Skip boundary frames (near t=0 and t=1)
        if skip_boundary > 0:
            if i <= skip_boundary or i > n_frames - skip_boundary:
                continue

        frame = model.inference(img0, img1, timestep=t)
        frames.append(frame)
    return frames


def rife_interpolate_frames(model, frame_paths, n_passes=RIFE_PASSES):
    """RIFE interpolation between consecutive frames loaded from disk.

    4 passes = 16x interpolation (15 intermediate frames per pair).
    All frames kept for maximum smoothness (768_smooth recipe).
    """
    import torch
    from PIL import Image

    result = []
    prev_tensor = None
    prev_np = None

    for i, fpath in enumerate(frame_paths):
        img = Image.open(fpath).convert("RGB")
        img_np = np.array(img)
        img_tensor = pil_to_tensor(img)

        if prev_tensor is not None:
            result.append(prev_np)
            with torch.no_grad():
                interps = linear_interp(model, prev_tensor, img_tensor, n_passes)
            for t in interps:
                result.append(tensor_to_np(t))

            if (i) % 20 == 0 or i == 1:
                print(f"    RIFE pair {i}/{len(frame_paths)-1}")

        prev_tensor = img_tensor
        prev_np = img_np

    # Append last frame
    if prev_np is not None:
        result.append(prev_np)

    return result


def crop_edges(img_np, margin=EDGE_CROP):
    """Crop margin pixels from all edges to remove RIFE interpolation artifacts."""
    if margin <= 0:
        return img_np
    return img_np[margin:-margin, margin:-margin].copy()


# ---------------------------------------------------------------------------
# ESRGAN upscale
# ---------------------------------------------------------------------------

def load_esrgan():
    """Load Real-ESRGAN x2 upscaler with cross-venv import."""
    # Pre-import torchvision from main venv so cross-venv .venv-sd doesn't
    # clobber it with an incompatible version (torch op registration conflict)
    import torchvision  # noqa: F401
    import torchvision.transforms.functional as _F
    sys.modules.setdefault('torchvision.transforms.functional_tensor', _F)

    try:
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
    except ImportError:
        pkg_str = str(VISUALS_VENV_PACKAGES)
        if pkg_str not in sys.path:
            sys.path.insert(0, pkg_str)
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=23, num_grow_ch=32, scale=ESRGAN_SCALE)
    upsampler = RealESRGANer(
        scale=ESRGAN_SCALE,
        model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        model=model, tile=ESRGAN_TILE, tile_pad=ESRGAN_TILE_PAD,
        pre_pad=0, half=True, gpu_id=0,
    )
    return upsampler


def upscale_frame(upsampler, img_path, out_path):
    """Upscale a single PNG frame with Real-ESRGAN x2."""
    from PIL import Image
    img = Image.open(img_path).convert("RGB")
    img_np = np.array(img)[:, :, ::-1]  # RGB -> BGR for ESRGAN
    output, _ = upsampler.enhance(img_np, outscale=ESRGAN_SCALE)
    # BGR -> RGB, save as PNG
    output_rgb = output[:, :, ::-1]
    Image.fromarray(output_rgb).save(out_path)


# ---------------------------------------------------------------------------
# Video encoding
# ---------------------------------------------------------------------------

def save_video(frames_np, path, fps=FPS, quality=DEFAULT_QUALITY):
    import imageio
    writer = imageio.get_writer(str(path), fps=fps, codec='libx264',
                                quality=quality, pixelformat='yuv420p')
    for f in frames_np:
        writer.append_data(f)
    writer.close()
    duration = len(frames_np) / fps
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Saved: {path.name} ({len(frames_np)} frames, {duration:.1f}s at {fps}fps, {size_mb:.1f} MB)")
    return {"frames": len(frames_np), "duration_s": round(duration, 1), "size_mb": round(size_mb, 1)}


# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------

def staging_dir(excerpt_id):
    return STAGING_DIR / excerpt_id


def keyframes_dir(excerpt_id):
    return staging_dir(excerpt_id) / "keyframes"


def upscaled_dir(excerpt_id):
    return staging_dir(excerpt_id) / "upscaled"


def count_pngs(directory):
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.png")))


def expected_keyframes(steady_n, trans_n, return_n=None, n_segments=3):
    """Total keyframes (excluding warmup). Last segment uses RETURN_FRAMES."""
    if return_n is None:
        return_n = trans_n  # fallback for phases that don't know about return
    # (n_segments-1) normal transitions + 1 extended return + 1 appended anchor
    return n_segments * steady_n + (n_segments - 1) * trans_n + return_n + 1


# ---------------------------------------------------------------------------
# Phase A: Keyframe Generation
# ---------------------------------------------------------------------------

def phase_a_generate_keyframes(target_ids, steady_n, trans_n, return_n,
                                no_lora=False, resume=False):
    """Generate keyframes for all excerpts using SDXL Turbo with full VAE."""
    import torch
    from PIL import Image
    import prompt_engine

    expected_kf = expected_keyframes(steady_n, trans_n, return_n)

    # Filter completed excerpts if resuming
    if resume:
        remaining = []
        for eid in target_ids:
            kf_dir = keyframes_dir(eid)
            if count_pngs(kf_dir) >= expected_kf:
                print(f"  [SKIP] {eid}: {count_pngs(kf_dir)} keyframes already exist")
            else:
                remaining.append(eid)
        target_ids = remaining

    if not target_ids:
        print("  Phase A: All keyframes already generated.")
        return

    print(f"\n{'='*60}")
    print(f"PHASE A: Keyframe Generation ({len(target_ids)} excerpts)")
    print(f"  Resolution: {GEN_WIDTH}x{GEN_HEIGHT} native portrait | TAESD")
    print(f"  {expected_kf} keyframes/excerpt ({steady_n} steady + {trans_n} transition + {return_n} return + 1 anchor)")
    print(f"{'='*60}\n")

    # Load SDXL base + Lightning 4-step LoRA (replaces Turbo — enables CFG for subject fidelity)
    print("Loading SDXL base (fp16) + Lightning 4-step LoRA + TAESD VAE...")
    from diffusers import StableDiffusionXLImg2ImgPipeline, AutoencoderTiny, EulerDiscreteScheduler

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
    ).to("cuda")

    # Lightning 4-step LoRA — enables 4-step inference with CFG support
    pipe.load_lora_weights(
        "ByteDance/SDXL-Lightning",
        weight_name="sdxl_lightning_4step_lora.safetensors",
    )
    pipe.fuse_lora()
    pipe.unload_lora_weights()
    print("  Lightning 4-step LoRA fused")

    # Scheduler must use trailing timesteps for Lightning
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )

    taesd = AutoencoderTiny.from_pretrained(
        "madebyollin/taesdxl",
        torch_dtype=torch.float16,
    ).to("cuda")
    pipe.vae = taesd
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()
    vram = torch.cuda.memory_allocated() / 1024**3
    print(f"  SDXL + Lightning + TAESD loaded | VRAM: {vram:.2f} GB")

    # Fresco style LoRA (applied on top of Lightning-fused weights)
    if not no_lora:
        lora_path = next((p for p in LORA_CANDIDATES if p.exists()), None)
        if lora_path:
            print(f"Loading fresco LoRA: {lora_path.name}...")
            try:
                pipe.load_lora_weights(str(lora_path))
                pipe.fuse_lora(lora_scale=LORA_SCALE)
                pipe.unload_lora_weights()
                torch.cuda.empty_cache()
                vram = torch.cuda.memory_allocated() / 1024**3
                print(f"  Fresco LoRA fused (scale={LORA_SCALE}) | VRAM: {vram:.2f} GB")
            except Exception as e:
                print(f"  Fresco LoRA failed: {e}")
        else:
            print("  No fresco LoRA weights found")

    # Negative prompt
    metadata = prompt_engine.get_metadata()
    neg_prompt = metadata.get("negative_prompt", "")

    print(f"\nReady. VRAM: {torch.cuda.memory_allocated()/1024**3:.2f} GB")

    t_total = time.perf_counter()
    completed = 0

    for vi, excerpt_id in enumerate(target_ids):
        print(f"\n{'='*40} [{vi+1}/{len(target_ids)}] {excerpt_id} {'='*40}")

        try:
            loop_prompts = prompt_engine.get_loop_prompts(excerpt_id)
            kf_dir = keyframes_dir(excerpt_id)
            kf_dir.mkdir(parents=True, exist_ok=True)

            t0 = time.perf_counter()
            _generate_keyframes_for_excerpt(
                pipe, excerpt_id, loop_prompts, neg_prompt,
                steady_n, trans_n, return_n, kf_dir,
            )
            gen_time = time.perf_counter() - t0
            completed += 1
            print(f"  Keyframes saved to {kf_dir} in {gen_time:.0f}s")

        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            torch.cuda.empty_cache()

    total_time = time.perf_counter() - t_total
    print(f"\nPhase A complete: {completed}/{len(target_ids)} excerpts in {total_time/60:.1f} min")

    # Unload SDXL
    del pipe
    gc.collect()
    torch.cuda.empty_cache()
    print(f"  SDXL unloaded | VRAM: {torch.cuda.memory_allocated()/1024**3:.2f} GB")


def _generate_keyframes_for_excerpt(pipe, excerpt_id, prompts, neg_prompt,
                                     steady_n, trans_n, return_n, output_dir):
    """Generate keyframes for one excerpt and save as numbered PNGs."""
    import torch
    from PIL import Image

    n_segments = len(prompts) - 1
    expected_kf = expected_keyframes(steady_n, trans_n, return_n, n_segments)
    print(f"  Generating ~{expected_kf} keyframes ({n_segments} segments, {return_n}-frame return)")
    for p in prompts:
        print(f"    {p['label']:25s} den={p['denoising']:.3f}  {p['prompt'][:60]}")

    # Pre-encode all prompt embeddings (with negative embeds for CFG)
    all_embeds = []
    for p in prompts:
        full = f"{STYLE_PREFIX}{p['prompt']}{STYLE_SUFFIX}"
        embeds, pooled, neg_embeds, neg_pooled = encode_prompt(pipe, full, neg_prompt)
        all_embeds.append((embeds, pooled, neg_embeds, neg_pooled))

    current_img = random_noise_image()
    anchor_img = None
    frame_idx = 0

    # --- Warmup: establish from noise ---
    print(f"    Warmup ({WARMUP_FRAMES} frames)...", end="", flush=True)
    embeds_cur, pooled_cur, neg_embeds_cur, neg_pooled_cur = all_embeds[0]
    cfg_kwargs = {}
    if neg_embeds_cur is not None:
        cfg_kwargs = {"negative_prompt_embeds": neg_embeds_cur,
                      "negative_pooled_prompt_embeds": neg_pooled_cur}
    for wi in range(WARMUP_FRAMES):
        strength = 0.85 if wi == 0 else 0.75
        input_img = edge_weighted_noise_blend(current_img)
        result = pipe(
            prompt_embeds=embeds_cur, pooled_prompt_embeds=pooled_cur,
            **cfg_kwargs,
            image=input_img, strength=strength,
            num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
            crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
            original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
            callback_on_step_end=edge_suppression_callback,
            callback_on_step_end_tensor_inputs=["latents"],
        ).images[0]
        current_img = result
    print(" done")

    # Save anchor frame (first coherent image = loop target)
    anchor_img = current_img.copy()

    # --- Generate segments ---
    for seg_idx in range(n_segments):
        embeds_cur, pooled_cur, neg_embeds_cur, neg_pooled_cur = all_embeds[seg_idx]
        embeds_next, pooled_next, neg_embeds_next, neg_pooled_next = all_embeds[seg_idx + 1]
        is_return = (seg_idx == n_segments - 1)
        cfg_kwargs = {}
        if neg_embeds_cur is not None:
            cfg_kwargs = {"negative_prompt_embeds": neg_embeds_cur,
                          "negative_pooled_prompt_embeds": neg_pooled_cur}

        p = prompts[seg_idx]
        print(f"    Segment {seg_idx+1}/{n_segments}: {p['label']}")

        # Steady state — cycling strength schedule (re-tuned for Lightning 4-step)
        for fi in range(steady_n):
            strength = STEADY_STRENGTHS[fi % len(STEADY_STRENGTHS)]

            input_img = edge_weighted_noise_blend(
                structural_decay(current_img, STRUCTURAL_DECAY_RADIUS))

            result = pipe(
                prompt_embeds=embeds_cur, pooled_prompt_embeds=pooled_cur,
                **cfg_kwargs,
                image=input_img, strength=strength,
                num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
                crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
                original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
                callback_on_step_end=edge_suppression_callback,
                callback_on_step_end_tensor_inputs=["latents"],
            ).images[0]
            current_img = result

            # Save as PNG
            out_path = output_dir / f"{frame_idx:04d}.png"
            current_img.save(out_path)
            frame_idx += 1

        # Transition to next prompt (or extended return)
        actual_trans_n = return_n if is_return else trans_n
        label = "return" if is_return else "transition"
        print(f"      -> {label} ({actual_trans_n} frames)")

        for ti in range(actual_trans_n):
            t_linear = (ti + 1) / (actual_trans_n + 1)
            t = 3 * t_linear**2 - 2 * t_linear**3  # smoothstep

            blended_embeds = slerp_embeddings(embeds_cur, embeds_next, t)
            blended_pooled = slerp_embeddings(pooled_cur, pooled_next, t)

            if is_return:
                # Progressive convergence back to anchor
                # 3 phases: gentle (0-5), medium (6-11), aggressive (12-15)
                progress = ti / max(1, actual_trans_n - 1)
                if ti < 6:
                    strength = 0.50 + progress * 0.20       # 0.50 -> 0.58
                    pixel_blend = 0.0
                elif ti < 12:
                    strength = 0.60 + (ti - 6) * 0.025      # 0.60 -> 0.75
                    pixel_blend = (ti - 6) / 6.0 * 0.40     # 0% -> 40%
                else:
                    strength = 0.75 + (ti - 12) * 0.0125    # 0.75 -> 0.80
                    pixel_blend = 0.40 + (ti - 12) / max(1, actual_trans_n - 13) * 0.45  # 40% -> 85%

                # Blend pixels toward anchor
                if pixel_blend > 0:
                    arr_cur = np.array(current_img).astype(np.float32)
                    arr_anchor = np.array(anchor_img).astype(np.float32)
                    blended_arr = arr_cur * (1 - pixel_blend) + arr_anchor * pixel_blend
                    current_img = Image.fromarray(blended_arr.clip(0, 255).astype(np.uint8))
            else:
                # Normal inter-segment transition
                if ti < len(TRANSITION_STRENGTHS):
                    strength = TRANSITION_STRENGTHS[ti]
                else:
                    strength = 0.65

            # Noise sweep: ramps up mid-transition to reshape composition
            if not is_return and ti < len(TRANSITION_NOISE_RAMP):
                trans_noise = TRANSITION_NOISE_RAMP[ti]
            else:
                trans_noise = NOISE_BLEND_TRANSITION
            input_img = edge_weighted_noise_blend(
                structural_decay(current_img, STRUCTURAL_DECAY_RADIUS),
                center_pct=trans_noise,
                edge_pct=max(trans_noise, NOISE_BLEND_EDGE))

            # Use current segment's negative embeds for transitions
            result = pipe(
                prompt_embeds=blended_embeds, pooled_prompt_embeds=blended_pooled,
                **cfg_kwargs,
                image=input_img, strength=strength,
                num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
                crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
                original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
                callback_on_step_end=edge_suppression_callback,
                callback_on_step_end_tensor_inputs=["latents"],
            ).images[0]
            current_img = result

            out_path = output_dir / f"{frame_idx:04d}.png"
            current_img.save(out_path)
            frame_idx += 1

    # Append anchor frame as final keyframe for seamless loop closure
    out_path = output_dir / f"{frame_idx:04d}.png"
    anchor_img.save(out_path)
    frame_idx += 1
    print(f"    Appended anchor frame for loop closure")

    print(f"    Saved {frame_idx} keyframes to {output_dir}")


# ---------------------------------------------------------------------------
# Phase A.5: Temporal Keyframe Smoothing
# ---------------------------------------------------------------------------

def temporal_smooth_keyframes(kf_dir, sigma=1.0, window=5, blur_radius=16):
    """Frequency-separated temporal smoothing of keyframes.

    Decomposes each frame into low-frequency (composition) and high-frequency
    (detail). Only the low-frequency component is temporally smoothed — this
    eliminates ghosting/overlay artifacts from naive pixel averaging while
    preserving the meditative pacing benefit.

    Low-freq: color masses, overall layout — safe to blend (already blurry)
    High-freq: brushwork, edges, faces — kept from center frame only (no ghosting)
    """
    from PIL import Image, ImageFilter
    paths = sorted(kf_dir.glob("*.png"))
    if len(paths) < 3:
        return

    print(f"    Temporal smoothing {len(paths)} keyframes (sigma={sigma}, window={window}, blur={blur_radius})...")

    # Load all frames
    images = [np.array(Image.open(p)).astype(np.float32) for p in paths]

    # Decompose each frame into low-freq and high-freq
    lows = []
    highs = []
    for img_arr in images:
        pil_img = Image.fromarray(img_arr.astype(np.uint8))
        low = np.array(pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))).astype(np.float32)
        high = img_arr - low  # detail residual
        lows.append(low)
        highs.append(high)

    # Temporally smooth ONLY the low-frequency component
    smoothed = []
    for i in range(len(images)):
        lo_idx = max(0, i - window)
        hi_idx = min(len(images), i + window + 1)
        weights = []
        frames = []
        for j in range(lo_idx, hi_idx):
            w = np.exp(-0.5 * ((j - i) / sigma) ** 2)
            weights.append(w)
            frames.append(lows[j])
        total_w = sum(weights)
        smoothed_low = sum(w / total_w * f for w, f in zip(weights, frames))

        # Recombine: smoothed low-freq + center frame's high-freq detail
        result = smoothed_low + highs[i]
        smoothed.append(result.clip(0, 255).astype(np.uint8))

    for path, img_arr in zip(paths, smoothed):
        Image.fromarray(img_arr).save(path)
    print(f"    Temporal smoothing complete")


# ---------------------------------------------------------------------------
# Phase B: ESRGAN Upscale
# ---------------------------------------------------------------------------

def phase_b_upscale(target_ids, steady_n, trans_n, return_n, resume=False):
    """Upscale all keyframes with Real-ESRGAN x2."""
    import torch

    expected_kf = expected_keyframes(steady_n, trans_n, return_n)

    # Filter excerpts
    todo = []
    for eid in target_ids:
        kf_dir = keyframes_dir(eid)
        up_dir = upscaled_dir(eid)
        kf_count = count_pngs(kf_dir)
        up_count = count_pngs(up_dir)

        if kf_count < expected_kf:
            print(f"  [SKIP] {eid}: only {kf_count}/{expected_kf} keyframes (run Phase A first)")
            continue
        if resume and up_count >= kf_count:
            print(f"  [SKIP] {eid}: {up_count} upscaled frames already exist")
            continue
        todo.append(eid)

    if not todo:
        print("  Phase B: All upscaling already done.")
        return

    print(f"\n{'='*60}")
    print(f"PHASE B: Real-ESRGAN x{ESRGAN_SCALE} Upscale ({len(todo)} excerpts)")
    print(f"  {GEN_WIDTH}x{GEN_HEIGHT} -> {FINAL_WIDTH}x{FINAL_HEIGHT}")
    print(f"{'='*60}\n")

    print(f"Loading Real-ESRGAN x{ESRGAN_SCALE}...")
    upsampler = load_esrgan()
    vram = torch.cuda.memory_allocated() / 1024**3
    print(f"  ESRGAN loaded | VRAM: {vram:.2f} GB")

    t_total = time.perf_counter()
    completed = 0

    for vi, eid in enumerate(todo):
        print(f"\n  [{vi+1}/{len(todo)}] {eid}")
        kf_dir = keyframes_dir(eid)
        up_dir = upscaled_dir(eid)
        up_dir.mkdir(parents=True, exist_ok=True)

        kf_files = sorted(kf_dir.glob("*.png"))
        t0 = time.perf_counter()

        for i, kf_path in enumerate(kf_files):
            out_path = up_dir / kf_path.name
            if resume and out_path.exists():
                continue
            upscale_frame(upsampler, kf_path, out_path)
            if (i + 1) % 20 == 0 or i == 0:
                print(f"    Upscaled {i+1}/{len(kf_files)}")

        elapsed = time.perf_counter() - t0
        print(f"    Done: {len(kf_files)} frames in {elapsed:.0f}s ({elapsed/len(kf_files)*1000:.0f}ms/frame)")
        completed += 1

    total_time = time.perf_counter() - t_total
    print(f"\nPhase B complete: {completed}/{len(todo)} excerpts in {total_time/60:.1f} min")

    # Unload ESRGAN
    del upsampler
    gc.collect()
    torch.cuda.empty_cache()
    print(f"  ESRGAN unloaded | VRAM: {torch.cuda.memory_allocated()/1024**3:.2f} GB")


# ---------------------------------------------------------------------------
# Phase C: RIFE Interpolation
# ---------------------------------------------------------------------------

def phase_c_interpolate(target_ids, steady_n, trans_n, return_n,
                         use_esrgan=True, resume=False, quality=DEFAULT_QUALITY):
    """RIFE 8x interpolation on upscaled (or raw) keyframes, encode to MP4."""
    import torch

    expected_kf = expected_keyframes(steady_n, trans_n, return_n)
    source_label = "upscaled" if use_esrgan else "keyframes"

    # Filter excerpts
    todo = []
    for eid in target_ids:
        src_dir = upscaled_dir(eid) if use_esrgan else keyframes_dir(eid)
        src_count = count_pngs(src_dir)
        output_mp4 = VIDEOS_DIR / f"{eid}.mp4"

        if src_count < expected_kf:
            print(f"  [SKIP] {eid}: only {src_count}/{expected_kf} {source_label} frames")
            continue
        if resume and output_mp4.exists():
            print(f"  [SKIP] {eid}: {output_mp4.name} already exists")
            continue
        todo.append(eid)

    if not todo:
        print("  Phase C+D: All videos already generated.")
        return

    src_w = FINAL_WIDTH if use_esrgan else GEN_WIDTH
    src_h = FINAL_HEIGHT if use_esrgan else GEN_HEIGHT

    print(f"\n{'='*60}")
    print(f"PHASE C+D: RIFE {2**RIFE_PASSES}x Interpolation + Encoding ({len(todo)} excerpts)")
    print(f"  Frame size: {src_w}x{src_h} | Source: {source_label} | Quality: {quality}")
    print(f"{'='*60}\n")

    print("Loading RIFE HDv3...")
    rife_model = load_rife()
    vram = torch.cuda.memory_allocated() / 1024**3
    print(f"  RIFE loaded | VRAM: {vram:.2f} GB")

    t_total = time.perf_counter()
    completed = 0
    manifest = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for vi, eid in enumerate(todo):
        print(f"\n  [{vi+1}/{len(todo)}] {eid}")
        src_dir = upscaled_dir(eid) if use_esrgan else keyframes_dir(eid)
        frame_paths = sorted(src_dir.glob("*.png"))

        t0 = time.perf_counter()

        # RIFE interpolation — stream pair-by-pair to video encoder (constant RAM)
        print(f"    RIFE {2**RIFE_PASSES}x on {len(frame_paths)} frames (streaming)...")
        import imageio
        from PIL import Image
        output_path = VIDEOS_DIR / f"{eid}.mp4"
        archive_if_exists(output_path)
        writer = imageio.get_writer(str(output_path), fps=FPS, codec='libx264',
                                     quality=quality, pixelformat='yuv420p')
        frame_count = 0
        prev_tensor = None
        prev_np = None
        first_np = None

        for i, fpath in enumerate(frame_paths):
            img = Image.open(fpath).convert("RGB")
            img_np = np.array(img)
            img_tensor = pil_to_tensor(img)

            if i == 0:
                first_np = img_np.copy()

            if prev_tensor is not None:
                # Write previous keyframe
                cropped = crop_edges(prev_np) if EDGE_CROP > 0 else prev_np
                writer.append_data(cropped)
                frame_count += 1
                # RIFE interpolate and write intermediate frames
                with torch.no_grad():
                    interps = linear_interp(rife_model, prev_tensor, img_tensor, RIFE_PASSES)
                for t in interps:
                    f = tensor_to_np(t)
                    cropped = crop_edges(f) if EDGE_CROP > 0 else f
                    writer.append_data(cropped)
                    frame_count += 1

                if (i) % 20 == 0 or i == 1:
                    print(f"    RIFE pair {i}/{len(frame_paths)-1}")

            prev_tensor = img_tensor
            prev_np = img_np

        # Write last keyframe
        if prev_np is not None:
            cropped = crop_edges(prev_np) if EDGE_CROP > 0 else prev_np
            writer.append_data(cropped)
            frame_count += 1

        rife_time = time.perf_counter() - t0
        print(f"    RIFE: {frame_count} frames in {rife_time:.0f}s")

        # RIFE wrap-around for seamless loop
        last_tensor = pil_to_tensor(Image.fromarray(prev_np))
        first_tensor = pil_to_tensor(Image.fromarray(first_np))
        with torch.no_grad():
            wrap_interps = linear_interp(rife_model, last_tensor, first_tensor, RIFE_PASSES)
        wrap_count = 0
        for i, t in enumerate(wrap_interps):
            if i == len(wrap_interps) - 1:
                break  # skip last (identical to first frame)
            f = tensor_to_np(t)
            cropped = crop_edges(f) if EDGE_CROP > 0 else f
            writer.append_data(cropped)
            frame_count += 1
            wrap_count += 1
        print(f"    Loop closure: +{wrap_count} wrap-around frames")
        del wrap_interps, prev_tensor, prev_np, first_np
        gc.collect()

        writer.close()
        duration = frame_count / FPS
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Saved: {output_path.name} ({frame_count} frames, {duration:.1f}s at {FPS}fps, {size_mb:.1f} MB)")

        crop_w = src_w - 2 * EDGE_CROP
        crop_h = src_h - 2 * EDGE_CROP
        meta = {
            "frames": frame_count, "duration_s": round(duration, 1),
            "size_mb": round(size_mb, 1), "excerpt_id": eid,
            "resolution": f"{crop_w}x{crop_h}",
            "pipeline": "taesd+esrgan+rife" if use_esrgan else "taesd+rife",
            "generation_time_s": round(time.perf_counter() - t0, 1),
        }
        manifest[eid] = meta
        completed += 1

        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    total_time = time.perf_counter() - t_total
    print(f"\nPhase C+D complete: {completed}/{len(todo)} videos in {total_time/60:.1f} min")

    del rife_model
    gc.collect()
    torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Phase D: Encode only (keyframes without RIFE)
# ---------------------------------------------------------------------------

def phase_d_encode_only(target_ids, steady_n, trans_n, return_n,
                         use_esrgan=True, resume=False, quality=DEFAULT_QUALITY):
    """Encode keyframes directly to MP4 without RIFE (for --no-rife mode)."""
    from PIL import Image

    expected_kf = expected_keyframes(steady_n, trans_n, return_n)
    source_label = "upscaled" if use_esrgan else "keyframes"

    todo = []
    for eid in target_ids:
        src_dir = upscaled_dir(eid) if use_esrgan else keyframes_dir(eid)
        src_count = count_pngs(src_dir)
        output_mp4 = VIDEOS_DIR / f"{eid}.mp4"

        if src_count < expected_kf:
            print(f"  [SKIP] {eid}: only {src_count}/{expected_kf} {source_label} frames")
            continue
        if resume and output_mp4.exists():
            print(f"  [SKIP] {eid}: {output_mp4.name} already exists")
            continue
        todo.append(eid)

    if not todo:
        print("  Phase D: All videos already encoded.")
        return

    print(f"\n{'='*60}")
    print(f"PHASE D: Direct Encoding ({len(todo)} excerpts, no RIFE) | Quality: {quality}")
    print(f"{'='*60}\n")

    manifest = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    src_w = FINAL_WIDTH if use_esrgan else GEN_WIDTH
    src_h = FINAL_HEIGHT if use_esrgan else GEN_HEIGHT

    for vi, eid in enumerate(todo):
        print(f"  [{vi+1}/{len(todo)}] {eid}")
        src_dir = upscaled_dir(eid) if use_esrgan else keyframes_dir(eid)
        frame_paths = sorted(src_dir.glob("*.png"))

        frames_np = [np.array(Image.open(p).convert("RGB")) for p in frame_paths]
        output_path = VIDEOS_DIR / f"{eid}.mp4"
        archive_if_exists(output_path)
        meta = save_video(frames_np, output_path, FPS, quality=quality)
        meta["excerpt_id"] = eid
        meta["resolution"] = f"{src_w}x{src_h}"
        meta["pipeline"] = "keyframes_only"
        manifest[eid] = meta

        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nPhase D complete: {len(todo)} videos encoded.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import torch

    parser = argparse.ArgumentParser(description="Generate seamless-loop videos for reading excerpts")
    parser.add_argument("--all", action="store_true", help="Generate all 54 excerpts")
    parser.add_argument("--excerpt", action="append", default=[], help="Specific excerpt ID(s)")
    parser.add_argument("--section", type=str, help="Generate all excerpts in section (I-VII)")
    parser.add_argument("--resume", action="store_true", help="Skip completed phases/excerpts")
    parser.add_argument("--phase", type=str, choices=["A", "B", "C", "D"],
                        help="Run only a specific phase")
    parser.add_argument("--no-rife", action="store_true", help="Skip RIFE interpolation")
    parser.add_argument("--no-esrgan", action="store_true", help="Skip ESRGAN upscale")
    parser.add_argument("--no-lora", action="store_true", help="Skip LoRA loading")
    parser.add_argument("--preview", action="store_true", help="Quick preview mode (fewer frames)")
    parser.add_argument("--benchmark", action="store_true",
                        help="VRAM benchmark: generate 3 test frames and exit")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY,
                        help=f"Encoding quality 0-10 (default {DEFAULT_QUALITY})")
    args = parser.parse_args()

    print("=" * 60)
    print("TUTTI I RE IN ASCOLTO -- Video Generation")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Pipeline: {GEN_WIDTH}x{GEN_HEIGHT} TAESD"
          f"{'' if args.no_esrgan else f' -> ESRGAN x{ESRGAN_SCALE} -> {FINAL_WIDTH}x{FINAL_HEIGHT}'}"
          f"{'' if args.no_rife else f' -> RIFE {2**RIFE_PASSES}x'}")
    print(f"Output: {VIDEOS_DIR}")
    print("=" * 60)

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    # --- Benchmark mode ---
    if args.benchmark:
        print(f"\nBenchmark: generating 3 test frames at {GEN_WIDTH}x{GEN_HEIGHT}...")
        from diffusers import AutoPipelineForImage2Image, AutoencoderTiny
        from diffusers import StableDiffusionXLImg2ImgPipeline, EulerDiscreteScheduler
        pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0",
            torch_dtype=torch.float16, variant="fp16",
        ).to("cuda")
        pipe.load_lora_weights("ByteDance/SDXL-Lightning",
                               weight_name="sdxl_lightning_4step_lora.safetensors")
        pipe.fuse_lora()
        pipe.unload_lora_weights()
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing")
        pipe.vae = AutoencoderTiny.from_pretrained(
            "madebyollin/taesdxl", torch_dtype=torch.float16
        ).to("cuda")
        pipe.safety_checker = None
        pipe.unet.to(memory_format=torch.channels_last)

        img = random_noise_image()
        for i in range(3):
            result = pipe(
                prompt="test benchmark frame, warm ochre fresco",
                image=img, strength=0.75,
                num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
            ).images[0]
            img = result

        peak_gb = torch.cuda.max_memory_allocated() / 1024**3
        current_gb = torch.cuda.memory_allocated() / 1024**3
        print(f"\n  Resolution: {GEN_WIDTH}x{GEN_HEIGHT}")
        print(f"  Current VRAM: {current_gb:.2f} GB")
        print(f"  Peak VRAM:    {peak_gb:.2f} GB")
        print(f"  Headroom:     {8.0 - peak_gb:.2f} GB")
        if peak_gb > 7.5:
            print("  WARNING: Peak VRAM > 7.5 GB -- OOM risk during batch generation!")
        else:
            print("  OK: Safe for batch generation.")
        del pipe
        torch.cuda.empty_cache()
        return

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Determine frame counts
    steady_n = PREVIEW_STEADY if args.preview else STEADY_FRAMES
    trans_n = PREVIEW_TRANSITION if args.preview else TRANSITION_FRAMES
    return_n = PREVIEW_TRANSITION if args.preview else RETURN_FRAMES
    use_esrgan = not args.no_esrgan
    use_rife = not args.no_rife

    # Load excerpt list
    import prompt_engine
    excerpts_path = BASE_DIR / "text" / "curated_excerpts.json"
    with open(excerpts_path, "r", encoding="utf-8") as f:
        all_excerpts = json.load(f)["excerpts"]

    # Filter excerpts
    if args.all:
        target_ids = [e["id"] for e in all_excerpts]
    elif args.section:
        target_ids = []
        for e in all_excerpts:
            sec = prompt_engine.get_section_for_passage(e["passage_index"])
            if sec == args.section:
                target_ids.append(e["id"])
    elif args.excerpt:
        target_ids = args.excerpt
    else:
        print("Specify --all, --excerpt E12, or --section III")
        sys.exit(1)

    kf_per_video = expected_keyframes(steady_n, trans_n, return_n)

    print(f"\nTarget: {len(target_ids)} excerpts, {kf_per_video} keyframes each")
    if args.phase:
        print(f"Running phase {args.phase} only")
    print()

    t_total = time.perf_counter()

    # Run phases
    if args.phase:
        # Single phase mode
        if args.phase == "A":
            phase_a_generate_keyframes(target_ids, steady_n, trans_n, return_n,
                                        no_lora=args.no_lora, resume=args.resume)
            # Temporal smoothing: reduce keyframe-to-keyframe detail pops before RIFE
            for eid in target_ids:
                temporal_smooth_keyframes(keyframes_dir(eid))
        elif args.phase == "B":
            if args.no_esrgan:
                print("Phase B skipped (--no-esrgan)")
            else:
                phase_b_upscale(target_ids, steady_n, trans_n, return_n,
                                 resume=args.resume)
        elif args.phase == "C":
            if use_rife:
                phase_c_interpolate(target_ids, steady_n, trans_n, return_n,
                                     use_esrgan=use_esrgan, resume=args.resume,
                                     quality=args.quality)
            else:
                phase_d_encode_only(target_ids, steady_n, trans_n, return_n,
                                     use_esrgan=use_esrgan, resume=args.resume,
                                     quality=args.quality)
        elif args.phase == "D":
            phase_d_encode_only(target_ids, steady_n, trans_n, return_n,
                                 use_esrgan=use_esrgan, resume=args.resume,
                                 quality=args.quality)
    else:
        # Full pipeline
        phase_a_generate_keyframes(target_ids, steady_n, trans_n, return_n,
                                    no_lora=args.no_lora, resume=args.resume)

        # Temporal smoothing: reduce keyframe-to-keyframe detail pops before RIFE
        for eid in target_ids:
            temporal_smooth_keyframes(keyframes_dir(eid))

        if use_esrgan:
            phase_b_upscale(target_ids, steady_n, trans_n, return_n,
                             resume=args.resume)

        if use_rife:
            phase_c_interpolate(target_ids, steady_n, trans_n, return_n,
                                 use_esrgan=use_esrgan, resume=args.resume,
                                 quality=args.quality)
        else:
            phase_d_encode_only(target_ids, steady_n, trans_n, return_n,
                                 use_esrgan=use_esrgan, resume=args.resume,
                                 quality=args.quality)

    # Summary
    total_time = time.perf_counter() - t_total
    total_size = sum(
        f.stat().st_size for f in VIDEOS_DIR.glob("*.mp4")
    ) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"COMPLETE in {total_time/60:.1f} minutes")
    print(f"  Videos: {len(list(VIDEOS_DIR.glob('*.mp4')))} MP4s, {total_size:.0f} MB total")
    print(f"  Staging: {STAGING_DIR}")
    print(f"  Manifest: {MANIFEST_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
