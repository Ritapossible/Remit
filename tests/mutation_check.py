"""Mutation harness for the deterministic engine.

PLAN.md Phase 1: *every guard must have a test that fails when the guard is
removed. A check that cannot fail is not evidence.*

Each entry below weakens or deletes one guard in ``remit_core.py``. The suite
is then run against the mutant and must FAIL. A mutant that survives means the
guard it broke is untested, and the run exits non-zero naming it.

Run with:  python3 tests/mutation_check.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "contracts", "remit_core.py")

# (name, what it breaks, original fragment, mutated fragment)
MUTATIONS = [
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
]


def run_suite():
    return subprocess.run(
        [sys.executable, "-m", "pytest", os.path.join(ROOT, "tests", "direct"), "-q", "-x"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def main():
    original = open(TARGET).read()

    baseline = run_suite()
    if baseline.returncode != 0:
        print("BASELINE SUITE IS RED - fix that before mutation testing.")
        print(baseline.stdout[-3000:])
        return 2

    backup = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    backup.write(original)
    backup.close()

    survived, killed, unapplied = [], [], []
    try:
        for name, why, old, new in MUTATIONS:
            if old not in original:
                unapplied.append((name, why))
                continue
            if original.count(old) != 1:
                unapplied.append((name, why + " [fragment not unique]"))
                continue
            open(TARGET, "w").write(original.replace(old, new, 1))
            result = run_suite()
            if result.returncode == 0:
                survived.append((name, why))
            else:
                killed.append(name)
    finally:
        shutil.copyfile(backup.name, TARGET)
        os.unlink(backup.name)

    restored = run_suite()
    if restored.returncode != 0:
        print("RESTORE FAILED - contracts/remit_core.py may be damaged.")
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
