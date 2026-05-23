# HuggingFace model gate-status drift

Date: 2026-05-19.
Scope: HuggingFace Hub model access policies can change between a model's
release and the date you actually try to download it. A model that was
unauthenticated-accessible at training-time research can become 401-gated
months or years later. Capture so future agents do not waste an iteration
diagnosing "why is this download failing".

## The case that surfaced this

**FLUX.1-schnell** (`black-forest-labs/FLUX.1-schnell`).

- Original release (2024-08): Apache 2.0 licensed, ungated on HuggingFace
  Hub. Anonymous `from_pretrained` downloads worked without a token.
- Status as of 2026-05-19: still Apache 2.0 by license file, but
  Hub-level access is GATED. Anonymous downloads return
  `401 Client Error`, `GatedRepoError`. Token required.

Discovered in [`../../cloud/validate_backbone.py`](../../cloud/validate_backbone.py) cold-run on
2026-05-18 + 2026-05-19. The harness was written under the assumption
schnell was open (matching the upstream license); the FLUX backbone
section initially scoped HF-token forwarding to `flux_dev` only.
Schnell hit the gate on first call.

Verbatim error:

```
huggingface_hub.errors.GatedRepoError: 401 Client Error.
Cannot access gated repo for url
https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/model_index.json.
Access to model black-forest-labs/FLUX.1-schnell is restricted. You
must have access to it and be authenticated to access it. Please log in.
```

## Implications

1. **Code that hardcodes "this model is open" as a runtime assumption
   will silently rot** as HuggingFace and model authors change access
   policies. Patterns like "we use schnell because it does not need
   auth" become incorrect without code changes.

2. **The model's stated license is not a proxy for Hub access state.**
   Apache 2.0 by license text + gated by Hub policy is a real
   combination. Some model authors gate to track usage even when
   they grant broad commercial rights.

3. **Token-requirement decisions should be runtime-data-driven**,
   not literal-string-pinned in code. The
   `cloud/validate_backbone.py` fix is the right pattern: forward an
   HF token whenever the backbone is FLUX (any FLUX variant), since
   the Hub may gate any of them at any time.

## Recommended defensive pattern

For any code that downloads a HuggingFace model:

1. Assume a token may be required. Read it from environment or the
   `huggingface-cli login` cache file
   (`~/.cache/huggingface/token`) at runtime.
2. Forward it to the download context only if available. If absent
   and the model is unexpectedly gated, fail with a clear error
   message that tells the user how to authenticate.
3. Do NOT hardcode "this model is open" in code paths or in comments
   without a "last verified" date.

Reference helper: `_read_local_hf_token()` in
[`../../cloud/validate_backbone.py`](../../cloud/validate_backbone.py).
Reads env vars `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`,
`HUGGINGFACE_HUB_TOKEN` in order, then falls back to the cache file.
Returns `None` if no token is found; callers decide whether that is
fatal.

## What to re-check if a Hub access error surfaces unexpectedly

1. Is the user's `huggingface-cli login` token valid? `huggingface-cli whoami`.
2. Has the user accepted the model's specific license? Some gates
   require per-model license acceptance even with a valid token.
3. Has the model been renamed, deleted, or moved to a private org?
4. Is the Hub itself returning 5xx (HF outage, not gating)?

## Cases tracked so far

| Model | Origin status | Status as of | Token required as of |
|---|---|---|---|
| `black-forest-labs/FLUX.1-schnell` | Apache 2.0 ungated (2024) | 2026-05-19 | Yes |
| `black-forest-labs/FLUX.1-dev` | Custom license, gated from launch (2024) | 2026-05-19 | Yes |
| `stabilityai/stable-diffusion-xl-base-1.0` | OpenRAIL ungated (2023) | 2026-05-19 | No |
| `ByteDance/SDXL-Lightning` | OpenRAIL ungated (2024) | 2026-05-19 | No |
| `madebyollin/taesdxl` | MIT ungated (2024) | 2026-05-19 | No |

Add rows as new cases surface. The "Status as of" date is the date the
finding was updated, not the date of the model release.

---
*Reproduced this with another model or found new behaviour? Contribution
welcome via the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
