"""Opt-in Help Scout evidence reads, separate from the synthetic credit engine."""

from .reader import EvidenceReader, EvidenceResult
from .transport import ReadClient, ReadError, SuppliedCredential

__all__ = ["EvidenceReader", "EvidenceResult", "ReadClient", "ReadError", "SuppliedCredential"]
