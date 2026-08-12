"""
KB export for the media query layer (Layer 3) -- OPTIONAL, pluggable.

Emits three parquet files keyed by slug so DuckDB (tools/media_query.py) can
JOIN your project's entity knowledge against the media catalogue:

    tools/data/kb-export/kb_people.parquet
    tools/data/kb-export/kb_events.parquet
    tools/data/kb-export/kb_orgs.parquet

Copies are pushed to the R2 bucket under _kb/ so remote agents can query
bucket-only. Zero LLM tokens.

WHERE THE ROWS COME FROM -- first adapter that resolves wins:

  1. tools/kb_adapter.py in this repo exposing `parse_all_profiles() -> list[dict]`.
     Use this when the project already has a parser for its own knowledge base.
     Each dict needs at least: {"id": <slug>, "type": "person"|"organization"|"event"}.

  2. The built-in frontmatter walker: point `kb.root` (in tools/media-archive.json)
     or --kb-root at a folder of markdown files carrying YAML frontmatter.
     `type:` in the frontmatter routes the node; the slug is `id`/`slug` in the
     frontmatter, else the containing folder name, else the filename stem.

  3. Nothing configured -> exits cleanly. media_query.py still works; only the
     people/events/orgs SQL views are unavailable.

Usage:
    py -3.11 tools/media-engine/kb_export.py [--kb-root <dir>] [--no-push]

Design doc: docs/media-archive-architecture.md
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import media_store  # noqa: E402

EXPORT_DIR = TOOLS_DIR / "data" / "kb-export"
CONFIG_PATH = TOOLS_DIR / "media-archive.json"

TYPE_ALIASES = {
    "person": "person", "people": "person", "human": "person", "artist": "person",
    "organization": "organization", "organisation": "organization", "org": "organization",
    "company": "organization", "venue": "organization", "institution": "organization",
    "event": "event", "events": "event", "exhibition": "event", "show": "event",
}


def load_config():
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[kb-export] WARN: bad {CONFIG_PATH.name}: {e}")
    return {}


# ------------------------------------------------------------------ adapter 1

def try_project_adapter():
    """tools/kb_adapter.py -> parse_all_profiles()."""
    if not (TOOLS_DIR / "kb_adapter.py").is_file():
        return None
    try:
        import kb_adapter  # noqa
    except Exception as e:
        print(f"[kb-export] WARN: tools/kb_adapter.py failed to import: {e}")
        return None
    fn = getattr(kb_adapter, "parse_all_profiles", None)
    if not callable(fn):
        print("[kb-export] WARN: kb_adapter.py has no parse_all_profiles()")
        return None
    nodes = list(fn())
    print(f"[kb-export] adapter: tools/kb_adapter.py ({len(nodes)} nodes)")
    return nodes


# ------------------------------------------------------------------ adapter 2

def parse_frontmatter(text):
    """YAML-frontmatter reader. Tries PyYAML, then falls back to a lenient
    key: value / '- item' parser.

    The fallback is not a nicety: real knowledge bases carry hand-written
    frontmatter with unquoted prose in it ("next_action: (1) URGENT: send..."),
    which strict YAML rejects outright. Dropping those profiles silently would
    quietly halve the export -- so a strict-parse failure degrades to lenient
    line parsing instead of discarding the node."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip("\n")
    try:
        import yaml
        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return data
    except Exception:
        pass  # strict parse failed -> lenient fallback below
    data, key = {}, None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and line.strip().startswith("- ") and key:
            data.setdefault(key, [])
            if isinstance(data[key], list):
                data[key].append(line.strip()[2:].strip().strip('"').strip("'"))
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            if val.startswith("[") and val.endswith("]"):
                data[key] = [v.strip().strip('"').strip("'")
                             for v in val[1:-1].split(",") if v.strip()]
            elif val:
                data[key] = val.strip('"').strip("'")
            else:
                data[key] = []
    return data


def walk_frontmatter(root):
    """Every *.md under root carrying a recognised `type:` becomes a node."""
    root = Path(root)
    if not root.is_dir():
        print(f"[kb-export] kb root not found: {root}")
        return None
    nodes = []
    for md in sorted(root.rglob("*.md")):
        fm = parse_frontmatter(md.read_text(encoding="utf-8", errors="ignore"))
        if not fm:
            continue
        raw_type = str(fm.get("type") or fm.get("kind") or "").strip().lower()
        node_type = TYPE_ALIASES.get(raw_type)
        if not node_type:
            continue
        slug = (fm.get("id") or fm.get("slug")
                or (md.parent.name if md.stem in ("_index", "index", "profile") else md.stem))
        node = dict(fm)
        node["id"] = str(slug)
        node["type"] = node_type
        node.setdefault("label", fm.get("name") or fm.get("label") or fm.get("title") or slug)
        nodes.append(node)
    print(f"[kb-export] adapter: frontmatter walk of {root} ({len(nodes)} nodes)")
    return nodes


# ------------------------------------------------------------------ normalise

def normalise(nodes, node_type):
    """Union of keys across nodes of one type; every column is uniformly
    list[str] or str. Real knowledge bases are ragged -- the same field is a
    scalar in one profile and a list in the next -- and parquet refuses a mixed
    column, so a column that is EVER a list becomes a list everywhere."""
    subset = [n for n in nodes if n.get("type") == node_type]
    keys, listy = [], set()
    for n in subset:
        for k, v in n.items():
            if k not in keys:
                keys.append(k)
            if isinstance(v, list):
                listy.add(k)

    def scalar(v):
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    rows = []
    for n in subset:
        row = {}
        for k in keys:
            v = n.get(k)
            if k in listy:
                if v is None:
                    row[k] = []
                elif isinstance(v, list):
                    row[k] = [scalar(x) for x in v]
                else:
                    row[k] = [scalar(v)]
            else:
                row[k] = None if v is None else scalar(v)
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description="Export project knowledge to parquet for media SQL joins")
    p.add_argument("--kb-root", help="folder of markdown profiles with YAML frontmatter")
    p.add_argument("--no-push", action="store_true", help="skip R2 upload of the parquets")
    args = p.parse_args()

    import pandas as pd

    config = load_config()
    root = args.kb_root or (config.get("kb") or {}).get("root")

    nodes = try_project_adapter()
    if nodes is None and root:
        candidate = Path(root)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        nodes = walk_frontmatter(candidate)
    if nodes is None:
        print("[kb-export] no KB adapter configured -- nothing to export.\n"
              "            Add tools/kb_adapter.py with parse_all_profiles(), or set\n"
              '            "kb": {"root": "<folder of md profiles>"} in tools/media-archive.json.\n'
              "            media_query.py still runs; only the people/events/orgs views are missing.")
        return

    outputs = {
        "kb_people.parquet": pd.DataFrame(normalise(nodes, "person")),
        "kb_events.parquet": pd.DataFrame(normalise(nodes, "event")),
        "kb_orgs.parquet": pd.DataFrame(normalise(nodes, "organization")),
    }

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        path = EXPORT_DIR / name
        df.to_parquet(path, index=False)
        print(f"[kb-export] {name}: {len(df)} rows -> {path}")

    if not args.no_push:
        env = media_store.load_env()
        if media_store.missing_r2_keys(env):
            print("[kb-export] WARN: no R2 creds, skipping push")
        else:
            client = media_store.r2_client(env)
            for name in outputs:
                media_store.upload(EXPORT_DIR / name, f"_kb/{name}",
                                   verify=False, client=client, env=env)
                print(f"[kb-export] pushed _kb/{name}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[kb-export] done {stamp}: "
          + ", ".join(f"{len(df)} rows in {name}" for name, df in outputs.items()))


if __name__ == "__main__":
    main()
