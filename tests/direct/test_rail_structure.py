"""Structural tests for the rail, the contract that actually holds money.

It cannot run outside GenVM, so these pin the properties a reviewer would
check by reading it: the one payout path, the order of its checks, and who can
move value.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNNER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"


@pytest.fixture(scope="module")
def rail():
    with open(os.path.join(ROOT, "contracts", "build", "rail.py")) as handle:
        return handle.read()


def method(src, name):
    start = src.index("    def %s(" % name)
    nxt = re.search(r"\n    (@gl\.|def )", src[start + 10 :])
    return src[start : start + 10 + nxt.start()] if nxt else src[start:]


def test_header_then_code(rail):
    lines = rail.splitlines()
    assert lines[0] == '# { "Depends": "%s" }' % RUNNER
    assert lines[1] == "from genlayer import *"
    compile(rail, "rail.py", "exec")


def test_pay_reads_settlement_not_the_shadow_aware_view(rail):
    body = method(rail, "pay")
    assert "settlement_of(" in body
    assert "authorization_of(" not in body


def test_every_check_runs_before_value_moves(rail):
    body = method(rail, "pay")
    transfer = body.index("emit_transfer(")
    for check in (
        "spend already paid",
        "the rail pays only authorized spends",
        "finality delay",
        "rail balance is below",
    ):
        assert body.index(check) < transfer, check
    # The paid mark is written before the transfer, so a second call in the
    # same block cannot pay twice.
    assert body.index("self.paid_amount[key] =") < transfer


def test_pay_sends_the_guards_recipient_and_amount_only(rail):
    body = method(rail, "pay")
    assert 'Address(str(s["recipient"]))' in body
    assert "value=u256(amount)" in body
    assert 'amount = int(s["amount"])' in body
    sig = body.splitlines()[0]
    assert sig.strip() == "def pay(self, spend_id: int) -> None:", "the caller must not choose who or how much"


def test_every_place_value_moves_is_listed_here(rail):
    """Four transfer sites, each pinned to who receives and what bounds it."""
    assert rail.count("emit_transfer(") == 4
    # pay: the guard's recipient (test above)
    # withdraw: the principal, from the treasury only - never a bond
    body = method(rail, "withdraw")
    assert body.index("self.principal") < body.index("emit_transfer(")
    assert "_Payee(self.principal)" in body
    assert "int(self.treasury) < value" in body and "self.balance" not in body
    # withdraw_bond: the agent, from its own bond, once nothing is challengeable
    body = method(rail, "withdraw_bond")
    assert "_Payee(self.agent)" in body
    for check in ("only the agent", "int(self.standing) < value", "a challenge is open", "clawback window"):
        assert body.index(check) < body.index("emit_transfer("), check
    # _send: the court's settlement, computed by the engine
    body = method(rail, "_send")
    assert "emit_transfer(value=u256(amount))" in body
    rule = method(rail, "rule")
    assert '_send(record["challenger"], int(settled["to_challenger"]))' in rule
    assert '_send(str(self.agent), int(settled["to_agent"]))' in rule
    assert '_send(record["challenger"], int(record["bond"]))' in method(rail, "lapse")
    assert rail.count("self._send(") == 3


def test_payouts_are_bounded_by_internal_accounting(rail):
    """The balance lags value already sent (it leaves at finality), so a
    payout is bounded by the treasury ledger, and bonds are never treasury."""
    body = method(rail, "pay")
    assert "int(self.treasury) < amount" in body
    assert body.index("self.treasury = ") < body.index("emit_transfer(")
    assert "self.treasury" not in method(rail, "post_bond")
    assert "self.treasury" not in method(rail, "challenge")


def test_a_challenge_holds_the_payout(rail):
    body = method(rail, "pay")
    transfer = body.index("emit_transfer(")
    for check in ("spend is under challenge", "an upheld challenge clawed this spend back", "revoked by a tier-3 ruling"):
        assert body.index(check) < transfer, check


def test_binding_refuses_other_principals_and_shadow_guards(rail):
    body = method(rail, "__init__")
    assert "only the guard's principal may deploy its rail" in body
    assert 'bool(info["shadow"])' in body


def test_receiving_is_the_only_payable_method(rail):
    """Value enters in three ways: funding the treasury, the agent's bond, a
    challenger's bond. Each lands in its own ledger."""
    assert rail.count("@gl.public.write.payable") == 3
    for name, ledger in (("fund", "self.treasury"), ("post_bond", "self.standing"), ("challenge", "self.escrowed")):
        assert "@gl.public.write.payable\n    def %s(" % name in rail
        assert ledger in method(rail, name), name
