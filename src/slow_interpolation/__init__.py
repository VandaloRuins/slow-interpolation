"""slow-interpolation: diffusion-based slow drift video pipeline.

SDXL Lightning img2img chain with a slowly-evolving noise tensor and SLERP'd
transitions, frequency-separated temporal smoothing, RIFE v4.25 64x linear
interpolation, anchored loop closure. See `docs/pipeline.md` for the spec.
"""

from .config import (
    BorderSuppressionConfig,
    EncodingConfig,
    FrameCounts,
    ModelsConfig,
    PipelineConfig,
    PromptConfig,
    RenderProfile,
    ResolutionConfig,
    RIFEConfig,
    StyleConfig,
    SubjectConfig,
    load_pipeline_config,
)
from .pipeline import Pipeline

__version__ = "0.0.1"

__all__ = [
    "BorderSuppressionConfig",
    "EncodingConfig",
    "FrameCounts",
    "ModelsConfig",
    "Pipeline",
    "PipelineConfig",
    "PromptConfig",
    "RenderProfile",
    "ResolutionConfig",
    "RIFEConfig",
    "StyleConfig",
    "SubjectConfig",
    "load_pipeline_config",
]
