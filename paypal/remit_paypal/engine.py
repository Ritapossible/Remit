"""Remit's GenLayer engine, imported unchanged.

``contracts/remit_core.py``, ``contracts/remit_prompts.py`` and
``contracts/jury_common.py`` are pure Python with no ``gl.*`` calls. The
PayPal guard uses them as they are, so the rules, the prompt and the
fail-closed reading of a verdict are the same code the GenLayer contracts
run, under the same tests.
"""

import os
import sys

_CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "contracts")
if _CONTRACTS not in sys.path:
    sys.path.insert(0, _CONTRACTS)

import remit_core as core  # noqa: E402
import remit_prompts as prompts  # noqa: E402
from jury_common import _read_verdict as read_verdict  # noqa: E402

__all__ = ["core", "prompts", "read_verdict"]
