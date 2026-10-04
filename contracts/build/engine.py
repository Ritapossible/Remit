# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

import datetime
import hashlib
import json
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# GENERATED FILE - do not edit.
# Built by deploy/build_contract.py from:
#   contracts/remit_core.py       deterministic engine (pure, chain-free)
#   contracts/remit_prompts.py    prompt construction
#   contracts/jury_common.py      reading a jury's answer (guard, rail)
#   contracts/*_shell.py          storage, entrypoints, consensus block
# ---------------------------------------------------------------------------


# --- remit_core.py -----------------------------------------------------

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
# ``recipient_*`` windows count only payments to the same recipient as the
# spend being evaluated. That is the shape of a split purchase: one order, one
# vendor, several payments. An agent-wide count cannot express it, and fires on
# unrelated spending to different vendors.
PREDICATES_WINDOW_AMOUNT = (
    "window_total_lte",
    "window_total_gte",
    "recipient_total_lte",
    "recipient_total_gte",
)
PREDICATES_WINDOW_COUNT = (
    "spend_count_lte",
    "spend_count_gte",
    "recipient_count_lte",
    "recipient_count_gte",
)
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


def is_category(value):
    """A category is a label, not prose: 1-40 ASCII letters, digits, spaces,
    '_', '.' or '-'. It reaches the jury's FACTS block, so a category carrying
    newlines or headings could pose as a fact (T3/T4)."""
    text = str(value)
    if len(text) < 1 or len(text) > 40:
        return False
    for ch in text:
        if not (ch.isascii() and (ch.isalnum() or ch in " _.-")):
            return False
    return True


def same_recipient(spend, history):
    """Prior spends to the same recipient as ``spend``. Addresses are compared
    normalised, so case cannot split one vendor into two."""
    mine = normalize_address(spend.recipient, "recipient")
    return [h for h in history if normalize_address(h.recipient, "recipient") == mine]


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

    if name.startswith("recipient_") and name not in PREDICATES_LIST_NAME:
        history = same_recipient(spend, history)

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
# A split is one purchase: its first slice waits for the ruling on the rest
# --------------------------------------------------------------------------

SPLIT_PREDICATES = ("recipient_total_lte", "recipient_total_gte", "recipient_count_lte", "recipient_count_gte")
SPLIT_PENDING = "pending"
SPLIT_REFUSED = "refused"


def split_windows(rules):
    """``{rule_id: seconds}`` for the judgment rules that ask whether payments
    to one vendor are one purchase split under the cap. ``rules`` are the
    guard's flattened rules (``predicate`` and window ``b``)."""
    out = {}
    for r in rules:
        if r.get("type") == RULE_JUDGMENT and r.get("predicate") in SPLIT_PREDICATES:
            out[str(r["id"])] = _require_int(r.get("b"), "rule %s window" % r.get("id"))
    return out


def split_hold(spend, later, rules):
    """Whether an authorized payment must wait for, or fall with, a later one.

    The structuring trigger holds the payment that takes a vendor over the cap.
    The payment under the cap was authorized first, and without this the rail
    would pay it: the gate caught the second slice, not the split. So a
    payment is linked to every later payment to the same vendor that a split
    rule held, inside that rule's window:

    - while a linked payment is still held, this one waits (``pending``);
    - if a linked payment was refused, and split rules were the only rules it
      fired, this one is refused with it (``refused``): the ruling was that
      they are one purchase;
    - otherwise it pays (``""``). A refusal that also involved another rule
      (purpose, say) is not read as a ruling on the split.

    ``spend`` and ``later`` are guard summaries (``id``, ``recipient``, ``at``,
    ``state``, ``rules``, ``outcome``).
    """
    windows = split_windows(rules)
    mine = normalize_address(spend["recipient"], "recipient")
    result = ""
    for other in later:
        if int(other["id"]) <= int(spend["id"]):
            continue
        if normalize_address(other["recipient"], "recipient") != mine:
            continue
        fired = [str(r) for r in other["rules"]]
        reach = 0
        for r in fired:
            if windows.get(r, 0) > reach:
                reach = windows[r]
        # Windows are half-open: a payment counts toward a later one while
        # later.at - seconds < payment.at.
        if reach <= 0 or int(other["at"]) - int(spend["at"]) >= reach:
            continue
        if other["state"] == SPEND_HELD:
            result = SPLIT_PENDING if result == "" else result
        elif other["outcome"] == OUTCOME_REFUSED and all(r in windows for r in fired):
            return SPLIT_REFUSED
    return result


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


# Validators whose own reading is "in_remit" at lower confidence than this are
# counted as unsure. Authorising money on a hesitant yes is the failure mode a
# gate exists to prevent; refusing on a hesitant no costs only a resubmission.
MIN_IN_REMIT_CONFIDENCE = 60


def harden_verdict(verdict, confidence):
    """A hesitant "in_remit" is an "undetermined". Applied to every parsed
    verdict, leader and validator alike, so the rule is symmetric."""
    _require_one_of(verdict, VERDICTS, "verdict")
    if verdict == VERDICT_IN_REMIT and int(confidence) < MIN_IN_REMIT_CONFIDENCE:
        return VERDICT_UNDETERMINED
    return verdict


def validator_agrees(*, leader_verdict, own_verdict, leader_outcome):
    """Does a validator accept the leader's verdict? The jury fails CLOSED.

    - The same verdict is agreement.
    - A leader whose verdict REFUSES the spend may stand over a validator that
      is unsure. Doubt does not release money.
    - A leader whose verdict ALLOWS the spend stands only on agreement. One
      confident "in_remit" over a committee of unsure validators is rejected.
    - A validator that is itself sure the spend is in remit vetoes any other
      answer. Opposite definite readings are a real disagreement; the round
      fails and the hold runs to its registered deadline default.

    ``leader_outcome`` is what the leader's verdict resolves to under this
    mandate's defaults (``resolve_hold``), so an "undetermined" that the
    mandate maps to release is treated as permissive, not as doubt.
    """
    _require_one_of(leader_verdict, VERDICTS, "leader verdict")
    _require_one_of(own_verdict, VERDICTS, "own verdict")
    _require_one_of(leader_outcome, OUTCOMES, "leader outcome")
    if leader_verdict == own_verdict:
        return True
    if own_verdict == VERDICT_IN_REMIT:
        return False
    return leader_outcome == OUTCOME_REFUSED


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
    """Resolve a hold into a credit ledger.

    Hard law 1: Remit never takes custody and never moves value. This returns
    who is owed what; a settlement rail acts on it. The proxy transfer
    primitive in the runner is a contract-to-contract call, which is precisely
    why value routed through it to an externally owned account is destroyed -
    a gate that holds nothing cannot destroy anything.

    Hard law 2: the amounts must match exactly. An inequality here is satisfied
    by two different states, so it is the wrong comparison.
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
# Challenges and graduated authority (T1, T7)
#
# A payment that cleared without a jury stays open to a bonded challenge for
# the mandate's clawback window. The jury answers the challenged rule's own
# question about that payment. Upholding is the dangerous direction here - it
# blocks or claws back a payment, pays the challenger from the agent's bond and
# can freeze the agent - so it is the answer that needs agreement, and doubt
# dismisses.
# --------------------------------------------------------------------------

CHALLENGE_OPEN = "open"
CHALLENGE_UPHELD = "upheld"
CHALLENGE_DISMISSED = "dismissed"
CHALLENGE_LAPSED = "lapsed"

MIN_UPHELD_CONFIDENCE = 60

# Tier semantics on a breach (a refusal by the guard's jury, or an upheld
# challenge): 1 refuses or claws back the payment; 2 also freezes the agent -
# no new spend is authorized until the principal lifts it; 3 also revokes every
# authorization the rail has not yet paid (by spend index: ``is_revoked``).
TIER_FREEZE = 2
TIER_REVOKE = 3


def harden_challenge(verdict, confidence):
    """A hesitant breach is not a breach: the burden is on the challenger."""
    _require_one_of(verdict, VERDICTS, "verdict")
    if verdict == VERDICT_OUT_OF_REMIT and int(confidence) < MIN_UPHELD_CONFIDENCE:
        return VERDICT_UNDETERMINED
    return verdict


def challenge_agrees(*, leader_verdict, own_verdict):
    """Does a validator accept the leader's ruling on a challenge? The mirror
    of ``validator_agrees``.

    - The same verdict is agreement.
    - A leader that UPHOLDS (out_of_remit) stands only on agreement.
    - A validator that is itself sure of the breach vetoes a dismissal; the
      round fails and the challenge runs to its deadline, where it lapses and
      the bond is returned.
    - Otherwise both readings dismiss, and that is agreement.
    """
    _require_one_of(leader_verdict, VERDICTS, "leader verdict")
    _require_one_of(own_verdict, VERDICTS, "own verdict")
    if leader_verdict == own_verdict:
        return True
    if leader_verdict == VERDICT_OUT_OF_REMIT:
        return False
    return own_verdict != VERDICT_OUT_OF_REMIT


def challenge_error(*, spend, rule, challenger, agent, now, clawback_window_seconds):
    """Why a challenge may not be opened, or "" if it may.

    ``spend`` is the guard's summary of the payment; ``rule`` the mandate rule
    the challenger says it breached (or None). Only a payment that cleared
    WITHOUT a jury is challengeable: a jury's verdict is reviewed by GenLayer's
    own appeal, and a principal's override is the principal's own decision.
    """
    if spend.get("authorization") != "authorized":
        return "only an authorized payment can be challenged"
    if str(spend.get("verdict", "")) != "" or str(spend.get("reason", "")) != "":
        return "this payment was decided by a jury or by the principal; appeal that decision instead"
    if rule is None or rule.get("type") != RULE_JUDGMENT:
        return "a challenge must name one of the mandate's judgment rules"
    if normalize_address(challenger, "challenger") == normalize_address(agent, "agent"):
        return "the agent cannot challenge its own payment"
    decided_at = int(spend.get("decided_at", 0))
    if decided_at <= 0 or now - decided_at > int(clawback_window_seconds):
        return "the clawback window for this payment has closed"
    return ""


def resolve_challenge(*, verdict, bond, amount, paid, standing, policy):
    """Who receives what when a challenge is decided. Conserved exactly.

    Upheld: the challenger's bond comes back with a reward, and the payment is
    clawed back - blocked if the rail has not paid it, otherwise made good to
    the treasury from the agent's standing bond, as far as it reaches. The
    principal is made whole before the challenger is rewarded.
    Dismissed (in_remit or undetermined): the bond goes to the agent (T1).
    """
    _require_one_of(verdict, VERDICTS, "verdict")
    bond = _require_int(bond, "bond")
    amount = _require_int(amount, "amount")
    standing = _require_int(standing, "standing")
    if verdict != VERDICT_OUT_OF_REMIT:
        out = {"state": CHALLENGE_DISMISSED, "to_challenger": 0, "to_agent": bond,
               "to_treasury": 0, "from_standing": 0, "blocked": False}
        _require_conserved(out["to_challenger"] + out["to_agent"], bond, "resolve_challenge/dismissed")
        return out
    clawback = min(amount, standing) if paid else 0
    reward = challenge_reward(refused_amount=amount, agent_standing=standing - clawback, policy=policy)
    out = {"state": CHALLENGE_UPHELD, "to_challenger": bond + reward, "to_agent": 0,
           "to_treasury": clawback, "from_standing": clawback + reward, "blocked": not paid}
    _require_conserved(out["to_challenger"] + out["to_treasury"], bond + out["from_standing"], "resolve_challenge/upheld")
    return out


def record_challenge_result(*, losses, upheld, now):
    """A challenger's loss streak after a ruling: a loss adds one step, a win
    clears it (BondPolicy). Returns ``(losses, last_loss_at)``; a win returns
    ``(0, 0)``."""
    losses = _require_int(losses, "losses")
    if upheld:
        return 0, 0
    return losses + 1, _require_int(now, "now")


def freeze_tier(*, tier, shadow):
    """The freeze a breach at ``tier`` imposes: 0 (none), 2 or 3. A shadow
    guard withholds nothing, so it freezes nothing."""
    tier = _require_int(tier, "tier")
    if shadow or tier < TIER_FREEZE:
        return 0
    return TIER_REVOKE if tier >= TIER_REVOKE else TIER_FREEZE


def is_revoked(*, spend_id, revoked_below):
    """A tier-3 breach revokes every payment requested before it: those with
    an id below ``revoked_below``, the ledger's length when the breach was
    found. By index, not by time - a payment decided in the same second as the
    breach is on one side of it or the other, never both."""
    return int(spend_id) < int(revoked_below)


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

    # 1 - version must strictly increase (T5).
    version = mandate.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        bad("version: expected int")
    elif version <= stored_version:
        bad("version: %r does not exceed stored version %r" % (version, stored_version))

    # 5 - every default is mandatory. An unstated default is a decision
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
        elif rule_id in seen:  # 2 - no duplicate ids
            bad("%s.id: duplicate rule id %r" % (where, rule_id))
        else:
            seen.add(rule_id)

        rule_type = rule.get("type")
        if rule_type not in RULE_TYPES:
            bad("%s.type: expected one of %s" % (where, list(RULE_TYPES)))
            continue

        key = "check" if rule_type == RULE_REFLEX else "when"
        try:
            # 3 - predicates must be inside the v1 vocabulary, and
            # 7 - operands must be non-negative ints where ints are expected.
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
                # 4 - a referenced vendor list must be defined.
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
                    # 6 - a rule may not request more authority than granted.
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


# --- engine_api.py -----------------------------------------------------

def _rule_view(rule):
    """A mandate rule in the flat shape the guard stores and readers see.

    ``cond`` keeps the original predicate so classification runs the tested
    engine unchanged; ``a``/``b``/``s`` flatten the operands for display.
    """
    kind = str(rule["type"])
    cond = rule["check"] if kind == RULE_REFLEX else rule["when"]
    name, operand = sole_predicate(cond, "rule " + str(rule["id"]))
    a, b, s = 0, 0, ""
    if name in PREDICATES_INT:
        a = int(operand)
    elif name in PREDICATES_WINDOW_AMOUNT:
        a, b = int(operand["amount"]), int(operand["seconds"])
    elif name in PREDICATES_WINDOW_COUNT:
        a, b = int(operand["count"]), int(operand["seconds"])
    elif name in PREDICATES_LIST_NAME:
        s = str(operand)
    else:
        s = ",".join([str(c) for c in operand])
    return {
        "id": str(rule["id"]),
        "type": kind,
        "predicate": name,
        "cond": {name: operand},
        "a": a,
        "b": b,
        "s": s,
        "requires_artifact": bool(rule.get("requires_artifact", False)),
        "tier": int(rule.get("on_breach", {}).get("tier", 0)),
        "ask": str(rule.get("ask", "")),
    }


def api_compile(mandate_json, max_tier):
    """Validate a mandate and flatten it for storage. A non-empty ``errors``
    means the guard must refuse to deploy."""
    try:
        mandate = json.loads(mandate_json)
    except Exception:
        return json.dumps({"errors": ["mandate: not valid JSON"]})
    errors = validate_mandate(mandate, stored_version=0, max_tier=int(max_tier))
    if errors:
        return json.dumps({"errors": errors})
    lists = {}
    for name in mandate.get("vendor_lists", {}):
        lists[str(name)] = [normalize_address(a) for a in mandate["vendor_lists"][name]]
    return json.dumps(
        {
            "errors": [],
            "mandate_version": int(mandate["version"]),
            "mandate_uri": str(mandate.get("mandate_uri", "")),
            "mandate_digest": str(mandate.get("mandate_digest", "")).lower(),
            "defaults": {k: mandate["defaults"][k] for k in REQUIRED_DEFAULTS},
            "vendor_lists": lists,
            "rules": [_rule_view(r) for r in mandate["rules"]],
        }
    )


def _mandate_of(compiled):
    rules = []
    for r in compiled["rules"]:
        rules.append({"id": r["id"], "type": r["type"], ("check" if r["type"] == RULE_REFLEX else "when"): r["cond"]})
    return {"rules": rules, "vendor_lists": compiled["vendor_lists"]}


def _spend_of(row):
    return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))


def api_classify(compiled_json, history_json, candidate_json):
    """SETTLED / REFUSED / HELD and the rules that decided it, by the tested
    engine classifier. ``candidate`` and each history row are
    ``[amount, recipient, category, at]``."""
    compiled = json.loads(compiled_json)
    candidate = json.loads(candidate_json)
    if not is_category(candidate[2]):
        return json.dumps({"error": "category must be 1-40 letters, digits, spaces, '_', '.' or '-'", "state": "invalid", "rules": []})
    state, fired = classify_spend(
        _mandate_of(compiled),
        _spend_of(candidate),
        [_spend_of(h) for h in json.loads(history_json)],
    )
    return json.dumps({"state": state, "rules": [str(r) for r in fired]})


def api_outcomes(compiled_json, requires_artifact):
    """What every possible verdict resolves to, for every artifact state.

    The guard's validator closure needs the leader's verdict mapped to an
    outcome to apply the fail-closed rule, and cannot call this contract from
    inside the closure, so the guard fetches the whole table first. Also
    carries the deadline outcomes (no verdict).
    """
    compiled = json.loads(compiled_json)
    table = {}
    for verdict in VERDICTS:
        table[verdict] = {}
        for artifact in ARTIFACT_STATES:
            table[verdict][artifact] = resolve_hold(
                verdict=verdict,
                artifact=artifact,
                requires_artifact=bool(requires_artifact),
                defaults=compiled["defaults"],
                deadline_reached=False,
            )
    table["deadline"] = {}
    for artifact in ARTIFACT_STATES:
        table["deadline"][artifact] = resolve_hold(
            verdict=None,
            artifact=artifact,
            requires_artifact=bool(requires_artifact),
            defaults=compiled["defaults"],
            deadline_reached=True,
        )
    return json.dumps(table)


def api_uncommitted(held_at, now, window):
    """FORECLOSED inside the response window, ABSENT after it (T9)."""
    return uncommitted_artifact(held_at=int(held_at), now=int(now), response_window_seconds=int(window))


def api_challenge_terms(spend_json, rule_json, challenger, agent, now, window, losses, last_loss_at, floor):
    """May this challenge be opened, and for what bond? ``{"error", "bond"}``.

    The court (the rail) asks before taking a bond: ``challenge_error`` for
    eligibility, ``challenge_bond`` on the challenger's loss streak for the
    price. ``rule_json`` is the named mandate rule, or ``null``.
    """
    spend = json.loads(spend_json)
    error = challenge_error(
        spend=spend,
        rule=json.loads(rule_json),
        challenger=str(challenger),
        agent=str(agent),
        now=int(now),
        clawback_window_seconds=int(window),
    )
    bond = challenge_bond(
        amount=int(spend["amount"]),
        losses=int(losses),
        last_loss_at=int(last_loss_at),
        now=int(now),
        policy=BondPolicy(floor=int(floor)),
    )
    return json.dumps({"error": error, "bond": bond})


def api_challenge_result(verdict, bond, amount, paid, standing, floor, losses, now, tier):
    """Everything a decided challenge changes, for the court to apply:
    ``resolve_challenge``'s transfers, the challenger's new loss streak
    (``record_challenge_result``) and the freeze an upheld breach imposes
    (``freeze_tier``; ``tier`` already capped by the guard's max tier)."""
    out = resolve_challenge(
        verdict=str(verdict),
        bond=int(bond),
        amount=int(amount),
        paid=bool(paid),
        standing=int(standing),
        policy=BondPolicy(floor=int(floor)),
    )
    upheld = out["state"] == CHALLENGE_UPHELD
    out["losses"], out["last_loss_at"] = record_challenge_result(losses=int(losses), upheld=upheld, now=int(now))
    out["freeze"] = freeze_tier(tier=int(tier), shadow=False) if upheld else 0
    return json.dumps(out)


# --- engine_shell.py ---------------------------------------------------

class RemitEngine(gl.Contract):
    release: str
    prompts: Address

    def __init__(self, prompts: str):
        self.release = "remit-engine/3"
        self.prompts = Address(prompts)

    @gl.public.view
    def compile_mandate(self, mandate_json: str, max_tier: int) -> str:
        return api_compile(str(mandate_json), int(max_tier))

    @gl.public.view
    def classify(self, compiled: str, history: str, candidate: str) -> str:
        return api_classify(str(compiled), str(history), str(candidate))

    @gl.public.view
    def outcomes(self, compiled: str, requires_artifact: bool) -> str:
        return api_outcomes(str(compiled), bool(requires_artifact))

    @gl.public.view
    def uncommitted(self, held_at: int, now: int, window: int) -> str:
        return api_uncommitted(int(held_at), int(now), int(window))

    @gl.public.view
    def challenge_terms(
        self, spend: str, rule: str, challenger: str, agent: str, now: int, window: int, losses: int, last_loss_at: int, floor: int
    ) -> str:
        return api_challenge_terms(
            str(spend), str(rule), str(challenger), str(agent), int(now), int(window), int(losses), int(last_loss_at), int(floor)
        )

    @gl.public.view
    def challenge_result(
        self, verdict: str, bond: int, amount: int, paid: bool, standing: int, floor: int, losses: int, now: int, tier: int
    ) -> str:
        return api_challenge_result(
            str(verdict), int(bond), int(amount), bool(paid), int(standing), int(floor), int(losses), int(now), int(tier)
        )

    @gl.public.view
    def prompts_address(self) -> str:
        """Where a guard asks for the jury's question."""
        return str(self.prompts)

    @gl.public.view
    def version(self) -> str:
        return self.release
