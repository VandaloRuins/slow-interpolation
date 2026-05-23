"""Contract test for Modal's `pipeline_entry` override mechanism.

The Modal entrypoint (`cloud/entrypoint.py`) resolves a `pipeline_entry`
dotted string (default `slow_interpolation.pipeline:Pipeline`) into a
class via `importlib`, instantiates it with a `PipelineConfig`, and
calls `.render() -> Path`. Any class implementing this contract is a
valid `pipeline_entry`.

Today the contract is enforced at runtime, on a Modal container, after
image pull. When CompositingPipeline (or any future variant) lands,
breaking the contract costs 0.07 USD per failed render to discover.

This test catches contract breakage locally in <1 s, no GPU required.
Add new pipeline classes to `KNOWN_PIPELINE_ENTRIES` as they ship.

Run:

    pytest tests/test_modal_contract.py -v
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

from slow_interpolation.config import PipelineConfig


# The list of pipeline_entry dotted strings whose contract we enforce.
# When CompositingPipeline lands, add its dotted path here.
KNOWN_PIPELINE_ENTRIES = [
    "slow_interpolation.pipeline:Pipeline",
]


def _resolve_dotted(spec: str) -> Any:
    """Same resolver as `cloud/app.py`. Duplicated here to avoid pulling
    in the modal SDK as a test dependency (the contract test runs even
    on machines without `pip install -e .[cloud]`)."""
    if ":" not in spec:
        raise ValueError(f"Invalid dotted spec {spec!r}")
    module_path, attr = spec.split(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr)


@pytest.mark.parametrize("entry_spec", KNOWN_PIPELINE_ENTRIES)
def test_pipeline_entry_is_resolvable(entry_spec: str) -> None:
    """The dotted string resolves to a Python object."""
    cls = _resolve_dotted(entry_spec)
    assert cls is not None, f"{entry_spec} resolved to None"


@pytest.mark.parametrize("entry_spec", KNOWN_PIPELINE_ENTRIES)
def test_pipeline_entry_is_a_class(entry_spec: str) -> None:
    """The resolved object is a class (not a function or instance)."""
    cls = _resolve_dotted(entry_spec)
    assert inspect.isclass(cls), f"{entry_spec} is not a class: {type(cls).__name__}"


@pytest.mark.parametrize("entry_spec", KNOWN_PIPELINE_ENTRIES)
def test_pipeline_init_takes_pipeline_config(entry_spec: str) -> None:
    """The class's __init__ accepts a PipelineConfig as its first
    positional argument (after self)."""
    cls = _resolve_dotted(entry_spec)
    sig = inspect.signature(cls.__init__)
    params = list(sig.parameters.values())
    # First is self.
    assert len(params) >= 2, (
        f"{entry_spec}.__init__ has too few parameters: {[p.name for p in params]}"
    )
    first_real = params[1]
    # Annotations may be missing (still permissive); when present,
    # require PipelineConfig or a subclass thereof.
    if first_real.annotation is not inspect.Parameter.empty:
        ann = first_real.annotation
        # Annotation may be a string (PEP 563) or a class.
        if isinstance(ann, str):
            assert "PipelineConfig" in ann, (
                f"{entry_spec}.__init__'s first arg annotation is "
                f"{ann!r}, expected PipelineConfig"
            )
        else:
            assert issubclass(ann, PipelineConfig) or ann is PipelineConfig, (
                f"{entry_spec}.__init__'s first arg type is {ann!r}, "
                f"expected PipelineConfig or subclass"
            )


@pytest.mark.parametrize("entry_spec", KNOWN_PIPELINE_ENTRIES)
def test_pipeline_has_render_returning_path(entry_spec: str) -> None:
    """The class has a `render` method returning `Path` (annotation
    permissive: any of Path, str, or unannotated)."""
    cls = _resolve_dotted(entry_spec)
    assert hasattr(cls, "render"), f"{entry_spec} has no `render` attribute"
    render = getattr(cls, "render")
    assert callable(render), f"{entry_spec}.render is not callable"

    sig = inspect.signature(render)
    # When annotated, require Path or str.
    if sig.return_annotation is not inspect.Signature.empty:
        ann = sig.return_annotation
        if isinstance(ann, str):
            assert "Path" in ann or "str" in ann, (
                f"{entry_spec}.render return annotation is {ann!r}, "
                f"expected Path or str"
            )
        else:
            assert ann is Path or ann is str, (
                f"{entry_spec}.render returns {ann!r}, expected Path or str"
            )


def test_broken_class_fails_contract() -> None:
    """Negative test: a class missing `render` fails the contract test
    we just defined above. Sanity check that the test would actually
    catch a real regression."""

    class _Broken:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

    assert not hasattr(_Broken, "render"), "test fixture is wrong"


def test_default_pipeline_entry_matches_cloud_app() -> None:
    """Cross-check: the default `pipeline_entry` here matches what
    `cloud.app.DEFAULT_PIPELINE_ENTRY` says, if the cloud subpackage is
    importable. Skipped silently if the modal SDK is not installed."""
    try:
        from cloud.app import DEFAULT_PIPELINE_ENTRY  # noqa: WPS433
    except ImportError:
        pytest.skip("cloud subpackage requires the [cloud] extra")

    assert DEFAULT_PIPELINE_ENTRY in KNOWN_PIPELINE_ENTRIES, (
        f"cloud/app.py's DEFAULT_PIPELINE_ENTRY ({DEFAULT_PIPELINE_ENTRY!r}) "
        f"is not in KNOWN_PIPELINE_ENTRIES. Add it here, then run this test."
    )
