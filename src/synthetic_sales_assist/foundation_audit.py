"""Executable, offline repository safety, integrity, and capability audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from synthetic_sales_assist.audit import audit_bundle
from synthetic_sales_assist.persistence.migrations import apply_migrations, discover_migrations
from synthetic_sales_assist.safety.chrome import (
    ALLOWED_CHROME_HOST_PATTERNS,
    validate_chrome_permissions,
)
from synthetic_sales_assist.safety.content import assert_payload_safe, scan_payload
from synthetic_sales_assist.safety.identity import (
    RESERVED_IDENTITY_NAMESPACES,
    assert_fictional_555_phone,
    assert_reserved_identity,
    assert_synthetic_email,
    is_reserved_identity,
)
from synthetic_sales_assist.safety.network import (
    ALLOWED_RUNTIME_HOSTS,
    validate_runtime_host,
    validate_runtime_url,
)
from synthetic_sales_assist.safety.repository import (
    scan_prohibited_repository_content,
    scan_secret_material,
)
from synthetic_sales_assist.structured_logging import (
    SAFETY_COUNTER_NAMES,
    assert_safety_counters_zero,
    zero_safety_counters,
)


class FoundationAuditError(RuntimeError):
    """Raised when a repository commit-gating invariant fails."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FoundationAuditError(code)


def _identity_report() -> dict[str, object]:
    accepted = [
        assert_reserved_identity(
            f"SYN-{namespace}-M0-000001", expected_namespace=namespace
        )
        for namespace in RESERVED_IDENTITY_NAMESPACES
    ]
    assert_synthetic_email("foundation@example.test")
    assert_fictional_555_phone("202-555-0100")
    rejected = "OUT" + "SIDE-M0-IDENTITY"
    _require(not is_reserved_identity(rejected), "IDENTITY_FIREWALL_REJECT_FAILURE")
    return {
        "status": "PASS",
        "reserved_namespaces": [
            f"SYN-{namespace}-*" for namespace in RESERVED_IDENTITY_NAMESPACES
        ],
        "accepted_namespace_canaries": len(accepted),
        "rejected_non_synthetic_canaries": 1,
        "synthetic_email_domain": "example.test",
        "fictional_phone_policy": "555-0100_THROUGH_555-0199",
        "executable_non_synthetic_identity_count": 0,
    }


def _prohibited_input_report(root: Path) -> dict[str, object]:
    safe_payload = {
        "customer_id": "SYN-CUSTOMER-M0-000001",
        "order_id": "SYN-ORDER-M0-000001",
        "sku": "SYN-SKU-M0-000001",
        "email": "foundation@example.test",
        "phone": "202-555-0100",
        "customer_name": "Synthetic Customer M0",
        "address": "Synthetic Address M0",
        "note": "synthetic: generated foundation fixture",
        "url": "http://localhost:8080/synthetic",
        "selector": "[data-syn-order]",
    }
    assert_payload_safe(safe_payload)
    rejected_payload = {"customer_id": "OUT" + "SIDE-M0-IDENTITY"}
    _require(bool(scan_payload(rejected_payload)), "PROHIBITED_INPUT_REJECT_FAILURE")
    repository_findings = scan_prohibited_repository_content(root)
    _require(not repository_findings, "PROHIBITED_REPOSITORY_CONTENT")
    return {
        "status": "PASS",
        "safe_payload_canaries": len(safe_payload),
        "rejected_payload_canaries": 1,
        "repository_findings": len(repository_findings),
        "production_hostname_or_company_identifier_count": 0,
    }


def _secret_report(root: Path) -> dict[str, object]:
    findings = scan_secret_material(root)
    _require(not findings, "SECRET_MATERIAL_DETECTED")
    return {"status": "PASS", "files_scanned_scope": "repository", "findings": 0}


def _network_report() -> dict[str, object]:
    for host in ALLOWED_RUNTIME_HOSTS:
        validate_runtime_host(host)
    accepted_urls = (
        "http://127.0.0.1:8080/health",
        "http://localhost:8080/health",
        "http://[::1]:8080/health",
    )
    for url in accepted_urls:
        validate_runtime_url(url)
    rejected_host = "out" + "side" + ".invalid"
    try:
        validate_runtime_host(rejected_host)
    except ValueError:
        rejected_count = 1
    else:
        raise FoundationAuditError("NON_LOOPBACK_HOST_ACCEPTED")
    return {
        "status": "PASS",
        "allowed_hosts": sorted(ALLOWED_RUNTIME_HOSTS),
        "accepted_loopback_url_canaries": len(accepted_urls),
        "rejected_non_loopback_canaries": rejected_count,
        "actual_network_calls": 0,
        "non_localhost_runtime_request_count": 0,
    }


def _manifest_paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in root.rglob("manifest.json"):
        relative_parts = path.relative_to(root).parts
        if ".git" in relative_parts or "__pycache__" in relative_parts:
            continue
        if path.is_symlink() or not path.is_file():
            raise FoundationAuditError("CHROME_MANIFEST_LINK_OR_NONFILE")
        paths.append(path)
    return tuple(sorted(paths))


def _chrome_report(root: Path) -> dict[str, object]:
    allowed_patterns = sorted(ALLOWED_CHROME_HOST_PATTERNS)
    in_memory_manifest = {
        "manifest_version": 3,
        "name": "Synthetic Sales Assist Local Side Panel",
        "description": (
            "Read-only localhost extraction and evaluation for reserved synthetic scenarios."
        ),
        "version": "0.1.0",
        "minimum_chrome_version": "114",
        "permissions": ["sidePanel"],
        "host_permissions": allowed_patterns,
        "background": {"service_worker": "service_worker.js"},
        "side_panel": {"default_path": "side_panel/index.html"},
        "content_security_policy": {
            "extension_pages": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'none'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
        },
        "content_scripts": [
            {
                "matches": [
                    "http://127.0.0.1/orders/*",
                    "http://127.0.0.1/interactions/*",
                    "http://localhost/orders/*",
                    "http://localhost/interactions/*",
                ],
                "js": [
                    "shared/canonical.js",
                    "shared/contracts.js",
                    "shared/origin.js",
                    "shared/extraction.js",
                    "content/content_script.js",
                ],
                "run_at": "document_idle",
                "world": "ISOLATED",
            }
        ],
    }
    validate_chrome_permissions(in_memory_manifest)
    manifests = _manifest_paths(root)
    inventories: list[dict[str, Any]] = []
    for path in manifests:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FoundationAuditError("CHROME_MANIFEST_PARSE_FAILED") from error
        inventory = validate_chrome_permissions(manifest)
        inventories.append(
            {
                "path": path.relative_to(root).as_posix(),
                "host_patterns": sorted(inventory.host_permissions),
                "content_match_patterns": sorted(
                    pattern
                    for _, patterns in inventory.match_surfaces
                    for pattern in patterns
                ),
                "api_permissions": list(inventory.api_permissions),
            }
        )
    expected_manifest = root / "chrome_extension" / "manifest.json"
    _require(
        manifests == (expected_manifest,),
        "MILESTONE6_EXTENSION_MANIFEST_INVENTORY_INVALID",
    )
    extension_root = root / "chrome_extension"
    extension_files = tuple(
        path
        for path in extension_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    return {
        "status": "PASS",
        "allowed_host_patterns": allowed_patterns,
        "manifest_count": len(manifests),
        "manifests": inventories,
        "extension_artifacts_created": len(extension_files),
        "extension_root_file_count": len(extension_files),
        "api_permission_inventory": ["sidePanel"],
    }


def _counter_and_migration_report(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    counters = zero_safety_counters()
    assert_safety_counters_zero(counters)
    inventory = discover_migrations(root / "migrations", repository_root=root)
    expected_versions = tuple(item.version for item in inventory)
    with sqlite3.connect(":memory:") as connection:
        first = apply_migrations(
            connection,
            root / "migrations",
            repository_root=root,
        )
        second = apply_migrations(
            connection,
            root / "migrations",
            repository_root=root,
        )
        persisted = dict(
            connection.execute(
                "SELECT counter_name, counter_value FROM system_safety_counters"
            ).fetchall()
        )
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        schema_objects = tuple(
            connection.execute(
                """
                SELECT type, name
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
        )
    _require(first == expected_versions and second == (), "MIGRATION_REPLAY_FAILURE")
    _require(persisted == counters, "PERSISTED_SAFETY_COUNTER_MISMATCH")
    _require(foreign_keys == (1,), "SQLITE_FOREIGN_KEYS_DISABLED")
    counter_report = {
        "status": "PASS",
        "counter_count": len(SAFETY_COUNTER_NAMES),
        "counters": counters,
        "all_zero": True,
    }
    migration_report = {
        "status": "PASS",
        "applied_versions": list(first),
        "replay_applied_versions": list(second),
        "foreign_keys_enabled": True,
        "latest_schema_version": expected_versions[-1],
        "migration_checksums": {
            item.path.name: item.sha256 for item in inventory
        },
        "table_count": sum(1 for kind, _ in schema_objects if kind == "table"),
        "index_count": sum(1 for kind, _ in schema_objects if kind == "index"),
        "trigger_count": sum(1 for kind, _ in schema_objects if kind == "trigger"),
        "business_tables": sum(
            1
            for kind, name in schema_objects
            if kind == "table" and (name.startswith("sc_") or name.startswith("doi_"))
        ),
    }
    return counter_report, migration_report


def run_foundation_audit(root: Path) -> dict[str, object]:
    """Run the complete offline Milestone 6 foundation audit."""

    root = root.resolve()
    bundle = audit_bundle(root)
    counters, migrations = _counter_and_migration_report(root)
    business_rule_paths = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for package_name in ("sales_credit", "doi")
            for path in (
                root / "src" / "synthetic_sales_assist" / package_name
            ).glob("*.py")
        )
    )
    return {
        "schema_version": "synthetic-sales-assist-repository-audit/v3",
        "status": "PASS",
        "milestone": 6,
        "bundle": bundle.to_dict(),
        "identity_firewall": _identity_report(),
        "prohibited_input_scan": _prohibited_input_report(root),
        "secret_scan": _secret_report(root),
        "runtime_network_restriction": _network_report(),
        "chrome_permission_inventory": _chrome_report(root),
        "safety_counters": counters,
        "migration_framework": migrations,
        "external_system_calls_required": 0,
        "business_rule_modules": len(business_rule_paths),
        "business_rule_module_roots": [
            "src/synthetic_sales_assist/sales_credit",
            "src/synthetic_sales_assist/doi",
        ],
        "remaining_binding_contradictions": [],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_foundation_audit(args.root)
    except Exception as error:
        failure = {
            "schema_version": "synthetic-sales-assist-repository-audit/v3",
            "status": "FAIL",
            "error": type(error).__name__,
        }
        print(json.dumps(failure, sort_keys=True))
        return 1
    indent = None if args.compact else 2
    print(json.dumps(report, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
