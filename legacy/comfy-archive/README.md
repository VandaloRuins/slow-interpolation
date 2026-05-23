# Comfy archive (not the source of truth)

`interpolate-easy.original.json` is a parallel ComfyUI experiment from earlier in the practice. It uses a completely different stack (SD1.5 + AnimateLCM + IPAdapter weighted batch). It is NOT the technique this repo is built around.

The real `slow-interpolation` technique lives in scripted Python (SDXL Lightning + img2img keyframe loop + temporal smoothing + RIFE v4.25 64x), inherited from the Choire-v2 and After Cole pipelines. See [../choire-v2/](../choire-v2/) and [../after-cole/](../after-cole/).

Kept here for reference only.
