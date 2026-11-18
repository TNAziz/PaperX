"""Paths and settings. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

PAPERX_VERSION = "0.1.0"

# Heavy, machine-local state (parser environments, model caches, staging, Crossref cache)
# lives outside Google Drive so it is not synced. Default: C:\Users\<you>\.paperx
HOME = Path(os.environ.get("PAPERX_HOME", Path.home() / ".paperx"))
ENVS = HOME / "envs"
WORK = HOME / "work"
CACHE = HOME / "cache"

# Repo root (holds tools/<parser>/run.py)
REPO = Path(__file__).resolve().parents[2]

# Default archive: a folder beside the Zotero data directory (plan's default answer).
ZOTERO_DIR = Path(os.environ.get("PAPERX_ZOTERO_DIR", Path.home() / "Zotero"))
ARCHIVE = Path(os.environ.get("PAPERX_ARCHIVE", ZOTERO_DIR.parent / "paperx-archive"))

# Claude verification
CLAUDE_MODEL = os.environ.get("PAPERX_CLAUDE_MODEL", "claude-opus-5-5")
# "cli": call the Claude Code CLI (`claude -p`) with the user's existing login (default).
# "api": call the Anthropic API directly (needs ANTHROPIC_API_KEY).
VERIFIER = os.environ.get("PAPERX_VERIFIER", "cli")
# Auto-correct failed tables/equations: Claude rewrites from the image, then a fresh check must pass.
AUTOCORRECT = os.environ.get("PAPERX_AUTOCORRECT", "1") != "0"
CORRECT_ROUNDS = int(os.environ.get("PAPERX_CORRECT_ROUNDS", "2"))
# Reuse stored Claude answers for identical requests (set 0 to force fresh calls).
CLAUDE_CACHE = os.environ.get("PAPERX_CLAUDE_CACHE", "1") != "0"
TOKEN_CAP = int(os.environ.get("PAPERX_TOKEN_CAP", "500000"))  # per paper (plan default was 200k; raised 2026-11-17 with Tarek's OK)
VERIFY_DPI = 200

# Parser subprocess timeout (seconds)
PARSER_TIMEOUT = int(os.environ.get("PAPERX_PARSER_TIMEOUT", "3600"))

PARSERS = ("mineru", "docling", "marker")


def env_python(tool: str) -> Path:
    return ENVS / tool / "Scripts" / "python.exe" if os.name == "nt" else ENVS / tool / "bin" / "python"


def env_script(tool: str, exe: str) -> Path:
    return ENVS / tool / "Scripts" / f"{exe}.exe" if os.name == "nt" else ENVS / tool / "bin" / exe
