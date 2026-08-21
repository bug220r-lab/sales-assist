"""Generate the checked-in Milestone 3 DOI traceability and KAT documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synthetic_sales_assist.doi.extraction import extraction_hash_fixture_records
from synthetic_sales_assist.doi.fixtures import render_scenario_inventory_markdown
from synthetic_sales_assist.doi.case_attention import case_attention_hash_fixtures
from synthetic_sales_assist.doi.interventions import intervention_hash_fixtures
from synthetic_sales_assist.doi.knowledge import knowledge_hash_fixtures
from synthetic_sales_assist.doi.lifecycle import lifecycle_hash_fixtures
from synthetic_sales_assist.doi.models import model_hash_fixtures
from synthetic_sales_assist.doi.retention import retention_hash_fixtures
from synthetic_sales_assist.doi.source import source_hash_fixture_records
from synthetic_sales_assist.doi.traceability import (
    render_reason_ownership_markdown,
    render_transition_matrix_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class DOIHashFixtureRow:
    """One exact provider-owned DOI hash known-answer row."""

    provider: str
    name: str
    domain: str
    canonical_bytes: bytes
    digest: str

    @property
    def preimage(self) -> bytes:
        return self.domain.encode("ascii") + b"\n" + self.canonical_bytes


def doi_hash_fixture_rows() -> tuple[DOIHashFixtureRow, ...]:
    """Return the complete deterministic 94-domain DOI KAT inventory."""

    providers = (
        ("source", source_hash_fixture_records),
        ("extraction", extraction_hash_fixture_records),
        ("case_attention", case_attention_hash_fixtures),
        ("models", model_hash_fixtures),
        ("knowledge", knowledge_hash_fixtures),
        ("lifecycle", lifecycle_hash_fixtures),
        ("interventions", intervention_hash_fixtures),
        ("retention", retention_hash_fixtures),
    )
    rows = tuple(
        DOIHashFixtureRow(provider, name, domain, canonical, digest)
        for provider, fixture_provider in providers
        for name, domain, canonical, digest in fixture_provider()
    )
    if (
        len(rows) != 94
        or len({row.name for row in rows}) != len(rows)
        or len({row.domain for row in rows}) != len(rows)
        or len({row.digest for row in rows}) != len(rows)
    ):
        raise RuntimeError("MILESTONE3_HASH_FIXTURE_INVENTORY_INVALID")
    return rows


def render_hash_preimages_markdown() -> str:
    """Render all exact domain/LF/canonical-JSON Milestone 3 preimages."""

    rows = doi_hash_fixture_rows()
    lines = [
        "# Milestone 3 DOI hash preimages",
        "",
        "Generated from the complete DOI hash-fixture provider inventory. Each preimage is",
        "the ASCII domain, exactly one `0A` byte, and the UTF-8 canonical JSON shown below.",
        "There is no trailing line feed in the hashed preimage. Executable tests pin every",
        "fixture name, domain, digest, canonical encoding, and published byte.",
        "",
        f"- Hash domains: {len(rows)}",
        f"- Fixture names: {len({row.name for row in rows})}",
        f"- Distinct fixed digests: {len({row.digest for row in rows})}",
        "",
        "| Provider | Binding fixture | Domain | Expected SHA-256 |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| `{row.provider}` | `{row.name}` | `{row.domain}` | `{row.digest}` |"
        for row in rows
    )
    lines.extend(
        (
            "",
            "## Exact preimages",
            "",
            "The visible newline after each domain is the single required separator.",
            "Every canonical JSON value occupies exactly one line.",
        )
    )
    for row in rows:
        lines.extend(
            (
                "",
                f"### {row.name}",
                "",
                "```text",
                row.domain,
                row.canonical_bytes.decode("utf-8"),
                "```",
            )
        )
    return "\n".join(lines) + "\n"


def generated_documents() -> tuple[tuple[Path, str], ...]:
    """Return every generated Milestone 3 document and its exact UTF-8 text."""

    return (
        (
            ROOT / "docs" / "milestone3-hash-preimages.md",
            render_hash_preimages_markdown(),
        ),
        (
            ROOT / "docs" / "milestone3-reason-owner-oracle-reconciliation.md",
            render_reason_ownership_markdown(),
        ),
        (
            ROOT / "docs" / "milestone3-transition-implementation-matrix.md",
            render_transition_matrix_markdown(),
        ),
        (
            ROOT / "docs" / "milestone3-synthetic-scenario-inventory.md",
            render_scenario_inventory_markdown(),
        ),
    )


def main() -> int:
    """Write the exact generated document bytes."""

    for path, content in generated_documents():
        path.write_bytes(content.encode("utf-8"))
        print(f"GENERATED {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
