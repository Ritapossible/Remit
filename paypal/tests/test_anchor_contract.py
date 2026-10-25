"""RemitAnchor, run as the deployed file in Remit's GenVM stand-in
(tests/direct/genvm_stub.py)."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests", "direct"))

from genvm_stub import Runtime, deploy, load  # noqa: E402

CONTRACT = os.path.join(ROOT, "paypal", "contracts", "remit_anchor.py")
OPERATOR = "0x00000000000000000000000000000000000000d1"
OTHER = "0x00000000000000000000000000000000000000e2"
A = "0xa0"
H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


@pytest.fixture
def chain():
    rt = Runtime()
    ns = load(CONTRACT, rt)
    deploy(rt, ns, "RemitAnchor", A, OPERATOR.upper().replace("0X", "0x"), "remit-paypal demo log", sender=OPERATOR)
    return rt


def test_the_header_is_the_first_line_and_code_follows():
    lines = open(CONTRACT).read().splitlines()
    assert lines[0].startswith('# { "Depends": "py-genlayer:') and lines[1] == "from genlayer import *"


def test_the_operator_anchors_and_anyone_reads(chain):
    assert chain.call(A, "latest") == "{}"
    chain.call(A, "anchor", 5, H1, sender=OPERATOR)
    chain.now += 60
    chain.call(A, "anchor", 12, H2.upper(), sender=OPERATOR)
    latest = json.loads(chain.call(A, "latest", sender=OTHER))
    assert latest == {"seq": 12, "hash": H2, "at": chain.now}
    assert chain.call(A, "hash_at", 5) == H1 and chain.call(A, "hash_at", 6) == ""
    assert [a["seq"] for a in json.loads(chain.call(A, "anchors", 1, 10))] == [5, 12]
    assert json.loads(chain.call(A, "status")) == {"release": "remit-anchor/1", "operator": OPERATOR,
                                                    "log_id": "remit-paypal demo log", "count": 2, "last_seq": 12}


def test_only_the_operator_anchors(chain):
    with pytest.raises(Exception, match="only the operator"):
        chain.call(A, "anchor", 1, H1, sender=OTHER)
    assert chain.call(A, "latest") == "{}"


@pytest.mark.parametrize("seq", [0, 4, 5, -1])
def test_entry_numbers_strictly_increase(chain, seq):
    chain.call(A, "anchor", 5, H1, sender=OPERATOR)
    with pytest.raises(Exception, match="not after"):
        chain.call(A, "anchor", seq, H3, sender=OPERATOR)
    assert chain.call(A, "hash_at", 5) == H1  # history is never re-anchored


@pytest.mark.parametrize("h", ["", "a" * 63, "a" * 65, "g" * 64, "0x" + "a" * 62])
def test_a_hash_is_64_hex_characters(chain, h):
    with pytest.raises(Exception, match="64 hex"):
        chain.call(A, "anchor", 1, h, sender=OPERATOR)


def test_the_operator_must_be_an_address():
    rt = Runtime()
    ns = load(CONTRACT, rt)
    with pytest.raises(Exception, match="not an address"):
        deploy(rt, ns, "RemitAnchor", A, "operator", "x", sender=OPERATOR)


def test_anchors_pages_are_bounded(chain):
    for i in range(1, 8):
        chain.call(A, "anchor", i, "%064x" % i, sender=OPERATOR)
    assert [a["seq"] for a in json.loads(chain.call(A, "anchors", 3, 2))] == [3, 4]
    assert json.loads(chain.call(A, "anchors", 7, 100))[-1]["seq"] == 7
    assert json.loads(chain.call(A, "anchors", 9, 5)) == [] and json.loads(chain.call(A, "anchors", 1, 0)) == []
