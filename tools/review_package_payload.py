"""Require the unchanged release migrations in a normal portal review package."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping


# Authoritative hashes from demo-0.2.0-5778896c373f/release-payload.json.
REQUIRED_MIGRATIONS = {
    "migrations/0001_foundation.sql": "5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638",
    "migrations/0002_shared_persistence.sql": "5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31",
    "migrations/0003_sales_credit_persistence.sql": "fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395",
    "migrations/0004_doi_persistence.sql": "5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d",
}


def validate_migration_payload(payloads: Mapping[str, bytes]) -> None:
    """Reject incomplete or altered migration bytes before a bundle is handed off."""
    actual = {name for name in payloads if name.startswith("migrations/")}
    if actual != set(REQUIRED_MIGRATIONS):
        raise ValueError("REVIEW_MIGRATION_INVENTORY_INVALID")
    for name, expected in REQUIRED_MIGRATIONS.items():
        payload = payloads[name]
        if type(payload) is not bytes or hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("REVIEW_MIGRATION_PAYLOAD_INVALID")
