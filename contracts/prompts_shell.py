"""Remit prompts contract: builds the jury's question. Stateless and view-only."""


class RemitPrompts(gl.Contract):
    release: str

    def __init__(self):
        self.release = "remit-prompts/3"

    @gl.public.view
    def jury_prompt(self, compiled: str, rule_ids: str, claim: str, candidate: str, history: str, spend_index: int) -> str:
        return api_jury_prompt(str(compiled), str(rule_ids), str(claim), str(candidate), str(history), int(spend_index))

    @gl.public.view
    def challenge_prompt(
        self, compiled: str, rule_id: str, claim: str, statement: str, candidate: str, history: str, spend_index: int
    ) -> str:
        return api_challenge_prompt(
            str(compiled), str(rule_id), str(claim), str(statement), str(candidate), str(history), int(spend_index)
        )

    @gl.public.view
    def version(self) -> str:
        return self.release
