#!/usr/bin/env python3
"""Assemble the deployable Intelligent Contract.

A GenVM contract is a single file, but the deterministic engine must be
testable without a chain and the prompt layer must be testable as pure string
building. So they are authored separately and inlined here.

Output: ``contracts/build/remit.py``. Never edit that file.
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

PARTS = ["remit_core.py", "remit_prompts.py", "contract_shell.py"]

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
DROP_IMPORT = re.compile(r"^(from dataclasses import dataclass|import json|import hashlib|import datetime)\s*$")


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    chunks = [PREAMBLE]

    for name in PARTS:
        path = os.path.join(SRC, name)
        with open(path) as handle:
            body = strip_module_docstring(handle.read())
        kept = [line for line in body.splitlines() if not DROP_IMPORT.match(line)]
        chunks.append("\n# --- %s %s\n" % (name, "-" * (66 - len(name))))
        chunks.append("\n".join(kept).strip("\n") + "\n")

    built = "\n".join(chunks)
    out_path = os.path.join(OUT_DIR, "remit.py")
    with open(out_path, "w") as handle:
        handle.write(built)

    compile(built, out_path, "exec")  # syntax gate before anything touches a network

    print("built  %s" % os.path.relpath(out_path, ROOT))
    print("lines  %d" % len(built.splitlines()))
    print("bytes  %d" % len(built.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
