"""Local-only Milestone 4 command contract."""

from __future__ import annotations

import argparse
import os
import platform
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO

from synthetic_sales_assist import __version__
from synthetic_sales_assist.demos import (
    AuditView,
    DemoAuditBackend,
    DemoError,
    DemoRunView,
    demo_catalog,
    demo_descriptor,
    validate_request_key,
)
from synthetic_sales_assist.domain.canonical import domain_hash
from synthetic_sales_assist.persistence.backup import (
    BackupError,
    create_backup,
    purge_expired_backup,
    purge_expired_backups,
    receipt_path,
    resolve_backup_path,
    restore_backup,
)
from synthetic_sales_assist.persistence.database import (
    DatabaseBusyError,
    DatabaseConfigurationError,
    DatabaseError,
    SQLiteDatabase,
)
from synthetic_sales_assist.persistence.doi_repository import DOIRepository
from synthetic_sales_assist.persistence.migrations import PROJECT_ROOT
from synthetic_sales_assist.persistence.paths import (
    DataPaths,
    PathPolicyError,
    resolve_data_paths,
)
from synthetic_sales_assist.persistence.projections import verify_sales_credit_projections
from synthetic_sales_assist.persistence.schema import (
    DatabaseVerification,
    DatabaseVerificationError,
    verify_database,
)
from synthetic_sales_assist.persistence.telemetry import (
    SAFETY_COUNTER_NAMES,
    ZERO_SAFETY_COUNTERS,
    TelemetryError,
    aggregate_processing_telemetry,
)
from synthetic_sales_assist.safety.identity import IdentityFirewallError, assert_reserved_identity

from .rendering import CLIEnvelope, render_human, render_json


EXIT_SUCCESS: Final = 0
EXIT_USAGE: Final = 2
EXIT_SAFETY: Final = 3
EXIT_CONFLICT: Final = 4
EXIT_DATABASE: Final = 5
EXIT_UNEXPECTED: Final = 70

_SYNTHETIC_ID_PREFIX = "SYN-"


class CLIUsageError(RuntimeError):
    def __init__(self, code: str = "CLI_USAGE_INVALID") -> None:
        self.code = code
        super().__init__(code)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise CLIUsageError()


@dataclass(frozen=True, slots=True)
class _CommonOptions:
    data_dir: str | None
    json_output: bool
    remaining: tuple[str, ...]


def _extract_common(argv: Sequence[str]) -> _CommonOptions:
    remaining: list[str] = []
    data_dir: str | None = None
    json_output = False
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--json":
            if json_output:
                raise CLIUsageError("CLI_JSON_DUPLICATE")
            json_output = True
        elif item == "--data-dir":
            if data_dir is not None or index + 1 >= len(argv):
                raise CLIUsageError("CLI_DATA_DIR_INVALID")
            index += 1
            data_dir = argv[index]
            if not data_dir or data_dir.startswith("--"):
                raise CLIUsageError("CLI_DATA_DIR_INVALID")
        else:
            remaining.append(item)
        index += 1
    return _CommonOptions(data_dir, json_output, tuple(remaining))


def _parser() -> _Parser:
    parser = _Parser(prog="python -m synthetic_sales_assist.cli", add_help=True)
    commands = parser.add_subparsers(dest="group", required=True)
    commands.add_parser("doctor")

    database = commands.add_parser("db").add_subparsers(dest="db_command", required=True)
    database.add_parser("init")
    database.add_parser("status")
    verify = database.add_parser("verify")
    verify.add_argument("--deep", action="store_true")
    backup = database.add_parser("backup")
    backup.add_argument("path")
    backup.add_argument("--overwrite", action="store_true")
    backup.add_argument("--create-parent", action="store_true")
    restore = database.add_parser("restore")
    restore.add_argument("path")
    restore.add_argument("--confirm", action="store_true")
    purge_backups = database.add_parser("purge-expired-backups")
    purge_backups.add_argument("path", nargs="?")

    demo = commands.add_parser("demo").add_subparsers(dest="demo_command", required=True)
    demo.add_parser("list")
    run_demo = demo.add_parser("run")
    run_demo.add_argument("alias")
    run_demo.add_argument("--request-key")

    order = commands.add_parser("order").add_subparsers(dest="order_command", required=True)
    order_show = order.add_parser("show")
    order_show.add_argument("synthetic_order_id")

    case = commands.add_parser("case").add_subparsers(dest="case_command", required=True)
    case_history = case.add_parser("history")
    case_history.add_argument("synthetic_order_id")
    case_history.add_argument("--after-sequence", type=int, default=0)
    case_history.add_argument("--through-sequence", type=int)
    case_history.add_argument("--through-event-id")
    case_history.add_argument("--limit", type=int, default=1_000)

    run = commands.add_parser("run").add_subparsers(dest="run_command", required=True)
    run_show = run.add_parser("show")
    run_show.add_argument("synthetic_run_id")

    metrics = commands.add_parser("metrics").add_subparsers(
        dest="metrics_command", required=True
    )
    metrics.add_parser("summary")
    return parser


def _command_name(arguments: argparse.Namespace) -> str:
    group = str(arguments.group)
    suffix = getattr(arguments, f"{group}_command", None)
    return group if suffix is None else f"{group} {suffix}"


def _verification_dict(verification: DatabaseVerification) -> dict[str, object]:
    return {
        "expected_schema_version": verification.expected_schema_version,
        "foreign_key_check": "ok" if not verification.foreign_key_violations else "failed",
        "healthy": verification.healthy,
        "integrity_check": verification.integrity_check,
        "migration_receipts": [
            {"name": item.name, "sha256": item.sha256, "version": item.version}
            for item in verification.migration_receipts
        ],
        "quick_check": verification.quick_check,
        "schema_object_count": len(verification.schema_objects),
        "schema_version": verification.schema_version,
    }


def _safe_counts(connection: sqlite3.Connection) -> dict[str, int]:
    names = tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    )
    counts: dict[str, int] = {}
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        row = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
        counts[name] = int(row[0]) if row is not None else 0
    return counts


def _last_receipt(
    connection: sqlite3.Connection,
    table: str,
    id_column: str,
) -> dict[str, object] | None:
    row = connection.execute(
        f"SELECT {id_column}, completed_at, status, error_code FROM {table} "
        "ORDER BY COALESCE(completed_at, '') DESC, rowid DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {
        "completed_at": row[1],
        "error_code": row[3],
        "id": row[0],
        "status": row[2],
    }


def _database_status(database: SQLiteDatabase, *, deep: bool = False) -> dict[str, object]:
    if not database.path.is_file():
        return {
            "database_path": str(database.path),
            "exists": False,
            "healthy": False,
            "size_bytes": 0,
        }
    with database.read() as connection:
        verification = verify_database(connection, deep=deep)
        result = _verification_dict(verification)
        result.update(
            {
                "database_path": str(database.path),
                "exists": True,
                "last_backup": _last_receipt(connection, "backup_receipts", "backup_id"),
                "last_restore": _last_receipt(connection, "restore_receipts", "restore_id"),
                "row_counts": _safe_counts(connection),
                "size_bytes": database.path.stat().st_size,
            }
        )
        return result


def _verify_receipt_hashes(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT c.command_domain, c.command_sha256, c.command_bytes,
               r.result_domain, r.result_sha256, r.result_bytes
        FROM durable_commands c
        JOIN durable_command_receipts r ON r.command_id = c.command_id
        ORDER BY c.command_id
        """
    ).fetchall()
    command_count = int(connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0])
    owner_orphans = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM durable_receipt_owners o
            LEFT JOIN durable_command_receipts r ON r.command_id = o.command_id
            WHERE r.command_id IS NULL
            """
        ).fetchone()[0]
    )
    if len(rows) != command_count or owner_orphans:
        raise DatabaseVerificationError("DURABLE_RECEIPT_INCOMPLETE")
    for row in rows:
        try:
            command = domain_hash(str(row[0]), bytes(row[2]))
            result = domain_hash(str(row[3]), bytes(row[5]))
        except (TypeError, ValueError):
            raise DatabaseVerificationError("DURABLE_RECEIPT_HASH_MISMATCH") from None
        if command.sha256 != str(row[1]) or result.sha256 != str(row[4]):
            raise DatabaseVerificationError("DURABLE_RECEIPT_HASH_MISMATCH")
    return len(rows)


def _system_safety_counters(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        str(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT counter_name, counter_value FROM system_safety_counters "
            "ORDER BY counter_name"
        ).fetchall()
    }


def _verify_safety_counters(connection: sqlite3.Connection) -> int:
    system = _system_safety_counters(connection)
    if tuple(system.items()) != tuple((name, 0) for name in SAFETY_COUNTER_NAMES):
        raise DatabaseVerificationError("SYSTEM_SAFETY_COUNTER_INVALID")
    invalid_snapshots = connection.execute(
        """
        SELECT operation_id
        FROM telemetry_safety_counters
        GROUP BY operation_id
        HAVING COUNT(*) != 9 OR MIN(counter_value) != 0 OR MAX(counter_value) != 0
        LIMIT 1
        """
    ).fetchone()
    telemetry_count = int(
        connection.execute("SELECT COUNT(*) FROM processing_telemetry").fetchone()[0]
    )
    snapshot_count = int(
        connection.execute(
            "SELECT COUNT(DISTINCT operation_id) FROM telemetry_safety_counters"
        ).fetchone()[0]
    )
    if invalid_snapshots is not None or telemetry_count != snapshot_count:
        raise DatabaseVerificationError("TELEMETRY_SAFETY_COUNTER_INVALID")
    return telemetry_count


def _extended_verification(database: SQLiteDatabase, *, deep: bool) -> dict[str, object]:
    if not database.path.is_file():
        raise DatabaseConfigurationError("DATABASE_NOT_INITIALIZED")
    with database.read() as connection:
        verification = verify_database(connection, deep=deep)
        sales_credit = verify_sales_credit_projections(connection)
        doi = DOIRepository(connection).verify_projections()
        if not sales_credit.valid:
            raise DatabaseVerificationError("SALES_CREDIT_PROJECTION_INVALID")
        if not doi.ok:
            raise DatabaseVerificationError("DOI_PROJECTION_INVALID")
        receipt_count = _verify_receipt_hashes(connection)
        telemetry_count = _verify_safety_counters(connection)
        maintenance_receipts = connection.execute(
            """
            SELECT COUNT(*) FROM backup_receipts
            WHERE status = 'COMPLETED'
              AND (backup_sha256 IS NULL OR quick_check != 'ok' OR foreign_key_check != 'ok')
            """
        ).fetchone()[0]
        if int(maintenance_receipts):
            raise DatabaseVerificationError("BACKUP_RECEIPT_INVALID")
        result = _verification_dict(verification)
        result.update(
            {
                "doi_projection_counts": {
                    "cases": doi.case_projection_count,
                    "owner_streams": doi.owner_stream_count,
                    "runs": doi.run_projection_count,
                },
                "durable_receipt_count": receipt_count,
                "projection_verification": "ok",
                "receipt_hash_verification": "ok",
                "safety_counter_verification": "ok",
                "sales_credit_projection_count": sales_credit.checked_count,
                "telemetry_snapshot_count": telemetry_count,
            }
        )
        return result


def _doctor(database: SQLiteDatabase, paths: DataPaths) -> dict[str, object]:
    status = _database_status(database)
    initialized = bool(status["exists"])
    safety_counters = dict(ZERO_SAFETY_COUNTERS)
    safety_counter_source = "CLOSED_BASELINE_DATABASE_NOT_INITIALIZED"
    if initialized:
        with database.read() as connection:
            safety_counters = _system_safety_counters(connection)
        safety_counter_source = "PERSISTED_DATABASE"
    return {
        "app_version": __version__,
        "data_directory": str(paths.root),
        "database_path": str(paths.database),
        "database_status": status,
        "extension_inventory": [],
        "foreign_key_check": status.get("foreign_key_check") if initialized else "not_run",
        "migration_status": "CURRENT" if initialized and status["healthy"] else "NOT_INITIALIZED",
        "network_policy": "localhost-only; CLI performs no networking",
        "python_version": platform.python_version(),
        "quick_check": status.get("quick_check") if initialized else "not_run",
        "safety_counters": safety_counters,
        "safety_counter_source": safety_counter_source,
        "schema_version": status.get("schema_version") if initialized else None,
        "worktree_build_version": os.environ.get("SYNTHETIC_SALES_ASSIST_BUILD_VERSION"),
    }


def _metrics(database: SQLiteDatabase) -> dict[str, object]:
    if not database.path.is_file():
        raise DatabaseConfigurationError("DATABASE_NOT_INITIALIZED")
    with database.read() as connection:
        summary = aggregate_processing_telemetry(connection).to_dict()
        summary.update(
            {
                "backup_status": _last_receipt(connection, "backup_receipts", "backup_id"),
                "database_size_bytes": database.path.stat().st_size,
                "restore_status": _last_receipt(connection, "restore_receipts", "restore_id"),
            }
        )
        return summary


def _synthetic_identifier(value: str, *, namespace: str) -> str:
    if type(value) is not str or not value.startswith(_SYNTHETIC_ID_PREFIX) or len(value) > 128:
        raise DemoError("SYNTHETIC_IDENTIFIER_INVALID")
    try:
        return assert_reserved_identity(value, expected_namespace=namespace)
    except IdentityFirewallError:
        raise DemoError("SYNTHETIC_IDENTIFIER_INVALID") from None


@dataclass(slots=True)
class CLIApplication:
    paths: DataPaths
    database: SQLiteDatabase
    backend: DemoAuditBackend

    def execute(self, arguments: argparse.Namespace) -> dict[str, object] | list[object]:
        command = _command_name(arguments)
        if command == "doctor":
            return _doctor(self.database, self.paths)
        if command == "db init":
            self.paths.ensure_directories()
            return _verification_dict(self.database.initialize())
        if command == "db status":
            return _database_status(self.database)
        if command == "db verify":
            return _extended_verification(self.database, deep=bool(arguments.deep))
        if command == "db backup":
            self.paths.ensure_directories()
            destination = resolve_backup_path(
                arguments.path,
                backups_directory=self.paths.backups,
                repository_root=PROJECT_ROOT,
                active_database=self.paths.database,
                for_write=True,
                create_parent=bool(arguments.create_parent),
            )
            receipt = create_backup(
                self.database,
                destination,
                overwrite=bool(arguments.overwrite),
            )
            return {"backup_path": str(destination), "receipt": receipt.to_dict()}
        if command == "db restore":
            source = resolve_backup_path(
                arguments.path,
                backups_directory=self.paths.backups,
                repository_root=PROJECT_ROOT,
                active_database=self.paths.database,
                for_write=False,
            )
            result = restore_backup(
                self.database,
                source,
                backups_directory=self.paths.backups,
                confirmed=bool(arguments.confirm),
            )
            return {
                "backup_id": result.backup.backup_id,
                "pre_restore_backup_id": result.pre_restore_backup.backup_id,
                "restore_id": result.restore_id,
                "schema_version": result.backup.schema_version,
            }
        if command == "db purge-expired-backups":
            self.paths.ensure_directories()
            if arguments.path is not None:
                path = resolve_backup_path(
                    arguments.path,
                    backups_directory=self.paths.backups,
                    repository_root=PROJECT_ROOT,
                    active_database=self.paths.database,
                    for_write=False,
                )
                was_present = path.exists() or receipt_path(path).exists()
                purged = purge_expired_backup(path)
                return {
                    "evaluated_count": int(was_present),
                    "purged_count": int(purged),
                }
            return purge_expired_backups(self.paths.backups).to_dict()
        if command == "demo list":
            return [item.to_dict() for item in demo_catalog()]
        if command == "demo run":
            demo_descriptor(arguments.alias)
            request_key = validate_request_key(arguments.request_key)
            view = self.backend.run_demo(arguments.alias, request_key)
            if type(view) is not DemoRunView:
                raise DemoError("DEMO_BACKEND_RESULT_INVALID")
            return view.to_dict(database_path=str(self.database.path))
        if command == "order show":
            view = self.backend.order_show(
                _synthetic_identifier(arguments.synthetic_order_id, namespace="ORDER")
            )
        elif command == "case history":
            view = self.backend.case_history(
                _synthetic_identifier(arguments.synthetic_order_id, namespace="ORDER"),
                after_sequence=arguments.after_sequence,
                through_sequence=arguments.through_sequence,
                through_event_id=arguments.through_event_id,
                limit=arguments.limit,
            )
        elif command == "run show":
            view = self.backend.run_show(
                _synthetic_identifier(arguments.synthetic_run_id, namespace="RUN")
            )
        elif command == "metrics summary":
            return _metrics(self.database)
        else:
            raise CLIUsageError()
        if type(view) is not AuditView:
            raise DemoError("AUDIT_BACKEND_RESULT_INVALID")
        return view.to_dict()


def _error_code(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", None)
    if type(code) is not str:
        message = str(error)
        code = (
            message
            if message and message.isupper() and " " not in message
            else type(error).__name__.upper()
        )
    if isinstance(error, CLIUsageError):
        return code, EXIT_USAGE
    if isinstance(error, (PathPolicyError, DemoError)):
        if "CONFLICT" in code:
            return code, EXIT_CONFLICT
        return code, EXIT_SAFETY
    if isinstance(error, (BackupError, DatabaseError, DatabaseVerificationError, TelemetryError)):
        if "CONFLICT" in code:
            return code, EXIT_CONFLICT
        return code, EXIT_DATABASE
    return "UNEXPECTED_ERROR", EXIT_UNEXPECTED


def main(
    argv: Sequence[str] | None = None,
    *,
    backend: DemoAuditBackend | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute one closed command and return its stable process exit code."""

    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    raw = tuple(sys.argv[1:] if argv is None else argv)
    command = "unknown"
    json_output = "--json" in raw
    try:
        common = _extract_common(raw)
        json_output = common.json_output
        arguments = _parser().parse_args(common.remaining)
        command = _command_name(arguments)
        paths = resolve_data_paths(common.data_dir)
        database = SQLiteDatabase(paths.database)
        if backend is None:
            from synthetic_sales_assist.durable_demo_backend import (
                DurableDemoAuditBackend,
            )

            selected_backend: DemoAuditBackend = DurableDemoAuditBackend(database)
        else:
            selected_backend = backend
        application = CLIApplication(
            paths=paths,
            database=database,
            backend=selected_backend,
        )
        envelope = CLIEnvelope(command, True, application.execute(arguments))
        (render_json if json_output else render_human)(envelope, output)
        return EXIT_SUCCESS
    except Exception as error:
        code, exit_code = _error_code(error)
        envelope = CLIEnvelope(command, False, None, (code,))
        (render_json if json_output else render_human)(
            envelope, error_output if not json_output else output
        )
        return exit_code


__all__ = [
    "EXIT_CONFLICT",
    "EXIT_DATABASE",
    "EXIT_SAFETY",
    "EXIT_SUCCESS",
    "EXIT_UNEXPECTED",
    "EXIT_USAGE",
    "CLIApplication",
    "CLIUsageError",
    "main",
]
