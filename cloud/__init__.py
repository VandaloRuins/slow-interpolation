"""Optional Modal.com cloud-render path for slow-interpolation.

This subpackage is OPT-IN. It is NOT imported by `slow_interpolation` and
the local CLI (`python -m slow_interpolation.run`) has no dependency on
it. Install with `pip install -e .[cloud]` to enable, then see
`docs/modal.md` for usage.

The directory is named `cloud/` (not `modal/`) to avoid shadowing the
`modal` Python SDK on sys.path. See docs/modal-progress.md.
"""
