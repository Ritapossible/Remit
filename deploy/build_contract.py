#!/usr/bin/env python3
"""Assemble the two deployable Intelligent Contracts.

A GenVM contract is a single file, but the deterministic engine must be
testable without a chain and the prompt layer must be testable as pure string
building. So they are authored separately and inlined here.

Remit deploys as three contracts because Bradbury caps a transaction at 2^24
gas and a deploy costs about 0.96M gas plus 782 per byte of code and arguments
(measured with deploy/probe_gas.mjs): the shared, stateless **engine** (rules)
and **prompts** (the jury's question), and one **guard** per agent. Outputs,
never edited by hand:

  contracts/build/<name>.py      readable, tested
  contracts/build/<name>.min.py  deployed: docstrings and comments stripped,
                                 unreachable definitions dropped
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "contracts")
OUT_DIR = os.path.join(SRC, "build")

# Pinned by skills.genlayer.com (genlayer-dev / write-contract). All GenLayer
# networks reject py-genlayer:test, :latest and unversioned aliases, so this is
# never floated.
RUNNER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"

BUILDS = {
    "engine": (["remit_core.py", "engine_api.py", "engine_shell.py"], "RemitEngine"),
    "prompts": (["remit_core.py", "remit_prompts.py", "prompts_api.py", "prompts_shell.py"], "RemitPrompts"),
    "guard": (["remit_core.py", "remit_prompts.py", "contract_shell.py"], "RemitGuard"),
}

# The runner header must be followed IMMEDIATELY by code. Any comment line
# between it and the first statement makes the deploy fail with an empty-stderr
# contract_error on every validator - measured on Studio, see CLAUDE.md. The
# "generated file" banner therefore sits *after* the imports, not before them.
PREAMBLE = '''# { "Depends": "%s" }
from genlayer import *

import datetime
import hashlib
import json
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# GENERATED FILE - do not edit.
# Built by deploy/build_contract.py from:
#   contracts/remit_core.py       deterministic engine (pure, chain-free)
#   contracts/remit_prompts.py    prompt construction
#   contracts/contract_shell.py   storage, entrypoints, consensus block
# ---------------------------------------------------------------------------
''' % RUNNER

# Imports the parts declare for themselves; the preamble already provides them.
DROP_IMPORT = re.compile(
    r"^(from dataclasses import dataclass|import json|import hashlib|import datetime"
    r"|from remit_core import \*|from remit_prompts import \*)\s*$"
)


def strip_module_docstring(text):
    """Remove a leading triple-quoted docstring, keeping everything after."""
    stripped = text.lstrip()
    for quote in ('"""', "'''"):
        if stripped.startswith(quote):
            end = stripped.find(quote, len(quote))
            if end == -1:
                raise SystemExit("unterminated module docstring")
            return stripped[end + len(quote) :].lstrip("\n")
    return text


def assemble(parts):
    chunks = [PREAMBLE]
    for name in parts:
        path = os.path.join(SRC, name)
        with open(path) as handle:
            body = strip_module_docstring(handle.read())
        kept = [line for line in body.splitlines() if not DROP_IMPORT.match(line)]
        chunks.append("\n# --- %s %s\n" % (name, "-" * (66 - len(name))))
        chunks.append("\n".join(kept).strip("\n") + "\n")
    return "\n".join(chunks)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from minify_contract import minify

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, (parts, root) in BUILDS.items():
        built = assemble(parts)
        out_path = os.path.join(OUT_DIR, name + ".py")
        compile(built, out_path, "exec")  # syntax gate before anything touches a network
        with open(out_path, "w") as handle:
            handle.write(built)
        small, removed = minify(built, root=root)
        min_path = os.path.join(OUT_DIR, name + ".min.py")
        compile(small, min_path, "exec")
        with open(min_path, "w") as handle:
            handle.write(small)
        print(
            "%-6s %6d bytes readable -> %6d bytes deployed (%d unreachable definitions dropped)"
            % (name, len(built.encode("utf-8")), len(small.encode("utf-8")), len(removed))
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
