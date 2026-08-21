"""Pure Milestone 3 capability boundary with no external-action implementation."""

from __future__ import annotations

from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


class DOICapabilityRequest(ImmutableStrEnum):
    """The only capability classes understood by the Milestone 3 rule pack."""

    READ_ONLY_INSPECTION = "READ_ONLY_INSPECTION"
    OA_WRITE = "OA_WRITE"
    UNSAFE_EXTERNAL_ACTION = "UNSAFE_EXTERNAL_ACTION"


class DOIBoundaryError(RuntimeError):
    """Reject a prohibited capability before any dispatch or side effect exists."""

    def __init__(self, code: str, *, reasons: ReasonSet) -> None:
        self.code = code
        self.reasons = reasons
        super().__init__(f"DOI capability rejected: {code}")


def _reasons(*codes: str) -> ReasonSet:
    registry = load_doi_registries()
    return ReasonSet(
        tuple(sorted((registry.reason_ref(code) for code in codes), key=lambda item: item.code))
    )


def enforce_milestone3_capability(request: DOICapabilityRequest) -> None:
    """Allow inspection only and emit the exact boundary reason for prohibited requests."""

    if type(request) is not DOICapabilityRequest:
        raise DOIBoundaryError(
            "UNSAFE_ACTION_REJECTED",
            reasons=_reasons("RC-083"),
        )
    if request is DOICapabilityRequest.READ_ONLY_INSPECTION:
        return
    if request is DOICapabilityRequest.OA_WRITE:
        raise DOIBoundaryError(
            "OA_WRITE_PROHIBITED",
            reasons=_reasons("RC-082"),
        )
    raise DOIBoundaryError(
        "UNSAFE_ACTION_REJECTED",
        reasons=_reasons("RC-083"),
    )


__all__ = [
    "DOIBoundaryError",
    "DOICapabilityRequest",
    "enforce_milestone3_capability",
]
