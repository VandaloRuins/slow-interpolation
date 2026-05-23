# `cloud/release_batch.py`: release-day batch with optional warm-pool

The Modal cloud-render path has two batch entry points:

| Script | When to use |
|---|---|
| `cloud/batch.py` | Fire-and-forget parallel batches. N configs dispatched simultaneously via `Function.map()`, each on its own cold-started container. **Most release-day workflows.** No idle billing. |
| `cloud/release_batch.py` | Sequential dispatch with human-in-the-loop iteration. Optional opt-in warm-pool skips ~30 s container cold-start per render. **Niche but valuable for ~7 to 25 render sessions under 1 hour where you're tweaking between dispatches.** |

This doc covers the second. If your batch is fire-and-forget parallel,
use `cloud/batch.py` instead, warm-pool gives nothing because each
parallel container cold-starts in parallel anyway.

## Quick reference

```bash
# Default: no warm pool. Same as cloud/batch.py.
modal run -m cloud.release_batch --configs "examples/configs/renoir/*.yaml"

# Warm pool active for 30 minutes.
modal run -m cloud.release_batch --configs "..." --warm 30m

# Warm pool for 45 min.
modal run -m cloud.release_batch --configs "..." --warm 45m

# Other unit suffixes.
modal run -m cloud.release_batch --configs "..." --warm 1h
modal run -m cloud.release_batch --configs "..." --warm 90s   # rarely useful
```

`--warm` requires a duration; there is no boolean form. Max accepted
is 60 minutes. To run longer, dispatch multiple sessions.

## When the warm-pool actually helps

Container cold-start on Modal is ~20 to 40 s. A render's GPU-active
phase is ~120 s for the standard tcole_valley config. Cold-start is
therefore ~25 % of total wall time per render.

| Batch shape | Cold-starts saved | Useful? |
|---|---|---|
| 7 renders dispatched in parallel via `cloud/batch.py` | 0 | No. Each parallel container cold-starts in parallel. |
| 7 renders dispatched sequentially over a 1-hour session | 6 | **Yes.** ~3 min wall time saved. |
| 25 renders dispatched sequentially over a 1-hour session | 24 | **Yes.** ~10 min wall time saved. |
| 25 renders dispatched in parallel via `cloud/batch.py` | 0 | No. |
| 1 render | 0 | No. |
| Many renders dispatched over hours-long iteration | depends | Maybe. The warm pool only holds for the session window you set. |

**Default to `cloud/batch.py` parallel fan-out.** Use `release_batch
--warm` only when you have a session-bounded sequential dispatch.

## The six safety layers

The accidental "I forgot it was on" scenario for a warm pool is real:
L40S idle ~1 USD/hr × 24 h × 30 d = ~720 USD/month worst case. Six
layers keep the worst-case bounded to ~0.50 USD.

| # | Layer | Where |
|---|---|---|
| 1 | `scaledown_window=1800` (30 min idle hard-cap) on `render_warm` | `cloud/app.py` |
| 2 | No persistent flag. No YAML setting, no boolean CLI flag, no `~/.modal.toml` entry. Warm activation is per-invocation only. | `cloud/release_batch.py` |
| 3 | Time-windowed activation: `--warm DURATION` is required; not boolean. Script enforces shutdown at the duration end. Max 60 min. | `cloud/release_batch.py` |
| 4 | Loud terminal banner at start (tier, idle USD/hr, auto-stop time, hard-cap). | `_print_warm_banner` |
| 5 | Explicit "released" message at end on success / exception / Ctrl+C (the layer 1 hard-cap is the safety net regardless). | `_shutdown_warm_pool` |
| 6 | Post-batch cost summary distinguishes render-active GPU-s vs warm-idle GPU-s vs total USD. Accidental waste shows loudly. | `_print_summary` |

### Layer 1 in detail

`render_warm` is defined in `cloud/app.py` with
`scaledown_window=1800`. This is Modal's hard cap on idle-container
lifetime: after 30 min with no calls, Modal spins the container down
regardless of anything else. Worst-case forgotten cost:

> L40S × 30 min × 1.95 USD/hr ≈ **0.98 USD** absolute upper bound.

In practice your script's natural exit (success / exception / Ctrl+C)
shuts things down sooner; the 30 min cap is the seatbelt.

### Layer 3 in detail

`--warm` takes a duration like `30m`, `45m`, `1h`, `90s`. There is no
boolean form. This forces a conscious decision about session bounds.
The duration is also enforced as a max-60-min cap to prevent typos
like `--warm 8h`.

## Modal 1.4.x API note

Modal renamed the legacy parameters in early 2025:

| Old | New |
|---|---|
| `keep_warm` | `min_containers` |
| `container_idle_timeout` | `scaledown_window` |

`cloud/app.py` uses the new names. `render_warm` has
`min_containers=0` (warm pool not held proactively) and
`scaledown_window=1800` (the 30-min hard cap). The "warm pool" effect
inside a session comes from rapid repeated calls keeping the
container active naturally; once calls stop, `scaledown_window` is
the timer.

## Future skill wrapper (deferred)

A Claude Code skill that:

- Invokes `release_batch.py --warm DURATION`.
- Watches stdout for the warm-active banner; re-prints it in chat at intervals.
- Surfaces the cost summary at end.
- Refuses to invoke if a previous session lock file is still active.

Not built yet. Build when the underlying script gets enough use that
the friction of running it from a terminal is worth automating.

## Cost worked example

A typical Renoir iteration session: 8 renders dispatched sequentially
over 35 min, each ~120 s wall.

Without `--warm`:

- 8 cold-starts × 30 s = 4 min of cold-start overhead.
- 8 × 120 s render = 16 min of GPU-active.
- Total wall: ~20 min. Cost: 8 × 0.07 = **0.56 USD.**

With `--warm 40m`:

- 1 cold-start at the first render: 30 s.
- 7 subsequent renders skip cold-start.
- 8 × 120 s render = 16 min of GPU-active.
- Brief warm-idle gaps between dispatches (likely 1 to 3 min total).
- Total wall: ~17 min. Cost: 8 × 0.07 + ~0.10 warm-idle = **~0.66 USD.**

Net: ~3 min wall saved, ~0.10 USD extra spent. Worth it when you're
iterating between renders and care about responsiveness.

## See also

- [`docs/modal.md`](../../../modal.md): base Modal docs.
- [`cloud/batch.py`](../../../../cloud/batch.py): parallel fan-out (the default choice).
- [`progress.md`](progress.md): workstream status log (sibling).
