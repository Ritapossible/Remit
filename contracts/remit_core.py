"""Remit deterministic engine.

Pure Python. No ``gl.*``, no network, no LLM, no floats, no wall clock. Every
decision that can be made without a jury is made here, so that most of the
product's logic is testable in milliseconds without a chain.

Threat ids (T1..T10) in comments refer to ``docs/THREAT-MODEL.md``. Hard laws
referenced by number refer to ``CLAUDE.md``.

All amounts are integers in the currency's smallest unit. Passing a float
anywhere is a defect, not a rounding question.
"""

from dataclasses import dataclass

# --------------------------------------------------------------------------
# States
# --------------------------------------------------------------------------

SPEND_SETTLED = "settled"
SPEND_REFUSED = "refused"
SPEND_HELD = "held"
SPEND_STATES = (SPEND_SETTLED, SPEND_REFUSED, SPEND_HELD)

# Artifact provenance. ABSENT and FORECLOSED are deliberately distinct and
# resolve in opposite directions (T9): foreclosed means the agent had not yet
# had its response window, absent means it had and stayed silent. Collapsing
# them reintroduces the foreclosure grief this design exists to prevent.
ARTIFACT_VERIFIED = "verified"
ARTIFACT_UNVERIFIED = "unverified"
ARTIFACT_ABSENT = "absent"
ARTIFACT_FORECLOSED = "foreclosed"
ARTIFACT_STATES = (
    ARTIFACT_VERIFIED,
    ARTIFACT_UNVERIFIED,
    ARTIFACT_ABSENT,
    ARTIFACT_FORECLOSED,
)

VERDICT_IN_REMIT = "in_remit"
VERDICT_OUT_OF_REMIT = "out_of_remit"
VERDICT_UNDETERMINED = "undetermined"
VERDICTS = (VERDICT_IN_REMIT, VERDICT_OUT_OF_REMIT, VERDICT_UNDETERMINED)

OUTCOME_ALLOWED = "allowed"
OUTCOME_REFUSED = "refused"
OUTCOMES = (OUTCOME_ALLOWED, OUTCOME_REFUSED)

DEFAULT_REFUND = "refund"
DEFAULT_RELEASE = "release"
DEFAULTS_VOCAB = (DEFAULT_REFUND, DEFAULT_RELEASE)

RULE_REFLEX = "reflex"
RULE_JUDGMENT = "judgment"
RULE_TYPES = (RULE_REFLEX, RULE_JUDGMENT)

DAY_SECONDS = 86400
BPS_DENOMINATOR = 10000

REQUIRED_DEFAULTS = (
    "on_deadline",
    "on_undetermined",
    "response_window_seconds",
    "hold_deadline_seconds",
    "clawback_window_seconds",
)

# The v1 predicate vocabulary. Deliberately small: every predicate is surface
# area, and an unevaluable one is worse than a missing one.
PREDICATES_INT = (
    "amount_lte",
    "amount_gte",
    "daily_total_lte",
    "daily_total_gte",
)
PREDICATES_WINDOW_AMOUNT = ("window_total_lte", "window_total_gte")
PREDICATES_WINDOW_COUNT = ("spend_count_lte", "spend_count_gte")
PREDICATES_LIST_NAME = ("recipient_in", "recipient_not_in")
PREDICATES_STR_SET = ("category_in", "category_not_in")
PREDICATES = (
    PREDICATES_INT
    + PREDICATES_WINDOW_AMOUNT
    + PREDICATES_WINDOW_COUNT
    + PREDICATES_LIST_NAME
    + PREDICATES_STR_SET
)


class RemitError(ValueError):
    """Raised on a condition the caller must not be able to ignore.

    Hard law 7: never return a falsy default from a lookup or a guard. A guard
    that cannot fail is decoration, not evidence.
    """


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Spend:
    """One spend, prospective or historical. Amounts are smallest-unit ints."""

    amount: int
    recipient: str
    category: str
    at: int


@dataclass(frozen=True)
class BondPolicy:
    """Bond economics (T1, T2).

    Denomination is a fraction of the spend with a floor. A flat bond makes a
    large spend cheap to grief; a pure fraction makes a small spend uneconomic
    to challenge at all. The floor sets the price of attention, the fraction
    scales with what is actually at risk.

    Escalation is geometric in the challenger's *effective* loss count, so a
    griefer prices themselves out in a handful of attempts while an honest
    challenger who is usually right pays the floor forever.

    Decay is one step per ``decay_seconds`` since the last loss, and a single
    win resets the streak outright. Being right clears your record immediately;
    waiting out an escalation costs a week per step, which is what makes
    sustained griefing impractical without banning someone who had a bad week.
    """

    floor: int = 500  # smallest unit; 500 = $5.00 at USD_CENTS
    bps: int = 1000  # 10% of the spend at risk
    escalation_factor: int = 2
    max_multiplier: int = 64
    decay_seconds: int = 604800  # 7 days
    appeal_multiplier: int = 2
    reward_bps: int = 500  # 5% of the refused spend


# --------------------------------------------------------------------------
# Typed guards. Fail loudly; never coerce, never default.
# --------------------------------------------------------------------------


def _require_int(value, context):
    """A non-negative int. ``bool`` is rejected: ``isinstance(True, int)``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemitError("%s: expected int, got %r" % (context, type(value).__name__))
    if value < 0:
        raise RemitError("%s: expected non-negative, got %d" % (context, value))
    return value


def _require_str(value, context):
    if not isinstance(value, str) or value == "":
        raise RemitError("%s: expected non-empty str" % context)
    return value


def _require_one_of(value, allowed, context):
    if value not in allowed:
        raise RemitError("%s: expected one of %s, got %r" % (context, list(allowed), value))
    return value


def _require_conserved(credited, available, context):
    """Hard law 2: resolve on equality, never on an inequality.

    ``held >= committed`` once restored an already-delivered payout when a
    residue was present. If two different states satisfy the comparison, the
    comparison is wrong.
    """
    if credited != available:
        raise RemitError(
            "%s: value not conserved, credited %d against %d" % (context, credited, available)
        )
    return credited


def normalize_address(value, context="address"):
    """Lowercase and validate. Accepts ``str`` only; the chain layer widens
    this to ``str | Address`` (hard law 7) before calling in."""
    text = _require_str(value, context).strip().lower()
    if not text.startswith("0x") or len(text) < 3:
        raise RemitError("%s: not an address: %r" % (context, value))
    for ch in text[2:]:
        if ch not in "0123456789abcdef":
            raise RemitError("%s: not hex: %r" % (context, value))
    return text


# --------------------------------------------------------------------------
# Windowed aggregates over history
# --------------------------------------------------------------------------
#
# All windows are half-open ``(now - seconds, now]`` and include the spend
# being evaluated. ``daily_*`` is a rolling 86400s window, not a calendar day:
# a mandate has no unambiguous way to carry a timezone.


def _window_slice(history, seconds, now):
    floor_at = now - _require_int(seconds, "window seconds")
    return [h for h in history if floor_at < h.at <= now]


def window_total(spend, history, seconds, now):
    return spend.amount + sum(h.amount for h in _window_slice(history, seconds, now))


def window_count(spend, history, seconds, now):
    return 1 + len(_window_slice(history, seconds, now))


# --------------------------------------------------------------------------
# Predicates
# --------------------------------------------------------------------------


def sole_predicate(obj, context):
    """A ``check`` or ``when`` holds exactly one predicate in v1.

    Multiple predicates would need stated conjunction semantics. An ambiguous
    rule is worse than a missing one, so this refuses rather than assuming AND.
    """
    if not isinstance(obj, dict):
        raise RemitError("%s: expected an object" % context)
    if len(obj) != 1:
        raise RemitError("%s: expected exactly 1 predicate, got %d" % (context, len(obj)))
    name = list(obj)[0]
    return name, obj[name]


def _window_operand(operand, amount_key, context):
    if not isinstance(operand, dict):
        raise RemitError("%s: expected an object operand" % context)
    if amount_key not in operand or "seconds" not in operand:
        raise RemitError("%s: operand needs %r and 'seconds'" % (context, amount_key))
    return (
        _require_int(operand[amount_key], context + "." + amount_key),
        _require_int(operand["seconds"], context + ".seconds"),
    )


def evaluate_predicate(name, operand, spend, history, vendor_lists):
    """Evaluate one predicate against contract-read facts.

    ``spend`` and ``history`` are facts the contract read from its own storage
    (T3). Nothing a claimant supplied reaches this function.
    """
    ctx = "predicate " + str(name)
    if name not in PREDICATES:
        raise RemitError("%s: outside the v1 vocabulary" % ctx)

    if name == "amount_lte":
        return spend.amount <= _require_int(operand, ctx)
    if name == "amount_gte":
        return spend.amount >= _require_int(operand, ctx)

    if name == "daily_total_lte":
        return window_total(spend, history, DAY_SECONDS, spend.at) <= _require_int(operand, ctx)
    if name == "daily_total_gte":
        return window_total(spend, history, DAY_SECONDS, spend.at) >= _require_int(operand, ctx)

    if name in PREDICATES_WINDOW_AMOUNT:
        limit, seconds = _window_operand(operand, "amount", ctx)
        total = window_total(spend, history, seconds, spend.at)
        return total <= limit if name.endswith("_lte") else total >= limit

    if name in PREDICATES_WINDOW_COUNT:
        limit, seconds = _window_operand(operand, "count", ctx)
        count = window_count(spend, history, seconds, spend.at)
        return count <= limit if name.endswith("_lte") else count >= limit

    if name in PREDICATES_LIST_NAME:
        list_name = _require_str(operand, ctx)
        if list_name not in vendor_lists:
            # T3/hard law 7: an undefined list must not silently evaluate.
            raise RemitError("%s: vendor list %r is not defined" % (ctx, list_name))
        members = [normalize_address(a, ctx) for a in vendor_lists[list_name]]
        present = normalize_address(spend.recipient, ctx) in members
        return present if name == "recipient_in" else not present

    if name in PREDICATES_STR_SET:
        if not isinstance(operand, (list, tuple)):
            raise RemitError("%s: expected a list operand" % ctx)
        members = [_require_str(c, ctx) for c in operand]
        present = spend.category in members
        return present if name == "category_in" else not present

    raise RemitError("%s: unhandled predicate" % ctx)


# --------------------------------------------------------------------------
# Spend classification
# --------------------------------------------------------------------------


def classify_spend(mandate, spend, history):
    """Decide SETTLED / REFUSED / HELD deterministically, in the spend tx.

    Returns ``(state, rule_ids)``. Rules are evaluated in mandate order and the
    first reflex failure wins, so the result is reproducible across validators.

    This is the whole reason the gate is usable: the common path returns
    SETTLED without convening anything.
    """
    vendor_lists = mandate.get("vendor_lists", {})
    rules = mandate.get("rules", [])

    for rule in rules:
        if rule.get("type") != RULE_REFLEX:
            continue
        name, operand = sole_predicate(rule.get("check"), "rule %s check" % rule.get("id"))
        if not evaluate_predicate(name, operand, spend, history, vendor_lists):
            return SPEND_REFUSED, [rule["id"]]

    fired = []
    for rule in rules:
        if rule.get("type") != RULE_JUDGMENT:
            continue
        name, operand = sole_predicate(rule.get("when"), "rule %s when" % rule.get("id"))
        if evaluate_predicate(name, operand, spend, history, vendor_lists):
            fired.append(rule["id"])

    if fired:
        return SPEND_HELD, fired
    return SPEND_SETTLED, []


# --------------------------------------------------------------------------
# Artifact provenance
# --------------------------------------------------------------------------


def verify_artifact(committed_digest, fetched_digest):
    """Classify a committed artifact by hash. Pure; the fetch happens above.

    A digest mismatch makes the artifact UNVERIFIED, which is not evidence
    (T4). It is never silently treated as the artifact the agent promised.
    """
    committed = _require_str(committed_digest, "committed digest").strip().lower()
    if fetched_digest is None:
        return ARTIFACT_UNVERIFIED
    fetched = _require_str(fetched_digest, "fetched digest").strip().lower()
    return ARTIFACT_VERIFIED if committed == fetched else ARTIFACT_UNVERIFIED


def uncommitted_artifact(*, held_at, now, response_window_seconds):
    """Distinguish FORECLOSED from ABSENT when nothing was committed (T9).

    Inside the response window the agent has not yet had its chance, so the
    record is FORECLOSED and resolves in its favour. Outside it, the silence
    is the agent's own and the record is ABSENT.
    """
    held_at = _require_int(held_at, "held_at")
    now = _require_int(now, "now")
    window = _require_int(response_window_seconds, "response_window_seconds")
    if now < held_at:
        raise RemitError("now %d precedes held_at %d" % (now, held_at))
    return ARTIFACT_FORECLOSED if (now - held_at) < window else ARTIFACT_ABSENT


def artifact_state(*, committed_digest, fetched_digest, held_at, now, response_window_seconds):
    """Full classification, committed or not."""
    if committed_digest is None or committed_digest == "":
        return uncommitted_artifact(
            held_at=held_at, now=now, response_window_seconds=response_window_seconds
        )
    return verify_artifact(committed_digest, fetched_digest)


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def _outcome_from_default(token, context):
    _require_one_of(token, DEFAULTS_VOCAB, context)
    return OUTCOME_REFUSED if token == DEFAULT_REFUND else OUTCOME_ALLOWED


def resolve_hold(*, verdict, artifact, requires_artifact, defaults, deadline_reached):
    """Resolve a held spend to ALLOWED or REFUSED.

    Order is load-bearing:

    1. FORECLOSED wins over everything. A party that was never given its window
       cannot lose for not using it (T9).
    2. A deadline with no verdict resolves to the registered default, never to
       an indefinite hold (T2).
    3. A required artifact that is ABSENT or UNVERIFIED refuses. The principal
       chose to make it a precondition; an unverifiable one is not evidence.
    4. Otherwise the verdict decides, with UNDETERMINED falling to the
       registered default. Unproven is not guilty.
    """
    _require_one_of(artifact, ARTIFACT_STATES, "artifact state")
    for key in REQUIRED_DEFAULTS:
        if key not in defaults:
            raise RemitError("defaults: missing %r" % key)

    if artifact == ARTIFACT_FORECLOSED:
        return OUTCOME_ALLOWED

    if verdict is None:
        if deadline_reached:
            return _outcome_from_default(defaults["on_deadline"], "defaults.on_deadline")
        raise RemitError("no verdict and deadline not reached: case is not resolvable yet")

    _require_one_of(verdict, VERDICTS, "verdict")

    if requires_artifact and artifact in (ARTIFACT_ABSENT, ARTIFACT_UNVERIFIED):
        return OUTCOME_REFUSED

    if verdict == VERDICT_IN_REMIT:
        return OUTCOME_ALLOWED
    if verdict == VERDICT_OUT_OF_REMIT:
        return OUTCOME_REFUSED
    return _outcome_from_default(defaults["on_undetermined"], "defaults.on_undetermined")


def settle_hold(*, escrow, committed, outcome, vendor, principal):
    """Credit owed balances for a resolved hold.

    Hard law 1: value is never pushed. This returns credits to be added to owed
    balances, which recipients withdraw. ``emit_transfer`` credits a contract
    and destroys value sent to an EOA.

    Hard law 2: the escrow must equal the committed amount exactly.
    """
    escrow = _require_int(escrow, "escrow")
    committed = _require_int(committed, "committed")
    if escrow != committed:
        raise RemitError("escrow %d != committed %d" % (escrow, committed))
    _require_one_of(outcome, OUTCOMES, "outcome")

    target = vendor if outcome == OUTCOME_ALLOWED else principal
    credits = {normalize_address(target, "credit target"): escrow}
    _require_conserved(sum(credits.values()), escrow, "settle_hold")
    return credits


# --------------------------------------------------------------------------
# Bond economics (T1, T2)
# --------------------------------------------------------------------------


def effective_losses(*, losses, last_loss_at, now, policy):
    """Losses after decay. One step forgiven per ``decay_seconds`` elapsed."""
    losses = _require_int(losses, "losses")
    if losses == 0:
        return 0
    last_loss_at = _require_int(last_loss_at, "last_loss_at")
    now = _require_int(now, "now")
    if now < last_loss_at:
        raise RemitError("now %d precedes last_loss_at %d" % (now, last_loss_at))
    forgiven = (now - last_loss_at) // _require_int(policy.decay_seconds, "decay_seconds")
    return max(0, losses - forgiven)


def challenge_bond(*, amount, losses, last_loss_at, now, policy):
    """Required bond to challenge a settled spend of ``amount``."""
    amount = _require_int(amount, "amount")
    base = max(
        _require_int(policy.floor, "floor"),
        amount * _require_int(policy.bps, "bps") // BPS_DENOMINATOR,
    )
    n = effective_losses(losses=losses, last_loss_at=last_loss_at, now=now, policy=policy)
    multiplier = 1
    cap = _require_int(policy.max_multiplier, "max_multiplier")
    factor = _require_int(policy.escalation_factor, "escalation_factor")
    if factor < 2:
        raise RemitError("escalation_factor must be at least 2, got %d" % factor)
    for _ in range(n):
        multiplier *= factor
        if multiplier >= cap:
            multiplier = cap
            break
    return base * multiplier


def appeal_bond(*, challenge_bond_amount, policy):
    """An appeal must cost strictly more than the challenge it contests (T2)."""
    challenge_bond_amount = _require_int(challenge_bond_amount, "challenge_bond_amount")
    multiplier = _require_int(policy.appeal_multiplier, "appeal_multiplier")
    if multiplier < 2:
        raise RemitError("appeal_multiplier must be at least 2, got %d" % multiplier)
    bond = challenge_bond_amount * multiplier
    if bond <= challenge_bond_amount:
        raise RemitError("appeal bond %d does not exceed challenge bond" % bond)
    return bond


def challenge_reward(*, refused_amount, agent_standing, policy):
    """Reward for a challenge that stands, capped by the agent's standing bond.

    Capped rather than promised: paying out more than the agent posted would
    make the reward a claim on somebody who never agreed to it. The cap is
    returned plainly so the caller can report a shortfall rather than silently
    zeroing it (hard law 7).
    """
    refused_amount = _require_int(refused_amount, "refused_amount")
    agent_standing = _require_int(agent_standing, "agent_standing")
    earned = refused_amount * _require_int(policy.reward_bps, "reward_bps") // BPS_DENOMINATOR
    return min(earned, agent_standing)


def settle_challenge(*, bond, refused_amount, upheld, agent, challenger, agent_standing, policy):
    """Credit owed balances for a resolved challenge.

    A forfeited bond credits the **agent** (T1): the party that was griefed is
    the party compensated, not the protocol.
    """
    bond = _require_int(bond, "bond")
    agent_addr = normalize_address(agent, "agent")
    challenger_addr = normalize_address(challenger, "challenger")
    if agent_addr == challenger_addr:
        raise RemitError("agent and challenger must differ")

    if upheld:
        reward = challenge_reward(
            refused_amount=refused_amount, agent_standing=agent_standing, policy=policy
        )
        credits = {challenger_addr: bond + reward}
        _require_conserved(sum(credits.values()), bond + reward, "settle_challenge/upheld")
        return credits, reward  # reward is debited from the agent's standing

    credits = {agent_addr: bond}
    _require_conserved(sum(credits.values()), bond, "settle_challenge/dismissed")
    return credits, 0


# --------------------------------------------------------------------------
# Mandate validation (registration)
# --------------------------------------------------------------------------


def validate_mandate(mandate, *, stored_version, max_tier):
    """Return a list of errors. Empty means the mandate may be registered.

    Errors are collected rather than raised so registration can report every
    problem at once; ``require_valid_mandate`` is the failing-loud wrapper.
    """
    errors = []

    def bad(message):
        errors.append(message)

    if not isinstance(mandate, dict):
        return ["mandate: expected an object"]

    # 1 — version must strictly increase (T5).
    version = mandate.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        bad("version: expected int")
    elif version <= stored_version:
        bad("version: %r does not exceed stored version %r" % (version, stored_version))

    # 5 — every default is mandatory. An unstated default is a decision
    # nobody made.
    defaults = mandate.get("defaults")
    if not isinstance(defaults, dict):
        bad("defaults: expected an object")
        defaults = {}
    for key in REQUIRED_DEFAULTS:
        if key not in defaults:
            bad("defaults: missing %r" % key)
    for key in ("on_deadline", "on_undetermined"):
        if key in defaults and defaults[key] not in DEFAULTS_VOCAB:
            bad("defaults.%s: expected one of %s" % (key, list(DEFAULTS_VOCAB)))
    for key in ("response_window_seconds", "hold_deadline_seconds", "clawback_window_seconds"):
        if key in defaults:
            try:
                _require_int(defaults[key], "defaults." + key)
            except RemitError as exc:
                bad(str(exc))
    if "response_window_seconds" in defaults and "hold_deadline_seconds" in defaults:
        try:
            window = _require_int(defaults["response_window_seconds"], "w")
            deadline = _require_int(defaults["hold_deadline_seconds"], "d")
            if window >= deadline:
                # Otherwise every hold would expire while still foreclosed and
                # no case could ever resolve against a silent agent (T9/T2).
                bad("defaults: response_window_seconds must be less than hold_deadline_seconds")
        except RemitError:
            pass

    vendor_lists = mandate.get("vendor_lists", {})
    if not isinstance(vendor_lists, dict):
        bad("vendor_lists: expected an object")
        vendor_lists = {}
    for name in vendor_lists:
        if not isinstance(vendor_lists[name], (list, tuple)):
            bad("vendor_lists.%s: expected a list" % name)
            continue
        for addr in vendor_lists[name]:
            try:
                normalize_address(addr, "vendor_lists." + str(name))
            except RemitError as exc:
                bad(str(exc))

    rules = mandate.get("rules")
    if not isinstance(rules, (list, tuple)):
        return errors + ["rules: expected a list"]

    seen = set()
    for index, rule in enumerate(rules):
        where = "rules[%d]" % index
        if not isinstance(rule, dict):
            bad("%s: expected an object" % where)
            continue

        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or rule_id == "":
            bad("%s.id: expected a non-empty string" % where)
        elif rule_id in seen:  # 2 — no duplicate ids
            bad("%s.id: duplicate rule id %r" % (where, rule_id))
        else:
            seen.add(rule_id)

        rule_type = rule.get("type")
        if rule_type not in RULE_TYPES:
            bad("%s.type: expected one of %s" % (where, list(RULE_TYPES)))
            continue

        key = "check" if rule_type == RULE_REFLEX else "when"
        try:
            # 3 — predicates must be inside the v1 vocabulary, and
            # 7 — operands must be non-negative ints where ints are expected.
            name, operand = sole_predicate(rule.get(key), "%s.%s" % (where, key))
            if name not in PREDICATES:
                bad("%s.%s: predicate %r is outside the v1 vocabulary" % (where, key, name))
            elif name in PREDICATES_INT:
                _require_int(operand, "%s.%s.%s" % (where, key, name))
            elif name in PREDICATES_WINDOW_AMOUNT:
                _window_operand(operand, "amount", "%s.%s.%s" % (where, key, name))
            elif name in PREDICATES_WINDOW_COUNT:
                _window_operand(operand, "count", "%s.%s.%s" % (where, key, name))
            elif name in PREDICATES_LIST_NAME:
                # 4 — a referenced vendor list must be defined.
                list_name = _require_str(operand, "%s.%s" % (where, key))
                if list_name not in vendor_lists:
                    bad("%s.%s: vendor list %r is not defined" % (where, key, list_name))
            elif name in PREDICATES_STR_SET:
                if not isinstance(operand, (list, tuple)) or not operand:
                    bad("%s.%s.%s: expected a non-empty list" % (where, key, name))
        except RemitError as exc:
            bad(str(exc))

        if rule_type == RULE_JUDGMENT:
            if not isinstance(rule.get("ask"), str) or not rule.get("ask"):
                bad("%s.ask: expected a non-empty string" % where)
            on_breach = rule.get("on_breach")
            if not isinstance(on_breach, dict) or "tier" not in on_breach:
                bad("%s.on_breach: expected an object with 'tier'" % where)
            else:
                try:
                    # 6 — a rule may not request more authority than granted.
                    tier = _require_int(on_breach["tier"], "%s.on_breach.tier" % where)
                    if tier > max_tier:
                        bad(
                            "%s.on_breach.tier: %d exceeds registered max_tier %d"
                            % (where, tier, max_tier)
                        )
                except RemitError as exc:
                    bad(str(exc))
            if rule.get("requires_artifact") and not isinstance(rule.get("requires_artifact"), bool):
                bad("%s.requires_artifact: expected a bool" % where)
            has_uri = bool(rule.get("context_uri"))
            has_digest = bool(rule.get("context_digest"))
            if has_uri != has_digest:
                # An unpinned context is not evidence (T5/T10).
                bad("%s: context_uri and context_digest must be given together" % where)

    return errors


def mandate_notices(mandate):
    """Advisories that are not rejections.

    The one that matters: a mandate with no judgment rules does not need
    GenLayer. Saying so is more useful than taking the deployment.
    """
    notices = []
    rules = mandate.get("rules", []) if isinstance(mandate, dict) else []
    judgments = [r for r in rules if isinstance(r, dict) and r.get("type") == RULE_JUDGMENT]
    if not judgments:
        notices.append(
            "This mandate contains no judgment rules. Every rule in it is "
            "arithmetic a plain smart contract would evaluate faster and more "
            "cheaply. Remit will register it, but it is not buying you anything."
        )
    return notices


def require_valid_mandate(mandate, *, stored_version, max_tier):
    """Raise unless the mandate is registerable. Returns its notices."""
    errors = validate_mandate(mandate, stored_version=stored_version, max_tier=max_tier)
    if errors:
        raise RemitError("mandate rejected: " + "; ".join(errors))
    return mandate_notices(mandate)
