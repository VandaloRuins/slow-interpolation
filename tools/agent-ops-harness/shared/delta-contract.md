# The Emergent-Truth Delta Block (the hook contract)

This is the machine-parseable hand-off between the two session-close phases:

```
SESSION CLOSE
  PHASE 1  ingest   -> reconciles the OPERATIONS file (task rows), emits a delta block
  PHASE 2  kb-sync  -> consumes the delta block, propagates truth into the WIDER KB
```

`ingest` (its final step) appends the block below to its close-out, after the courtesy
summary. `kb-sync` reads **only** this block plus the `touched_slugs` set — it does not
re-read the whole conversation. This keeps Phase 2 delta-driven, never a full KB scan.

The block is fenced with the language tag `kb-sync-delta` so it is unambiguous to find.

````
```kb-sync-delta
session: 2026-01-15
touched_slugs:
  - acme-spring-showcase
  - acme-warehouse-venue
deltas:
  - fact_domain: event-title
    entity: acme-spring-showcase
    old_value: "Spring Mixer"
    new_value: "Spring Showcase"
    canonical_doc: knowledge/network/events/acme-spring-showcase/acme-spring-showcase.md
    evidence: "user renamed mid-session 2026-01-15"
  - fact_domain: event-venue
    entity: acme-spring-showcase
    old_value: "The Annex"
    new_value: "Warehouse 4"
    canonical_doc: knowledge/network/events/acme-spring-showcase/acme-spring-showcase.md
    evidence: "venue change confirmed in conversation 2026-01-15"
```
````

## Field contract

Each delta is exactly `{fact_domain, entity, old_value, new_value, canonical_doc, evidence}`.

- `fact_domain` — the kind of fact (e.g. `event-title`, `person-role`, `event-venue`,
  `org-status`). This is the key `kb-sync` looks up in the source-of-truth registry to
  find where the canonical value lives and whether the domain is a guard tier.
- `entity` — the slug the fact is about.
- `old_value` / `new_value` — what the KB currently carries vs. the session's established
  truth. `kb-sync` searches for `old_value` (and obvious variants) during its bounded grep.
- `canonical_doc` — `ingest`'s **best guess** at the canonical file. `kb-sync`
  **re-resolves** this against the registry and never trusts the guess blindly (an ops
  skill can mis-map a knowledge-domain fact).
- `evidence` — a one-line provenance note (what in the session established this).

## Trust levels

- **From an `ingest` run in the same chat:** the block is authoritative input; `kb-sync`
  still re-resolves the canonical doc and still gates its own diff.
- **`kb-sync --from-session` (no upstream block):** `kb-sync` re-derives the deltas by
  scanning the conversation for correction language ("actually it's…", "we renamed…",
  "that's wrong, it's now…"). This path is **lower-trust**: every re-derived delta is
  confirmed with the user *before* registry resolution, not just at the final gate.
- **Deferred block:** if the user ignores the "run kb-sync?" offer, `ingest` logs the
  block to the state file so the propagation is not lost; `kb-sync` can re-read it later.

## Why a contract and not a shared library

The two phases are deliberately decoupled: `ingest` owns the operations file, `kb-sync`
owns the wider KB, and they are separate approval batches. A fenced text block is the
entire coupling — either phase can run without the other, and a third tool could emit or
consume the same block. Keep the shape stable; that stability is what makes the hand-off
safe.
