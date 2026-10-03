"""Remit guard: one per agent. Storage, entrypoints, and the jury.

Built by ``deploy/build_contract.py`` into ``contracts/build/guard.py`` (and a
minified ``guard.min.py``, the bytes that are deployed). Do not edit the build.

**The split.** Every deterministic decision - validating a mandate, classifying
a spend, resolving a case, building the jury's question - is delegated to the
shared engine contract (``engine_shell.py``; the jury's question comes from
``prompts_shell.py``), because Bradbury caps a
transaction at 2^24 gas and the whole product does not fit in one deploy. The
jury stays here: consensus closures cannot call another contract, so the guard
asks the engine for the question and the verdict-to-outcome table first, and
the closures do only the fetch, the model call and the comparison. The engine
address is fixed at deployment; the engine itself is stateless and ownerless.

**The guard holds no funds.** It authorises; a rail settles.
``contracts/rail.py`` holds GEN and pays a spend only when ``settlement_of``
says it is authorized and the decision has had time to finalise.

Hard laws enforced here (see CLAUDE.md):

- **Never custody in the gate.** No ``emit_transfer`` and no payable
  entrypoint in this file. Value lives in the rail.
- **The fetch is inline in both closures.** ``genvm-lint`` cannot trace a
  ``gl.nondet.web`` call through a helper, so it is written out twice on
  purpose. Do not refactor it.
- **The engine is called only OUTSIDE the consensus closures**, and every
  value the closures capture is coerced to plain Python first.
- **ACCEPTED is not success.** Consensus agreeing on a refusal is a network
  success and a spend refusal. State is the record.
"""

AUTH_AUTHORIZED = "authorized"
AUTH_REFUSED = "refused"
AUTH_PENDING = "pending"
AUTH_REVOKED = "revoked"


class RemitGuard(gl.Contract):
    # --- identity and authority ---
    principal: Address
    agent: Address
    engine: Address
    max_tier: u256
    shadow: bool

    # --- the mandate, as the engine validated and flattened it (T5) ---
    compiled: str

    # --- the spend ledger ---
    spend_count: u256
    s_amount: TreeMap[u256, u256]
    s_recipient: TreeMap[u256, str]
    s_category: TreeMap[u256, str]
    s_at: TreeMap[u256, u256]
    s_state: TreeMap[u256, str]
    s_rules: TreeMap[u256, str]
    s_memo_uri: TreeMap[u256, str]
    s_memo_digest: TreeMap[u256, str]
    s_claim: TreeMap[u256, str]
    s_held_at: TreeMap[u256, u256]
    s_verdict: TreeMap[u256, str]
    s_reason: TreeMap[u256, str]
    s_confidence: TreeMap[u256, u256]
    s_artifact: TreeMap[u256, str]
    s_outcome: TreeMap[u256, str]
    s_tier: TreeMap[u256, u256]
    # When each spend's authorization became final here (the request for
    # reflex decisions, the resolution for held ones). A rail waits a finality
    # delay after this before paying.
    s_decided_at: TreeMap[u256, u256]

    # --- graduated authority (tiers 2 and 3) ---
    # A jury breach at tier 2 freezes the agent; at tier 3 it also revokes
    # every authorization decided before it. The rail's court can freeze the
    # agent too, for an upheld challenge; the guard reads that on every spend.
    frozen_tier: u256
    frozen_by: u256
    revoked_below: u256
    rail: str

    # ----------------------------------------------------------------- init

    def __init__(self, agent: str, mandate_json: str, max_tier: int, shadow: bool, engine: str):
        self.engine = Address(engine)
        compiled = str(self._eng().compile_mandate(str(mandate_json), int(max_tier)))
        errors = json.loads(compiled).get("errors", [])
        if errors:
            raise Exception("[EXPECTED] mandate rejected: " + "; ".join([str(e) for e in errors]))
        self.principal = gl.message.sender_address
        self.agent = Address(agent)
        self.max_tier = u256(int(max_tier))
        self.shadow = bool(shadow)
        self.compiled = compiled
        self.spend_count = u256(0)
        self.rail = ""

    # -------------------------------------------------------------- helpers

    def _eng(self):
        return gl.get_contract_at(self.engine).view()

    def _now(self) -> int:
        return int(datetime.datetime.now().timestamp())

    def _mandate(self) -> dict:
        return json.loads(self.compiled)

    def _require_spend(self, spend_id: int):
        if int(spend_id) < 0 or int(spend_id) >= int(self.spend_count):
            raise Exception("[EXPECTED] unknown spend")
        return u256(int(spend_id))

    def _history(self) -> list:
        """Spends that consumed budget: settled or held, as
        ``[amount, recipient, category, at]``. A refused spend never moved
        value and must not count against a later one."""
        out = []
        index = 0
        total = int(self.spend_count)
        while index < total:
            key = u256(index)
            if self.s_state[key] in (SPEND_SETTLED, SPEND_HELD):
                out.append([int(self.s_amount[key]), str(self.s_recipient[key]), str(self.s_category[key]), int(self.s_at[key])])
            index += 1
        return out

    def _classify(self, recipient: str, value: int, category: str, at: int) -> dict:
        return json.loads(
            str(self._eng().classify(self.compiled, json.dumps(self._history()), json.dumps([value, recipient, category, at])))
        )

    def _rule_ids(self, key) -> list:
        return [r for r in str(self.s_rules[key]).split(",") if r != ""]

    def _needs_artifact(self, key) -> bool:
        fired = self._rule_ids(key)
        for r in self._mandate()["rules"]:
            if r["id"] in fired and bool(r["requires_artifact"]):
                return True
        return False

    def _tier_for(self, key) -> int:
        fired = self._rule_ids(key)
        tier = 0
        for r in self._mandate()["rules"]:
            if r["id"] in fired and int(r["tier"]) > tier:
                tier = int(r["tier"])
        cap = int(self.max_tier)
        return tier if tier < cap else cap

    def _outcomes(self, key) -> dict:
        """verdict -> artifact state -> outcome, from the engine."""
        return json.loads(str(self._eng().outcomes(self.compiled, self._needs_artifact(key))))

    def _defaults(self) -> dict:
        return self._mandate()["defaults"]

    def _frozen(self) -> int:
        """The freeze in force: this guard's own, or its rail's court's."""
        tier = int(self.frozen_tier)
        if self.rail != "":
            court = int(gl.get_contract_at(Address(self.rail)).view().court_freeze())
            if court > tier:
                tier = court
        return tier

    def _auth(self, key) -> str:
        """The authorization a rail acts on (shadow mode aside)."""
        if self.s_state[key] == SPEND_HELD:
            return AUTH_PENDING
        if self.s_outcome[key] != OUTCOME_ALLOWED:
            return AUTH_REFUSED
        if is_revoked(spend_id=int(key), revoked_below=int(self.revoked_below)):
            return AUTH_REVOKED
        return AUTH_AUTHORIZED

    def _finalise(self, key, outcome: str, artifact: str, confidence: int) -> None:
        self.s_state[key] = SPEND_SETTLED if outcome == OUTCOME_ALLOWED else SPEND_REFUSED
        self.s_outcome[key] = outcome
        self.s_artifact[key] = artifact
        self.s_confidence[key] = u256(int(confidence))
        self.s_tier[key] = u256(self._tier_for(key) if outcome == OUTCOME_REFUSED else 0)
        self.s_decided_at[key] = u256(self._now())

    # ---------------------------------------------------------- entrypoints

    @gl.public.write
    def request_spend(
        self,
        recipient: str,
        amount: int,
        category: str,
        memo_uri: str,
        memo_digest: str,
        claim: str,
    ) -> None:
        """The gate. Reflex rules and triggers are evaluated in this
        transaction; the common path is authorised here with no jury.

        The guard takes no custody. ``amount`` is declared, not sent.
        """
        if gl.message.sender_address != self.agent:
            raise Exception("[EXPECTED] only the registered agent may request a spend")
        frozen = self._frozen()
        if frozen >= TIER_FREEZE:
            raise Exception("[EXPECTED] the agent is frozen at tier %d; only the principal can lift it" % frozen)
        value = int(amount)
        if value <= 0:
            raise Exception("[EXPECTED] a spend must declare a positive amount")
        if str(memo_uri) != "" and not _is_sha256_hex(memo_digest):
            raise Exception("[EXPECTED] a committed artifact needs a sha256 digest")

        now = self._now()
        who = normalize_address(recipient)
        decided = self._classify(who, value, str(category), now)
        if decided.get("error"):
            raise Exception("[EXPECTED] " + str(decided["error"]))
        state = str(decided["state"])
        fired = [str(r) for r in decided["rules"]]

        key = u256(int(self.spend_count))
        self.s_amount[key] = u256(value)
        self.s_recipient[key] = who
        self.s_category[key] = str(category)
        self.s_at[key] = u256(now)
        self.s_rules[key] = ",".join(fired)
        self.s_memo_uri[key] = str(memo_uri)
        self.s_memo_digest[key] = str(memo_digest).strip().lower()
        self.s_claim[key] = str(claim)[:2000]
        self.s_verdict[key] = ""
        self.s_reason[key] = ""
        self.s_confidence[key] = u256(0)
        self.s_artifact[key] = ""
        self.s_tier[key] = u256(0)
        self.s_held_at[key] = u256(0)
        self.s_state[key] = state
        self.s_outcome[key] = ""
        self.s_decided_at[key] = u256(0 if state == SPEND_HELD else now)
        self.spend_count = u256(int(self.spend_count) + 1)

        if state == SPEND_REFUSED:
            self.s_outcome[key] = OUTCOME_REFUSED
            self.s_tier[key] = u256(1 if int(self.max_tier) >= 1 else 0)
            return
        if state == SPEND_SETTLED:
            self.s_outcome[key] = OUTCOME_ALLOWED
            return
        self.s_held_at[key] = u256(now)

    @gl.public.write
    def commit_artifact(self, spend_id: int, uri: str, digest: str) -> None:
        """The agent's response window (T9). Frozen once a case resolves."""
        key = self._require_spend(spend_id)
        if gl.message.sender_address != self.agent:
            raise Exception("[EXPECTED] only the agent may commit an artifact")
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held; the artifact is frozen")
        if not _is_sha256_hex(digest):
            raise Exception("[EXPECTED] digest must be 64 hex characters")
        self.s_memo_uri[key] = str(uri)
        self.s_memo_digest[key] = str(digest).strip().lower()

    @gl.public.write
    def adjudicate(self, spend_id: int) -> None:
        """Convene the jury on a held spend.

        Every deterministic guard, and every call to the engine, runs before
        anything that could reach the network. The artifact fetch is written
        inline in both closures on purpose: ``genvm-lint`` cannot trace it
        through a helper, and a helper that lints clean at authoring time fails
        on the network.
        """
        key = self._require_spend(spend_id)
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held")

        now = self._now()
        defaults = self._defaults()
        # Coerce every value captured by the consensus closures to a plain
        # Python type. The leader runs in-process and tolerates a storage-
        # backed value; the validator is sandboxed and its closure is pickled,
        # where a storage proxy does not survive. Measured on Studio: without
        # these casts the leader returned a correct verdict and every validator
        # disagreed, deterministically, with no error anywhere in the receipt.
        memo_uri = str(self.s_memo_uri[key])
        memo_digest = str(self.s_memo_digest[key])

        if memo_uri == "":
            # T9: a party that has not yet had its response window cannot lose
            # for not using it. Refuse to convene rather than adjudicate on an
            # empty record.
            state_now = str(
                self._eng().uncommitted(int(self.s_held_at[key]), now, int(defaults["response_window_seconds"]))
            )
            if state_now == ARTIFACT_FORECLOSED:
                raise Exception("[EXPECTED] response window has not elapsed")

        fired = self._rule_ids(key)
        if not fired:
            raise Exception("[EXPECTED] held spend has no fired rule")
        candidate = [int(self.s_amount[key]), str(self.s_recipient[key]), str(self.s_category[key]), int(self.s_at[key])]
        # The engine builds the whole question from this guard's ledger - every
        # fired rule, the payment, the history - leaving only the evidence,
        # which the closures fetch themselves.
        question = json.loads(
            str(
                gl.get_contract_at(Address(str(self._eng().prompts_address())))
                .view()
                .jury_prompt(
                    self.compiled,
                    ",".join(fired),
                    str(self.s_claim[key]),
                    json.dumps(candidate),
                    json.dumps(self._history()),
                    int(spend_id) + 1,
                )
            )
        )
        template = str(question["template"])
        notes = {str(k): str(v) for k, v in question["notes"].items()}
        # What each verdict would do, so the validator can fail closed on the
        # leader's verdict without calling the engine inside the closure.
        table = {}
        for _v, _row in self._outcomes(key).items():
            table[str(_v)] = {str(_a): str(_o) for _a, _o in _row.items()}

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
            # JSON mode: the model is asked for a structured answer rather than
            # prose with JSON inside it. Measured on Bradbury: in text mode a
            # case the jury should release came back unreadable twice, which
            # fail-closed turns into a refusal. _parse_verdict still validates
            # every field - JSON mode does not guarantee the schema.
            _out = gl.nondet.exec_prompt(
                template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes)), response_format="json"
            )
            _parsed = _parse_verdict(_out)
            _parsed["artifact"] = _state
            return json.dumps(_parsed)

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
            if not _theirs:
                return False

            # The deterministic half is compared EXACTLY. This validator
            # fetched and hash-checked the artifact itself, so the leader
            # cannot lie about the evidence.
            if str(_theirs.get("artifact", "")) != _state:
                return False

            _verdict = str(_theirs.get("verdict", ""))
            if _verdict not in VERDICTS:
                return False

            # The judgement: this validator answers the SAME question, from
            # evidence it fetched and hash-checked itself. Asking a validator
            # to grade someone else's answer was measured on Studio and is not
            # stable; re-answering a narrow question is.
            _mine = _parse_verdict(
                gl.nondet.exec_prompt(
                    template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes)), response_format="json"
                )
            )
            # Fail CLOSED (validator_agrees): a leader's refusal may stand over
            # a validator that is unsure; a leader's authorization stands only
            # on agreement; a validator sure the spend is in remit vetoes
            # anything else. Confidence was applied by _parse_verdict, where a
            # hesitant in_remit becomes undetermined.
            return validator_agrees(
                leader_verdict=_verdict,
                own_verdict=_mine["verdict"],
                leader_outcome=table[_verdict][_state],
            )

        raw = gl.vm.run_nondet(leader, validator, compare_user_errors=True)
        decoded = _as_dict(raw)
        result = _parse_verdict(decoded)
        artifact = str(decoded.get("artifact", ARTIFACT_ABSENT))
        if artifact not in ARTIFACT_STATES:
            artifact = ARTIFACT_UNVERIFIED

        self.s_verdict[key] = result["verdict"]
        self.s_reason[key] = result["reason"]
        self._finalise(key, table[result["verdict"]][artifact], artifact, result["confidence"])
        if result["verdict"] == VERDICT_OUT_OF_REMIT:
            # Graduated authority: a breach at tier 2 freezes the agent; at
            # tier 3 it also revokes what the rail has not yet paid.
            freeze = freeze_tier(tier=int(self.s_tier[key]), shadow=bool(self.shadow))
            if freeze > int(self.frozen_tier):
                self.frozen_tier = u256(freeze)
                self.frozen_by = u256(int(spend_id) + 1)
            if freeze >= TIER_REVOKE:
                self.revoked_below = u256(int(self.spend_count))

    @gl.public.write
    def resolve_deadline(self, spend_id: int) -> None:
        """A hold that reached its deadline with no verdict resolves to the
        registered default. No hold is indefinite (T2)."""
        key = self._require_spend(spend_id)
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held")
        defaults = self._defaults()
        now = self._now()
        if (now - int(self.s_held_at[key])) < int(defaults["hold_deadline_seconds"]):
            raise Exception("[EXPECTED] deadline not reached")

        if self.s_memo_uri[key] == "":
            artifact = str(self._eng().uncommitted(int(self.s_held_at[key]), now, int(defaults["response_window_seconds"])))
        else:
            artifact = ARTIFACT_UNVERIFIED

        self.s_reason[key] = "deadline_default"
        self._finalise(key, str(self._outcomes(key)["deadline"][artifact]), artifact, 0)

    @gl.public.write
    def override_release(self, spend_id: int) -> None:
        """The principal's key always outranks Remit. Additive authority."""
        self._override(spend_id, OUTCOME_ALLOWED)

    @gl.public.write
    def override_refuse(self, spend_id: int) -> None:
        self._override(spend_id, OUTCOME_REFUSED)

    @gl.public.write
    def lift_freeze(self) -> None:
        """The principal's key outranks Remit: it may lift a freeze. A tier-3
        revocation stands - those payments stay unpaid; the principal can pay
        them from the rail's treasury directly. A freeze imposed by the rail's
        court is lifted on the rail."""
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may lift a freeze")
        self.frozen_tier = u256(0)
        self.frozen_by = u256(0)

    @gl.public.write
    def attach_rail(self, rail: str) -> None:
        """Once, by the principal: the rail whose court this guard obeys."""
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may attach a rail")
        if self.rail != "":
            raise Exception("[EXPECTED] a rail is already attached")
        self.rail = str(Address(rail))

    def _override(self, spend_id: int, outcome: str) -> None:
        key = self._require_spend(spend_id)
        if gl.message.sender_address != self.principal:
            raise Exception("[EXPECTED] only the principal may override")
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held")
        self.s_reason[key] = "principal_override"
        existing = self.s_artifact[key]
        self._finalise(key, outcome, existing if existing != "" else ARTIFACT_ABSENT, 0)

    # ---------------------------------------------------------------- views

    @gl.public.view
    def authorization_of(self, spend_id: int) -> str:
        """What a settlement rail asks before releasing funds.

        Under shadow mode (tier 0) a refusal is recorded but never withheld:
        the docket builds a public record while the principal decides whether
        to grant real authority.
        """
        key = self._require_spend(spend_id)
        auth = self._auth(key)
        if auth != AUTH_PENDING and self.shadow:
            return AUTH_AUTHORIZED
        return auth

    @gl.public.view
    def settlement_of(self, spend_id: int) -> str:
        """Everything a rail needs to pay a spend, in one read.

        A rail must not pay on ``authorization_of`` alone: it also needs who is
        owed, how much, and when the decision was made, so it can wait for the
        decision to finalise. ``authorization`` here ignores shadow mode - a
        shadow guard withholds nothing, so a rail must refuse to bind to one
        rather than pay refused spends.
        """
        key = self._require_spend(spend_id)
        return json.dumps(
            {
                "id": int(spend_id),
                "authorization": self._auth(key),
                "recipient": self.s_recipient[key],
                "amount": int(self.s_amount[key]),
                "decided_at": int(self.s_decided_at.get(key, u256(0))),
                "shadow": bool(self.shadow),
                "principal": str(self.principal),
                "agent": str(self.agent),
            }
        )

    @gl.public.view
    def get_spend(self, spend_id: int) -> str:
        key = self._require_spend(spend_id)
        return json.dumps(self._summarise(int(spend_id)))

    @gl.public.view
    def docket(self) -> str:
        """Every case, including shadow cases that withheld nothing."""
        out = []
        index = 0
        total = int(self.spend_count)
        while index < total:
            out.append(self._summarise(index))
            index += 1
        return json.dumps(out)

    @gl.public.view
    def mandate_info(self) -> str:
        """The mandate as registered, with who is bound by it. ``rules`` carry
        the engine's flattened view of each rule."""
        m = self._mandate()
        m.pop("errors", None)
        m["principal"] = str(self.principal)
        m["agent"] = str(self.agent)
        m["engine"] = str(self.engine)
        m["max_tier"] = int(self.max_tier)
        m["shadow"] = bool(self.shadow)
        m["spend_count"] = int(self.spend_count)
        m["release"] = "remit-guard/3"
        m["rail"] = self.rail
        m["frozen_tier"] = int(self.frozen_tier)
        m["frozen_by"] = int(self.frozen_by) - 1
        m["revoked_below"] = int(self.revoked_below)
        # The rail's court may freeze the agent too (its court_freeze view);
        # not read here, because the rail itself reads this view.
        return json.dumps(m)

    @gl.public.view
    def preview_spend(self, recipient: str, amount: int, category: str) -> str:
        """Dry-run the gate: what WOULD happen to this spend right now.

        Asks the engine the same question ``request_spend`` asks, against the
        same history, so a client can tell a user "this will be held for a
        jury" before they sign anything - and the prediction cannot drift from
        the decision the way a reimplementation in the frontend would.
        """
        value = int(amount)
        if value <= 0:
            return json.dumps({"state": "invalid", "rules": [], "reason": "amount must be positive"})
        decided = self._classify(normalize_address(recipient), value, str(category), self._now())
        return json.dumps(
            {"state": str(decided["state"]), "rules": [str(r) for r in decided["rules"]], "reason": str(decided.get("error", ""))}
        )

    def _summarise(self, index: int) -> dict:
        key = u256(int(index))
        state = self.s_state[key]
        authorization = self._auth(key)
        if authorization != AUTH_PENDING and self.shadow:
            authorization = AUTH_AUTHORIZED
        return {
            "id": int(index),
            "amount": int(self.s_amount[key]),
            "recipient": self.s_recipient[key],
            "category": self.s_category[key],
            "at": int(self.s_at[key]),
            "state": state,
            "rules": [r for r in self.s_rules[key].split(",") if r != ""],
            "memo_uri": self.s_memo_uri[key],
            "memo_digest": self.s_memo_digest[key],
            # The agent's own account of the spend. Shown to readers exactly as
            # it is shown to the jury: labelled untrusted, never as fact.
            "claim": self.s_claim[key],
            "held_at": int(self.s_held_at[key]),
            "verdict": self.s_verdict[key],
            "reason": self.s_reason[key],
            "confidence": int(self.s_confidence[key]),
            "artifact": self.s_artifact[key],
            "outcome": self.s_outcome[key],
            "tier": int(self.s_tier[key]),
            "decided_at": int(self.s_decided_at.get(key, u256(0))),
            "authorization": authorization,
            "shadow": bool(self.shadow),
        }


def _parse_verdict(raw) -> dict:
    """A jury answer as the guard counts it: read defensively
    (``_read_verdict``), then a hesitant yes is not a yes (harden_verdict).
    Applied here so the leader, every validator and the recorded result all
    follow the same rule."""
    result = _read_verdict(raw)
    result["verdict"] = harden_verdict(result["verdict"], result["confidence"])
    return result
