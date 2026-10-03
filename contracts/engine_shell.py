"""Remit engine contract: the deterministic rules, shared by every guard.

Stateless, ownerless and view-only. It stores only a release tag and the
address of the prompts contract, both fixed at deployment, so nobody can change
its behaviour afterwards. A guard fixes the engine address at its own
deployment, and anyone can check it against deploy/deployments.json. Each
method wraps a tested adapter in engine_api.py.
"""


class RemitEngine(gl.Contract):
    release: str
    prompts: Address

    def __init__(self, prompts: str):
        self.release = "remit-engine/2"
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
    def prompts_address(self) -> str:
        """Where a guard asks for the jury's question."""
        return str(self.prompts)

    @gl.public.view
    def version(self) -> str:
        return self.release
