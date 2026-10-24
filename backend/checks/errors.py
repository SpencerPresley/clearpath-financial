"""Refusals from the AI check actions. `config.api` maps every DomainError subclass; nothing to register."""

from core.domain import CheckStatus
from core.errors import Conflict


class LlmCheckNotFailed(Conflict):
    code = "llm_check_not_failed"

    def __init__(self, *, status: CheckStatus) -> None:
        super().__init__(
            f"Only a failed AI check can be run again; this one is {status}.",
            details={"llm_check_status": str(status)},
        )
