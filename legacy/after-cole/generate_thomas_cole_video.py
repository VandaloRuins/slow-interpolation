"""
Generate a horizontal Thomas Cole inspired video using SDXL Turbo + LoRA + RIFE.
Output: 1 minute (60s), 8 FPS = 480 frames.
Pipeline:
1. SDXL Turbo img2img loop (60 frames, 16:9 aspect ratio)
2. Real-ESRGAN x4 upscale (optional, can be memory heavy)
3. RIFE 8x interpolation -> 480 frames
"""

import sys
import torchvision.transforms.functional as _F
sys.modules['torchvision.transforms.functional_tensor'] = _F

import time
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from diffusers import AutoPipelineForImage2Image
import os

visuals_dir = Path(__file__).parent
sys.path.insert(0, str(visuals_dir))
sys.path.insert(0, str(visuals_dir / "rife"))

OUTPUT_DIR = visuals_dir / "benchmark_output" / "thomas_cole_video"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = OUTPUT_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)


FPS = 8
TARGET_DURATION = 60  # seconds
TOTAL_FRAMES = TARGET_DURATION * FPS # 480
RIFE_PASSES = 3 # 8x interpolation
GEN_FRAMES = TOTAL_FRAMES // 8 # 60

WIDTH = 1024
HEIGHT = 576

# Thomas Cole narrative phases
PROMPTS = [
    "Morning light, sweeping sublime landscape, distant brick aqueduct ruins in the middle of a vast grass field, towering mountains in the background",
    "Golden hour glowing on ancient brick aqueduct ruins stretching across a lush green grass field, massive mountain peaks looming in the distance",
    "Overcast dramatic clouds, distant ruined brick aqueduct resting in an expansive grass meadow, distant blue mountains fading into the background",
    "Sunset casting long shadows across a vast flat grass field, ancient brick aqueduct ruins in the middle distance, tall mountain range background",
    "Twilight, tranquil grand landscape, distant Roman brick aqueduct ruins sitting softly in a large grass plain, faint majestic mountains in the background"
]

LORA_WEIGHTS_PATH = visuals_dir / "lora_weights" / "thomas_cole.safetensors"

def random_noise_image(w=WIDTH, h=HEIGHT):
    arr = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    return Image.fromarray(arr)

def perlin_noise_blend(img, blend_pct=0.08):
    arr = np.array(img).astype(np.float32)
    noise = np.random.randint(0, 256, arr.shape).astype(np.float32)
    blended = arr * (1 - blend_pct) + noise * blend_pct
    return Image.fromarray(blended.clip(0, 255).astype(np.uint8))

def generate_sdxl_sequence():
    print("Loading SDXL Turbo...")
    pipe = AutoPipelineForImage2Image.from_pretrained(
        "stabilityai/sdxl-turbo",
        torch_dtype=torch.float16,
        variant="fp16"
    ).to("cuda")

    if LORA_WEIGHTS_PATH.exists():
        print(f"Loading LoRA from {LORA_WEIGHTS_PATH}...")
        pipe.load_lora_weights(str(LORA_WEIGHTS_PATH))
        pipe.fuse_lora(lora_scale=0.8)
        pipe.unload_lora_weights()
    else:
        print(f"[WARN] LoRA weights not found at {LORA_WEIGHTS_PATH}, proceeding without LoRA.")

    frames = []
    current_img = random_noise_image(WIDTH, HEIGHT)
    frames_per_prompt = GEN_FRAMES // len(PROMPTS)

    print(f"Generating {GEN_FRAMES} frames...")

    for pi, base_prompt in enumerate(PROMPTS):
        prompt_text = f"by Thomas Cole, {base_prompt}, masterpiece, oil on canvas, sweeping vista, luminous lighting"
        print(f"  Phase {pi+1}: {prompt_text[:60]}...")
        
        for fi in range(frames_per_prompt):
            if fi == 0: strength = 0.8
            elif fi == 1: strength = 0.65
            else: strength = 0.55

            input_img = perlin_noise_blend(current_img, 0.08)
            
            try:
                result = pipe(
                    prompt=prompt_text,
                    image=input_img,
                    strength=strength,
                    num_inference_steps=4,
                    guidance_scale=0.0
                ).images[0]
                current_img = result
            except RuntimeError:
                pass
                
            frames.append(current_img.copy())
            current_img.save(FRAMES_DIR / f"{pi:02d}_{fi:02d}.png")
            
    del pipe
    torch.cuda.empty_cache()
    return frames

def load_rife():
    from train_log.RIFE_HDv3 import Model
    model = Model()
    model.load_model(str(visuals_dir / "rife" / "train_log"), -1)
    model.eval()
    model.device()
    return model

def pil_to_tensor(img):
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).cuda()

def tensor_to_np(t):
    arr = t.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return (arr * 255).astype(np.uint8)

def recursive_interp(model, img0, img1, n_passes):
    if n_passes == 0: return []
    mid = model.inference(img0, img1)
    if n_passes == 1: return [mid]
    left = recursive_interp(model, img0, mid, n_passes - 1)
    right = recursive_interp(model, mid, img1, n_passes - 1)
    return left + [mid] + right

def pad_to_32(tensor):
    n, c, h, w = tensor.shape
    ph = ((h - 1) // 32 + 1) * 32
    pw = ((w - 1) // 32 + 1) * 32
    padded = torch.nn.functional.pad(tensor, (0, pw - w, 0, ph - h))
    return padded, h, w

def rife_interpolate(model, frames_pil, n_passes=RIFE_PASSES):
    result = []
    tensors = [pil_to_tensor(f) for f in frames_pil]
    
    for i in range(len(tensors) - 1):
        padded0, orig_h, orig_w = pad_to_32(tensors[i])
        padded1, _, _ = pad_to_32(tensors[i + 1])
        
        result.append(tensor_to_np(tensors[i]))
        with torch.no_grad():
            interps = recursive_interp(model, padded0, padded1, n_passes)
        for t in interps:
            result.append(tensor_to_np(t[:, :, :orig_h, :orig_w]))
            
        print(f"    RIFE pair {i+1}/{len(tensors)-1}")
        
    result.append(tensor_to_np(tensors[-1]))
    return result

def save_video(frames_np, path, fps=FPS):
    try:
        import imageio.v3 as iio
        iio.imwrite(path, frames_np, fps=fps, codec="libx264", plugin="pyav", output_params=["-crf", "18", "-preset", "slow"])
    except:
        import imageio
        writer = imageio.get_writer(str(path), fps=fps, codec='libx264', quality=8)
        for f in frames_np: writer.append_data(f)
        writer.close()
    print(f"Saved: {path}")

def main():
    print("Starting Thomas Cole Video Generation...")
    src_frames = generate_sdxl_sequence()
    
    print("Interpolating with RIFE...")
    rife_model = load_rife()
    final_frames = rife_interpolate(rife_model, src_frames)
    
    del rife_model
    torch.cuda.empty_cache()
    
    out_path = OUTPUT_DIR / "thomas_cole_1min.mp4"
    save_video(final_frames, out_path, fps=FPS)
    print("Done!")

if __name__ == "__main__":
    main()
