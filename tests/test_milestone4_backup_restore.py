from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from synthetic_sales_assist.domain.canonical import domain_hash
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.persistence.backup import (
    BackupError,
    create_backup,
    purge_expired_backup,
    purge_expired_backups,
    receipt_path,
    resolve_backup_path,
    restore_backup,
    verify_backup,
)
from synthetic_sales_assist.persistence.database import DatabaseBusyError, SQLiteDatabase
from synthetic_sales_assist.persistence.migrations import PROJECT_ROOT
from synthetic_sales_assist.persistence.telemetry import (
    ProcessingResultClass,
    ProcessingTelemetry,
    RulePack,
    record_processing_telemetry,
)


def _record(database: SQLiteDatabase, suffix: str) -> None:
    with database.write() as connection:
        record_processing_telemetry(
            connection,
            ProcessingTelemetry(
                operation_id=f"SYN-EVIDENCE-M4-BACKUP-{suffix}",
                rule_pack=RulePack.DOI,
                demo_alias="doi-full-ds",
                started_at=CanonicalTimestamp("2026-08-21T00:00:00Z"),
                ended_at=CanonicalTimestamp("2026-08-21T00:00:00.1Z"),
                extraction_ns=1,
                validation_ns=1,
                normalization_ns=1,
                rule_ns=1,
                database_ns=1,
                total_ns=10,
                result_class=ProcessingResultClass.SUCCESS,
                human_review=False,
                fail_closed=False,
                replay=False,
                conflict=False,
                database_error=False,
                rule_version="m4/v1",
                schema_version="4",
                catalog_version=None,
                error_code=None,
            ),
        )


def _insert_retention_audit(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    purge_eligible_at: str,
) -> None:
    command_id = f"{audit_id}-COMMAND"
    material = b"{}"
    command = domain_hash("m4-backup-retention-command/v1", material)
    result = domain_hash("m4-backup-retention-result/v1", material)
    connection.execute(
        """
        INSERT INTO durable_commands (
            command_id, natural_namespace, natural_key, command_domain,
            command_sha256, command_bytes, accepted_at
        ) VALUES (?, 'm4.backup.retention', ?, ?, ?, ?, '2026-08-20T00:00:00Z')
        """,
        (command_id, audit_id, command.domain, command.sha256, material),
    )
    connection.execute(
        """
        INSERT INTO durable_command_receipts (
            command_id, result_domain, result_sha256, result_bytes, recorded_at
        ) VALUES (?, ?, ?, ?, '2026-08-20T00:00:00Z')
        """,
        (command_id, result.domain, result.sha256, material),
    )
    connection.execute(
        """
        INSERT INTO sc_no_order_closed_audits (
            audit_id, command_id, closed_at, purge_eligible_at,
            material_sha256, canonical_bytes
        ) VALUES (?, ?, '2026-08-20T00:00:00Z', ?, ?, ?)
        """,
        (audit_id, command_id, purge_eligible_at, result.sha256, material),
    )


class Milestone4BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m4-backup-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_online_backup_and_exact_restore_preserve_active_validity(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "BEFORE")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "exact.sqlite3"
        receipt = create_backup(database, backup)
        self.assertEqual(verify_backup(backup), receipt)
        self.assertTrue(receipt_path(backup).is_file())

        _record(database, "AFTER")
        result = restore_backup(
            database,
            backup,
            backups_directory=backups,
            confirmed=True,
        )
        self.assertEqual(result.backup, receipt)
        with database.read() as connection:
            operations = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT operation_id FROM processing_telemetry ORDER BY operation_id"
                )
            )
            restore_count = int(
                connection.execute("SELECT COUNT(*) FROM restore_receipts").fetchone()[0]
            )
        self.assertEqual(operations, ("SYN-EVIDENCE-M4-BACKUP-BEFORE",))
        self.assertEqual(restore_count, 1)

    def test_empty_new_database_backup_is_verified(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backup = self.root / "empty.sqlite3"
        receipt = create_backup(database, backup)
        self.assertEqual(verify_backup(backup), receipt)
        self.assertGreater(len(receipt.table_rows), 1)

    def test_corrupt_wrong_checksum_and_future_schema_backups_are_rejected(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        original = self.root / "original.sqlite3"
        create_backup(database, original)

        wrong_checksum = self.root / "wrong-checksum.sqlite3"
        wrong_checksum.write_bytes(original.read_bytes() + b"synthetic-corruption")
        receipt_path(wrong_checksum).write_bytes(receipt_path(original).read_bytes())
        with self.assertRaisesRegex(BackupError, "BACKUP_CHECKSUM_MISMATCH"):
            verify_backup(wrong_checksum)

        corrupt = self.root / "corrupt.sqlite3"
        corrupt_bytes = bytearray(original.read_bytes())
        corrupt_bytes[0:16] = b"not a sqlite file"
        corrupt.write_bytes(corrupt_bytes)
        corrupt_receipt = json.loads(receipt_path(original).read_text(encoding="utf-8"))
        corrupt_receipt["backup_sha256"] = hashlib.sha256(corrupt_bytes).hexdigest()
        receipt_path(corrupt).write_text(
            json.dumps(corrupt_receipt, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        with self.assertRaises(BackupError):
            verify_backup(corrupt)

        future = self.root / "future.sqlite3"
        future.write_bytes(original.read_bytes())
        future_receipt = json.loads(receipt_path(original).read_text(encoding="utf-8"))
        future_receipt["schema_version"] = 5
        future_receipt["migration_checksums"].append(
            {"sha256": "0" * 64, "version": 5}
        )
        receipt_path(future).write_text(
            json.dumps(future_receipt, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BackupError, "BACKUP_SCHEMA_UNSUPPORTED"):
            verify_backup(future)

    def test_rejected_or_interrupted_restore_leaves_active_database_valid(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "ORIGINAL")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "exact.sqlite3"
        create_backup(database, backup)
        _record(database, "POST-BACKUP")

        with self.assertRaisesRegex(BackupError, "RESTORE_CONFIRMATION_REQUIRED"):
            restore_backup(database, backup, backups_directory=backups, confirmed=False)

        def interrupt(stage: str) -> None:
            if stage == "after_restore_swap":
                raise RuntimeError("synthetic fault")

        with self.assertRaisesRegex(BackupError, "RESTORE_POST_SWAP_FAILED"):
            restore_backup(
                database,
                backup,
                backups_directory=backups,
                confirmed=True,
                fault_injector=interrupt,
            )
        with database.read() as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            operations = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT operation_id FROM processing_telemetry ORDER BY operation_id"
                )
            )
        self.assertEqual(
            operations,
            (
                "SYN-EVIDENCE-M4-BACKUP-ORIGINAL",
                "SYN-EVIDENCE-M4-BACKUP-POST-BACKUP",
            ),
        )

    def test_rollback_staging_failures_remove_all_identity_temporaries(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "ROLLBACK-STAGE-ORIGINAL")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "rollback-stage.sqlite3"
        create_backup(database, backup)
        _record(database, "ROLLBACK-STAGE-AFTER")

        for failure_stage in (
            "after_rollback_stage_copy",
            "before_rollback_stage_digest",
            "before_rollback_stage_connect",
            "before_rollback_stage_verify",
        ):
            with self.subTest(failure_stage=failure_stage):

                def fail_stage(stage: str) -> None:
                    if stage == failure_stage:
                        raise RuntimeError(f"synthetic {failure_stage} fault")

                with self.assertRaisesRegex(
                    BackupError,
                    "RESTORE_ROLLBACK_STAGE_FAILED",
                ):
                    restore_backup(
                        database,
                        backup,
                        backups_directory=backups,
                        confirmed=True,
                        fault_injector=fail_stage,
                    )
                with database.read() as connection:
                    self.assertEqual(
                        connection.execute("PRAGMA quick_check").fetchone()[0],
                        "ok",
                    )
                    self.assertEqual(
                        connection.execute("PRAGMA foreign_key_check").fetchall(),
                        [],
                    )
                    operations = tuple(
                        str(row[0])
                        for row in connection.execute(
                            "SELECT operation_id FROM processing_telemetry "
                            "ORDER BY operation_id"
                        )
                    )
                self.assertEqual(
                    operations,
                    (
                        "SYN-EVIDENCE-M4-BACKUP-ROLLBACK-STAGE-AFTER",
                        "SYN-EVIDENCE-M4-BACKUP-ROLLBACK-STAGE-ORIGINAL",
                    ),
                )
                self.assertEqual(
                    tuple(
                        item.name
                        for item in database.path.parent.iterdir()
                        if item.name.endswith((".restore.tmp", ".rollback.tmp"))
                    ),
                    (),
                )

    def test_fault_before_atomic_replace_leaves_original_database(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "ORIGINAL-BETWEEN-RENAMES")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "between-renames.sqlite3"
        create_backup(database, backup)
        _record(database, "AFTER-BACKUP")

        def interrupt(stage: str) -> None:
            if stage == "before_restore_swap":
                raise RuntimeError("synthetic pre-replace fault")

        with self.assertRaisesRegex(BackupError, "RESTORE_POST_SWAP_FAILED"):
            restore_backup(
                database,
                backup,
                backups_directory=backups,
                confirmed=True,
                fault_injector=interrupt,
            )
        with database.read() as connection:
            operations = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT operation_id FROM processing_telemetry ORDER BY operation_id"
                )
            )
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
        self.assertEqual(
            operations,
            (
                "SYN-EVIDENCE-M4-BACKUP-AFTER-BACKUP",
                "SYN-EVIDENCE-M4-BACKUP-ORIGINAL-BETWEEN-RENAMES",
            ),
        )

    def test_restore_rebinds_source_content_immediately_before_activation(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "ACTIVE")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "source-change.sqlite3"
        create_backup(database, backup)

        def mutate_source(stage: str) -> None:
            if stage != "before_restore_copy":
                return
            source = sqlite3.connect(backup)
            try:
                source.execute(
                    "UPDATE application_metadata SET application_version = '0.1.2'"
                )
                source.commit()
            finally:
                source.close()

        with self.assertRaisesRegex(BackupError, "RESTORE_SOURCE_CHANGED"):
            restore_backup(
                database,
                backup,
                backups_directory=backups,
                confirmed=True,
                fault_injector=mutate_source,
            )
        with database.read() as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
            operations = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT operation_id FROM processing_telemetry ORDER BY operation_id"
                )
            )
        self.assertEqual(operations, ("SYN-EVIDENCE-M4-BACKUP-ACTIVE",))

    def test_restore_then_same_request_is_exact_replay(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backend = DurableDemoAuditBackend(database)
        first = backend.run_demo("sales-credit-target-rep", "restore-replay")
        self.assertFalse(first.exact_replay)
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "replay.sqlite3"
        create_backup(database, backup)
        backend.run_demo("sales-credit-human-review", "after-backup")
        restore_backup(database, backup, backups_directory=backups, confirmed=True)
        replay = DurableDemoAuditBackend(database).run_demo(
            "sales-credit-target-rep",
            "restore-replay",
        )
        self.assertTrue(replay.exact_replay)

    def test_online_backup_captures_complete_snapshot_while_writer_is_uncommitted(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backup = self.root / "concurrent.sqlite3"
        writer_active = threading.Event()
        writer_committed = threading.Event()
        backup_started = threading.Event()
        backup_copied = threading.Event()
        release_writer = threading.Event()
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                with database.write() as connection:
                    _insert_retention_audit(
                        connection,
                        audit_id="SYN-EVIDENCE-M4-CONCURRENT-AUDIT",
                        purge_eligible_at="2026-08-22T00:00:00Z",
                    )
                    writer_active.set()
                    if not release_writer.wait(5):
                        raise RuntimeError("writer release timeout")
                writer_committed.set()
            except BaseException as error:
                errors.append(error)

        def backup_worker() -> None:
            try:
                def stage(name: str) -> None:
                    if name == "before_online_backup":
                        backup_started.set()
                    if name == "after_online_backup":
                        backup_copied.set()

                create_backup(
                    database,
                    backup,
                    clock=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
                    fault_injector=stage,
                )
            except BaseException as error:
                errors.append(error)

        writer_thread = threading.Thread(target=writer)
        backup_thread = threading.Thread(target=backup_worker)
        writer_thread.start()
        self.assertTrue(writer_active.wait(5))
        backup_thread.start()
        self.assertTrue(backup_started.wait(5))
        self.assertTrue(backup_copied.wait(5))
        self.assertFalse(writer_committed.is_set())
        release_writer.set()
        writer_thread.join(10)
        backup_thread.join(10)
        self.assertFalse(writer_thread.is_alive())
        self.assertFalse(backup_thread.is_alive())
        self.assertEqual(errors, [])
        receipt = verify_backup(
            backup,
            clock=lambda: datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(receipt.expires_at.value, "2026-11-18T00:00:00Z")
        snapshot = sqlite3.connect(backup)
        try:
            self.assertEqual(snapshot.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(snapshot.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                snapshot.execute(
                    "SELECT COUNT(*) FROM sc_no_order_closed_audits"
                ).fetchone(),
                (0,),
            )
            self.assertEqual(
                snapshot.execute(
                    "SELECT COUNT(*) FROM durable_commands "
                    "WHERE natural_key = 'SYN-EVIDENCE-M4-CONCURRENT-AUDIT'"
                ).fetchone(),
                (0,),
            )
        finally:
            snapshot.close()
        with database.read() as active:
            self.assertEqual(active.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(active.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                active.execute(
                    "SELECT COUNT(*) FROM sc_no_order_closed_audits "
                    "WHERE audit_id = 'SYN-EVIDENCE-M4-CONCURRENT-AUDIT'"
                ).fetchone()[0],
                1,
            )

    def test_due_retention_blocks_backup_and_active_operation_blocks_restore(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        with database.write() as connection:
            _insert_retention_audit(
                connection,
                audit_id="SYN-EVIDENCE-M4-DUE-AUDIT",
                purge_eligible_at="2026-08-20T00:00:00Z",
            )
        with self.assertRaisesRegex(BackupError, "BACKUP_RETENTION_DUE"):
            create_backup(
                database,
                self.root / "due.sqlite3",
                clock=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
            )

        clean_database = SQLiteDatabase(self.root / "clean" / "active.sqlite3")
        clean_database.initialize()
        backups = self.root / "clean-backups"
        backups.mkdir()
        backup = backups / "active.sqlite3"
        create_backup(clean_database, backup)
        active_reader = SQLiteDatabase(clean_database.path)
        self.assertIsNot(active_reader, clean_database)
        with active_reader.read():
            with self.assertRaises(DatabaseBusyError):
                restore_backup(
                    clean_database,
                    backup,
                    backups_directory=backups,
                    confirmed=True,
                )

    def test_exact_expiry_rejects_restore_and_deletes_managed_pair_idempotently(self) -> None:
        created = datetime(2026, 8, 21, tzinfo=timezone.utc)
        exact_expiry = created + timedelta(days=89)
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "EXPIRY-ACTIVE")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "expiry.sqlite3"
        receipt = create_backup(database, backup, clock=lambda: created)
        self.assertEqual(
            receipt.expires_at.value,
            exact_expiry.isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        self.assertFalse(
            purge_expired_backup(
                backup,
                clock=lambda: exact_expiry - timedelta(microseconds=1),
            )
        )
        with self.assertRaisesRegex(BackupError, "BACKUP_EXPIRED"):
            verify_backup(backup, clock=lambda: exact_expiry)
        with self.assertRaisesRegex(BackupError, "BACKUP_EXPIRED"):
            restore_backup(
                database,
                backup,
                backups_directory=backups,
                confirmed=True,
                clock=lambda: exact_expiry,
            )
        with database.read() as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
        self.assertTrue(purge_expired_backup(backup, clock=lambda: exact_expiry))
        self.assertFalse(backup.exists())
        self.assertFalse(receipt_path(backup).exists())
        self.assertFalse(purge_expired_backup(backup, clock=lambda: exact_expiry))

    def test_expired_backup_purge_faults_rollback_or_finish_forward(self) -> None:
        created = datetime(2026, 8, 21, tzinfo=timezone.utc)
        exact_expiry = created + timedelta(days=89)
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backups = self.root / "backups"
        backups.mkdir()

        rollback_backup = backups / "rollback.sqlite3"
        create_backup(database, rollback_backup, clock=lambda: created)

        def fail_before_deletion(stage: str) -> None:
            if stage == "before_expired_backup_delete":
                raise RuntimeError("synthetic pre-deletion purge fault")

        with self.assertRaisesRegex(BackupError, "BACKUP_PURGE_FAILED"):
            purge_expired_backup(
                rollback_backup,
                clock=lambda: exact_expiry,
                fault_injector=fail_before_deletion,
            )
        self.assertTrue(rollback_backup.is_file())
        self.assertTrue(receipt_path(rollback_backup).is_file())
        self.assertEqual(tuple(backups.glob("*.expired")), ())
        self.assertEqual(
            verify_backup(
                rollback_backup,
                clock=lambda: exact_expiry - timedelta(microseconds=1),
            ).expires_at.value,
            CanonicalTimestamp(
                exact_expiry.isoformat(timespec="microseconds").replace("+00:00", "Z")
            ).value,
        )

        forward_backup = backups / "forward.sqlite3"
        create_backup(database, forward_backup, clock=lambda: created)

        def fail_after_deletion(stage: str) -> None:
            if stage == "after_expired_backup_deleted":
                raise RuntimeError("synthetic post-deletion purge fault")

        with self.assertRaisesRegex(BackupError, "BACKUP_PURGE_FAILED"):
            purge_expired_backup(
                forward_backup,
                clock=lambda: exact_expiry,
                fault_injector=fail_after_deletion,
            )
        self.assertFalse(forward_backup.exists())
        self.assertFalse(receipt_path(forward_backup).exists())
        self.assertEqual(tuple(backups.glob("*.expired")), ())
        self.assertFalse(
            purge_expired_backup(forward_backup, clock=lambda: exact_expiry)
        )

        orphan_backup = backups / "orphan-sidecar.sqlite3"
        create_backup(database, orphan_backup, clock=lambda: created)
        orphan_backup.unlink()
        self.assertFalse(
            purge_expired_backup(orphan_backup, clock=lambda: exact_expiry)
        )
        self.assertFalse(receipt_path(orphan_backup).exists())

        scanned_orphan = backups / "scanned-orphan-sidecar.sqlite3"
        create_backup(database, scanned_orphan, clock=lambda: created)
        scanned_orphan.unlink()
        summary = purge_expired_backups(backups, clock=lambda: exact_expiry)
        self.assertEqual(summary.evaluated_count, 2)
        self.assertEqual(summary.purged_count, 1)
        self.assertFalse(rollback_backup.exists())
        self.assertFalse(receipt_path(scanned_orphan).exists())

    def test_restore_rejects_operation_held_by_another_process(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "cross-process.sqlite3"
        create_backup(database, backup)
        worker_source = "\n".join(
            (
                "import sys",
                "from pathlib import Path",
                "from synthetic_sales_assist.persistence.database import SQLiteDatabase",
                "database = SQLiteDatabase(Path(sys.argv[1]))",
                "with database.read():",
                "    print('READY', flush=True)",
                "    sys.stdin.readline()",
            )
        )
        environment = os.environ.copy()
        source_root = Path(__file__).resolve().parents[1] / "src"
        inherited_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(source_root)
            if not inherited_pythonpath
            else str(source_root) + os.pathsep + inherited_pythonpath
        )
        process = subprocess.Popen(
            [sys.executable, "-c", worker_source, str(database.path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        try:
            assert process.stdout is not None
            ready = process.stdout.readline().strip()
            if ready != "READY":
                assert process.stderr is not None
                self.fail(f"worker failed before lock acquisition: {process.stderr.read()}")
            with self.assertRaisesRegex(DatabaseBusyError, "DATABASE_OPERATION_ACTIVE"):
                restore_backup(
                    database,
                    backup,
                    backups_directory=backups,
                    confirmed=True,
                )
        finally:
            if process.stdin is not None:
                try:
                    process.stdin.write("\n")
                    process.stdin.flush()
                except OSError:
                    pass
            try:
                _, errors = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                _, errors = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, errors)

    def test_atomic_restore_replace_never_removes_active_path_for_observer(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        _record(database, "ATOMIC-BEFORE")
        backups = self.root / "backups"
        backups.mkdir()
        backup = backups / "atomic-observer.sqlite3"
        create_backup(database, backup)
        _record(database, "ATOMIC-AFTER")
        stop_path = self.root / "observer.stop"
        worker_source = "\n".join(
            (
                "import sys",
                "from pathlib import Path",
                "active = Path(sys.argv[1])",
                "stop = Path(sys.argv[2])",
                "missing = False",
                "samples = 0",
                "print('READY', flush=True)",
                "while not stop.exists():",
                "    missing = missing or not active.exists()",
                "    samples += 1",
                "print(f'{\"MISSING\" if missing else \"PRESENT\"}:{samples}', flush=True)",
            )
        )
        process = subprocess.Popen(
            [sys.executable, "-c", worker_source, str(database.path), str(stop_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
        )
        try:
            assert process.stdout is not None
            self.assertEqual(process.stdout.readline().strip(), "READY")
            restore_backup(
                database,
                backup,
                backups_directory=backups,
                confirmed=True,
            )
            stop_path.write_text("stop", encoding="ascii")
            observed, errors = process.communicate(timeout=10)
        except BaseException:
            process.kill()
            process.communicate(timeout=10)
            raise
        self.assertEqual(process.returncode, 0, errors)
        state, sample_count = observed.strip().split(":", 1)
        self.assertEqual(state, "PRESENT")
        self.assertGreater(int(sample_count), 0)
        self.assertTrue(database.path.is_file())

    def test_overwrite_receipt_fault_finishes_forward_without_previous_identity(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backup = self.root / "overwrite.sqlite3"
        original = create_backup(database, backup)
        original_image = backup.read_bytes()
        _record(database, "OVERWRITE-FINISH-FORWARD")
        publication_observation: list[tuple[bool, tuple[str, ...]]] = []

        def fail_before_receipt(stage: str) -> None:
            if stage == "after_backup_sidecar_publish":
                identity_previous = tuple(
                    item.name
                    for item in self.root.iterdir()
                    if item.name.startswith(f".{backup.name}.")
                    and ".receipt.json." not in item.name
                    and item.name.endswith(".previous")
                )
                publication_observation.append(
                    (backup.read_bytes() == original_image, identity_previous)
                )
            if stage == "before_backup_receipt":
                raise RuntimeError("synthetic receipt fault")

        replacement = create_backup(
            database,
            backup,
            overwrite=True,
            fault_injector=fail_before_receipt,
        )
        self.assertNotEqual(replacement.backup_id, original.backup_id)
        self.assertNotEqual(backup.read_bytes(), original_image)
        self.assertEqual(publication_observation, [(True, ())])
        self.assertEqual(verify_backup(backup), replacement)
        self.assertEqual(tuple(self.root.glob(".*.previous")), ())
        with database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM backup_receipts WHERE backup_id = ?",
                    (replacement.backup_id,),
                ).fetchone()[0],
                1,
            )

    def test_backup_maintenance_scavenges_strict_crash_identity_artifacts(self) -> None:
        created = datetime(2026, 8, 21, tzinfo=timezone.utc)
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backup = self.root / "scavenge.sqlite3"
        receipt = create_backup(database, backup, clock=lambda: created)
        prior_sidecar = receipt_path(backup).read_bytes()
        _record(database, "SCAVENGE-NEW-SNAPSHOT")
        staging = self.root / "staging"
        staging.mkdir()
        replacement = staging / "replacement.sqlite3"
        create_backup(database, replacement, clock=lambda: created)
        identifier = "A" * 32
        artifacts = (
            self.root / f".{backup.name}.{identifier}.tmp",
            self.root / f".{backup.name}.{identifier}.previous",
            self.root / f".{receipt_path(backup).name}.{identifier}.tmp",
            self.root / f".{receipt_path(backup).name}.{identifier}.previous",
        )
        artifacts[0].write_bytes(replacement.read_bytes())
        artifacts[1].write_bytes(backup.read_bytes())
        artifacts[2].write_bytes(receipt_path(replacement).read_bytes())
        artifacts[3].write_bytes(prior_sidecar)
        receipt_path(backup).write_bytes(receipt_path(replacement).read_bytes())

        summary = purge_expired_backups(
            self.root,
            clock=lambda: created + timedelta(days=1),
        )
        self.assertEqual(summary.evaluated_count, 1)
        self.assertEqual(summary.purged_count, 0)
        self.assertTrue(all(not item.exists() for item in artifacts))
        self.assertEqual(
            verify_backup(
                backup,
                clock=lambda: created + timedelta(days=1),
            ),
            receipt,
        )

    def test_new_backup_publishes_sidecar_before_identity_database(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "active.sqlite3")
        database.initialize()
        backup = self.root / "publish-order.sqlite3"
        observed: list[tuple[bool, bool]] = []

        def stop_after_sidecar(stage: str) -> None:
            if stage == "after_backup_sidecar_publish":
                observed.append((backup.exists(), receipt_path(backup).exists()))
                raise RuntimeError("synthetic publish interruption")

        with self.assertRaisesRegex(BackupError, "BACKUP_FAILED"):
            create_backup(database, backup, fault_injector=stop_after_sidecar)
        self.assertEqual(observed, [(False, True)])
        self.assertFalse(backup.exists())
        self.assertFalse(receipt_path(backup).exists())

    def test_backup_path_policy_rejects_nonlocal_or_ambiguous_paths(self) -> None:
        unsafe_values = (
            "https:" + "//invalid.example/backup.sqlite3",
            "file:///C:/invalid/backup.sqlite3",
            "../escape.sqlite3",
            "nested/relative.sqlite3",
            r"\\server\share\backup.sqlite3",
            r"\\?\C:\backup.sqlite3",
        )
        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe), self.assertRaises(BackupError):
                resolve_backup_path(
                    unsafe,
                    backups_directory=self.root / "backups",
                    repository_root=PROJECT_ROOT,
                    active_database=self.root / "active.sqlite3",
                    for_write=True,
                    create_parent=True,
                )


if __name__ == "__main__":
    unittest.main()
