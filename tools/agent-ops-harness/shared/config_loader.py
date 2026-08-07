"""
agent-ops-harness -- config loader.

The four skills (todo, ingest, kb-sync, platform-ingest) are prose instruction
sets that an agent follows. Every project-specific fact they need -- where the
priorities file lives, what the buckets are called, which command fetches mail,
what the source-of-truth registry path is -- lives in ONE JSON config, not baked
into the prose. This module is the single reader/validator of that config.

It deliberately does NOT parse the registry or project-registry documents: those
are prose markdown the *agent* reads directly (as the human would), the same way
the source system does. This loader only resolves and existence-checks their
paths, and validates the structured scalars the skills branch on.

Usage:
    python shared/config_loader.py --config tools/agent-ops-harness.config.json
        -> validates and prints a resolved summary (non-zero exit on error)

    from shared.config_loader import load_config
    cfg = load_config(path)          # raises ConfigError on a fatal problem
    cfg.priorities_file              # resolved Path
    cfg.buckets                      # [{'id','label','dated'}, ...]
    cfg.hook('mail_fetch', days=7)   # concrete command string, or None
    cfg.route('budget')              # target skill name, or None (=> FLAG to user)
"""

import argparse
import json
import sys
from pathlib import Path


class ConfigError(Exception):
    pass


REQUIRED_TOP = ["project_name", "project_slug", "paths", "buckets", "registry", "scan_roots"]
REQUIRED_PATHS = ["kb_root", "priorities_file", "state_file", "archive_dir"]
KNOWN_ROUTES = ["graph", "budget", "dedupe"]
KNOWN_SCAN_ROOTS = ["living", "derived_indices", "snapshots"]


class Config:
    def __init__(self, raw, config_path):
        self._raw = raw
        self._config_path = Path(config_path).resolve()
        # the repo root the paths are relative to = the dir that holds the config's
        # `tools/` folder. We resolve relative paths against the current working dir
        # (the agent runs skills from the repo root), falling back to config-dir.
        self.root = Path.cwd()

    # --- scalars -------------------------------------------------------------
    @property
    def project_name(self):
        return self._raw["project_name"]

    @property
    def project_slug(self):
        return self._raw["project_slug"]

    # --- paths (resolved) ----------------------------------------------------
    def _p(self, key):
        return (self.root / self._raw["paths"][key]).as_posix()

    @property
    def kb_root(self):
        return self._p("kb_root")

    @property
    def priorities_file(self):
        return self._p("priorities_file")

    @property
    def state_file(self):
        return self._p("state_file")

    @property
    def archive_dir(self):
        return self._p("archive_dir")

    @property
    def drafts_dir(self):
        return (self.root / self._raw["paths"].get("drafts_dir", "")).as_posix() \
            if self._raw["paths"].get("drafts_dir") else None

    def mail_path(self, which):
        """Optional mail-store locations (inbox / sent / threads_index). Returns a
        resolved path, or None when the adopter has no mail integration -- the todo
        sweep's mail steps self-skip in that case. `which` in
        {'mail_inbox', 'mail_sent', 'threads_index'}."""
        v = self._raw.get("paths", {}).get(which)
        return (self.root / v).as_posix() if v else None

    # --- buckets -------------------------------------------------------------
    @property
    def buckets(self):
        return self._raw["buckets"]

    def bucket_ids(self):
        return [b["id"] for b in self._raw["buckets"]]

    # --- registries (paths only; prose the agent reads) ----------------------
    @property
    def registry_path(self):
        return (self.root / self._raw["registry"]["source_of_truth"]).as_posix()

    @property
    def project_registry_path(self):
        pr = self._raw.get("project_registry")
        return (self.root / pr).as_posix() if pr else None

    # --- scan roots ----------------------------------------------------------
    @property
    def scan_roots(self):
        return self._raw["scan_roots"]

    # --- git -----------------------------------------------------------------
    # The `git` block is consumed by shared/ship.py, which reads the config file
    # directly (it must also run standalone, in a repo mid-install or without the
    # harness at all). These accessors exist so skills can report the settings.
    @property
    def commit_email(self):
        """Pin an identity on commits, or None to use the repo's own. Set this if
        a deploy provider attributes builds by commit email."""
        return self._raw.get("git", {}).get("commit_email")

    @property
    def commit_name(self):
        return self._raw.get("git", {}).get("commit_name")

    @property
    def trunk(self):
        """Integration branch, e.g. 'origin/main'. 'auto' asks the remote."""
        return self._raw.get("git", {}).get("trunk", "auto")

    @property
    def claims_ttl_hours(self):
        return self._raw.get("git", {}).get("claims_ttl_hours", 6)

    @property
    def extra_deploy_surfaces(self):
        """[[glob, label], ...] for deploys NOT expressed as a workflow `paths:`
        filter. Keep EMPTY unless you truly have one -- a phantom surface next to
        a real one is worse than silence."""
        return self._raw.get("git", {}).get("extra_deploy_surfaces") or []

    # Retired 2026-08: `scoped_add` and `branch` described the old
    # `git add && commit && push` close-the-loop, which is unsafe with parallel
    # sessions. Landing work now goes through shared/ship.py -- see
    # shared/parallel-git.md and UPGRADE.md. Kept as read-only accessors so an
    # old config does not break; nothing in the bundle reads them any more.
    @property
    def scoped_add(self):
        return self._raw.get("git", {}).get("scoped_add", True)

    @property
    def branch(self):
        return self._raw.get("git", {}).get("branch", "current")

    # --- hooks (optional external commands) ----------------------------------
    def hook(self, name, **fmt):
        """Return the configured command string with {placeholders} filled, or
        None when the adopter has no such hook (the skill then self-skips that
        step). Example: cfg.hook('mail_fetch', days=7)."""
        cmd = self._raw.get("hooks", {}).get(name)
        if not cmd:
            return None
        try:
            return cmd.format(**fmt)
        except KeyError:
            return cmd

    # --- routes (guard-tier hand-offs) ---------------------------------------
    def route(self, name):
        """Target skill for a guard-tier delta (e.g. 'budget' -> '/budget-review'),
        or None. None means: do not write it and do not route it -- FLAG it to the
        user instead. See shared/doctrine.md 'Guard tiers'."""
        return self._raw.get("routes", {}).get(name)


def _validate(raw):
    errs = []
    for k in REQUIRED_TOP:
        if k not in raw:
            errs.append(f"missing top-level key: {k}")
    if "paths" in raw:
        for k in REQUIRED_PATHS:
            if k not in raw["paths"]:
                errs.append(f"missing paths.{k}")
    if "buckets" in raw:
        if not isinstance(raw["buckets"], list) or not raw["buckets"]:
            errs.append("buckets must be a non-empty list")
        else:
            for i, b in enumerate(raw["buckets"]):
                if "id" not in b or "label" not in b:
                    errs.append(f"buckets[{i}] needs both 'id' and 'label'")
    if "registry" in raw and "source_of_truth" not in raw.get("registry", {}):
        errs.append("registry.source_of_truth is required")
    if "scan_roots" in raw:
        for k in KNOWN_SCAN_ROOTS:
            if k not in raw["scan_roots"]:
                errs.append(f"scan_roots.{k} is required (may be an empty list)")
    for r in raw.get("routes", {}):
        if r not in KNOWN_ROUTES:
            errs.append(f"unknown route '{r}' (known: {', '.join(KNOWN_ROUTES)})")
    if errs:
        raise ConfigError("config invalid:\n  - " + "\n  - ".join(errs))


def load_config(path):
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"config is not valid JSON: {e}")
    _validate(raw)
    return Config(raw, path)


def main():
    ap = argparse.ArgumentParser(description="Validate an agent-ops-harness config")
    ap.add_argument("--config", required=True)
    ap.add_argument("--check-paths", action="store_true",
                    help="also warn if referenced files/dirs are absent on disk")
    args = ap.parse_args()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    print(f"OK: config for '{cfg.project_name}' ({cfg.project_slug})")
    print(f"  priorities : {cfg.priorities_file}")
    print(f"  state      : {cfg.state_file}")
    print(f"  archive    : {cfg.archive_dir}")
    print(f"  buckets    : {', '.join(cfg.bucket_ids())}")
    print(f"  registry   : {cfg.registry_path}")
    print(f"  mail hook  : {cfg.hook('mail_fetch', days=7) or '(none -- mail step self-skips)'}")
    print(f"  routes     : " + ", ".join(f"{r}={cfg.route(r) or 'FLAG'}" for r in KNOWN_ROUTES))
    if args.check_paths:
        for label, pth in [("registry", cfg.registry_path), ("kb_root", cfg.kb_root)]:
            if not Path(pth).exists():
                print(f"  WARN: {label} path does not exist yet: {pth}")


if __name__ == "__main__":
    main()
