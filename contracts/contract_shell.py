"""Remit chain layer: storage, entrypoints, and the consensus block.

Built into a single deployable file by ``deploy/build_contract.py``, which
prepends the pinned runner header and inlines ``remit_core`` and
``remit_prompts``. Do not edit the build output.

**Remit holds no funds.** It authorises; a rail settles. This was forced by a
measured constraint and is the better design for it: introspection of the live
runner (see ``docs/ARCHITECTURE.md`` §11) shows the only value-movement
primitive is ``ContractProxy.emit_transfer``, a contract-to-contract call —
which is exactly why value sent to an externally owned account is destroyed. A
gate that never takes custody cannot destroy anything, and a provisional
refusal that an appeal reverses costs nothing because no value ever moved.

Hard laws enforced here (see CLAUDE.md):

- **Never custody, never push.** There is no ``emit_transfer`` in this file and
  no payable entrypoint. Structurally, not by convention.
- **The fetch is inline in both closures.** ``genvm-lint`` cannot trace a
  ``gl.nondet.web`` call through a helper, so it is written out twice on
  purpose. Do not refactor it.
- **Cheap classified guards first.** A view call into a codeless address is
  uncatchable and hangs to the leader timeout, so every deterministic check
  runs before anything that could reach an unknown address.
- **ACCEPTED is not success.** Consensus agreeing on a refusal is a network
  success and a spend refusal. State is the record.
"""

AUTH_AUTHORIZED = "authorized"
AUTH_REFUSED = "refused"
AUTH_PENDING = "pending"


class RemitGuard(gl.Contract):
    # --- identity and authority ---
    principal: Address
    agent: Address
    max_tier: u256
    shadow: bool

    # --- the pinned mandate (T5) ---
    mandate_uri: str
    mandate_digest: str
    mandate_version: u256

    # --- registered defaults; no implicit fallbacks ---
    d_on_deadline: str
    d_on_undetermined: str
    d_response_window: u256
    d_hold_deadline: u256
    d_clawback_window: u256

    # --- rules, flattened (a mandate is small; this avoids layout risk) ---
    rule_ids: DynArray[str]
    rule_kind: TreeMap[str, str]
    rule_pred: TreeMap[str, str]
    rule_a: TreeMap[str, u256]
    rule_b: TreeMap[str, u256]
    rule_s: TreeMap[str, str]
    rule_needs_artifact: TreeMap[str, bool]
    rule_tier: TreeMap[str, u256]
    rule_ask: TreeMap[str, str]

    # "listname|0xaddress" -> True
    vendor_member: TreeMap[str, bool]

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

    # "listname|0xaddress", in registration order. Membership is asked through
    # vendor_member; this exists so anyone can read who an agent may pay.
    # Appended last: storage layout is position-sensitive.
    vendor_entries: DynArray[str]

    # ----------------------------------------------------------------- init

    def __init__(self, agent: str, mandate_json: str, max_tier: int, shadow: bool):
        mandate = json.loads(mandate_json)
        errors = validate_mandate(mandate, stored_version=0, max_tier=int(max_tier))
        if errors:
            raise Exception("[EXPECTED] mandate rejected: " + "; ".join(errors))

        self.principal = gl.message.sender_address
        self.agent = Address(agent)
        self.max_tier = u256(int(max_tier))
        self.shadow = bool(shadow)

        self.mandate_uri = str(mandate.get("mandate_uri", ""))
        self.mandate_digest = str(mandate.get("mandate_digest", "")).lower()
        self.mandate_version = u256(int(mandate["version"]))

        defaults = mandate["defaults"]
        self.d_on_deadline = str(defaults["on_deadline"])
        self.d_on_undetermined = str(defaults["on_undetermined"])
        self.d_response_window = u256(int(defaults["response_window_seconds"]))
        self.d_hold_deadline = u256(int(defaults["hold_deadline_seconds"]))
        self.d_clawback_window = u256(int(defaults["clawback_window_seconds"]))

        for list_name in mandate.get("vendor_lists", {}):
            for member in mandate["vendor_lists"][list_name]:
                entry = str(list_name) + "|" + normalize_address(member)
                self.vendor_member[entry] = True
                self.vendor_entries.append(entry)

        for rule in mandate["rules"]:
            rule_id = str(rule["id"])
            kind = str(rule["type"])
            source = rule["check"] if kind == RULE_REFLEX else rule["when"]
            name, operand = sole_predicate(source, "rule " + rule_id)

            operand_a = 0
            operand_b = 0
            operand_s = ""
            if name in PREDICATES_INT:
                operand_a = int(operand)
            elif name in PREDICATES_WINDOW_AMOUNT:
                operand_a = int(operand["amount"])
                operand_b = int(operand["seconds"])
            elif name in PREDICATES_WINDOW_COUNT:
                operand_a = int(operand["count"])
                operand_b = int(operand["seconds"])
            elif name in PREDICATES_LIST_NAME:
                operand_s = str(operand)
            else:
                operand_s = ",".join([str(c) for c in operand])

            self.rule_ids.append(rule_id)
            self.rule_kind[rule_id] = kind
            self.rule_pred[rule_id] = name
            self.rule_a[rule_id] = u256(operand_a)
            self.rule_b[rule_id] = u256(operand_b)
            self.rule_s[rule_id] = operand_s
            self.rule_needs_artifact[rule_id] = bool(rule.get("requires_artifact", False))
            self.rule_tier[rule_id] = u256(int(rule.get("on_breach", {}).get("tier", 0)))
            self.rule_ask[rule_id] = str(rule.get("ask", ""))

        self.spend_count = u256(0)

    # -------------------------------------------------------------- helpers

    def _now(self) -> int:
        return int(datetime.datetime.now().timestamp())

    def _in_list(self, list_name: str, who: str) -> bool:
        key = str(list_name) + "|" + normalize_address(who)
        return bool(self.vendor_member.get(key, False))

    def _history(self) -> list:
        """Spends that consumed budget: settled or held. A refused spend never
        moved value and must not count against a later one."""
        out = []
        index = 0
        total = int(self.spend_count)
        while index < total:
            key = u256(index)
            if self.s_state[key] in (SPEND_SETTLED, SPEND_HELD):
                out.append(
                    Spend(
                        amount=int(self.s_amount[key]),
                        recipient=self.s_recipient[key],
                        category=self.s_category[key],
                        at=int(self.s_at[key]),
                    )
                )
            index += 1
        return out

    def _evaluate(self, rule_id: str, candidate, history) -> bool:
        """List predicates are answered against storage membership flags rather
        than through the engine's vendor-list path, because enumerating a list
        on chain would be unbounded."""
        name = self.rule_pred[rule_id]
        if name in PREDICATES_LIST_NAME:
            present = self._in_list(self.rule_s[rule_id], candidate.recipient)
            return present if name == "recipient_in" else not present

        if name in PREDICATES_INT:
            operand = int(self.rule_a[rule_id])
        elif name in PREDICATES_WINDOW_AMOUNT:
            operand = {"amount": int(self.rule_a[rule_id]), "seconds": int(self.rule_b[rule_id])}
        elif name in PREDICATES_WINDOW_COUNT:
            operand = {"count": int(self.rule_a[rule_id]), "seconds": int(self.rule_b[rule_id])}
        else:
            operand = [c for c in self.rule_s[rule_id].split(",") if c != ""]
        return evaluate_predicate(name, operand, candidate, history, {})

    def _classify(self, candidate, history):
        for rule_id in self.rule_ids:
            if self.rule_kind[rule_id] != RULE_REFLEX:
                continue
            if not self._evaluate(rule_id, candidate, history):
                return SPEND_REFUSED, [rule_id]
        fired = []
        for rule_id in self.rule_ids:
            if self.rule_kind[rule_id] != RULE_JUDGMENT:
                continue
            if self._evaluate(rule_id, candidate, history):
                fired.append(rule_id)
        if fired:
            return SPEND_HELD, fired
        return SPEND_SETTLED, []

    def _defaults(self) -> dict:
        return {
            "on_deadline": self.d_on_deadline,
            "on_undetermined": self.d_on_undetermined,
            "response_window_seconds": int(self.d_response_window),
            "hold_deadline_seconds": int(self.d_hold_deadline),
            "clawback_window_seconds": int(self.d_clawback_window),
        }

    def _rule_context(self) -> list:
        """The arithmetic limits a judgment rule exists to protect.

        Without these a structuring question is unjudgeable: "is this one
        purchase split?" cannot be answered without knowing the cap it would
        be splitting under.
        """
        out = []
        for rule_id in self.rule_ids:
            if self.rule_kind[rule_id] != RULE_REFLEX:
                continue
            name = self.rule_pred[rule_id]
            if name == "amount_lte":
                out.append("per-payment cap: %d (smallest unit)" % int(self.rule_a[rule_id]))
            elif name == "daily_total_lte":
                out.append(
                    "cap on the rolling 86400-second total: %d (smallest unit)"
                    % int(self.rule_a[rule_id])
                )
        return out

    def _needs_artifact(self, key) -> bool:
        for rule_id in self.s_rules[key].split(","):
            if rule_id != "" and bool(self.rule_needs_artifact.get(rule_id, False)):
                return True
        return False

    def _tier_for(self, key) -> int:
        tier = 0
        for rule_id in self.s_rules[key].split(","):
            if rule_id != "":
                candidate = int(self.rule_tier.get(rule_id, 0))
                if candidate > tier:
                    tier = candidate
        cap = int(self.max_tier)
        return tier if tier < cap else cap

    def _require_spend(self, spend_id: int):
        if int(spend_id) < 0 or int(spend_id) >= int(self.spend_count):
            raise Exception("[EXPECTED] unknown spend")
        return u256(int(spend_id))

    def _finalise(self, key, outcome: str, artifact: str, confidence: int) -> None:
        self.s_state[key] = SPEND_SETTLED if outcome == OUTCOME_ALLOWED else SPEND_REFUSED
        self.s_outcome[key] = outcome
        self.s_artifact[key] = artifact
        self.s_confidence[key] = u256(int(confidence))
        self.s_tier[key] = u256(self._tier_for(key) if outcome == OUTCOME_REFUSED else 0)

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

        Remit takes no custody. ``amount`` is declared, not sent.
        """
        if gl.message.sender_address != self.agent:
            raise Exception("[EXPECTED] only the registered agent may request a spend")
        value = int(amount)
        if value <= 0:
            raise Exception("[EXPECTED] a spend must declare a positive amount")
        if str(memo_uri) != "" and not _is_sha256_hex(memo_digest):
            raise Exception("[EXPECTED] a committed artifact needs a sha256 digest")

        now = self._now()
        candidate = Spend(
            amount=value,
            recipient=normalize_address(recipient),
            category=str(category),
            at=now,
        )
        state, fired = self._classify(candidate, self._history())

        key = u256(int(self.spend_count))
        self.s_amount[key] = u256(value)
        self.s_recipient[key] = candidate.recipient
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

        Every deterministic guard runs before anything that could reach the
        network (hard law 6). The artifact fetch is written inline in both
        closures on purpose: ``genvm-lint`` cannot trace it through a helper,
        and a helper that lints clean at authoring time fails on the network.
        """
        key = self._require_spend(spend_id)
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held")

        now = self._now()
        held_at = int(self.s_held_at[key])
        window = int(self.d_response_window)
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
            if uncommitted_artifact(
                held_at=held_at, now=now, response_window_seconds=window
            ) == ARTIFACT_FORECLOSED:
                raise Exception("[EXPECTED] response window has not elapsed")

        fired = [r for r in self.s_rules[key].split(",") if r != ""]
        if not fired:
            raise Exception("[EXPECTED] held spend has no fired rule")
        rule_id = str(fired[0])
        ask = str(self.rule_ask[rule_id])
        needs_artifact = self._needs_artifact(key)

        window_seconds = int(self.rule_b[rule_id]) or 3600
        history = self._history()
        candidate = Spend(
            amount=int(self.s_amount[key]),
            recipient=str(self.s_recipient[key]),
            category=str(self.s_category[key]),
            at=int(self.s_at[key]),
        )
        prior = [h for h in history if h.at < candidate.at]
        recent = []
        for h in sorted(prior, key=lambda x: -x.at)[:8]:
            if (candidate.at - h.at) <= window_seconds:
                recent.append((h.amount, h.recipient, candidate.at - h.at, h.category))
        facts = build_facts_lines(
            recent=recent,
            amount=candidate.amount,
            recipient=candidate.recipient,
            category=candidate.category,
            spend_index=int(spend_id) + 1,
            window_count=window_count(candidate, prior, window_seconds, candidate.at),
            window_seconds=window_seconds,
            window_total=window_total(candidate, prior, window_seconds, candidate.at),
            daily_total=window_total(candidate, prior, DAY_SECONDS, candidate.at),
            rule_id=rule_id,
        )
        claim = str(self.s_claim[key])
        facts = [str(f) for f in facts]
        rule_context = [str(c) for c in self._rule_context()]

        def leader() -> str:
            _state = ARTIFACT_ABSENT
            _text = ""
            if memo_uri != "":
                _state = ARTIFACT_UNVERIFIED
                try:
                    # INLINE fetch — do not factor this into a helper.
                    _resp = gl.nondet.web.get(memo_uri)
                    _raw = _resp.body
                    if isinstance(_raw, str):
                        _raw = _raw.encode("utf-8")
                    if hashlib.sha256(_raw).hexdigest().lower() == memo_digest:
                        _state = ARTIFACT_VERIFIED
                        _text = _raw.decode("utf-8", "replace")[:3000]
                except Exception:
                    _state = ARTIFACT_UNVERIFIED
            _out = gl.nondet.exec_prompt(
                build_verdict_prompt(
                    ask=ask,
                    facts_lines=facts,
                    artifact_state=_state,
                    artifact_text=_text,
                    claim_text=claim,
                    rule_context=rule_context,
                )
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
                    # INLINE fetch again — the duplication is deliberate.
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

            # The judgement: this validator answers the SAME structured
            # question, from evidence it fetched and hash-checked itself.
            #
            # Asking a validator to grade someone else's answer instead was
            # measured on Studio and is not stable: models split roughly evenly
            # on "is this defensible?", which fails consensus on exactly the
            # questions this product exists to answer. Re-answering a narrow,
            # well-specified question is far more determinate than grading a
            # verdict.
            _mine = _parse_verdict(
                gl.nondet.exec_prompt(
                    build_verdict_prompt(
                        ask=ask,
                        facts_lines=facts,
                        artifact_state=_state,
                        artifact_text=_text,
                        claim_text=claim,
                        rule_context=rule_context,
                    )
                )
            )
            if _mine["verdict"] == _verdict:
                return True
            # A validator that is itself unsure does not get to veto a
            # colleague who reached a definite answer on the same record. Two
            # validators reaching opposite DEFINITE answers is a real
            # disagreement, and that is what the appeal path is for.
            return _mine["verdict"] == VERDICT_UNDETERMINED

        raw = gl.vm.run_nondet(leader, validator, compare_user_errors=True)
        decoded = _as_dict(raw)
        result = _parse_verdict(decoded)
        artifact = str(decoded.get("artifact", ARTIFACT_ABSENT))
        if artifact not in ARTIFACT_STATES:
            artifact = ARTIFACT_UNVERIFIED

        self.s_verdict[key] = result["verdict"]
        self.s_reason[key] = result["reason"]
        outcome = resolve_hold(
            verdict=result["verdict"],
            artifact=artifact,
            requires_artifact=needs_artifact,
            defaults=self._defaults(),
            deadline_reached=False,
        )
        self._finalise(key, outcome, artifact, result["confidence"])

    @gl.public.write
    def resolve_deadline(self, spend_id: int) -> None:
        """A hold that reached its deadline with no verdict resolves to the
        registered default. No hold is indefinite (T2)."""
        key = self._require_spend(spend_id)
        if self.s_state[key] != SPEND_HELD:
            raise Exception("[EXPECTED] spend is not held")
        if (self._now() - int(self.s_held_at[key])) < int(self.d_hold_deadline):
            raise Exception("[EXPECTED] deadline not reached")

        if self.s_memo_uri[key] == "":
            artifact = uncommitted_artifact(
                held_at=int(self.s_held_at[key]),
                now=self._now(),
                response_window_seconds=int(self.d_response_window),
            )
        else:
            artifact = ARTIFACT_UNVERIFIED

        outcome = resolve_hold(
            verdict=None,
            artifact=artifact,
            requires_artifact=self._needs_artifact(key),
            defaults=self._defaults(),
            deadline_reached=True,
        )
        self.s_reason[key] = "deadline_default"
        self._finalise(key, outcome, artifact, 0)

    @gl.public.write
    def override_release(self, spend_id: int) -> None:
        """The principal's key always outranks Remit. Additive authority."""
        self._override(spend_id, OUTCOME_ALLOWED)

    @gl.public.write
    def override_refuse(self, spend_id: int) -> None:
        self._override(spend_id, OUTCOME_REFUSED)

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
        state = self.s_state[key]
        if state == SPEND_HELD:
            return AUTH_PENDING
        if self.s_outcome[key] == OUTCOME_ALLOWED:
            return AUTH_AUTHORIZED
        if self.shadow:
            return AUTH_AUTHORIZED
        return AUTH_REFUSED

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
        rules = []
        for rule_id in self.rule_ids:
            rules.append(
                {
                    "id": rule_id,
                    "type": self.rule_kind[rule_id],
                    "predicate": self.rule_pred[rule_id],
                    "a": int(self.rule_a[rule_id]),
                    "b": int(self.rule_b[rule_id]),
                    "s": self.rule_s[rule_id],
                    "requires_artifact": bool(self.rule_needs_artifact[rule_id]),
                    "tier": int(self.rule_tier[rule_id]),
                    "ask": self.rule_ask[rule_id],
                }
            )
        return json.dumps(
            {
                "principal": str(self.principal),
                "agent": str(self.agent),
                "max_tier": int(self.max_tier),
                "shadow": bool(self.shadow),
                "mandate_uri": self.mandate_uri,
                "mandate_digest": self.mandate_digest,
                "mandate_version": int(self.mandate_version),
                "defaults": self._defaults(),
                "rules": rules,
                "vendor_lists": self._vendor_lists(),
                "spend_count": int(self.spend_count),
            }
        )

    @gl.public.view
    def preview_spend(self, recipient: str, amount: int, category: str) -> str:
        """Dry-run the gate: what WOULD happen to this spend right now.

        Runs the same ``_classify`` the real spend runs, against the same
        history, so a client can tell a user "this will be held for a jury"
        before they sign anything. It is a view, so it costs nothing and
        changes nothing — and because it is the contract's own code path, the
        prediction cannot drift from the decision the way a reimplementation
        in the frontend would.
        """
        value = int(amount)
        if value <= 0:
            return json.dumps({"state": "invalid", "rules": [], "reason": "amount must be positive"})
        candidate = Spend(
            amount=value,
            recipient=normalize_address(recipient),
            category=str(category),
            at=self._now(),
        )
        state, fired = self._classify(candidate, self._history())
        return json.dumps({"state": state, "rules": [str(r) for r in fired], "reason": ""})

    def _vendor_lists(self) -> dict:
        out = {}
        for entry in self.vendor_entries:
            name, _, addr = str(entry).partition("|")
            if name not in out:
                out[name] = []
            out[name].append(addr)
        return out

    def _summarise(self, index: int) -> dict:
        key = u256(int(index))
        state = self.s_state[key]
        if state == SPEND_HELD:
            authorization = AUTH_PENDING
        elif self.s_outcome[key] == OUTCOME_ALLOWED or self.shadow:
            authorization = AUTH_AUTHORIZED
        else:
            authorization = AUTH_REFUSED
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
            "authorization": authorization,
            "shadow": bool(self.shadow),
        }


def _is_sha256_hex(value) -> bool:
    text = str(value).strip().lower()
    if len(text) != 64:
        return False
    for ch in text:
        if ch not in "0123456789abcdef":
            return False
    return True


def _is_defensible(raw) -> bool:
    """Read a validator review. Anything unreadable is a disagreement.

    Failing closed here is deliberate: an unparseable review must not be
    allowed to wave a leader's verdict through.
    """
    data = raw
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    if isinstance(data, str):
        text = data.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            data = json.loads(text)
        except Exception:
            return False
    if not isinstance(data, dict):
        return False
    for alias in ("defensible", "valid", "agree", "acceptable"):
        if alias in data:
            value = data[alias]
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "yes", "1")
    return False


def _as_dict(value) -> dict:
    """Decode a consensus payload into a dict, however it arrives.

    A leader's return value reaches the validator JSON-encoded, so a single
    ``json.loads`` yields a *string* rather than an object. Calling ``.get`` on
    that raises, the validator closure errors, and the error counts as a
    disagreement — which is how a correct verdict came to be rejected by every
    validator with nothing in the receipt pointing at the cause.

    So decode until it is a dict, and return an empty dict rather than raising.
    """
    data = value
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    elif not isinstance(data, (dict, str)):
        # A leader's value does not arrive as a plain str. Measured on Studio
        # with a per-predicate consensus readout: isinstance(x, str) is False,
        # yet "verified" in str(x) is True — the payload is reachable only
        # through str(). Returning {} for anything unrecognised is what made a
        # correct verdict look like unanimous disagreement.
        data = str(data)
    for _ in range(4):
        if isinstance(data, dict):
            return data
        if not isinstance(data, str):
            return {}
        text = data.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start and not text.startswith('"'):
            text = text[start : end + 1]
        try:
            data = json.loads(text)
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _parse_verdict(raw) -> dict:
    """Defensive parsing of an LLM response.

    Models return unpredictable shapes. Accept a dict or a string, strip
    wrapping prose, alias the keys models actually use, and coerce the
    confidence. Anything that cannot be read as one of the three verdicts is
    UNDETERMINED, which resolves to the registered default rather than to a
    guess.
    """
    data = _as_dict(raw)

    verdict = ""
    for alias in ("verdict", "answer", "decision", "result", "label"):
        if alias in data and isinstance(data[alias], str):
            verdict = data[alias].strip().lower().replace("-", "_").replace(" ", "_")
            break
    if verdict in ("in_remit", "inremit", "within_remit", "allowed", "yes"):
        verdict = VERDICT_IN_REMIT
    elif verdict in ("out_of_remit", "outofremit", "outside_remit", "refused", "no"):
        verdict = VERDICT_OUT_OF_REMIT
    else:
        verdict = VERDICT_UNDETERMINED

    reason = ""
    for alias in ("reason", "reason_code", "code", "rationale"):
        if alias in data and isinstance(data[alias], str):
            reason = data[alias].strip().lower()[:64]
            break

    confidence = 0
    for alias in ("confidence", "certainty", "score"):
        if alias in data:
            try:
                confidence = int(float(str(data[alias]).strip().rstrip("%")))
            except Exception:
                confidence = 0
            break
    if confidence < 0:
        confidence = 0
    if confidence > 100:
        confidence = 100

    return {"verdict": verdict, "reason": reason, "confidence": confidence}
