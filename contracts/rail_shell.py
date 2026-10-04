"""Remit rail: the treasury a guard gates, and the court for what it paid.

Built by ``deploy/build_contract.py`` into ``contracts/build/rail.py`` (and the
deployed ``rail.min.py``). One rail per guard.

**Treasury.** The guard decides; this contract holds the money and pays. Its
one payout path, ``pay(spend_id)``, sends exactly the authorized amount to
exactly the authorized recipient, once, after the decision has had time to
finalise. The agent's key has no method here that moves treasury funds: once
the principal funds this rail instead of the agent's wallet, the agent's
spending reaches money only through the guard's verdict.

**Court.** A payment that cleared without a jury stays open to a bonded
challenge for the mandate's clawback window (T1, T7). Anyone but the agent may
challenge, naming one of the mandate's judgment rules and posting a bond on
the engine's rising curve. The agent may answer with evidence inside the
response window; then the jury rules, failing closed in the challenge's
direction (``challenge_agrees``). Upheld: the payment is blocked if the rail
has not paid it, or made good to the treasury from the agent's standing bond if
it has; the challenger gets the bond back with a reward; a tier-2 rule freezes
the agent, a tier-3 rule also revokes what is unpaid. Dismissed: the bond goes
to the agent, the party that was griefed.

Accounting is internal (``treasury``, ``standing``, ``escrowed``), never read
from the balance: value sent by ``emit_transfer`` leaves when the paying
transaction finalises, so the balance lags what is already owed.
"""


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

    # --- treasury ---
    funded: u256
    treasury: u256
    paid_total: u256
    paid_count: u256
    paid_amount: TreeMap[u256, u256]
    paid_at: TreeMap[u256, u256]

    # --- court ---
    # Each challenge is one JSON record (see ``challenge``), keyed by id: one
    # storage map instead of a map per field keeps the deployed code under
    # Bradbury's per-transaction gas cap.
    bond_floor: u256
    standing: u256
    escrowed: u256
    open_count: u256
    challenge_count: u256
    c: TreeMap[u256, str]
    open_on: TreeMap[u256, u256]
    upheld_on: TreeMap[u256, u256]
    streak: TreeMap[str, str]

    # --- graduated authority, from upheld challenges ---
    frozen_tier: u256
    frozen_by: u256
    revoked_below: u256

    def __init__(self, guard: str, finality_seconds: int, bond_floor: int):
        if int(finality_seconds) < 0 or int(bond_floor) <= 0:
            raise Exception("[EXPECTED] the finality delay must not be negative and the bond floor must be positive")
        self.guard = Address(guard)
        info = self._info()
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
        self.bond_floor = u256(int(bond_floor))

    # -------------------------------------------------------------- helpers

    def _now(self) -> int:
        return int(datetime.datetime.now().timestamp())

    def _guard(self):
        return gl.get_contract_at(self.guard).view()

    def _info(self) -> dict:
        return json.loads(str(self._guard().mandate_info()))

    def _spend(self, spend_id: int) -> dict:
        return json.loads(str(self._guard().get_spend(int(spend_id))))

    def _eng(self):
        return gl.get_contract_at(Address(str(self._info()["engine"]))).view()

    def _send(self, to: str, amount: int) -> None:
        if amount > 0:
            _Payee(Address(to)).emit_transfer(value=u256(amount))

    def _terms(self, spend_id: int, rule_id: str, challenger: str) -> dict:
        """Eligibility and bond, from the engine: ``{"error", "bond"}``."""
        info = self._info()
        rule = None
        for r in info["rules"]:
            if r["id"] == str(rule_id):
                rule = r
        streak = json.loads(self.streak.get(str(challenger).lower(), "[0, 0]"))
        return json.loads(
            str(
                self._eng().challenge_terms(
                    str(self._guard().get_spend(int(spend_id))),
                    json.dumps(rule),
                    str(challenger),
                    str(self.agent),
                    self._now(),
                    int(info["defaults"]["clawback_window_seconds"]),
                    int(streak[0]),
                    int(streak[1]),
                    int(self.bond_floor),
                )
            )
        )

    def _open(self, challenge_id: int) -> dict:
        if int(challenge_id) < 0 or int(challenge_id) >= int(self.challenge_count):
            raise Exception("[EXPECTED] unknown challenge")
        record = json.loads(self.c[u256(int(challenge_id))])
        if record["state"] != CHALLENGE_OPEN:
            raise Exception("[EXPECTED] the challenge is already decided")
        return record

    def _close(self, record: dict, state: str) -> None:
        record["state"] = state
        record["decided_at"] = self._now()
        self.c[u256(int(record["id"]))] = json.dumps(record)
        self.escrowed = u256(int(self.escrowed) - int(record["bond"]))
        self.open_count = u256(int(self.open_count) - 1)
        self.open_on[u256(int(record["spend"]))] = u256(0)

    # ------------------------------------------------------------- treasury

    @gl.public.write.payable
    def fund(self) -> None:
        """Anyone may add to the treasury; normally the principal does."""
        value = int(gl.message.value)
        if value <= 0:
            raise Exception("[EXPECTED] send some GEN to fund the rail")
        self.funded = u256(int(self.funded) + value)
        self.treasury = u256(int(self.treasury) + value)

    @gl.public.write
    def pay(self, spend_id: int) -> None:
        """Pay one spend, if and only if the guard authorized it and no
        challenge holds it.

        Anyone may call this - the vendor, the agent, a keeper - because the
        recipient and amount come from the guard, not from the caller. Every
        check runs before value moves, and each failure reverts with a reason.
        """
        key = u256(int(spend_id))
        if int(self.paid_amount.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] spend already paid")
        if int(self.open_on.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] spend is under challenge; it pays only if the challenge is dismissed")
        if int(self.upheld_on.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] an upheld challenge clawed this spend back")

        s = json.loads(str(self._guard().settlement_of(int(spend_id))))
        auth = str(s["authorization"])
        if auth != AUTHORIZED:
            raise Exception("[EXPECTED] spend is " + auth + "; the rail pays only authorized spends")

        decided_at = int(s["decided_at"])
        if decided_at <= 0:
            raise Exception("[EXPECTED] the guard recorded no decision time")
        if is_revoked(spend_id=int(spend_id), revoked_below=int(self.revoked_below)):
            raise Exception("[EXPECTED] spend was revoked by a tier-3 ruling")
        if self._now() - decided_at < int(self.finality_seconds):
            raise Exception("[EXPECTED] decision is not yet past the finality delay")

        # A split is one purchase. If a later payment to this vendor was held
        # as a possible split of this one, this slice waits for that ruling,
        # and falls with it. Spends are numbered in time order, so the scan
        # stops at the widest split window.
        info = self._info()
        reach = max([0] + list(split_windows(info["rules"]).values()))
        if reach > 0:
            me = self._spend(spend_id)
            later = []
            j = int(spend_id) + 1
            while j < int(info["spend_count"]):
                other = self._spend(j)
                if int(other["at"]) - int(me["at"]) >= reach:
                    break
                later.append(other)
                j += 1
            link = split_hold(me, later, info["rules"])
            if link == SPLIT_PENDING:
                raise Exception("[EXPECTED] waits: a later payment to this vendor is held as a split of it")
            if link == SPLIT_REFUSED:
                raise Exception("[EXPECTED] refused with the split it belongs to")

        amount = int(s["amount"])
        if amount <= 0:
            raise Exception("[EXPECTED] nothing to pay")
        if int(self.treasury) < amount:
            raise Exception("[EXPECTED] rail balance is below the authorized amount")

        self.paid_amount[key] = u256(amount)
        self.paid_at[key] = u256(self._now())
        self.paid_total = u256(int(self.paid_total) + amount)
        self.paid_count = u256(int(self.paid_count) + 1)
        self.treasury = u256(int(self.treasury) - amount)
        _Payee(Address(str(s["recipient"]))).emit_transfer(value=u256(amount))

    @gl.public.write
    def withdraw(self, amount: int) -> None:
        """The principal takes back unspent treasury. Never a bond."""
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may withdraw")
        value = int(amount)
        if value <= 0 or int(self.treasury) < value:
            raise Exception("[EXPECTED] invalid withdrawal amount")
        self.treasury = u256(int(self.treasury) - value)
        _Payee(self.principal).emit_transfer(value=u256(value))

    # ---------------------------------------------------------------- court

    @gl.public.write.payable
    def post_bond(self) -> None:
        """The agent's standing bond: what makes a payment that already left
        recoverable. Anyone may post it; only the agent withdraws it."""
        value = int(gl.message.value)
        if value <= 0:
            raise Exception("[EXPECTED] send some GEN to post a bond")
        self.standing = u256(int(self.standing) + value)

    @gl.public.write
    def withdraw_bond(self, amount: int) -> None:
        """The agent takes its bond back once nothing it paid is still
        challengeable: no open challenge, and every payment that cleared
        without a jury is past the clawback window."""
        if gl.message.sender_address != self.agent:
            raise Exception("[EXPECTED] only the agent may withdraw its bond")
        value = int(amount)
        if value <= 0 or int(self.standing) < value:
            raise Exception("[EXPECTED] invalid bond withdrawal amount")
        if int(self.open_count) > 0:
            raise Exception("[EXPECTED] a challenge is open")
        window = int(self._info()["defaults"]["clawback_window_seconds"])
        now = self._now()
        for s in json.loads(str(self._guard().docket())):
            if s["authorization"] == AUTHORIZED and s["verdict"] == "" and s["reason"] == "":
                if now - int(s["decided_at"]) <= window:
                    raise Exception("[EXPECTED] a payment is still inside its clawback window")
        self.standing = u256(int(self.standing) - value)
        _Payee(self.agent).emit_transfer(value=u256(value))

    @gl.public.write.payable
    def challenge(self, spend_id: int, rule_id: str, statement: str) -> None:
        """Allege that a payment which cleared without a jury breached one of
        the mandate's judgment rules. The bond is the value sent with this
        call and must meet ``bond_quote``."""
        key = u256(int(spend_id))
        if int(self.open_on.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] this payment is already under challenge")
        if int(self.upheld_on.get(key, u256(0))) > 0:
            raise Exception("[EXPECTED] a challenge against this payment was already upheld")
        challenger = str(gl.message.sender_address)
        terms = self._terms(spend_id, rule_id, challenger)
        if terms["error"]:
            raise Exception("[EXPECTED] " + str(terms["error"]))
        bond = int(gl.message.value)
        if bond < int(terms["bond"]):
            raise Exception("[EXPECTED] the bond for this challenge is %d" % int(terms["bond"]))
        cid = int(self.challenge_count)
        self.c[u256(cid)] = json.dumps(
            {
                "id": cid,
                "spend": int(spend_id),
                "rule": str(rule_id),
                "challenger": challenger.lower(),
                "bond": bond,
                "statement": str(statement)[:1000],
                "opened_at": self._now(),
                "state": CHALLENGE_OPEN,
                "memo_uri": "",
                "memo_digest": "",
            }
        )
        self.challenge_count = u256(cid + 1)
        self.open_count = u256(int(self.open_count) + 1)
        self.escrowed = u256(int(self.escrowed) + bond)
        self.open_on[key] = u256(cid + 1)

    @gl.public.write
    def respond(self, challenge_id: int, uri: str, digest: str) -> None:
        """The agent's answer: evidence pinned by digest, as for a hold."""
        record = self._open(challenge_id)
        if gl.message.sender_address != self.agent:
            raise Exception("[EXPECTED] only the agent may respond to a challenge")
        if not _is_sha256_hex(digest):
            raise Exception("[EXPECTED] digest must be 64 hex characters")
        record["memo_uri"] = str(uri)
        record["memo_digest"] = str(digest).strip().lower()
        self.c[u256(int(challenge_id))] = json.dumps(record)

    @gl.public.write
    def rule(self, challenge_id: int) -> None:
        """Convene the jury on a challenge. Anyone may call it once the agent
        has answered or its response window has passed (T9)."""
        record = self._open(challenge_id)
        info = self._info()
        defaults = info["defaults"]
        now = self._now()
        memo_uri = str(record["memo_uri"])
        memo_digest = str(record["memo_digest"])
        if memo_uri == "":
            if str(self._eng().uncommitted(int(record["opened_at"]), now, int(defaults["response_window_seconds"]))) == ARTIFACT_FORECLOSED:
                raise Exception("[EXPECTED] response window has not elapsed")

        spend_id = int(record["spend"])
        spend = self._spend(spend_id)
        history = []
        for s in json.loads(str(self._guard().docket())):
            if s["state"] in (SPEND_SETTLED, SPEND_HELD):
                history.append([int(s["amount"]), str(s["recipient"]), str(s["category"]), int(s["at"])])
        candidate = [int(spend["amount"]), str(spend["recipient"]), str(spend["category"]), int(spend["at"])]
        prompts = gl.get_contract_at(Address(str(self._eng().prompts_address())))
        question = json.loads(
            str(
                prompts.view().challenge_prompt(
                    json.dumps(info),
                    str(record["rule"]),
                    str(spend["claim"]),
                    str(record["statement"]),
                    json.dumps(candidate),
                    json.dumps(history),
                    spend_id + 1,
                )
            )
        )
        # Plain values only: the validator's closure is pickled into a sandbox
        # where a storage proxy does not survive.
        template = str(question["template"])
        notes = {str(k): str(v) for k, v in question["notes"].items()}

        def leader() -> str:
            _state = ARTIFACT_ABSENT
            _text = ""
            if memo_uri != "":
                _state = ARTIFACT_UNVERIFIED
                try:
                    # INLINE fetch - do not factor this into a helper.
                    _resp = gl.nondet.web.get(memo_uri)
                    _raw = _resp.body
                    if isinstance(_raw, str):
                        _raw = _raw.encode("utf-8")
                    if hashlib.sha256(_raw).hexdigest().lower() == memo_digest:
                        _state = ARTIFACT_VERIFIED
                        _text = _raw.decode("utf-8", "replace")[:3000]
                except Exception:
                    _state = ARTIFACT_UNVERIFIED
            _out = _read_verdict(
                gl.nondet.exec_prompt(
                    template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes)), response_format="json"
                )
            )
            _out["verdict"] = harden_challenge(_out["verdict"], _out["confidence"])
            _out["artifact"] = _state
            return json.dumps(_out)

        def validator(leader_result: str) -> bool:
            _state = ARTIFACT_ABSENT
            _text = ""
            if memo_uri != "":
                _state = ARTIFACT_UNVERIFIED
                try:
                    # INLINE fetch again - the duplication is deliberate.
                    _resp = gl.nondet.web.get(memo_uri)
                    _raw = _resp.body
                    if isinstance(_raw, str):
                        _raw = _raw.encode("utf-8")
                    if hashlib.sha256(_raw).hexdigest().lower() == memo_digest:
                        _state = ARTIFACT_VERIFIED
                        _text = _raw.decode("utf-8", "replace")[:3000]
                except Exception:
                    _state = ARTIFACT_UNVERIFIED
            _theirs = _as_dict(leader_result)
            if not _theirs or str(_theirs.get("artifact", "")) != _state:
                return False
            _verdict = str(_theirs.get("verdict", ""))
            if _verdict not in VERDICTS:
                return False
            _mine = _read_verdict(
                gl.nondet.exec_prompt(
                    template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes)), response_format="json"
                )
            )
            # Fail closed in the challenge's direction: upholding needs
            # agreement; a validator sure of the breach vetoes a dismissal.
            return challenge_agrees(
                leader_verdict=_verdict,
                own_verdict=harden_challenge(_mine["verdict"], _mine["confidence"]),
            )

        decoded = _as_dict(gl.vm.run_nondet(leader, validator, compare_user_errors=True))
        result = _read_verdict(decoded)
        verdict = harden_challenge(result["verdict"], result["confidence"])
        artifact = str(decoded.get("artifact", ARTIFACT_ABSENT))
        if artifact not in ARTIFACT_STATES:
            artifact = ARTIFACT_UNVERIFIED

        spend_key = u256(spend_id)
        tier = 0
        for r in info["rules"]:
            if r["id"] == record["rule"]:
                tier = int(r["tier"])
        if tier > int(info["max_tier"]):
            tier = int(info["max_tier"])
        streak = json.loads(self.streak.get(record["challenger"], "[0, 0]"))
        settled = json.loads(
            str(
                self._eng().challenge_result(
                    verdict,
                    int(record["bond"]),
                    int(spend["amount"]),
                    int(self.paid_amount.get(spend_key, u256(0))) > 0,
                    int(self.standing),
                    int(self.bond_floor),
                    int(streak[0]),
                    now,
                    tier,
                )
            )
        )
        self.streak[record["challenger"]] = json.dumps([int(settled["losses"]), int(settled["last_loss_at"])])
        self.standing = u256(int(self.standing) - int(settled["from_standing"]))
        self.treasury = u256(int(self.treasury) + int(settled["to_treasury"]))
        if settled["state"] == CHALLENGE_UPHELD:
            self.upheld_on[spend_key] = u256(int(record["id"]) + 1)
            freeze = int(settled["freeze"])
            if freeze > int(self.frozen_tier):
                self.frozen_tier = u256(freeze)
                self.frozen_by = u256(int(record["id"]) + 1)
            if freeze >= TIER_REVOKE:
                self.revoked_below = u256(int(info["spend_count"]))
        record["verdict"] = verdict
        record["reason"] = result["reason"]
        record["confidence"] = int(result["confidence"])
        record["artifact"] = artifact
        record["tier"] = tier
        record["settlement"] = settled
        self._close(record, str(settled["state"]))
        self._send(record["challenger"], int(settled["to_challenger"]))
        self._send(str(self.agent), int(settled["to_agent"]))

    @gl.public.write
    def lapse(self, challenge_id: int) -> None:
        """A challenge the jury could not decide by the mandate's hold deadline
        lapses: the bond goes back and nobody is marked as having lost. No
        challenge is indefinite (T2)."""
        record = self._open(challenge_id)
        deadline = int(self._info()["defaults"]["hold_deadline_seconds"])
        if self._now() - int(record["opened_at"]) < deadline:
            raise Exception("[EXPECTED] deadline not reached")
        self._close(record, CHALLENGE_LAPSED)
        self._send(record["challenger"], int(record["bond"]))

    @gl.public.write
    def lift_freeze(self) -> None:
        """The principal's key outranks the court. A tier-3 revocation stands."""
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may lift a freeze")
        self.frozen_tier = u256(0)
        self.frozen_by = u256(0)

    # ---------------------------------------------------------------- views

    @gl.public.view
    def court_freeze(self) -> int:
        """What the guard reads before every spend."""
        return int(self.frozen_tier)

    @gl.public.view
    def bond_quote(self, spend_id: int, rule_id: str, challenger: str) -> str:
        """Whether ``challenger`` may challenge this payment now under this
        rule, and the bond it must post: ``{"error", "bond"}``."""
        return json.dumps(self._terms(spend_id, rule_id, challenger))

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
                "treasury": int(self.treasury),
                "paid_total": int(self.paid_total),
                "paid_count": int(self.paid_count),
                "bond_floor": int(self.bond_floor),
                "standing": int(self.standing),
                "escrowed": int(self.escrowed),
                "challenge_count": int(self.challenge_count),
                "open_challenges": int(self.open_count),
                "frozen_tier": int(self.frozen_tier),
                "frozen_by": int(self.frozen_by) - 1,
                "revoked_below": int(self.revoked_below),
            }
        )

    @gl.public.view
    def payment_of(self, spend_id: int) -> str:
        """Where one spend stands at the rail: paid, held by a challenge,
        clawed back, or revoked by a tier-3 ruling."""
        key = u256(int(spend_id))
        amount = int(self.paid_amount.get(key, u256(0)))
        return json.dumps(
            {
                "id": int(spend_id),
                "paid": amount > 0,
                "revoked": amount == 0 and is_revoked(spend_id=int(spend_id), revoked_below=int(self.revoked_below)),
                "amount": amount,
                "paid_at": int(self.paid_at.get(key, u256(0))),
                "challenge": int(self.open_on.get(key, u256(0))) - 1,
                "upheld_by": int(self.upheld_on.get(key, u256(0))) - 1,
            }
        )

    @gl.public.view
    def challenges(self) -> str:
        out = []
        index = 0
        while index < int(self.challenge_count):
            out.append(self.c[u256(index)])
            index += 1
        return "[" + ",".join(out) + "]"
