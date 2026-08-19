"""Independent, read-only integrity checks for the supplied v1.0.1 bundle."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECKSUM_LINE_PATTERN = re.compile(r"^([0-9a-f]{64})  (.+)$")
BASE_TEST_ID_PATTERN = re.compile(r"SYN-[A-Z0-9-]+-\d{3}")
EXPECTED_SCHEMA = "synthetic-sales-assist-spec-bundle/v1.0.1"
EXPECTED_PROVENANCE_SCHEMA = "synthetic-spec-source-provenance/v1.0.1"
EXPECTED_REASON_COUNT = 138
EXPECTED_OWNERSHIP_COUNT = 138
EXPECTED_TRANSITION_COUNT = 115


class BundleAuditError(RuntimeError):
    """Raised when immutable bundle bytes or closed inventories do not verify."""


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class BundleAuditReport:
    schema_version: str
    checksum_entries: int
    manifest_entries: int
    specification_files: int
    reference_files: int
    json_files: int
    reasons: int
    ownership_rows: int
    transitions: int
    provenance_rows: int
    base_test_ids: int
    test_families: int
    checksum_file_sha256: str
    manifest_sha256: str
    inventory: tuple[InventoryEntry, ...]
    unverifiable_predecessor_fields: int

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "PASS",
            "schema_version": self.schema_version,
            "checksum_entries": self.checksum_entries,
            "manifest_entries": self.manifest_entries,
            "specification_files": self.specification_files,
            "reference_files": self.reference_files,
            "json_files": self.json_files,
            "reasons": self.reasons,
            "ownership_rows": self.ownership_rows,
            "transitions": self.transitions,
            "provenance_rows": self.provenance_rows,
            "base_test_ids": self.base_test_ids,
            "test_families": self.test_families,
            "checksum_file_sha256": self.checksum_file_sha256,
            "manifest_sha256": self.manifest_sha256,
            "unverifiable_predecessor_fields": self.unverifiable_predecessor_fields,
            "inventory": [asdict(entry) for entry in self.inventory],
        }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleAuditError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleAuditError(f"JSON_PARSE_FAILED:{path.name}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise BundleAuditError(f"FILE_UNREADABLE:{path.name}") from error
    return digest.hexdigest()


def _within(root: Path, relative_path: str) -> Path:
    if not relative_path or "\\" in relative_path:
        raise BundleAuditError("NONCANONICAL_MANIFEST_PATH")
    supplied_path = root / relative_path
    if supplied_path.is_symlink():
        raise BundleAuditError(f"MISSING_OR_LINKED_FILE:{relative_path}")
    candidate = supplied_path.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise BundleAuditError("PATH_ESCAPES_REPOSITORY") from error
    if not candidate.is_file():
        raise BundleAuditError(f"MISSING_OR_LINKED_FILE:{relative_path}")
    return candidate


def _inventory(root: Path, directory: str) -> list[InventoryEntry]:
    base = root / directory
    entries: list[InventoryEntry] = []
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise BundleAuditError(f"LINKED_BUNDLE_PATH:{path.name}")
        if path.is_file():
            entries.append(
                InventoryEntry(
                    path=path.relative_to(root).as_posix(),
                    bytes=path.stat().st_size,
                    sha256=_sha256(path),
                )
            )
    return entries


def _checksum_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise BundleAuditError("CHECKSUM_FILE_UNREADABLE") from error
    for line in lines:
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise BundleAuditError("MALFORMED_CHECKSUM_ROW")
        digest, relative_path = match.groups()
        if relative_path in rows:
            raise BundleAuditError("DUPLICATE_CHECKSUM_PATH")
        rows[relative_path] = digest
    return rows


def _as_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BundleAuditError(f"INVALID_LIST:{label}")
    return value


def _as_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleAuditError(f"INVALID_OBJECT:{label}")
    return value


def _unique_text(rows: list[Any], key: str, label: str) -> set[str]:
    values: list[str] = []
    for raw_row in rows:
        row = _as_dict(raw_row, label)
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise BundleAuditError(f"INVALID_IDENTIFIER:{label}")
        values.append(value)
    if len(values) != len(set(values)):
        raise BundleAuditError(f"DUPLICATE_IDENTIFIER:{label}")
    return set(values)


def _semantic_checks(root: Path, manifest: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    registry = _as_dict(_read_json(root / "specs/doi/reason_registry.json"), "registry")
    ownership = _as_dict(_read_json(root / "specs/doi/reason_ownership.json"), "ownership")
    transitions_doc = _as_dict(
        _read_json(root / "specs/doi/state_transitions.json"), "transitions"
    )
    reasons = _as_list(registry.get("reasons"), "reasons")
    rows = _as_list(ownership.get("rows"), "ownership_rows")
    transitions = _as_list(transitions_doc.get("transitions"), "transitions")

    reason_ids = _unique_text(reasons, "reason_id", "reason")
    ownership_ids = _unique_text(rows, "reason_code", "ownership")
    transition_ids = _unique_text(transitions, "Transition", "transition")
    counts = (len(reasons), len(rows), len(transitions))
    if counts != (EXPECTED_REASON_COUNT, EXPECTED_OWNERSHIP_COUNT, EXPECTED_TRANSITION_COUNT):
        raise BundleAuditError("CLOSED_INVENTORY_COUNT_MISMATCH")
    if reason_ids != ownership_ids:
        raise BundleAuditError("REASON_OWNERSHIP_SET_MISMATCH")
    reason_labels = {
        _as_dict(row, "reason")["reason_id"]: _as_dict(row, "reason").get("label")
        for row in reasons
    }
    ownership_labels = {
        _as_dict(row, "ownership")["reason_code"]: _as_dict(row, "ownership").get(
            "canonical_label"
        )
        for row in rows
    }
    if reason_labels != ownership_labels:
        raise BundleAuditError("REASON_LABEL_MISMATCH")

    if manifest.get("binding_reason_count") != len(reasons):
        raise BundleAuditError("MANIFEST_REASON_COUNT_MISMATCH")
    if manifest.get("binding_reason_ownership_count") != len(rows):
        raise BundleAuditError("MANIFEST_OWNERSHIP_COUNT_MISMATCH")
    if manifest.get("binding_transition_count") != len(transitions):
        raise BundleAuditError("MANIFEST_TRANSITION_COUNT_MISMATCH")
    if ownership.get("reason_count") != len(rows):
        raise BundleAuditError("DECLARED_OWNERSHIP_COUNT_MISMATCH")
    if transitions_doc.get("transition_count") != len(transitions):
        raise BundleAuditError("DECLARED_TRANSITION_COUNT_MISMATCH")

    tr004_rows = [
        _as_dict(row, "transition") for row in transitions if row.get("Transition") == "TR-004"
    ]
    if len(tr004_rows) != 1:
        raise BundleAuditError("TR004_CARDINALITY")
    tr004 = tr004_rows[0]
    branches = _as_list(tr004.get("Legal branches"), "TR004_BRANCHES")
    branch_ids = _unique_text(branches, "branch_id", "TR004_BRANCH")
    if branch_ids != {
        "SOURCE_IMPORT_FAILED_EXPLICIT_NO_RETRY",
        "PRE_EXTRACTION_RULES_UNAVAILABLE",
    }:
        raise BundleAuditError("TR004_BRANCH_SET_MISMATCH")
    forbidden = " ".join(str(item) for item in _as_list(
        tr004.get("Forbidden interpretations"), "TR004_FORBIDDEN"
    )).lower()
    if "absence of a retry command" not in forbidden or "automatic failure" not in forbidden:
        raise BundleAuditError("TR004_MISSING_NON_EVENT_GUARD")

    tr100_rows = [
        _as_dict(row, "transition") for row in transitions if row.get("Transition") == "TR-100"
    ]
    if len(tr100_rows) != 1:
        raise BundleAuditError("TR100_CARDINALITY")
    tr100_effects = str(tr100_rows[0].get("Required effects", "")).lower()
    required_tr100_phrases = (
        "terminalizes only the current attempt",
        "parent run remains in_progress indefinitely",
        "absence of either command is not an event",
        "never terminalizes the run",
    )
    if any(phrase not in tr100_effects for phrase in required_tr100_phrases):
        raise BundleAuditError("TR100_SCOPE_MISMATCH")

    rc084_rows = [
        _as_dict(row, "ownership") for row in rows if row.get("reason_code") == "RC-084"
    ]
    if len(rc084_rows) != 1:
        raise BundleAuditError("RC084_CARDINALITY")
    owned = {item.strip() for item in str(rc084_rows[0].get("owning_transitions", "")).split(",")}
    if owned != {"TR-004", "TR-027", "TR-037"}:
        raise BundleAuditError("RC084_OWNERSHIP_MISMATCH")
    if not {"TR-004", "TR-027", "TR-037"}.issubset(transition_ids):
        raise BundleAuditError("RC084_TRANSITION_MISSING")

    matrix_text = (root / "reference/doi/acceptance_test_matrix.md").read_text(encoding="utf-8")
    base_ids = {
        value
        for value in BASE_TEST_ID_PATTERN.findall(matrix_text)
        if not value.startswith(("SYN-DOI-CASE-", "SYN-DOI-ORDER-"))
    }
    families = {value.rsplit("-", 1)[0].removeprefix("SYN-") for value in base_ids}
    if manifest.get("source_derived_doi_base_test_id_count") != len(base_ids):
        raise BundleAuditError("BASE_TEST_ID_COUNT_MISMATCH")
    if manifest.get("source_derived_doi_test_family_count") != len(families):
        raise BundleAuditError("TEST_FAMILY_COUNT_MISMATCH")
    return (
        len(reasons),
        len(rows),
        len(transitions),
        len(base_ids),
        len(families),
        len(transition_ids),
    )


def audit_bundle(root: Path) -> BundleAuditReport:
    """Verify supplied bytes, metadata, provenance, JSON, and closed DOI inventories."""

    root = root.resolve()
    checksum_path = _within(root, "SHA256SUMS.txt")
    manifest_path = _within(root, "BUNDLE_MANIFEST.json")
    checksums = _checksum_rows(checksum_path)
    manifest = _as_dict(_read_json(manifest_path), "manifest")
    if manifest.get("schema_version") != EXPECTED_SCHEMA:
        raise BundleAuditError("MANIFEST_SCHEMA_MISMATCH")

    raw_files = _as_list(manifest.get("files"), "manifest_files")
    manifest_rows: dict[str, dict[str, Any]] = {}
    for raw_entry in raw_files:
        entry = _as_dict(raw_entry, "manifest_file")
        relative_path = entry.get("path")
        digest = entry.get("sha256")
        byte_count = entry.get("bytes")
        if not isinstance(relative_path, str) or relative_path in manifest_rows:
            raise BundleAuditError("INVALID_OR_DUPLICATE_MANIFEST_PATH")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise BundleAuditError("INVALID_MANIFEST_HASH")
        if not isinstance(byte_count, int) or byte_count < 0:
            raise BundleAuditError("INVALID_MANIFEST_SIZE")
        manifest_rows[relative_path] = entry

    expected_checksum_paths = set(manifest_rows) | {"BUNDLE_MANIFEST.json"}
    if set(checksums) != expected_checksum_paths:
        raise BundleAuditError("CHECKSUM_PATH_SET_MISMATCH")
    for relative_path, expected_hash in checksums.items():
        if _sha256(_within(root, relative_path)) != expected_hash:
            raise BundleAuditError(f"CHECKSUM_MISMATCH:{relative_path}")
    for relative_path, entry in manifest_rows.items():
        path = _within(root, relative_path)
        if path.stat().st_size != entry["bytes"]:
            raise BundleAuditError(f"MANIFEST_SIZE_MISMATCH:{relative_path}")
        if _sha256(path) != entry["sha256"]:
            raise BundleAuditError(f"MANIFEST_HASH_MISMATCH:{relative_path}")

    specification_inventory = _inventory(root, "specs")
    reference_inventory = _inventory(root, "reference")
    supplied_inventory = specification_inventory + reference_inventory
    supplied_paths = {entry.path for entry in supplied_inventory}
    if not supplied_paths.issubset(manifest_rows):
        raise BundleAuditError("SUPPLIED_FILE_MISSING_FROM_MANIFEST")

    json_paths = sorted(
        [root / entry.path for entry in supplied_inventory if entry.path.endswith(".json")]
        + [manifest_path]
    )
    for json_path in json_paths:
        _read_json(json_path)

    provenance = _as_dict(_read_json(root / "specs/SOURCE_PROVENANCE.json"), "provenance")
    if provenance.get("schema_version") != EXPECTED_PROVENANCE_SCHEMA:
        raise BundleAuditError("PROVENANCE_SCHEMA_MISMATCH")
    sources = _as_list(provenance.get("sources"), "provenance_sources")
    source_paths = _unique_text(sources, "sanitized_reference_path", "provenance_source")
    _unique_text(sources, "source_label", "provenance_label")
    if source_paths != {entry.path for entry in reference_inventory}:
        raise BundleAuditError("PROVENANCE_REFERENCE_SET_MISMATCH")
    for raw_source in sources:
        source = _as_dict(raw_source, "provenance_source")
        expected_hash = source.get("sanitized_sha256")
        if not isinstance(expected_hash, str) or SHA256_PATTERN.fullmatch(expected_hash) is None:
            raise BundleAuditError("INVALID_PROVENANCE_HASH")
        if _sha256(_within(root, source["sanitized_reference_path"])) != expected_hash:
            raise BundleAuditError("PROVENANCE_HASH_MISMATCH")

    reasons, ownership, transitions, base_ids, families, _ = _semantic_checks(root, manifest)
    predecessor = _as_dict(manifest.get("predecessor"), "predecessor")
    unverifiable_predecessor_fields = sum(
        1 for key in ("zip_sha256", "checksum_manifest_sha256") if key in predecessor
    )
    return BundleAuditReport(
        schema_version=EXPECTED_SCHEMA,
        checksum_entries=len(checksums),
        manifest_entries=len(manifest_rows),
        specification_files=len(specification_inventory),
        reference_files=len(reference_inventory),
        json_files=len(json_paths),
        reasons=reasons,
        ownership_rows=ownership,
        transitions=transitions,
        provenance_rows=len(sources),
        base_test_ids=base_ids,
        test_families=families,
        checksum_file_sha256=_sha256(checksum_path),
        manifest_sha256=_sha256(manifest_path),
        inventory=tuple(supplied_inventory),
        unverifiable_predecessor_fields=unverifiable_predecessor_fields,
    )
