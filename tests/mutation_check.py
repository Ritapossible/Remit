"""Mutation harness for the deterministic engine.

PLAN.md Phase 1: *every guard must have a test that fails when the guard is
removed. A check that cannot fail is not evidence.*

Each entry below weakens or deletes one guard in ``remit_core.py`` or
``remit_prompts.py``, or in a contract shell. The contracts are rebuilt from the mutant, so the tests
that run the built and deployed bytes see it too, and the suite must FAIL. A mutant that survives means the
guard it broke is untested, and the run exits non-zero naming it.

Run with:  python3 tests/mutation_check.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "contracts", "remit_core.py")
PROMPTS = os.path.join(ROOT, "contracts", "remit_prompts.py")
GUARD = os.path.join(ROOT, "contracts", "contract_shell.py")
RAIL = os.path.join(ROOT, "contracts", "rail_shell.py")
REGISTRY = os.path.join(ROOT, "contracts", "registry_shell.py")
BUILD = os.path.join(ROOT, "contracts", "build")

# (name, what it breaks, original fragment, mutated fragment[, file])
# The file defaults to remit_core.py.
MUTATIONS = [
    (
        "jury-fails-open",
        "an unsure validator must not accept a leader that releases money",
        "    if own_verdict == VERDICT_IN_REMIT:\n        return False\n    return leader_outcome == OUTCOME_REFUSED",
        "    if own_verdict == VERDICT_IN_REMIT:\n        return False\n    return own_verdict == VERDICT_UNDETERMINED or leader_outcome == OUTCOME_REFUSED",
    ),
    (
        "in-remit-validator-loses-veto",
        "a validator sure the spend is in remit vetoes any other answer",
        "    if own_verdict == VERDICT_IN_REMIT:\n        return False\n",
        "",
    ),
    (
        "hesitant-yes-counts",
        "an in_remit below the confidence floor is undetermined",
        "    if verdict == VERDICT_IN_REMIT and int(confidence) < MIN_IN_REMIT_CONFIDENCE:",
        "    if verdict == VERDICT_IN_REMIT and int(confidence) < 0:",
    ),
    (
        "recipient-window-sees-everyone",
        "same-recipient predicates must ignore other recipients",
        "        history = same_recipient(spend, history)",
        "        history = history",
    ),
    (
        "equality-to-inequality",
        "hard law 2: settle on equality, never an inequality",
        "    if escrow != committed:\n        raise RemitError",
        "    if escrow < committed:\n        raise RemitError",
    ),
    (
        "foreclosure-removed",
        "T9: a foreclosed artifact must resolve in the agent's favour",
        "    if artifact == ARTIFACT_FORECLOSED:\n        return OUTCOME_ALLOWED",
        "    if artifact == ARTIFACT_FORECLOSED and False:\n        return OUTCOME_ALLOWED",
    ),
    (
        "response-window-boundary",
        "T9: the window is a minimum guarantee, inclusive at the boundary",
        "return ARTIFACT_FORECLOSED if (now - held_at) < window else ARTIFACT_ABSENT",
        "return ARTIFACT_FORECLOSED if (now - held_at) <= window else ARTIFACT_ABSENT",
    ),
    (
        "undefined-list-silently-false",
        "hard law 7: a guard that silently evaluates False is not a guard",
        '            raise RemitError("%s: vendor list %r is not defined" % (ctx, list_name))',
        "            return False",
    ),
    (
        "bool-accepted-as-int",
        "isinstance(True, int) is True; the guard must reject bool",
        "    if isinstance(value, bool) or not isinstance(value, int):",
        "    if not isinstance(value, (int, bool)):",
    ),
    (
        "negative-amounts-allowed",
        "operands must be non-negative",
        '        raise RemitError("%s: expected non-negative, got %d" % (context, value))',
        "        pass",
    ),
    (
        "escalation-flattened",
        "T1: a repeat false challenger's bond must escalate",
        "        multiplier *= factor",
        "        multiplier *= 1",
    ),
    (
        "escalation-uncapped",
        "T1: the multiplier must stay a number",
        "        if multiplier >= cap:\n            multiplier = cap\n            break",
        "        if multiplier >= cap and False:\n            multiplier = cap\n            break",
    ),
    (
        "decay-disabled",
        "open question 2: one loss forgiven per decay window",
        "    return max(0, losses - forgiven)",
        "    return losses",
    ),
    (
        "appeal-bond-not-greater",
        "T2: an appeal must cost strictly more than the challenge",
        "    if multiplier < 2:\n        raise RemitError(\"appeal_multiplier",
        "    if multiplier < 0:\n        raise RemitError(\"appeal_multiplier",
    ),
    (
        "reward-uncapped",
        "T1: the reward may not exceed what the agent posted",
        "    return min(earned, agent_standing)",
        "    return earned",
    ),
    (
        "self-challenge-allowed",
        "an agent must not be able to challenge itself",
        '        raise RemitError("agent and challenger must differ")',
        "        pass",
    ),
    (
        "version-not-strictly-increasing",
        "T5: a republished mandate may not reuse its version",
        "    elif version <= stored_version:",
        "    elif version < stored_version:",
    ),
    (
        "duplicate-ids-allowed",
        "duplicate rule ids must be refused",
        '            bad("%s.id: duplicate rule id %r" % (where, rule_id))',
        "            pass",
    ),
    (
        "tier-cap-ignored",
        "T-tier: a rule may not request more authority than was granted",
        "                    if tier > max_tier:",
        "                    if tier > 10**9:",
    ),
    (
        "ambiguous-rule-accepted",
        "a check holds exactly one predicate in v1",
        '        raise RemitError("%s: expected exactly 1 predicate, got %d" % (context, len(obj)))',
        "        for _k in obj:\n            return _k, obj[_k]",
    ),
    (
        "unknown-predicate-accepted",
        "the v1 vocabulary is closed",
        '        raise RemitError("%s: outside the v1 vocabulary" % ctx)',
        "        return False",
    ),
    (
        "reflex-precedence-lost",
        "a refused spend must never reach a jury",
        "            return SPEND_REFUSED, [rule[\"id\"]]",
        "            pass",
    ),
    (
        "conservation-unchecked",
        "credits must sum exactly to what was available",
        "    if credited != available:",
        "    if credited > available + 10**18:",
    ),
    (
        "missing-default-assumed",
        "an unstated default is a decision nobody made",
        '            raise RemitError("defaults: missing %r" % key)',
        "            pass",
    ),
    (
        "category-accepts-prose",
        "a declared category with newlines could pose as a fact for the jury",
        '        if not (ch.isascii() and (ch.isalnum() or ch in " _.-")):',
        '        if not (ch.isascii()):',
    ),
    (
        "claim-not-neutralized",
        "the agent's claim must not be able to open a fake answer section",
        "    parts.append(neutralize(claim_text) if claim_text else \"(none)\")",
        "    parts.append(str(claim_text) if claim_text else \"(none)\")",
        PROMPTS,
    ),
    (
        "artifact-not-neutralized",
        "the fetched artifact must not be able to close the untrusted block",
        "        parts.append(neutralize(artifact_text))",
        "        parts.append(str(artifact_text))",
        PROMPTS,
    ),
    (
        "headings-survive-neutralize",
        "runs of '=' that build section headings must be broken up",
        "    while \"===\" in out or \"---\" in out:",
        "    while \"---\" in out:",
        PROMPTS,
    ),
    (
        "challenge-uphold-fails-open",
        "an upheld challenge must stand only on agreement",
        "    if leader_verdict == VERDICT_OUT_OF_REMIT:\n        return False\n    return own_verdict != VERDICT_OUT_OF_REMIT",
        "    return own_verdict != VERDICT_OUT_OF_REMIT",
    ),
    (
        "challenge-breach-veto-lost",
        "a validator sure of the breach must veto a dismissal",
        "        return False\n    return own_verdict != VERDICT_OUT_OF_REMIT",
        "        return False\n    return True",
    ),
    (
        "hesitant-breach-counts",
        "a hesitant breach must not uphold a challenge",
        "    if verdict == VERDICT_OUT_OF_REMIT and int(confidence) < MIN_UPHELD_CONFIDENCE:",
        "    if False:",
    ),
    (
        "jury-decisions-rechallengeable",
        "a jury's or principal's decision is appealed, not challenged",
        '    if str(spend.get("verdict", "")) != "" or str(spend.get("reason", "")) != "":',
        "    if False:",
    ),
    (
        "clawback-window-ignored",
        "a payment past the clawback window is final",
        "    if decided_at <= 0 or now - decided_at > int(clawback_window_seconds):",
        "    if decided_at <= 0:",
    ),
    (
        "challenger-paid-before-principal",
        "the principal is made whole before the challenger is rewarded",
        "agent_standing=standing - clawback, policy=policy)",
        "agent_standing=standing, policy=policy)",
    ),
    (
        "unpaid-payment-not-blocked",
        "an upheld challenge must stop a payment the rail has not made",
        '"from_standing": clawback + reward, "blocked": not paid}',
        '"from_standing": clawback + reward, "blocked": False}',
    ),
    (
        "win-does-not-reset-streak",
        "a challenger who is right pays the floor again",
        "    if upheld:\n        return 0, 0",
        "    if upheld:\n        return losses, 0",
    ),
    (
        "tier-two-does-not-freeze",
        "a tier-2 breach must freeze the agent",
        "    if shadow or tier < TIER_FREEZE:",
        "    if shadow or tier < TIER_REVOKE:",
    ),
    (
        "shadow-mode-freezes",
        "shadow mode withholds nothing, so it freezes nothing",
        "    if shadow or tier < TIER_FREEZE:",
        "    if tier < TIER_FREEZE:",
    ),
    (
        "revocation-reaches-forward",
        "a tier-3 revocation must not touch what is requested after it",
        "    return int(spend_id) < int(revoked_below)",
        "    return int(spend_id) <= int(revoked_below)",
    ),
    (
        "guard-ignores-court-freeze",
        "an agent frozen by the rail's court must not spend",
        "            if court > tier:",
        "            if False:",
        GUARD,
    ),
    (
        "guard-breach-does-not-freeze",
        "the guard's own out-of-remit verdict must apply its tier",
        "        if result[\"verdict\"] == VERDICT_OUT_OF_REMIT:\n            # Graduated",
        "        if False:\n            # Graduated",
        GUARD,
    ),
    (
        "guard-revocation-ignored",
        "a tier-3 revocation must withdraw the guard's authorization",
        "            return AUTH_REVOKED",
        "            return AUTH_AUTHORIZED",
        GUARD,
    ),
    (
        "rail-pays-under-challenge",
        "the rail must not pay a payment that is under challenge",
        '        if int(self.open_on.get(key, u256(0))) > 0:\n            raise Exception("[EXPECTED] spend is under challenge',
        '        if False:\n            raise Exception("[EXPECTED] spend is under challenge',
        RAIL,
    ),
    (
        "rail-pays-clawed-back",
        "the rail must not pay a payment an upheld challenge clawed back",
        '        if int(self.upheld_on.get(key, u256(0))) > 0:\n            raise Exception("[EXPECTED] an upheld',
        '        if False:\n            raise Exception("[EXPECTED] an upheld',
        RAIL,
    ),
    (
        "rail-withdraws-bonds",
        "the principal's withdrawal must never reach a bond",
        "        if value <= 0 or int(self.treasury) < value:\n            raise Exception(\"[EXPECTED] invalid withdrawal",
        "        if value <= 0 or int(self.balance) < value:\n            raise Exception(\"[EXPECTED] invalid withdrawal",
        RAIL,
    ),
    (
        "bond-withdrawn-inside-window",
        "the agent's bond must stay while a payment is challengeable",
        "                if now - int(s[\"decided_at\"]) <= window:",
        "                if False:",
        RAIL,
    ),
    (
        "first-slice-of-split-paid",
        "the rail must not pay a slice while a later slice of the split is held",
        "            if link == SPLIT_PENDING:",
        "            if False:",
        RAIL,
    ),
    (
        "refused-split-first-slice-paid",
        "a slice falls with the split it belongs to",
        "            if link == SPLIT_REFUSED:",
        "            if False:",
        RAIL,
    ),
    (
        "split-window-ignored",
        "a payment outside the split rule's window is not linked",
        "        if reach <= 0 or int(other[\"at\"]) - int(spend[\"at\"]) >= reach:",
        "        if reach <= 0:",
    ),
    (
        "mixed-refusal-read-as-split",
        "a refusal that also involved another rule is not a ruling on the split",
        "        elif other[\"outcome\"] == OUTCOME_REFUSED and all(r in windows for r in fired):",
        "        elif other[\"outcome\"] == OUTCOME_REFUSED:",
    ),
    (
        "split-across-vendors",
        "only payments to the same vendor are slices of one purchase",
        "        if normalize_address(other[\"recipient\"], \"recipient\") != mine:\n            continue",
        "",
    ),
    (
        "registry-lets-agent-move",
        "another principal must not take over a registered agent",
        "            if self.r_principal[old] != who:",
        "            if False:",
        REGISTRY,
    ),
]


def run_suite():
    return subprocess.run(
        [sys.executable, "-m", "pytest", os.path.join(ROOT, "tests", "direct"), "-q", "-x"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def rebuild():
    """Regenerate contracts/build from whatever the sources now say."""
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "deploy", "build_contract.py")],
        check=True, capture_output=True, cwd=ROOT,
    )


def main():
    originals = {path: open(path).read() for path in (CORE, PROMPTS, GUARD, RAIL, REGISTRY)}
    snapshot = tempfile.mkdtemp()
    shutil.copytree(BUILD, os.path.join(snapshot, "build"))

    baseline = run_suite()
    if baseline.returncode != 0:
        print("BASELINE SUITE IS RED - fix that before mutation testing.")
        print(baseline.stdout[-3000:])
        return 2

    survived, killed, unapplied = [], [], []
    try:
        for entry in MUTATIONS:
            name, why, old, new = entry[:4]
            target = entry[4] if len(entry) > 4 else CORE
            original = originals[target]
            if old not in original:
                unapplied.append((name, why))
                continue
            if original.count(old) != 1:
                unapplied.append((name, why + " [fragment not unique]"))
                continue
            try:
                open(target, "w").write(original.replace(old, new, 1))
                try:
                    rebuild()
                except subprocess.CalledProcessError:
                    killed.append(name)  # the build itself refused the mutant
                    continue
                result = run_suite()
            finally:
                open(target, "w").write(original)
            if result.returncode == 0:
                survived.append((name, why))
            else:
                killed.append(name)
    finally:
        for path, text in originals.items():
            open(path, "w").write(text)
        shutil.rmtree(BUILD)
        shutil.copytree(os.path.join(snapshot, "build"), BUILD)
        shutil.rmtree(snapshot)

    restored = run_suite()
    if restored.returncode != 0:
        print("RESTORE FAILED - the sources or contracts/build may be damaged.")
        print(restored.stdout[-3000:])
        return 3

    print("mutants killed   : %d" % len(killed))
    print("mutants survived : %d" % len(survived))
    print("not applied      : %d" % len(unapplied))
    for name, why in unapplied:
        print("  ?  %-32s %s" % (name, why))
    for name, why in survived:
        print("  !  %-32s UNTESTED GUARD: %s" % (name, why))
    if survived or unapplied:
        return 1
    print("\nEvery guard has a test that fails when the guard is removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
