"""Immutable typed access to the closed DOI reason and transition registries.

This module validates registry identity and cross-file ownership only.  It does
not evaluate a reason, authorize a transition, or execute business behavior.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast


REASON_REGISTRY_VERSION: Final = "synthetic-doi-reason-registry/v1.0.1"
REASON_REGISTRY_BASE_VERSION: Final = "synthetic-doi-reason-registry/v1"
OWNERSHIP_REGISTRY_VERSION: Final = "synthetic-doi-reason-ownership/v1.0.1"
TRANSITION_REGISTRY_VERSION: Final = "synthetic-doi-transition-registry/v1.0.1"
EXPECTED_REASON_COUNT: Final = 138
EXPECTED_OWNERSHIP_COUNT: Final = 138
EXPECTED_TRANSITION_COUNT: Final = 115

PROJECT_ROOT: Final = Path(__file__).resolve().parents[3]
_REASON_PATH: Final = PROJECT_ROOT / "specs" / "doi" / "reason_registry.json"
_OWNERSHIP_PATH: Final = PROJECT_ROOT / "specs" / "doi" / "reason_ownership.json"
_TRANSITION_PATH: Final = PROJECT_ROOT / "specs" / "doi" / "state_transitions.json"

_REASON_ID = re.compile(r"\ARC-[0-9]{3}\Z", re.ASCII)
_TRANSITION_ID = re.compile(r"\ATR-[0-9]{3}A?\Z", re.ASCII)
_CANONICAL_LABEL = re.compile(r"\A[A-Z][A-Z0-9_]*\Z", re.ASCII)
_REFERENCE_TOKEN = object()
_OWNERSHIP_VIEW_TOKEN = object()
_REGISTRIES_TOKEN = object()

_REASON_TOP_KEYS = frozenset({"reasons", "rules", "schema_version", "source_lineage"})
_REASON_ROW_KEYS = frozenset(
    {"class", "description", "label", "owner", "reason_id", "source_section"}
)
_OWNERSHIP_TOP_KEYS = frozenset(
    {"global_rule", "reason_count", "rows", "schema_version", "selector_warning"}
)
_OWNERSHIP_REQUIRED_KEYS = frozenset(
    {
        "canonical_label",
        "governing_refs",
        "ownership_mode",
        "owning_deterministic_oracles",
        "owning_rule_service_area",
        "owning_transitions",
        "reason_code",
        "registry_version",
    }
)
_OWNERSHIP_OPTIONAL_KEYS = frozenset(
    {"emission_sites", "oracle_status", "transition_guard"}
)
_OWNERSHIP_MODES = frozenset({"ASSERTED_ONLY_UNREACHABLE", "EMITTED_AND_ASSERTED"})
_OWNERSHIP_GUARDED_CODES = frozenset(f"RC-{number:03d}" for number in range(116, 139))
_TRANSITION_TOP_KEYS = frozenset(
    {
        "default_rule",
        "portal_safety",
        "reconciliation",
        "schema_version",
        "transition_count",
        "transitions",
    }
)
_TRANSITION_COMMON_KEYS = frozenset({"Transition", "section"})
_TRANSITION_SHAPES = frozenset(
    {
        frozenset({"From", "Required effects", "Required guard/evidence", "To"}),
        frozenset(
            {
                "Allowed codes",
                "Deterministic guard/evidence",
                "Entity/from",
                "Required effects",
                "To/action",
            }
        ),
        frozenset({"From", "Required effects/precedence", "Required guard/evidence", "To"}),
        frozenset(
            {
                "Allowed codes",
                "Forbidden interpretations",
                "From",
                "Legal branches",
                "Required effects",
                "Required guard/evidence",
                "To",
            }
        ),
    }
)
_TR004_FORBIDDEN_INTERPRETATIONS = (
    "Mere passage of time",
    "Absence of a retry command",
    "Retry-window expiry",
    "Background or scheduled finalization",
    "Implicit automatic failure after a failed source attempt",
)
_TR100_REQUIRED_EFFECT_FRAGMENTS = (
    "terminalizes only the current attempt",
    "parent run remains IN_PROGRESS indefinitely",
    "Absence of either command is not an event",
    "never terminalizes the run",
)


class RegistryValidationError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("DOI registry validation failed")


class RegistryLookupError(LookupError):
    def __init__(self) -> None:
        super().__init__("DOI registry reference rejected")


@dataclass(frozen=True, slots=True, init=False)
class ReasonRef:
    code: str
    label: str
    registry_version: str

    def __init__(
        self,
        code: str,
        label: str,
        registry_version: str,
        *,
        _token: object | None = None,
    ) -> None:
        if _token is not _REFERENCE_TOKEN:
            raise RegistryLookupError
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "registry_version", registry_version)


@dataclass(frozen=True, slots=True, init=False)
class TransitionRef:
    transition_id: str
    registry_version: str

    def __init__(
        self,
        transition_id: str,
        registry_version: str,
        *,
        _token: object | None = None,
    ) -> None:
        if _token is not _REFERENCE_TOKEN:
            raise RegistryLookupError
        object.__setattr__(self, "transition_id", transition_id)
        object.__setattr__(self, "registry_version", registry_version)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ReasonOwnershipView:
    """Sanitized runtime ownership metadata without planning-oracle selectors."""

    reason_code: str
    canonical_label: str
    registry_version: str
    ownership_mode: str
    owning_rule_service_area: str
    governing_refs: str
    owning_transitions: tuple[TransitionRef, ...]
    rule_or_boundary_only: bool

    def __init__(
        self,
        *,
        reason_code: str,
        canonical_label: str,
        registry_version: str,
        ownership_mode: str,
        owning_rule_service_area: str,
        governing_refs: str,
        owning_transitions: tuple[TransitionRef, ...],
        rule_or_boundary_only: bool,
        _token: object | None = None,
    ) -> None:
        if _token is not _OWNERSHIP_VIEW_TOKEN:
            raise RegistryLookupError
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "canonical_label", canonical_label)
        object.__setattr__(self, "registry_version", registry_version)
        object.__setattr__(self, "ownership_mode", ownership_mode)
        object.__setattr__(self, "owning_rule_service_area", owning_rule_service_area)
        object.__setattr__(self, "governing_refs", governing_refs)
        object.__setattr__(self, "owning_transitions", owning_transitions)
        object.__setattr__(self, "rule_or_boundary_only", rule_or_boundary_only)

    def __repr__(self) -> str:
        return "ReasonOwnershipView(<closed>)"


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryValidationError
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise RegistryValidationError


def _load_document(path: Path) -> dict[str, object]:
    load_failed = False
    decoded: object = None
    try:
        path.resolve(strict=True).relative_to(PROJECT_ROOT)
        if path.is_symlink():
            raise RegistryValidationError
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise RegistryValidationError
        decoded = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_closed_json_object,
            parse_constant=_reject_json_constant,
        )
    except Exception:
        load_failed = True
    if load_failed:
        raise RegistryValidationError
    if type(decoded) is not dict:
        raise RegistryValidationError
    return cast(dict[str, object], decoded)


def _require_closed_object(
    value: object,
    *,
    exact_keys: frozenset[str],
) -> dict[str, object]:
    if type(value) is not dict:
        raise RegistryValidationError
    result = cast(dict[str, object], value)
    if set(result) != exact_keys:
        raise RegistryValidationError
    return result


def _require_list(value: object) -> list[object]:
    if type(value) is not list:
        raise RegistryValidationError
    return cast(list[object], value)


def _require_string(value: object) -> str:
    if type(value) is not str or not value:
        raise RegistryValidationError
    return value


def _require_count(value: object, expected: int) -> None:
    if type(value) is not int or value != expected:
        raise RegistryValidationError


def _require_string_list(
    value: object,
    *,
    exact: tuple[str, ...] | None = None,
    allow_empty: bool = False,
) -> list[object]:
    result = _require_list(value)
    if not allow_empty and not result:
        raise RegistryValidationError
    for item in result:
        _require_string(item)
    if exact is not None and tuple(result) != exact:
        raise RegistryValidationError
    return result


def _freeze_json(value: object) -> object:
    if type(value) is dict:
        source = cast(dict[str, object], value)
        return MappingProxyType({key: _freeze_json(item) for key, item in source.items()})
    if type(value) is list:
        return tuple(_freeze_json(item) for item in cast(list[object], value))
    if value is None or type(value) in (str, int, bool):
        return value
    raise RegistryValidationError


def _validate_reason_metadata(document: dict[str, object]) -> None:
    lineage = _require_closed_object(
        document["source_lineage"],
        exact_keys=frozenset(
            {"approved_r01_additions", "baseline_reason_count", "effective_reason_count"}
        ),
    )
    _require_count(lineage["baseline_reason_count"], 115)
    _require_count(lineage["approved_r01_additions"], 23)
    _require_count(lineage["effective_reason_count"], EXPECTED_REASON_COUNT)
    _require_string_list(document["rules"])


def _validate_reason_rc084_emission_sites(value: object) -> None:
    sites = _require_list(value)
    if len(sites) != 2:
        raise RegistryValidationError
    evaluation = _require_closed_object(
        sites[0], exact_keys=frozenset({"site", "transitions"})
    )
    if _require_string(evaluation["site"]) != "DOIEvaluation rules-version gate":
        raise RegistryValidationError
    _require_string_list(evaluation["transitions"], exact=("TR-027", "TR-037"))

    run = _require_closed_object(
        sites[1],
        exact_keys=frozenset({"site", "transition_branch", "transitions"}),
    )
    if _require_string(run["site"]) != "DOIRun pre-extraction systemic rules gate":
        raise RegistryValidationError
    if _require_string(run["transition_branch"]) != "PRE_EXTRACTION_RULES_UNAVAILABLE":
        raise RegistryValidationError
    _require_string_list(run["transitions"], exact=("TR-004",))


def _validate_ownership_rc084_emission_sites(value: object) -> None:
    sites = _require_list(value)
    if len(sites) != 2:
        raise RegistryValidationError
    common = frozenset(
        {"persistence", "required_oracle_semantics", "site", "transitions"}
    )
    evaluation = _require_closed_object(sites[0], exact_keys=common)
    if _require_string(evaluation["site"]) != "evaluation":
        raise RegistryValidationError
    _require_string(evaluation["persistence"])
    _require_string(evaluation["required_oracle_semantics"])
    _require_string_list(evaluation["transitions"], exact=("TR-027", "TR-037"))

    run = _require_closed_object(
        sites[1], exact_keys=common | {"transition_branch"}
    )
    if _require_string(run["site"]) != "run_pre_extraction":
        raise RegistryValidationError
    _require_string(run["persistence"])
    _require_string(run["required_oracle_semantics"])
    if _require_string(run["transition_branch"]) != "PRE_EXTRACTION_RULES_UNAVAILABLE":
        raise RegistryValidationError
    _require_string_list(run["transitions"], exact=("TR-004",))


def _validate_tr004_nested_fields(row: dict[str, object]) -> None:
    branches = _require_list(row["Legal branches"])
    if len(branches) != 2:
        raise RegistryValidationError
    branch_keys = frozenset(
        {"actor", "branch_id", "guards", "predecessor", "reason_set", "terminal_trigger"}
    )
    explicit = _require_closed_object(branches[0], exact_keys=branch_keys)
    systemic = _require_closed_object(branches[1], exact_keys=branch_keys)

    if _require_string(explicit["branch_id"]) != "SOURCE_IMPORT_FAILED_EXPLICIT_NO_RETRY":
        raise RegistryValidationError
    if _require_string(explicit["terminal_trigger"]) != (
        "FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY"
    ):
        raise RegistryValidationError
    if _require_string(explicit["actor"]) != "AUTHORIZED_HUMAN":
        raise RegistryValidationError
    _require_string(explicit["predecessor"])
    _require_string_list(explicit["guards"])
    _require_string(explicit["reason_set"])

    if _require_string(systemic["branch_id"]) != "PRE_EXTRACTION_RULES_UNAVAILABLE":
        raise RegistryValidationError
    if _require_string(systemic["terminal_trigger"]) != (
        "REQUIRED_RULES_AUTHORITY_UNAVAILABLE_BEFORE_EXTRACTION"
    ):
        raise RegistryValidationError
    if _require_string(systemic["actor"]) != "SYSTEM_RULES_GATE":
        raise RegistryValidationError
    _require_string(systemic["predecessor"])
    _require_string_list(systemic["guards"])
    _require_string_list(systemic["reason_set"], exact=("RC-084",))
    _require_string_list(
        row["Forbidden interpretations"], exact=_TR004_FORBIDDEN_INTERPRETATIONS
    )


def _validate_tr100_protected_effects(row: dict[str, object]) -> None:
    effects = _require_string(row["Required effects"])
    if any(fragment not in effects for fragment in _TR100_REQUIRED_EFFECT_FRAGMENTS):
        raise RegistryValidationError


def _validate_reason_rows(document: dict[str, object]) -> list[dict[str, object]]:
    if set(document) != _REASON_TOP_KEYS:
        raise RegistryValidationError
    if document["schema_version"] != REASON_REGISTRY_VERSION:
        raise RegistryValidationError
    _validate_reason_metadata(document)
    rows = _require_list(document["reasons"])
    _require_count(len(rows), EXPECTED_REASON_COUNT)

    result: list[dict[str, object]] = []
    expected_ids = tuple(f"RC-{number:03d}" for number in range(1, 139))
    seen_labels: set[str] = set()
    for index, value in enumerate(rows):
        if type(value) is not dict:
            raise RegistryValidationError
        row = cast(dict[str, object], value)
        valid_keys = _REASON_ROW_KEYS
        if row.get("reason_id") == "RC-084":
            valid_keys = valid_keys | {"emission_sites"}
        if set(row) != valid_keys:
            raise RegistryValidationError
        code = _require_string(row["reason_id"])
        label = _require_string(row["label"])
        if code != expected_ids[index] or _REASON_ID.fullmatch(code) is None:
            raise RegistryValidationError
        if _CANONICAL_LABEL.fullmatch(label) is None or label in seen_labels:
            raise RegistryValidationError
        seen_labels.add(label)
        for key in ("class", "description", "owner", "source_section"):
            _require_string(row[key])
        if code == "RC-084":
            _validate_reason_rc084_emission_sites(row["emission_sites"])
        result.append(row)
    return result


def _validate_transition_rows(document: dict[str, object]) -> list[dict[str, object]]:
    if set(document) != _TRANSITION_TOP_KEYS:
        raise RegistryValidationError
    if document["schema_version"] != TRANSITION_REGISTRY_VERSION:
        raise RegistryValidationError
    _require_count(document["transition_count"], EXPECTED_TRANSITION_COUNT)
    _require_string(document["default_rule"])
    _require_string(document["portal_safety"])
    reconciliation = _require_closed_object(
        document["reconciliation"], exact_keys=frozenset({"changes", "version"})
    )
    if _require_string(reconciliation["version"]) != "v1.0.1":
        raise RegistryValidationError
    _require_string_list(reconciliation["changes"])
    rows = _require_list(document["transitions"])
    _require_count(len(rows), EXPECTED_TRANSITION_COUNT)

    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in rows:
        if type(value) is not dict:
            raise RegistryValidationError
        row = cast(dict[str, object], value)
        transition_id = _require_string(row.get("Transition"))
        if _TRANSITION_ID.fullmatch(transition_id) is None or transition_id in seen:
            raise RegistryValidationError
        seen.add(transition_id)
        if not _TRANSITION_COMMON_KEYS.issubset(row):
            raise RegistryValidationError
        if frozenset(row) - _TRANSITION_COMMON_KEYS not in _TRANSITION_SHAPES:
            raise RegistryValidationError
        for key, item in row.items():
            if key not in {"Forbidden interpretations", "Legal branches"}:
                _require_string(item)
        if transition_id == "TR-004":
            if not {"Forbidden interpretations", "Legal branches"}.issubset(row):
                raise RegistryValidationError
            _validate_tr004_nested_fields(row)
        elif "Forbidden interpretations" in row or "Legal branches" in row:
            raise RegistryValidationError
        if transition_id == "TR-100":
            _validate_tr100_protected_effects(row)
        result.append(row)
    return result


def _validate_ownership_rows(document: dict[str, object]) -> list[dict[str, object]]:
    if set(document) != _OWNERSHIP_TOP_KEYS:
        raise RegistryValidationError
    if document["schema_version"] != OWNERSHIP_REGISTRY_VERSION:
        raise RegistryValidationError
    _require_count(document["reason_count"], EXPECTED_OWNERSHIP_COUNT)
    _require_string(document["global_rule"])
    _require_string(document["selector_warning"])
    rows = _require_list(document["rows"])
    _require_count(len(rows), EXPECTED_OWNERSHIP_COUNT)

    result: list[dict[str, object]] = []
    for value in rows:
        if type(value) is not dict:
            raise RegistryValidationError
        row = cast(dict[str, object], value)
        code = _require_string(row.get("reason_code"))
        keys = frozenset(row)
        if code == "RC-084":
            expected_keys = _OWNERSHIP_REQUIRED_KEYS | {"emission_sites", "oracle_status"}
        elif code in _OWNERSHIP_GUARDED_CODES:
            expected_keys = _OWNERSHIP_REQUIRED_KEYS | {"oracle_status", "transition_guard"}
        else:
            expected_keys = _OWNERSHIP_REQUIRED_KEYS
        if keys != expected_keys or keys - _OWNERSHIP_REQUIRED_KEYS - _OWNERSHIP_OPTIONAL_KEYS:
            raise RegistryValidationError
        for key in _OWNERSHIP_REQUIRED_KEYS:
            _require_string(row[key])
        if row["ownership_mode"] not in _OWNERSHIP_MODES:
            raise RegistryValidationError
        version = row["registry_version"]
        if version not in {REASON_REGISTRY_BASE_VERSION, REASON_REGISTRY_VERSION}:
            raise RegistryValidationError
        if "oracle_status" in row:
            _require_string(row["oracle_status"])
        if "transition_guard" in row:
            _require_string(row["transition_guard"])
        if code == "RC-084":
            _validate_ownership_rc084_emission_sites(row["emission_sites"])
        result.append(row)
    return result


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DoiRegistries:
    reason_registry_version: str
    ownership_registry_version: str
    transition_registry_version: str
    reason_refs: tuple[ReasonRef, ...]
    transition_refs: tuple[TransitionRef, ...]
    _reason_by_code: Mapping[str, ReasonRef]
    _reason_by_label: Mapping[str, ReasonRef]
    _transition_by_id: Mapping[str, TransitionRef]
    _reason_records: Mapping[str, Mapping[str, object]]
    _ownership_by_code: Mapping[str, ReasonOwnershipView]
    _transition_records: Mapping[str, Mapping[str, object]]

    def __init__(self) -> None:
        raise RegistryLookupError

    @classmethod
    def _create(
        cls,
        *,
        reason_registry_version: str,
        ownership_registry_version: str,
        transition_registry_version: str,
        reason_refs: tuple[ReasonRef, ...],
        transition_refs: tuple[TransitionRef, ...],
        reason_by_code: dict[str, ReasonRef],
        reason_by_label: dict[str, ReasonRef],
        transition_by_id: dict[str, TransitionRef],
        reason_records: dict[str, Mapping[str, object]],
        ownership_by_code: dict[str, ReasonOwnershipView],
        transition_records: dict[str, Mapping[str, object]],
        _token: object | None = None,
    ) -> DoiRegistries:
        if _token is not _REGISTRIES_TOKEN:
            raise RegistryLookupError
        result = object.__new__(cls)
        object.__setattr__(result, "reason_registry_version", reason_registry_version)
        object.__setattr__(result, "ownership_registry_version", ownership_registry_version)
        object.__setattr__(result, "transition_registry_version", transition_registry_version)
        object.__setattr__(result, "reason_refs", reason_refs)
        object.__setattr__(result, "transition_refs", transition_refs)
        object.__setattr__(result, "_reason_by_code", MappingProxyType(dict(reason_by_code)))
        object.__setattr__(result, "_reason_by_label", MappingProxyType(dict(reason_by_label)))
        object.__setattr__(
            result, "_transition_by_id", MappingProxyType(dict(transition_by_id))
        )
        object.__setattr__(
            result, "_reason_records", MappingProxyType(dict(reason_records))
        )
        object.__setattr__(
            result, "_ownership_by_code", MappingProxyType(dict(ownership_by_code))
        )
        object.__setattr__(
            result, "_transition_records", MappingProxyType(dict(transition_records))
        )
        return result

    def __repr__(self) -> str:
        return "DoiRegistries(<closed>)"

    @property
    def reason_count(self) -> int:
        return len(self.reason_refs)

    @property
    def ownership_count(self) -> int:
        return len(self._ownership_by_code)

    @property
    def transition_count(self) -> int:
        return len(self.transition_refs)

    def reason_ref(
        self,
        code: object,
        *,
        expected_label: str | None = None,
        expected_registry_version: str | None = None,
    ) -> ReasonRef:
        if type(code) is not str:
            raise RegistryLookupError
        result = self._reason_by_code.get(code)
        if result is None:
            raise RegistryLookupError
        if expected_label is not None and expected_label != result.label:
            raise RegistryLookupError
        if (
            expected_registry_version is not None
            and expected_registry_version != result.registry_version
        ):
            raise RegistryLookupError
        return result

    def reason_ref_by_label(
        self,
        label: object,
        *,
        expected_registry_version: str | None = None,
    ) -> ReasonRef:
        if type(label) is not str:
            raise RegistryLookupError
        result = self._reason_by_label.get(label)
        if result is None:
            raise RegistryLookupError
        if (
            expected_registry_version is not None
            and expected_registry_version != result.registry_version
        ):
            raise RegistryLookupError
        return result

    def transition_ref(
        self,
        transition_id: object,
        *,
        expected_registry_version: str | None = None,
    ) -> TransitionRef:
        if type(transition_id) is not str:
            raise RegistryLookupError
        result = self._transition_by_id.get(transition_id)
        if result is None:
            raise RegistryLookupError
        if (
            expected_registry_version is not None
            and expected_registry_version != result.registry_version
        ):
            raise RegistryLookupError
        return result

    def reason_record(self, reason: ReasonRef | str) -> Mapping[str, object]:
        ref = reason if isinstance(reason, ReasonRef) else self.reason_ref(reason)
        if ref.registry_version != self.reason_registry_version:
            raise RegistryLookupError
        record = self._reason_records.get(ref.code)
        if record is None:
            raise RegistryLookupError
        return record

    def ownership_record(self, reason: ReasonRef | str) -> ReasonOwnershipView:
        ref = reason if isinstance(reason, ReasonRef) else self.reason_ref(reason)
        if ref.registry_version != self.reason_registry_version:
            raise RegistryLookupError
        record = self._ownership_by_code.get(ref.code)
        if record is None:
            raise RegistryLookupError
        return record

    def transition_record(self, transition: TransitionRef | str) -> Mapping[str, object]:
        ref = (
            transition
            if isinstance(transition, TransitionRef)
            else self.transition_ref(transition)
        )
        if ref.registry_version != self.transition_registry_version:
            raise RegistryLookupError
        record = self._transition_records.get(ref.transition_id)
        if record is None:
            raise RegistryLookupError
        return record

    def ownership_transition_refs(
        self, reason: ReasonRef | str
    ) -> tuple[TransitionRef, ...]:
        return self.ownership_record(reason).owning_transitions

    def is_rule_or_boundary_only(self, reason: ReasonRef | str) -> bool:
        return self.ownership_record(reason).rule_or_boundary_only


def _build_registries() -> DoiRegistries:
    reason_document = _load_document(_REASON_PATH)
    ownership_document = _load_document(_OWNERSHIP_PATH)
    transition_document = _load_document(_TRANSITION_PATH)
    reason_rows = _validate_reason_rows(reason_document)
    ownership_rows = _validate_ownership_rows(ownership_document)
    transition_rows = _validate_transition_rows(transition_document)

    reason_refs = tuple(
        ReasonRef(
            cast(str, row["reason_id"]),
            cast(str, row["label"]),
            REASON_REGISTRY_VERSION,
            _token=_REFERENCE_TOKEN,
        )
        for row in reason_rows
    )
    transition_refs = tuple(
        TransitionRef(
            cast(str, row["Transition"]),
            TRANSITION_REGISTRY_VERSION,
            _token=_REFERENCE_TOKEN,
        )
        for row in transition_rows
    )
    reason_by_code = {ref.code: ref for ref in reason_refs}
    reason_by_label = {ref.label: ref for ref in reason_refs}
    transition_by_id = {ref.transition_id: ref for ref in transition_refs}

    ownership_codes = tuple(cast(str, row["reason_code"]) for row in ownership_rows)
    if ownership_codes != tuple(ref.code for ref in reason_refs):
        raise RegistryValidationError

    ownership_transitions: dict[str, tuple[TransitionRef, ...]] = {}
    rule_or_boundary_only: set[str] = set()
    for row in ownership_rows:
        code = cast(str, row["reason_code"])
        reason = reason_by_code.get(code)
        if reason is None or row["canonical_label"] != reason.label:
            raise RegistryValidationError
        if code == "RC-084":
            if row["registry_version"] != REASON_REGISTRY_VERSION:
                raise RegistryValidationError
        elif row["registry_version"] != REASON_REGISTRY_BASE_VERSION:
            raise RegistryValidationError

        raw_transitions = cast(str, row["owning_transitions"])
        if raw_transitions == "NONE_RULE_OR_BOUNDARY":
            ownership_transitions[code] = ()
            rule_or_boundary_only.add(code)
            continue
        transition_ids = tuple(raw_transitions.split(","))
        if len(set(transition_ids)) != len(transition_ids):
            raise RegistryValidationError
        unresolved_transition = False
        try:
            ownership_transitions[code] = tuple(
                transition_by_id[transition_id] for transition_id in transition_ids
            )
        except KeyError:
            unresolved_transition = True
        if unresolved_transition:
            raise RegistryValidationError

    reason_records = {
        cast(str, row["reason_id"]): cast(Mapping[str, object], _freeze_json(row))
        for row in reason_rows
    }
    transition_records = {
        cast(str, row["Transition"]): cast(Mapping[str, object], _freeze_json(row))
        for row in transition_rows
    }
    ownership_by_code = {
        cast(str, row["reason_code"]): ReasonOwnershipView(
            reason_code=cast(str, row["reason_code"]),
            canonical_label=cast(str, row["canonical_label"]),
            registry_version=cast(str, row["registry_version"]),
            ownership_mode=cast(str, row["ownership_mode"]),
            owning_rule_service_area=cast(str, row["owning_rule_service_area"]),
            governing_refs=cast(str, row["governing_refs"]),
            owning_transitions=ownership_transitions[cast(str, row["reason_code"])],
            rule_or_boundary_only=cast(str, row["reason_code"])
            in rule_or_boundary_only,
            _token=_OWNERSHIP_VIEW_TOKEN,
        )
        for row in ownership_rows
    }

    return DoiRegistries._create(
        reason_registry_version=REASON_REGISTRY_VERSION,
        ownership_registry_version=OWNERSHIP_REGISTRY_VERSION,
        transition_registry_version=TRANSITION_REGISTRY_VERSION,
        reason_refs=reason_refs,
        transition_refs=transition_refs,
        reason_by_code=reason_by_code,
        reason_by_label=reason_by_label,
        transition_by_id=transition_by_id,
        reason_records=reason_records,
        ownership_by_code=ownership_by_code,
        transition_records=transition_records,
        _token=_REGISTRIES_TOKEN,
    )


@lru_cache(maxsize=1)
def load_doi_registries() -> DoiRegistries:
    """Load, validate, and cache the immutable supplied DOI registries."""

    return _build_registries()


__all__ = [
    "EXPECTED_OWNERSHIP_COUNT",
    "EXPECTED_REASON_COUNT",
    "EXPECTED_TRANSITION_COUNT",
    "OWNERSHIP_REGISTRY_VERSION",
    "REASON_REGISTRY_BASE_VERSION",
    "REASON_REGISTRY_VERSION",
    "TRANSITION_REGISTRY_VERSION",
    "DoiRegistries",
    "ReasonOwnershipView",
    "ReasonRef",
    "RegistryLookupError",
    "RegistryValidationError",
    "TransitionRef",
    "load_doi_registries",
]
