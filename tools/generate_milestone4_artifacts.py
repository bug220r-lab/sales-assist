"""Generate exact Milestone 4 migration and SQLite schema documentation."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from synthetic_sales_assist.persistence.migrations import (  # noqa: E402
    apply_migrations,
    discover_migrations,
)
from synthetic_sales_assist.persistence.schema import schema_inventory  # noqa: E402


FIXED_MIGRATION_TIME = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    apply_migrations(
        connection,
        ROOT / "migrations",
        repository_root=ROOT,
        clock=lambda: FIXED_MIGRATION_TIME,
    )
    return connection


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def render_migration_verification() -> str:
    migrations = discover_migrations(ROOT / "migrations", repository_root=ROOT)
    with _database() as connection:
        replay = apply_migrations(
            connection,
            ROOT / "migrations",
            repository_root=ROOT,
            clock=lambda: FIXED_MIGRATION_TIME,
        )
        objects = schema_inventory(connection)
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    lines = [
        "# Milestone 4 migration verification",
        "",
        "Generated from the immutable migration bytes and a fresh in-memory database.",
        "Executable tests reject any document or migration drift.",
        "",
        f"- Latest schema version: {migrations[-1].version}",
        f"- Migration files: {len(migrations)}",
        f"- Fresh applied versions: {', '.join(str(item.version) for item in migrations)}",
        f"- Exact replay applied versions: {list(replay)}",
        f"- SQLite quick check: `{quick}`",
        f"- Foreign-key violations: {len(foreign_keys)}",
        f"- Tables: {sum(item.object_type == 'table' for item in objects)}",
        f"- Indexes: {sum(item.object_type == 'index' for item in objects)}",
        f"- Triggers: {sum(item.object_type == 'trigger' for item in objects)}",
        "",
        "| Version | Migration | Bytes | SHA-256 |",
        "|---:|---|---:|---|",
    ]
    for migration in migrations:
        lines.append(
            f"| {migration.version} | `{migration.path.name}` | "
            f"{migration.path.stat().st_size} | `{migration.sha256}` |"
        )
    return "\n".join(lines) + "\n"


def render_schema_inventory() -> str:
    with _database() as connection:
        objects = schema_inventory(connection)
        tables = tuple(item for item in objects if item.object_type == "table")
        indexes = tuple(item for item in objects if item.object_type == "index")
        triggers = tuple(item for item in objects if item.object_type == "trigger")
        views = tuple(item for item in objects if item.object_type == "view")
        lines = [
            "# Milestone 4 SQLite schema inventory",
            "",
            "Generated from a fresh database upgraded through every checked-in migration.",
            "The exact `sqlite_schema` SQL below documents every table, index, trigger, view,",
            "column constraint, and foreign-key declaration.",
            "",
            f"- Tables: {len(tables)}",
            f"- Indexes: {len(indexes)}",
            f"- Triggers: {len(triggers)}",
            f"- Views: {len(views)}",
            "",
            "## Tables",
        ]
        for table in tables:
            identifier = _quote_identifier(table.name)
            columns = connection.execute(f"PRAGMA table_xinfo({identifier})").fetchall()
            foreign_keys = connection.execute(
                f"PRAGMA foreign_key_list({identifier})"
            ).fetchall()
            lines.extend(
                (
                    "",
                    f"### `{table.name}`",
                    "",
                    "| Column | Declared type | Not null | Default | PK order | Hidden |",
                    "|---|---|---:|---|---:|---:|",
                )
            )
            for column in columns:
                default = "-" if column[4] is None else f"`{column[4]}`"
                lines.append(
                    f"| `{column[1]}` | `{column[2]}` | {column[3]} | "
                    f"{default} | {column[5]} | {column[6]} |"
                )
            if foreign_keys:
                lines.extend(
                    (
                        "",
                        "Foreign keys:",
                        "",
                        "| From | Target | To | On update | On delete |",
                        "|---|---|---|---|---|",
                    )
                )
                for foreign_key in foreign_keys:
                    lines.append(
                        f"| `{foreign_key[3]}` | `{foreign_key[2]}` | "
                        f"`{foreign_key[4]}` | `{foreign_key[5]}` | `{foreign_key[6]}` |"
                    )
            lines.extend(("", "```sql", table.sql or "", "```"))

        for heading, rows in (("Indexes", indexes), ("Triggers", triggers), ("Views", views)):
            lines.extend(("", f"## {heading}"))
            if not rows:
                lines.extend(("", "None."))
                continue
            for row in rows:
                lines.extend(
                    (
                        "",
                        f"### `{row.name}` on `{row.table_name}`",
                        "",
                        "```sql",
                        row.sql or "",
                        "```",
                    )
                )
    return "\n".join(lines) + "\n"


def render_schema_map() -> str:
    with _database() as connection:
        tables = tuple(
            item.name
            for item in schema_inventory(connection)
            if item.object_type == "table"
        )
    shared = tuple(name for name in tables if not name.startswith(("sc_", "doi_")))
    sales_credit = tuple(name for name in tables if name.startswith("sc_"))
    doi = tuple(name for name in tables if name.startswith("doi_"))
    lines = [
        "# Milestone 4 logical schema map",
        "",
        "```text",
        "shared migration / safety / replay / telemetry / maintenance",
        "             |                         |",
        "     Sales Credit root          DOI run/case roots",
        "       |            |          |                 |",
        " immutable facts  projection  immutable events  projections",
        "       |            |          |                 |",
        " minimized audit / aggregate   KPI aggregate / graph purge",
        "```",
        "",
        "There is no Sales Credit-to-DOI foreign key and no external-system capability.",
    ]
    for heading, names in (
        ("Shared and system tables", shared),
        ("Sales Credit tables", sales_credit),
        ("DOI tables", doi),
    ):
        lines.extend(("", f"## {heading}", ""))
        lines.extend(f"- `{name}`" for name in names)
    return "\n".join(lines) + "\n"


def generated_documents() -> tuple[tuple[Path, str], ...]:
    return (
        (ROOT / "docs" / "milestone4-migration-verification.md", render_migration_verification()),
        (ROOT / "docs" / "milestone4-schema-inventory.md", render_schema_inventory()),
        (ROOT / "docs" / "milestone4-schema-map.md", render_schema_map()),
    )


def main() -> int:
    for path, text in generated_documents():
        path.write_bytes(text.encode("utf-8"))
        print(f"GENERATED {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
