# Customising the stack for this project

The installer already stamped the project-specific values. This is the map of *what* it stamped and what else is worth changing once real assets are in.

## Values set at install

Recorded in `tools/media-archive.json`. Re-running the installer with `--force` re-stamps them.

| Config key | Where it lands |
|---|---|
| `project_name` | UI header, the captioning prompt, skill + agent descriptions |
| `bucket` | `R2_BUCKET` default, the `r2://` URI shown in the Library |
| `collection` | default `--edition` on ingest/serve/query, docs examples |
| `collection_term` | prose only ("edition" / "season" / "project") |
| `scene_examples` | the example scene tags inside the captioning prompt |
| `py` | the interpreter written into every documented command |
| `report_dir` | where ingest run reports are written |
| `default_source` | the Engine Room's default staging folder |
| `vector_dir` | `tools/data/<dir>` for the optional similarity index |
| `kb.root` | folder of markdown entity profiles for the SQL join export |

## The taxonomy — change this early, not late

Retagging 900 assets is a chore; deciding well on day one is not. Three vocabularies matter:

**1. `asset_class`** — ships as `event-photo | event-video | press-kit | original-work | document`. It answers "what *kind* of thing is this", and it is what most queries filter on first. Rename freely to fit the project (`session-photo`, `product-shot`, `master`, `contract`), but keep the list short and mutually exclusive.

**2. Scene tags** — free-form lowercase tags the VLM proposes per asset (`install-shot`, `wide`, `portrait`). Seed the prompt with 5 examples that look like your material; the model anchors hard on them. Set at install via `scene_examples`; to change later, edit `CAPTION_PROMPT` in `tools/media-engine/ingest.py`.

**3. Key prefixes** — `{collection}/{group}/{entity}/{media-type}/`. The middle two segments should be **the slugs your project already uses elsewhere**, because that is what makes the SQL joins work without a mapping table. If the project has no natural "group", use dates (`day-YYYY-MM-DD/`) — a shape the pipeline already supports.

## The captioning prompt

`CAPTION_PROMPT` near the top of `tools/media-engine/ingest.py`. It must keep returning strict JSON with the same four keys (`caption`, `scene`, `artwork_guess`, `artwork_confidence`) — the parser depends on it. What is worth tuning is the **context sentence**: telling the model what kind of material it is looking at measurably improves caption quality. Change the model with `CAPTION_MODEL` in the same file.

## Joining to project entities (optional)

`tools/media-engine/kb_export.py` produces `people` / `events` / `orgs` parquet views for `media_query.py`. Two ways to feed it:

- **Frontmatter walk** — set `kb.root` to a folder of markdown profiles carrying YAML frontmatter with a `type:` field (`person` / `organization` / `event`). The slug comes from `id` / `slug`, else the containing folder name.
- **Project adapter** — drop `tools/kb_adapter.py` exposing `parse_all_profiles() -> list[dict]`, each dict having at least `id` and `type`. Use this when the project already has a parser for its own knowledge base; it wins over the frontmatter walk.

Neither is required. Without an export, `media_query.py` runs fine and only the `people` / `events` / `orgs` views are missing.

## Adding canned queries

`CANNED` at the top of `tools/media_query.py` — a dict of name → SQL with `?` placeholders. Anything you find yourself writing as `--sql` more than twice belongs there, and the SKILL.md mode list should learn about it too.

## Wiring it into the agent

The installer drops:
- `.claude/commands/media-archive.md` → makes `/media-archive` available
- `.claude/agents/media-archivist.md` → the custodian subagent (delete it if the project doesn't use subagents; the skill works standalone)
- `tools/skills/media-archive/SKILL.md` → the protocol both of them read

If the project has a `CLAUDE.md`, add a routing line so natural language reaches the skill without the slash command:

```markdown
| "find photos of X" / "search the media archive" / "get the footage of" / "publish this asset" | main session (Skill) | Invoke `/media-archive` (default `find`). Reads are always safe; publishing needs explicit per-asset clearance. See `tools/skills/media-archive/SKILL.md`. |
```

## What was deliberately left out

- **Face recognition.** The reference design specifies self-hosted embeddings matched against a closed, project-internal gallery, with unknown faces left untagged. It is not in this kit: it carries real legal weight, and it should be a deliberate decision with its own legal basis, not something inherited from a copied folder. The catalogue schema already has the `persons[]` slot with `status` if you add it.
- **Project-specific ingest wrappers** and per-source provenance docs. Those are yours to write.
