import pytest
from conftest import answer

from remit_paypal.engine import core
from remit_paypal.facts import cents, payer_address
from remit_paypal.panel import Panel, Vote, aggregate


def v(verdict):
    return Vote("m", verdict, 90, "", "")


@pytest.mark.parametrize("votes,quorum,expected", [
    (["in_remit", "in_remit", "in_remit"], 2, "in_remit"),
    (["in_remit", "in_remit", "undetermined"], 2, "in_remit"),
    (["in_remit", "undetermined", "undetermined"], 2, "undetermined"),
    (["in_remit", "in_remit", "out_of_remit"], 2, "out_of_remit"),  # one confident no stops money
    (["in_remit", "in_remit", "undetermined"], 3, "undetermined"),
])
def test_aggregate_fails_closed(votes, quorum, expected):
    assert aggregate([v(x) for x in votes], quorum) == expected


def test_quorum_must_be_possible():
    with pytest.raises(core.RemitError):
        Panel({"a": lambda p: ""}, quorum=2)


def test_a_model_error_or_a_hesitant_yes_is_a_doubt():
    def boom(prompt):
        raise TimeoutError("slow")
    verdict, votes = Panel({"a": boom, "b": lambda p: answer("in_remit", 59), "c": lambda p: answer("in_remit")},
                           quorum=2).decide("q")
    assert verdict == "undetermined"
    assert votes[0].verdict == "undetermined" and "TimeoutError" in votes[0].error
    assert votes[1].verdict == "undetermined"  # in_remit at 59 is hardened


@pytest.mark.parametrize("text,value", [("45.00", 4500), ("45", 4500), ("0.5", 50), ("1234.07", 123407)])
def test_amounts_parse_exactly(text, value):
    assert cents(text) == value


@pytest.mark.parametrize("text", ["-1.00", "1.234", "1e3", "", "12.3.4", "abc"])
def test_bad_amounts_are_refused(text):
    with pytest.raises(ValueError):
        cents(text)


def test_payer_addresses_are_stable_and_engine_shaped():
    a = payer_address("PAYER1")
    assert a == payer_address("PAYER1") != payer_address("PAYER2")
    assert core.normalize_address(a) == a and len(a) == 42
