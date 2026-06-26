#!/usr/bin/env python3
"""armarium.paths — the single source of truth for WHERE things live.

The engine/instance split, made physical. Every office imports this instead of
hardcoding ~/.kilo or ~/.scriptorium:

  - engine assets  (method skill, etc.) resolve under the PLUGIN root
  - instance data  (the manuscripts: CANON.md, memory/, skills/, data/) resolve
    under SCRIPTORIUM_HOME

One engine, many instances — switching agents is just pointing SCRIPTORIUM_HOME
somewhere else.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = Path.home() / ".scriptorium"


def instance_home() -> Path:
    """The agent's manuscripts root. SCRIPTORIUM_HOME wins; else ~/.scriptorium."""
    env = os.environ.get("SCRIPTORIUM_HOME")
    return Path(env).expanduser() if env else DEFAULT_HOME


def engine_root() -> Path:
    """Where the engine (this plugin) is installed. CLAUDE_PLUGIN_ROOT when run as
    a CC plugin; else the repo root inferred from this file."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


# --- instance data (under SCRIPTORIUM_HOME) — the manuscripts ---
def canon() -> Path:        return instance_home() / "CANON.md"          # identity
def memory_dir() -> Path:   return instance_home() / "memory"            # durable facts
def skills_dir() -> Path:   return instance_home() / "skills"            # personal (instance) skills
def agents_dir() -> Path:   return instance_home() / "agents"            # delegation fleet (4th manuscript)
def data_dir() -> Path:     return instance_home() / "data"
def events_dir() -> Path:   return data_dir() / "events"                 # scribe's signal log
def state_dir() -> Path:    return instance_home() / "state"             # office working state
def staged_dir() -> Path:   return instance_home() / "staged"            # corrector proposals


# --- external manuscripts (NOT under instance_home) — a standalone repo the engine
#     tends but does not contain (e.g. a CLI toolbox). Located via its own env var so
#     the engine names no specific repo, staying personal-content-free. ---
def tools_dir() -> Path | None:
    """Scripts dir of the external tool repo. SCRIPTORIUM_TOOLS_DIR; None if unwired."""
    env = os.environ.get("SCRIPTORIUM_TOOLS_DIR")
    return Path(env).expanduser() if env else None


# --- engine assets (under the plugin) — the offices' own tooling ---
def engine_skills_dir() -> Path: return engine_root() / "skills"         # method / dreaming / review
def method_assets_dir() -> Path: return engine_skills_dir() / "method" / "assets"
