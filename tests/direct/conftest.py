"""Shared fixtures for the direct (in-memory) suite.

These tests import ``remit_core`` directly. No chain, no server, no network.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "contracts"))

import remit_core as core  # noqa: E402

T0 = 1_700_000_000  # arbitrary fixed epoch; no wall clock anywhere in the suite

VENDOR_A = "0x00000000000000000000000000000000000000a1"
VENDOR_B = "0x00000000000000000000000000000000000000a2"
DROPPED = "0x00000000000000000000000000000000000000b1"
AGENT = "0x00000000000000000000000000000000000000c1"
PRINCIPAL = "0x00000000000000000000000000000000000000d1"
CHALLENGER = "0x00000000000000000000000000000000000000e1"


def defaults(**overrides):
    base = {
        "on_deadline": core.DEFAULT_REFUND,
        "on_undetermined": core.DEFAULT_REFUND,
        "response_window_seconds": 900,
        "hold_deadline_seconds": 86400,
        "clawback_window_seconds": 604800,
    }
    base.update(overrides)
    return base


def mandate(rules, *, version=1, lists=None, **default_overrides):
    return {
        "remit_mandate_version": 1,
        "version": version,
        "currency": "USD_CENTS",
        "defaults": defaults(**default_overrides),
        "vendor_lists": lists if lists is not None else {"vendors": [VENDOR_A, VENDOR_B], "dropped": [DROPPED]},
        "rules": rules,
    }


def spend(amount, *, to=VENDOR_A, category="media", at=T0):
    return core.Spend(amount=amount, recipient=to, category=category, at=at)


@pytest.fixture
def policy():
    return core.BondPolicy()
