# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

import datetime
import json

# ---------------------------------------------------------------------------
# RemitRail - the treasury a Remit guard gates.
#
# The guard decides; this contract holds the money and pays. Its one payout
# path, pay(spend_id), sends exactly the authorized amount to exactly the
# authorized recipient, once, and only after the decision has had time to
# finalise. Nothing else moves funds except the principal withdrawing their
# own deposit. The agent's key has no method here that moves value: once the
# principal funds this rail instead of the agent's wallet, the only way the
# agent's spending reaches money is through the guard's verdict.
#
# Deployed standalone: the first line must stay the runner header, with code
# immediately after it (a comment in between fails every validator).
# ---------------------------------------------------------------------------


@gl.evm.contract_interface
class _Payee:
    """Any address, as a value recipient. Sending value to a wallet goes
    through an EVM contract interface; ``gl.get_contract_at(wallet)`` is for
    Intelligent Contracts and is not used for wallets."""

    class View:
        pass

    class Write:
        pass


AUTHORIZED = "authorized"


class RemitRail(gl.Contract):
    guard: Address
    principal: Address
    agent: Address
    finality_seconds: u256
    funded: u256
    paid_total: u256
    paid_count: u256
    paid_amount: TreeMap[u256, u256]
    paid_at: TreeMap[u256, u256]

    def __init__(self, guard: str, finality_seconds: int):
        if int(finality_seconds) < 0:
            raise Exception("[EXPECTED] finality delay must not be negative")
        self.guard = Address(guard)
        info = json.loads(gl.get_contract_at(self.guard).view().mandate_info())
        # Only the guard's principal may put a treasury behind it, and never
        # behind a shadow guard: shadow mode withholds nothing by design, so a
        # rail bound to one would pay refused spends.
        if Address(str(info["principal"])) != gl.message.sender_address:
            raise Exception("[EXPECTED] only the guard's principal may deploy its rail")
        if bool(info["shadow"]):
            raise Exception("[EXPECTED] a rail cannot bind to a shadow-mode guard")
        self.principal = gl.message.sender_address
        self.agent = Address(str(info["agent"]))
        self.finality_seconds = u256(int(finality_seconds))
        self.funded = u256(0)
        self.paid_total = u256(0)
        self.paid_count = u256(0)

    def _now(self) -> int:
        return int(datetime.datetime.now().timestamp())

    @gl.public.write.payable
    def fund(self) -> None:
        """Anyone may add funds; normally the principal does."""
        value = gl.message.value
        if value == u256(0):
            raise Exception("[EXPECTED] send some GEN to fund the rail")
        self.funded = u256(int(self.funded) + int(value))

    @gl.public.write
    def pay(self, spend_id: int) -> None:
        """Pay one spend, if and only if the guard authorized it.

        Anyone may call this - the vendor, the agent, a keeper - because the
        recipient and amount come from the guard, not from the caller. Every
        check runs before value moves, and each failure reverts with a reason.
        """
        key = u256(int(spend_id))
        if int(self.paid_amount.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] spend already paid")

        s = json.loads(gl.get_contract_at(self.guard).view().settlement_of(int(spend_id)))
        auth = str(s["authorization"])
        if auth != AUTHORIZED:
            raise Exception("[EXPECTED] spend is " + auth + "; the rail pays only authorized spends")

        decided_at = int(s["decided_at"])
        if decided_at <= 0:
            raise Exception("[EXPECTED] the guard recorded no decision time")
        if self._now() - decided_at < int(self.finality_seconds):
            raise Exception("[EXPECTED] decision is not yet past the finality delay")

        amount = int(s["amount"])
        if amount <= 0:
            raise Exception("[EXPECTED] nothing to pay")
        if int(self.balance) < amount:
            raise Exception("[EXPECTED] rail balance is below the authorized amount")

        self.paid_amount[key] = u256(amount)
        self.paid_at[key] = u256(self._now())
        self.paid_total = u256(int(self.paid_total) + amount)
        self.paid_count = u256(int(self.paid_count) + 1)
        _Payee(Address(str(s["recipient"]))).emit_transfer(value=u256(amount))

    @gl.public.write
    def withdraw(self, amount: int) -> None:
        """The principal takes back unspent funds. The agent cannot."""
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may withdraw")
        value = int(amount)
        if value <= 0 or int(self.balance) < value:
            raise Exception("[EXPECTED] invalid withdrawal amount")
        _Payee(self.principal).emit_transfer(value=u256(value))

    @gl.public.view
    def status(self) -> str:
        return json.dumps(
            {
                "guard": str(self.guard),
                "principal": str(self.principal),
                "agent": str(self.agent),
                "finality_seconds": int(self.finality_seconds),
                "balance": int(self.balance),
                "funded": int(self.funded),
                "paid_total": int(self.paid_total),
                "paid_count": int(self.paid_count),
            }
        )

    @gl.public.view
    def payment_of(self, spend_id: int) -> str:
        key = u256(int(spend_id))
        amount = int(self.paid_amount.get(key, u256(0)))
        return json.dumps(
            {"id": int(spend_id), "paid": amount > 0, "amount": amount, "paid_at": int(self.paid_at.get(key, u256(0)))}
        )
