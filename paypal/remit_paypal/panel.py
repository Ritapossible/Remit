"""A panel of AI models, deciding one question, failing closed.

On GenLayer, validators run by different people vote and must agree. Here
the guard's operator runs every model, so the panel buys independence of
*models*, not of operators, and only as much as the models differ: money
moves only when enough of them agree that it should, and one confident no
stops it.

Each answer is read by Remit's own parser (``read_verdict``) and hardened by
``harden_verdict``: an ``in_remit`` below 60 confidence counts as
undetermined. A model that errors, times out or answers nonsense counts as
undetermined too.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .engine import core, read_verdict

IN, OUT, UNSURE = core.VERDICT_IN_REMIT, core.VERDICT_OUT_OF_REMIT, core.VERDICT_UNDETERMINED


@dataclass(frozen=True)
class Vote:
    model: str
    verdict: str  # after hardening
    confidence: int
    reason: str
    raw: str
    error: str = ""


def aggregate(votes, quorum):
    """The panel's verdict.

    - Any ``out_of_remit`` refuses: a single confident breach is enough to
      stop money, never enough to move it.
    - ``in_remit`` needs at least ``quorum`` hardened ``in_remit`` votes.
    - Anything else is ``undetermined``, which the mandate's default decides.
    """
    if quorum < 1 or quorum > len(votes):
        raise core.RemitError("quorum %d is outside 1..%d" % (quorum, len(votes)))
    if any(v.verdict == OUT for v in votes):
        return OUT
    if sum(1 for v in votes if v.verdict == IN) >= quorum:
        return IN
    return UNSURE


class Panel:
    """``models`` maps a name to a callable taking a prompt and returning the
    model's raw text. Calls run in parallel; each is bounded by ``timeout``."""

    def __init__(self, models, quorum, timeout=60):
        if not models:
            raise core.RemitError("a panel needs at least one model")
        self.models = dict(models)
        self.quorum = int(quorum)
        self.timeout = timeout
        aggregate([Vote(n, UNSURE, 0, "", "") for n in self.models], self.quorum)  # validates the quorum

    def _ask(self, name, prompt):
        try:
            raw = str(self.models[name](prompt))
        except Exception as exc:  # fail closed: an error is a doubt, never a yes
            return Vote(name, UNSURE, 0, "", "", error="%s: %s" % (type(exc).__name__, exc))
        parsed = read_verdict(raw)
        verdict = core.harden_verdict(parsed["verdict"], parsed["confidence"])
        return Vote(name, verdict, parsed["confidence"], parsed["reason"], raw)

    def decide(self, prompt):
        """Every model's vote within ``timeout`` seconds in all. A model still
        running then counts as unsure and is not waited for."""
        names = list(self.models)
        pool = ThreadPoolExecutor(max_workers=len(names))
        try:
            futures = {n: pool.submit(self._ask, n, prompt) for n in names}
            deadline = time.monotonic() + self.timeout
            votes = []
            for n in names:
                try:
                    votes.append(futures[n].result(timeout=max(0.0, deadline - time.monotonic())))
                except Exception as exc:
                    votes.append(Vote(n, UNSURE, 0, "", "", error="timeout: %s" % (exc or "no answer in time")))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return aggregate(votes, self.quorum), votes
