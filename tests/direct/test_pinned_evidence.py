"""Milestone 1: the agent cannot be its own witness.

A mandate may pin, per vendor, the URL prefixes that vendor's evidence comes
from (``evidence_sources``). A document anywhere else - a forged invoice the
agent hosts itself, or one on the same shared host under another account - is
refused when it is committed, before any fetch or model. These tests cover
the rule (remit_core), the mandate's validation, and the built guard, readable
and deployed, end to end.
"""

import hashlib
import json
import os

import pytest

from genvm_stub import Runtime, deploy, load
from remit_core import evidence_prefix_ok, pinned_source_error, validate_mandate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(ROOT, "contracts", "build")

PRINCIPAL = "0x00000000000000000000000000000000000000d1"
AGENT = "0x00000000000000000000000000000000000000c1"
VENDOR = "0x00000000000000000000000000000000000000a1"
OTHER = "0x00000000000000000000000000000000000000a2"
E, P, G = "0xe0", "0xe1", "0xe2"
GEN = 10**15
PREFIX = "https://invoice.vendor.test/i/acct_123/"
SOURCES = {VENDOR: [PREFIX]}


# --- the rule ---------------------------------------------------------------

@pytest.mark.parametrize("prefix,ok", [
    (PREFIX, True),
    ("https://vendor.test/", True),
    ("https://vendor.test", False),                 # no trailing "/": would match vendor.test.attacker.io
    ("http://vendor.test/", False),                 # not https
    ("https://localhost/", False),                  # no dot in the host
    ("https://vendor.test/a/../b/", False),
    ("https://vendor.test/a/%2E%2E/", False),
    ("https://user@vendor.test/", False),
    ("https://vendor.test/?x=1/", False),
    ("https://vendor.test/#a/", False),
])
def test_a_pinned_prefix_names_an_https_host_and_ends_with_a_slash(prefix, ok):
    assert evidence_prefix_ok(prefix) is ok


@pytest.mark.parametrize("uri,allowed", [
    (PREFIX + "inv_91.json", True),
    (PREFIX.replace("acct_123", "acct_999") + "inv_91.json", False),   # same host, another account
    ("https://raw.githubusercontent.test/agent/forged.json", False),     # the agent's own host
    ("https://invoice.vendor.test.attacker.io/i/acct_123/x", False),
    (PREFIX + "../acct_999/inv.json", False),                             # path traversal
    (PREFIX + "%2e%2e/acct_999/inv.json", False),
    (PREFIX + "%2E%2E/acct_999/inv.json", False),
    (PREFIX + "inv.json?redirect=https://evil", False),
    ("https://agent@invoice.vendor.test/i/acct_123/x", False),
])
def test_evidence_for_a_pinned_vendor_must_come_from_its_prefix(uri, allowed):
    error = pinned_source_error(SOURCES, VENDOR, uri)
    assert (error == "") is allowed, (uri, error)
    if not allowed:
        assert "must come from the vendor" in error and PREFIX in error


def test_a_vendor_nobody_pinned_is_unrestricted_and_addresses_match_in_any_case():
    assert pinned_source_error(SOURCES, OTHER, "https://anywhere.test/x.json") == ""
    assert pinned_source_error({}, VENDOR, "https://anywhere.test/x.json") == ""
    upper = "0x" + VENDOR[2:].upper()
    assert "must come from the vendor" in pinned_source_error(SOURCES, upper, "https://anywhere.test/x.json")


def _mandate(sources):
    return {
        "remit_mandate_version": 1, "version": 1, "currency": "ATTO_GEN",
        "defaults": {"on_deadline": "refund", "on_undetermined": "refund", "response_window_seconds": 60,
                     "hold_deadline_seconds": 3600, "clawback_window_seconds": 604800},
        "vendor_lists": {"vendors": [VENDOR, OTHER]},
        "evidence_sources": sources,
        "rules": [
            {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 200 * GEN}},
            {"id": "invoice-match", "type": "judgment", "when": {"amount_gte": 100 * GEN},
             "ask": "Does this payment correspond to a delivered order?", "requires_artifact": True,
             "on_breach": {"tier": 1}},
        ],
    }


@pytest.mark.parametrize("sources,valid", [
    (SOURCES, True),
    ({}, True),
    ({VENDOR: [PREFIX, "https://billing.vendor.test/"]}, True),
    ({"not-an-address": [PREFIX]}, False),
    ({VENDOR: []}, False),
    ({VENDOR: [PREFIX] * 5}, False),
    ({VENDOR: "https://vendor.test/"}, False),
    ({VENDOR: ["http://vendor.test/"]}, False),
    ([PREFIX], False),
])
def test_a_mandate_with_unusable_sources_is_refused(sources, valid):
    errors = validate_mandate(_mandate(sources), stored_version=0, max_tier=3)
    assert (errors == []) is valid, errors
    if not valid:
        assert any(e.startswith("evidence_sources") for e in errors)


# --- the built guard, readable and deployed -----------------------------------

HONEST_URL = PREFIX + "inv_91.json"
HONEST = b'{"invoice": "INV-91", "issuer": "Vendor", "total": "0.15", "status": "delivered"}'
FORGED_URL = "https://agent-host.test/forged.json"
FORGED = b'{"invoice": "INV-92", "issuer": "Vendor", "total": "0.15", "status": "delivered"}'


def model(prompt):
    # A jury that believes any invoice it is shown: the point is that it never
    # sees the forged one.
    if "INV-91" in prompt or "INV-92" in prompt:
        return {"verdict": "in_remit", "reason": "matches_rule", "confidence": 92}
    return {"verdict": "undetermined", "reason": "insufficient_evidence", "confidence": 50}


def attempt(fn, *args):
    try:
        fn(*args)
        return "ok"
    except Exception as exc:
        return "refused: " + str(exc)


def scenario(suffix):
    rt = Runtime()
    rt.model = model
    rt.web = {HONEST_URL: HONEST, FORGED_URL: FORGED}
    engine_ns = load(os.path.join(BUILD, "engine" + suffix), rt)
    prompts_ns = load(os.path.join(BUILD, "prompts" + suffix), rt)
    guard_ns = load(os.path.join(BUILD, "guard" + suffix), rt)
    deploy(rt, prompts_ns, "RemitPrompts", P)
    deploy(rt, engine_ns, "RemitEngine", E, P)
    g = deploy(rt, guard_ns, "RemitGuard", G, AGENT, json.dumps(_mandate(SOURCES)), 2, False, E, sender=PRINCIPAL)

    out = {}
    rt.sender = AGENT
    # Forged evidence with the request itself: refused, nothing recorded.
    out["request with forged evidence"] = attempt(
        g.request_spend, VENDOR, 150 * GEN, "media", FORGED_URL, hashlib.sha256(FORGED).hexdigest(), "PO-7")
    # Held without evidence, then forged evidence committed: refused.
    out["held 0"] = attempt(g.request_spend, VENDOR, 150 * GEN, "media", "", "", "PO-7")
    out["commit forged"] = attempt(g.commit_artifact, 0, FORGED_URL, hashlib.sha256(FORGED).hexdigest())
    out["commit traversal"] = attempt(g.commit_artifact, 0, PREFIX + "../acct_9/x.json", hashlib.sha256(FORGED).hexdigest())
    rt.now += 61  # the response window passes with no admissible evidence
    rt.sender = PRINCIPAL
    out["adjudicate 0"] = attempt(g.adjudicate, 0)
    # The honest invoice, from the vendor's own prefix, with the request.
    rt.sender = AGENT
    out["held 1"] = attempt(g.request_spend, VENDOR, 150 * GEN, "media", HONEST_URL, hashlib.sha256(HONEST).hexdigest(), "INV-91")
    rt.sender = PRINCIPAL
    out["adjudicate 1"] = attempt(g.adjudicate, 1)
    # A vendor nobody pinned: evidence from anywhere is still committed.
    rt.sender = AGENT
    out["unpinned vendor"] = attempt(g.request_spend, OTHER, 150 * GEN, "media", FORGED_URL, hashlib.sha256(FORGED).hexdigest(), "PO-8")
    out["docket"] = json.loads(g.docket())
    out["prompts"] = rt.prompts_seen
    return out


@pytest.fixture(scope="module")
def readable():
    return scenario(".py")


@pytest.fixture(scope="module")
def deployed():
    return scenario(".min.py")


def test_deployed_bytes_behave_exactly_like_the_tested_build(readable, deployed):
    assert readable == deployed


def test_the_agent_cannot_be_its_own_witness(readable):
    r = readable
    for key in ("request with forged evidence", "commit forged", "commit traversal"):
        assert "must come from the vendor" in r[key], key
    assert r["held 0"] == "ok" and r["adjudicate 0"] == "ok" and r["held 1"] == "ok" and r["adjudicate 1"] == "ok"
    rows = [(s["state"], s["authorization"], s["verdict"], s["artifact"]) for s in r["docket"]]
    # 0: no admissible evidence -> refused by the mandate's default, whatever the jury says.
    assert rows[0][0] == "refused" and rows[0][3] in ("absent", "unverified")
    # 1: the vendor's own invoice, fetched and hash-checked -> released.
    assert rows[1] == ("settled", "authorized", "in_remit", "verified")
    # The forged invoice never reached a jury prompt.
    assert r["prompts"] and not any("INV-92" in p for p in r["prompts"])
    assert r["unpinned vendor"] == "ok"
