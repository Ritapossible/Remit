"""The engine's court views are the tested court rules, as JSON.

The rail asks ``challenge_terms`` before taking a bond and
``challenge_result`` after the jury rules; both must say exactly what the pure
functions in remit_core say.
"""

import itertools
import json

import pytest
from conftest import AGENT, CHALLENGER, T0

import engine_api
import remit_core as core

WEEK = 604800
FLOOR = 10**16
RULE = {"id": "structuring", "type": "judgment", "tier": 2}


def spend(**over):
    s = {"authorization": "authorized", "verdict": "", "reason": "", "decided_at": T0, "amount": 15 * 10**16}
    s.update(over)
    return s


def terms(s=None, rule=RULE, challenger=CHALLENGER, now=T0 + 10, losses=0, last=0):
    return json.loads(
        engine_api.api_challenge_terms(
            json.dumps(s or spend()), json.dumps(rule), challenger, AGENT, now, WEEK, losses, last, FLOOR
        )
    )


def test_terms_quote_the_bond_curve():
    assert terms() == {"error": "", "bond": 15 * 10**15}
    assert terms(losses=1, last=T0)["bond"] == 30 * 10**15
    assert terms(spend(amount=1))["bond"] == FLOOR


def test_terms_carry_the_eligibility_error():
    assert "judgment rules" in terms(rule=None)["error"]
    assert "own payment" in terms(challenger=AGENT)["error"]
    assert "window" in terms(now=T0 + WEEK + 1)["error"]


@pytest.mark.parametrize(
    "verdict,paid,tier", list(itertools.product(core.VERDICTS, (True, False), (0, 1, 2, 3)))
)
def test_result_is_resolve_record_and_freeze(verdict, paid, tier):
    out = json.loads(engine_api.api_challenge_result(verdict, 100, 1000, paid, 5000, FLOOR, 2, T0, tier))
    policy = core.BondPolicy(floor=FLOOR)
    expected = core.resolve_challenge(verdict=verdict, bond=100, amount=1000, paid=paid, standing=5000, policy=policy)
    upheld = verdict == core.VERDICT_OUT_OF_REMIT
    for k, v in expected.items():
        assert out[k] == v
    assert (out["losses"], out["last_loss_at"]) == ((0, 0) if upheld else (3, T0))
    assert out["freeze"] == (core.freeze_tier(tier=tier, shadow=False) if upheld else 0)
