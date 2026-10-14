"""Bounded ephemeral human-review projection, separate from DOI evaluation."""

from __future__ import annotations

import copy
import csv
import io
import json
import re
import time
from collections.abc import Callable
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .staging import LINE_HEADERS, SUMMARY_HEADERS, purchase_nature, stage_capture_csvs, _time
from .review_marks import ReviewMarkError, ReviewMarkStore, evidence_key, order_key
from .triage import (
    classify_order,
    REASON_CODES,
    MISSING_FACT_CODES,
    EVIDENCE_FIELDS,
    _safe_value,
    _date,
    _APPARENT,
    _GLOBAL,
    _STRUCTURAL,
)
from .split_review import SPLIT_STATUSES, classify_split_order, validate_split_projection, _waiting
from .split_discovery import classify_split_discovery, validate_discovery_projection
from .ownership import (
    RepScopePolicy,
    DEFAULT_REP_POLICY,
    REP_SCOPES,
    classify_rep_scope,
    ownership_counts,
    full_total_order_key,
)
from .review_policy import (
    OwnerConfirmations,
    EMPTY_CONFIRMATIONS,
    text_digest,
    currency_projection,
    validate_currency,
)
from synthetic_sales_assist.domain.normalization import ascii_four_trim
from synthetic_sales_assist.domain.timestamps import canonicalize_timestamp, parse_timestamp

SCHEMA = "doi-csv-review/v6"
MAX_CSV_BYTES = 4 * 1024 * 1024
MAX_BODY_BYTES = 16 * 1024 * 1024
# DOI-specific projection bound; CSV/order/record bounds remain independent.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 5000
MAX_ORDERS = 1000
GLOBAL_HOLDS = frozenset(
    {
        "MISSING_HEADER",
        "DUPLICATE_HEADER",
        "MISSING_COLUMN",
        "UNEXPECTED_COLUMN",
        "MALFORMED_CSV",
        "MALFORMED_ROW_WIDTH",
        "INVALID_ORDER_ID",
        "CSV_INPUT_TYPE",
        "CSV_FORMULA_RISK",
    }
)
HOLD_CODES = GLOBAL_HOLDS | frozenset(
    (
        "COMPONENT_COVERAGE_INCOMPLETE CONFLICTING_LINE CONFLICTING_SUMMARY "
        "CURRENCY_UNKNOWN DISPLAYED_ORDER_ID_UNVERIFIED DS_EVIDENCE_UNKNOWN "
        "DUPLICATE_LINE_ID DUPLICATE_SUMMARY INVALID_COMPONENT_PARENT INVALID_QUANTITY "
        "LINE_EVIDENCE_GAP LINE_NATURE_UNKNOWN LINE_STRUCTURE_CONFLICT "
        "LINE_STRUCTURE_UNRESOLVED MISSING_COMPONENT_PARENT MISSING_LINE_ID MISSING_LINES "
        "MISSING_SUMMARY ORDER_CAPTURE_INCOMPLETE ORPHAN_LINE "
        "PACKAGED_PRODUCT_STRUCTURE_UNRESOLVED PAGINATION_COVERAGE_UNVERIFIED "
        "PRODUCTION_EVALUATION_NOT_PERFORMED READINESS_UNVERIFIED "
        "REQUIRED_QUANTITY_UNKNOWN REVIEW_ASSIGNMENT_UNVERIFIED "
        "SNAPSHOT_EVIDENCE_INCOMPLETE SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN "
        "SOURCE_JOIN_MISMATCH STRUCTURAL_COVERAGE_INCOMPLETE SUMMARY_LINE_COUNT_MISMATCH "
        "TIMESTAMP_INVALID_OR_NAIVE TIMESTAMP_MISMATCH TIMESTAMP_RANGE_UNSUPPORTED "
        "TIMEZONE_MISMATCH UTC_OFFSET_MISMATCH VISIBLE_COVERAGE_GAP COVERAGE_INCOMPLETE "
        "GLOBAL_INPUT_HOLD"
    ).split()
)
ERROR_CODES = frozenset(
    (
        "REVIEW_BODY_TOO_LARGE REVIEW_DUPLICATE_JSON_KEY REVIEW_JSON_INVALID "
        "REVIEW_REQUEST_MEMBERS_INVALID REVIEW_REVISION_INVALID REVIEW_CSV_TYPE_INVALID "
        "REVIEW_CSV_TOO_LARGE REVIEW_RECORD_LIMIT REVIEW_ORDER_LIMIT REVIEW_INTERNAL_ERROR "
        "REVIEW_TRANSPORT_INVALID REVIEW_RESPONSE_LIMIT REVIEW_RESPONSE_INVALID "
        "REVIEW_TTL_INVALID REVISION_MISMATCH"
    ).split()
)
HOLD_CODES = HOLD_CODES | {"CURRENCY_CONFLICT"}


class DOIReviewError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_review_envelope(raw: bytes) -> dict[str, object]:
    """Extract a trustworthy unique revision before validating action fields."""
    if type(raw) is not bytes or len(raw) > MAX_BODY_BYTES:
        raise DOIReviewError("REVIEW_BODY_TOO_LARGE")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise DOIReviewError("REVIEW_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(DOIReviewError("REVIEW_JSON_INVALID")),
        )
    except DOIReviewError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise DOIReviewError("REVIEW_JSON_INVALID") from None
    if (
        type(value) is not dict
        or "revision" not in value
        or type(value["revision"]) is not int
        or not 0 <= value["revision"] <= 2**53 - 1
    ):
        raise DOIReviewError("REVIEW_REVISION_INVALID")
    return value


def validate_review_request(value: dict[str, object], *, clear: bool = False) -> dict[str, object]:
    """Validate action fields after the caller checks the trusted revision."""
    members = {"revision"} if clear else {"revision", "summary_csv", "lines_csv"}
    if set(value) != members:
        raise DOIReviewError("REVIEW_REQUEST_MEMBERS_INVALID")
    if not clear and (type(value["summary_csv"]) is not str or type(value["lines_csv"]) is not str):
        raise DOIReviewError("REVIEW_CSV_TYPE_INVALID")
    return value


def parse_review_request(raw: bytes, *, clear: bool = False) -> dict[str, object]:
    """Convenience pure parser; HTTP uses the two phases around revision checks."""
    return validate_review_request(parse_review_envelope(raw), clear=clear)


def _empty(revision: int, status: str = "empty", code: str | None = None) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "revision": revision,
        "status": status,
        "counts": {
            name: 0
            for name in (
                "summary_records",
                "line_records",
                "orders",
                "invalid_summary_records",
                "invalid_line_records",
                "orphan_line_records",
                "purchased_records",
                "physical_purchased_records",
                "service_purchased_records",
                "component_records",
                "placeholder_records",
            )
        },
        "groups": {
            "all": 0,
            "review": 0,
            "quarantined": 0,
            "coverage_held": 0,
            "missing_evidence": 0,
            "batch_quarantine": 0,
        },
        "orders": [],
        "batch_holds": [],
        "error_code": code,
        "expires_in_seconds": 0,
        "ownership_review": ownership_counts([]),
        "split_review": {
            "schema": "doi-split-review/v1",
            "as_of": None,
            "order_count": 0,
            "status_counts": {key: 0 for key in SPLIT_STATUSES},
            "confirmed_split_count": 0,
            "decision_eligible_count": 0,
        },
    }


def _record_bound(text: str) -> None:
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        next(reader, None)
        for index, _ in enumerate(reader, 1):
            if index > MAX_RECORDS:
                raise DOIReviewError("REVIEW_RECORD_LIMIT")
    except csv.Error:
        # Staging retains parse errors and exposes closed quarantine codes.
        return


class DOIReviewSession:
    """One server-local session; never retain the raw staging batch."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: int = 1800,
        as_of: Callable[[], str] | None = None,
        rep_policy: RepScopePolicy = DEFAULT_REP_POLICY,
        owner_confirmations: OwnerConfirmations = EMPTY_CONFIRMATIONS,
        review_mark_store: ReviewMarkStore | None = None,
    ) -> None:
        if type(rep_policy) is not RepScopePolicy:
            raise DOIReviewError("REVIEW_RESPONSE_INVALID")
        self._rep_policy = rep_policy
        if type(owner_confirmations) is not OwnerConfirmations:
            raise DOIReviewError("REVIEW_RESPONSE_INVALID")
        self._owner_confirmations = owner_confirmations
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise DOIReviewError("REVIEW_TTL_INVALID")
        self._clock = clock
        if as_of is not None and not callable(as_of):
            raise DOIReviewError("REVIEW_INTERNAL_ERROR")
        self._as_of = as_of or (
            lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        self._ttl = ttl_seconds
        self._deadline: float | None = None
        self._state = _empty(0)
        self._mark_store = review_mark_store
        self._mark_bindings: dict[str, str | None] = {}

    def _expire(self) -> None:
        if self._deadline is not None and self._clock() >= self._deadline:
            self._state = _empty(int(self._state["revision"]) + 1, "expired")
            self._deadline = None
            self._mark_bindings = {}

    def _revision(self, expected: int) -> None:
        self._expire()
        if type(expected) is not int or expected != self._state["revision"]:
            raise DOIReviewError("REVISION_MISMATCH")

    def assert_revision(self, expected_revision: int) -> None:
        """Check a trustworthy request revision without altering a live session."""
        self._revision(expected_revision)

    def snapshot(self) -> dict[str, object]:
        self._expire()
        state = copy.deepcopy(self._state)
        state["expires_in_seconds"] = (
            max(0, int(self._deadline - self._clock())) if self._deadline is not None else 0
        )
        return state

    def alternate_draft_context(self, order_id: str, expected_revision: int) -> dict[str, object]:
        """Return minimized draft context without changing the review, marks or deadline."""
        self._revision(expected_revision)
        order = next((item for item in self._state["orders"] if item["order_id"] == order_id), None)
        if order is None:
            raise DOIReviewError("DRAFT_ORDER_NOT_LOADED")
        source_holds = sorted(
            set(
                order["holds"]
                + order["split"]["missing_fact_codes"]
                + order["evidence"]["missing_fact_codes"]
                + order["evidence"]["reason_codes"]
            )
        )
        return {
            "order_id": order_id,
            "evidence_key": self._mark_bindings.get(order_id),
            "rep_scope": order["rep_scope"],
            "source_holds": source_holds,
            "split_eligibility": "UNKNOWN",
            "hard_conflicts": sorted(
                set(order["holds"])
                & {
                    "CONFLICTING_LINE",
                    "CONFLICTING_SUMMARY",
                    "CURRENCY_CONFLICT",
                    "LINE_STRUCTURE_CONFLICT",
                    "SOURCE_JOIN_MISMATCH",
                }
            ),
        }

    def reviewed_snapshot(self) -> dict[str, object]:
        """Separate attention metadata; never modify the review or its deadline."""
        self._expire()
        available, storage_revision, records = False, None, {}
        if self._mark_store is not None:
            try:
                storage_revision, records = self._mark_store.read()
                available = True
            except ReviewMarkError:
                pass
        orders = []
        for item in self._state["orders"]:
            order_id = item["order_id"]
            evidence = self._mark_bindings.get(order_id)
            previous = records.get(order_key(order_id))
            status = (
                "UNAVAILABLE"
                if not available
                else "AMBIGUOUS"
                if evidence is None
                else "REVIEWED"
                if previous == evidence
                else "CHANGED"
                if previous
                else "UNREVIEWED"
            )
            orders.append({"order_id": order_id, "evidence_key": evidence, "status": status})
        return {
            "schema": "doi-reviewed-split/v1",
            "revision": self._state["revision"],
            "storage_revision": storage_revision,
            "storage_available": available,
            "orders": orders,
        }

    def set_reviewed(self, value: dict[str, object]) -> dict[str, object]:
        self._revision(value.get("revision"))
        if (
            set(value) != {"revision", "storage_revision", "order_id", "evidence_key", "reviewed"}
            or type(value["order_id"]) is not str
            or type(value["reviewed"]) is not bool
            or type(value["storage_revision"]) is not int
            or not 0 <= value["storage_revision"] < 2**53 - 1
        ):
            raise ReviewMarkError("REVIEW_MARK_REQUEST_INVALID")
        order_id = value["order_id"]
        evidence = self._mark_bindings.get(order_id)
        if evidence is None or value["evidence_key"] != evidence:
            raise ReviewMarkError("REVIEW_MARK_EVIDENCE_MISMATCH")
        if self._mark_store is None:
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE")
        self._mark_store.set(
            order_key(order_id), evidence, value["reviewed"], value["storage_revision"]
        )
        return self.reviewed_snapshot()

    def invalidate(self, code: str) -> dict[str, object]:
        allowed = {
            "REVIEW_BODY_TOO_LARGE",
            "REVIEW_DUPLICATE_JSON_KEY",
            "REVIEW_JSON_INVALID",
            "REVIEW_REQUEST_MEMBERS_INVALID",
            "REVIEW_REVISION_INVALID",
            "REVIEW_CSV_TYPE_INVALID",
            "REVIEW_CSV_TOO_LARGE",
            "REVIEW_RECORD_LIMIT",
            "REVIEW_ORDER_LIMIT",
            "REVIEW_INTERNAL_ERROR",
            "REVIEW_TRANSPORT_INVALID",
            "REVIEW_RESPONSE_LIMIT",
        }
        self._state = _empty(
            int(self._state["revision"]) + 1,
            "error",
            code if code in allowed else "REVIEW_INTERNAL_ERROR",
        )
        self._deadline = None
        self._mark_bindings = {}
        return self.snapshot()

    def clear(self, expected_revision: int) -> dict[str, object]:
        self._revision(expected_revision)
        self._state = _empty(int(self._state["revision"]) + 1)
        self._deadline = None
        self._mark_bindings = {}
        return self.snapshot()

    def close(self) -> None:
        self._state = _empty(int(self._state["revision"]) + 1)
        self._deadline = None
        self._mark_bindings = {}

    def load(self, summary_csv: str, lines_csv: str, expected_revision: int) -> dict[str, object]:
        self._revision(expected_revision)
        revision = int(self._state["revision"]) + 1
        self._state = _empty(revision)
        self._deadline = None
        self._mark_bindings = {}
        try:
            if type(summary_csv) is not str or type(lines_csv) is not str:
                raise DOIReviewError("REVIEW_CSV_TYPE_INVALID")
            for text in (summary_csv, lines_csv):
                if len(text.encode("utf-8", errors="strict")) > MAX_CSV_BYTES:
                    raise DOIReviewError("REVIEW_CSV_TOO_LARGE")
                _record_bound(text)
            batch = stage_capture_csvs(summary_csv, lines_csv)
            if len(batch.orders) > MAX_ORDERS:
                raise DOIReviewError("REVIEW_ORDER_LIMIT")
            state = _empty(revision, "loaded")
            counts = state["counts"]
            assert isinstance(counts, dict)
            counts.update(
                summary_records=len(batch.summary_occurrences),
                line_records=len(batch.line_occurrences),
                orders=len(batch.orders),
                invalid_summary_records=sum(
                    r.canonical_order_id is None for r in batch.summary_occurrences
                ),
                invalid_line_records=sum(
                    r.canonical_order_id is None for r in batch.line_occurrences
                ),
                orphan_line_records=sum(i.code == "ORPHAN_LINE" for i in batch.issues),
            )
            for row in batch.line_occurrences:
                fields = dict(row.raw_fields)
                flag = ascii_four_trim(fields.get("counts_as_purchase", "")).lower()
                purchase = flag in {"yes", "true"}
                nonpurchase = flag in {"no", "false"}
                role = ascii_four_trim(fields.get("row_type", "")).lower()
                if purchase:
                    counts["purchased_records"] += 1
                    nature = purchase_nature(
                        role,
                        fields.get("physical_or_service", ""),
                        fields.get("parent_line_id", ""),
                    )
                    if nature == "physical":
                        counts["physical_purchased_records"] += 1
                    elif nature == "service":
                        counts["service_purchased_records"] += 1
                elif nonpurchase and role in {"component", "kit_component", "kit component"}:
                    counts["component_records"] += 1
                elif nonpurchase and role in {
                    "coverage_gap",
                    "coverage-gap",
                    "coverage gap",
                    "placeholder",
                    "component coverage gap - not a merchandise line",
                }:
                    counts["placeholder_records"] += 1
            holds = sorted({i.code for i in batch.issues if i.code in GLOBAL_HOLDS})
            state["batch_holds"] = holds
            as_of = canonicalize_timestamp(self._as_of())
            summary_hash, lines_hash = text_digest(summary_csv), text_digest(lines_csv)
            orders = []
            quarantined = 0
            for order in batch.orders:
                if re.fullmatch(r"[1-9][0-9]{0,127}", order.canonical_order_id) is None:
                    raise DOIReviewError("REVIEW_ORDER_LIMIT")
                codes = sorted({i for i in order.holds if i in HOLD_CODES})
                blocked = bool(holds) or not order.visible_coverage_complete
                quarantined += int(blocked)
                projection = dict(order.review_projection)
                scope = classify_rep_scope(
                    order, policy=self._rep_policy, global_input_held=bool(holds)
                )
                confirmation = self._owner_confirmations.match(
                    order,
                    scope=scope,
                    summary_hash=summary_hash,
                    lines_hash=lines_hash,
                    as_of=as_of,
                )
                fields = (
                    dict(order.summary_occurrences[0].raw_fields)
                    if order.summary_occurrences
                    else {}
                )
                currency = currency_projection(
                    fields.get("currency_code", ""), fields.get("currency_symbol_displayed", "")
                )
                item = {
                    "order_id": order.canonical_order_id,
                    "rep_scope": "OTHER_REP" if confirmation else scope,
                    "currency": currency,
                    "reviewer_assignment": (
                        "Jude" if projection.get("review_assignment") == "Jude" else None
                    ),
                    "sales_credit_observed": (
                        "OBSERVED"
                        if projection.get("sales_credit_observed_uninterpreted") == "OBSERVED"
                        else "UNKNOWN"
                    ),
                    "sales_credit_entitlement": "UNINTERPRETED",
                    "summary_record_ordinals": [r.row_number for r in order.summary_occurrences],
                    "line_record_ordinals": [r.row_number for r in order.line_occurrences],
                    "visible_coverage_complete": order.visible_coverage_complete,
                    "evidence_complete": False,
                    "decision_eligible": False,
                    "holds": codes,
                    "split": classify_split_order(
                        order, as_of=as_of, global_input_held=bool(holds)
                    ),
                    "evidence": {
                        key: value
                        for key, value in classify_order(
                            order, as_of=as_of, global_input_held=bool(holds)
                        ).items()
                        if key
                        in {
                            "reason_codes",
                            "missing_fact_codes",
                            "evidence_references",
                            "evidence_omitted_count",
                            "capture_time",
                            "snapshot_age_seconds",
                            "snapshot_age_status",
                        }
                    },
                }
                if confirmation:
                    item["rep_confirmation"] = confirmation
                if currency[2] == "CONFLICT":
                    item["holds"] = sorted(set(item["holds"]) | {"CURRENCY_CONFLICT"})
                else:
                    item["holds"] = [code for code in item["holds"] if code != "CURRENCY_UNKNOWN"]
                    item["split"]["missing_fact_codes"] = [
                        code
                        for code in item["split"]["missing_fact_codes"]
                        if code != "CURRENCY_UNVERIFIED"
                    ]
                    item["evidence"]["missing_fact_codes"] = [
                        code
                        for code in item["evidence"]["missing_fact_codes"]
                        if code != "CURRENCY_NOT_CONFIRMED"
                    ]
                item["discovery"] = classify_split_discovery(
                    order, as_of=as_of, global_input_held=bool(holds), split=item["split"]
                )
                orders.append(item)
            state["orders"] = sorted(orders, key=full_total_order_key)
            state["ownership_review"] = ownership_counts(orders)
            observed = Counter(order["split"]["status"] for order in orders)
            state["split_review"] = {
                "schema": "doi-split-review/v1",
                "as_of": as_of,
                "order_count": len(orders),
                "status_counts": {key: observed.get(key, 0) for key in SPLIT_STATUSES},
                "confirmed_split_count": 0,
                "decision_eligible_count": 0,
            }
            state["groups"] = {
                "all": len(orders),
                "review": len(orders) - quarantined,
                "quarantined": quarantined,
                "coverage_held": sum(not o["visible_coverage_complete"] for o in orders),
                "missing_evidence": len(orders),
                "batch_quarantine": len(orders) if holds else 0,
            }
            state["status"] = "quarantined" if holds or quarantined else "loaded"
            state["expires_in_seconds"] = self._ttl
            if len(review_response_bytes(state)) > MAX_RESPONSE_BYTES:
                raise DOIReviewError("REVIEW_RESPONSE_LIMIT")
            self._state = state
            self._mark_bindings = {
                order.canonical_order_id: evidence_key(order, global_held=bool(holds))
                for order in batch.orders
            }
            self._deadline = self._clock() + self._ttl
            # batch/raw CSV are local variables only, discarded on return.
            return self.snapshot()
        except DOIReviewError as exc:
            self._state = _empty(revision, "error", exc.code)
        except Exception:
            self._state = _empty(revision, "error", "REVIEW_INTERNAL_ERROR")
        return self.snapshot()


def _validate_evidence(value: object) -> None:
    """Validate only closed source facts retained for the focused split review."""

    def bad() -> None:
        raise DOIReviewError("REVIEW_RESPONSE_INVALID")

    keys = {
        "reason_codes",
        "missing_fact_codes",
        "evidence_references",
        "evidence_omitted_count",
        "capture_time",
        "snapshot_age_seconds",
        "snapshot_age_status",
    }
    if type(value) is not dict or set(value) != keys:
        bad()
    for field, allowed, limit in (
        ("reason_codes", REASON_CODES, 12),
        ("missing_fact_codes", MISSING_FACT_CODES, 8),
    ):
        items = value[field]
        if (
            type(items) is not list
            or len(items) > limit
            or len(set(items)) != len(items)
            or any(type(x) is not str or x not in allowed for x in items)
        ):
            bad()
    if type(value["evidence_omitted_count"]) is not int or value["evidence_omitted_count"] < 0:
        bad()
    if value["snapshot_age_status"] not in {"KNOWN", "STALE", "FUTURE_CAPTURE", "UNVERIFIED"}:
        bad()
    if value["snapshot_age_seconds"] is not None and (
        type(value["snapshot_age_seconds"]) is not int or value["snapshot_age_seconds"] < 0
    ):
        bad()
    capture = value["capture_time"]
    if capture is not None and (
        type(capture) is not str or canonicalize_timestamp(capture) != capture
    ):
        bad()
    refs = value["evidence_references"]
    if type(refs) is not list or len(refs) > 6:
        bad()
    seen = set()
    for ref in refs:
        if (
            type(ref) is not dict
            or set(ref) != {"scope", "record_ordinal", "field", "observed_value", "redacted"}
            or ref["scope"] not in {"summary", "lines"}
            or type(ref["record_ordinal"]) is not int
            or not 2 <= ref["record_ordinal"] <= MAX_RECORDS + 1
            or ref["field"] not in EVIDENCE_FIELDS
            or type(ref["redacted"]) is not bool
        ):
            bad()
        identity = (ref["scope"], ref["record_ordinal"], ref["field"])
        if identity in seen:
            bad()
        seen.add(identity)
        observed = ref["observed_value"]
        if observed is None:
            if not ref["redacted"]:
                bad()
        elif (
            type(observed) is not str
            or ref["redacted"]
            or _safe_value(ref["field"], observed) != observed
        ):
            bad()


def review_response_bytes(state: dict[str, object]) -> bytes:
    """Only sessions create this closed projection; no raw model serialization."""

    def bad() -> None:
        raise DOIReviewError("REVIEW_RESPONSE_INVALID")

    if type(state) is not dict or set(state) != {
        "schema",
        "revision",
        "status",
        "counts",
        "groups",
        "orders",
        "batch_holds",
        "error_code",
        "expires_in_seconds",
        "split_review",
        "ownership_review",
    }:
        bad()
    if state["schema"] != SCHEMA or state["status"] not in {
        "empty",
        "loaded",
        "quarantined",
        "error",
        "expired",
    }:
        bad()
    for field in ("revision", "expires_in_seconds"):
        if type(state[field]) is not int or not 0 <= state[field] <= 2**53 - 1:
            bad()
    count_fields = set(_empty(0)["counts"])
    group_fields = set(_empty(0)["groups"])
    for field, expected in (("counts", count_fields), ("groups", group_fields)):
        values = state[field]
        if type(values) is not dict or set(values) != expected:
            bad()
        if any(type(value) is not int or not 0 <= value <= 10000 for value in values.values()):
            bad()

    def codes(value: object) -> None:
        if (
            type(value) is not list
            or len(value) > 256
            or any(type(code) is not str or code not in HOLD_CODES for code in value)
        ):
            bad()

    codes(state["batch_holds"])
    error = state["error_code"]
    if error is not None and (type(error) is not str or error not in ERROR_CODES):
        bad()
    orders = state["orders"]
    if type(orders) is not list or len(orders) > MAX_ORDERS:
        bad()
    for order in orders:
        expected_keys = {
            "order_id",
            "rep_scope",
            "currency",
            "reviewer_assignment",
            "sales_credit_observed",
            "sales_credit_entitlement",
            "summary_record_ordinals",
            "line_record_ordinals",
            "visible_coverage_complete",
            "evidence_complete",
            "decision_eligible",
            "holds",
            "split",
            "discovery",
            "evidence",
        }
        if type(order) is not dict or set(order) not in (
            expected_keys,
            expected_keys | {"rep_confirmation"},
        ):
            bad()
        if (
            type(order["order_id"]) is not str
            or re.fullmatch(r"[1-9][0-9]{0,127}", order["order_id"]) is None
        ):
            bad()
        if (
            order["reviewer_assignment"] not in (None, "Jude")
            or order["sales_credit_observed"] not in {"OBSERVED", "UNKNOWN"}
            or order["sales_credit_entitlement"] != "UNINTERPRETED"
        ):
            bad()
        if type(order["rep_scope"]) is not str or order["rep_scope"] not in REP_SCOPES:
            bad()
        if (
            type(order["visible_coverage_complete"]) is not bool
            or order["evidence_complete"] is not False
            or order["decision_eligible"] is not False
        ):
            bad()
        for field in ("summary_record_ordinals", "line_record_ordinals"):
            ordinals = order[field]
            if (
                type(ordinals) is not list
                or len(ordinals) > MAX_RECORDS
                or any(type(n) is not int or not 2 <= n <= MAX_RECORDS + 1 for n in ordinals)
            ):
                bad()
        codes(order["holds"])
        try:
            validate_currency(order["currency"])
            if (order["currency"][2] == "CONFLICT") != ("CURRENCY_CONFLICT" in order["holds"]):
                bad()
            if "rep_confirmation" in order:
                proof = order["rep_confirmation"]
                if (
                    order["rep_scope"] != "OTHER_REP"
                    or type(proof) is not dict
                    or set(proof) != {"confirmed_at", "evidence_reference"}
                    or type(proof["confirmed_at"]) is not str
                    or canonicalize_timestamp(proof["confirmed_at"]) != proof["confirmed_at"]
                    or type(proof["evidence_reference"]) is not str
                    or re.fullmatch(
                        r"(?:Sentinel_[a-f0-9]{32}|SYN-[A-Z0-9_-]{1,64})",
                        proof["evidence_reference"],
                    )
                    is None
                ):
                    bad()
        except (ValueError, TypeError, KeyError):
            bad()
        try:
            validate_split_projection(order["split"])
            validate_discovery_projection(order["discovery"])
            _validate_evidence(order["evidence"])
        except (ValueError, TypeError, KeyError):
            bad()
        if any(
            item["record_ordinal"] not in order["line_record_ordinals"]
            for item in order["split"]["line_items"]
        ):
            bad()
        items = {item["record_ordinal"]: item for item in order["split"]["line_items"]}
        discovery = order["discovery"]
        category = discovery["category"]
        if category != "NONE":
            blocked = (
                _GLOBAL
                | _STRUCTURAL
                | {"ORDER_CAPTURE_INCOMPLETE", "DISPLAYED_ORDER_ID_UNVERIFIED"}
            ) - {"SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN"}
            if (
                state["batch_holds"]
                or not order["visible_coverage_complete"]
                or set(order["holds"]) & blocked
                or "TERMINAL_ORDER_OBSERVED" in order["split"]["reason_codes"]
                or order["evidence"]["snapshot_age_status"] in {"UNVERIFIED", "FUTURE_CAPTURE"}
                or order["split"]["status"] == "APPARENT_SPLIT_CANDIDATE"
            ):
                bad()
            references = (
                discovery["ready_line_ordinals"]
                + discovery["waiting_line_ordinals"]
                + [clue["record_ordinal"] for clue in discovery["stock_clues"]]
            )
            if any(ordinal not in items or items[ordinal]["ds"] == "YES" for ordinal in references):
                bad()
            if category == "HELD_MIXED_LABELS":
                if (
                    order["split"]["status"] != "CAPTURE_HELD"
                    or "SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN" not in order["holds"]
                ):
                    bad()
                if any(
                    (items[ordinal]["current_stock"] or "").lower() not in _APPARENT
                    for ordinal in discovery["ready_line_ordinals"]
                ):
                    bad()
                try:
                    capture_date = (
                        _time(order["evidence"]["capture_time"])
                        .astimezone(ZoneInfo("America/New_York"))
                        .date()
                    )
                    if any(
                        not _waiting(items[ordinal]["current_stock"] or "", capture_date)
                        for ordinal in discovery["waiting_line_ordinals"]
                    ):
                        bad()
                except (ValueError, TypeError, OverflowError, AttributeError):
                    bad()
        for ordinal in order["split"]["waiting_line_ordinals"]:
            dated = _date(items[ordinal]["current_stock"] or "")
            if dated is not None:
                try:
                    captured = _time(order["evidence"]["capture_time"] or "")
                    if (
                        captured is None
                        or dated < captured.astimezone(ZoneInfo("America/New_York")).date()
                    ):
                        bad()
                except (ValueError, TypeError, OverflowError):
                    bad()
        for ref in order["evidence"]["evidence_references"]:
            scope = ref["scope"]
            headers = SUMMARY_HEADERS if scope == "summary" else LINE_HEADERS
            ordinals = (
                order["summary_record_ordinals"]
                if scope == "summary"
                else order["line_record_ordinals"]
            )
            if ref["field"] not in headers or ref["record_ordinal"] not in ordinals:
                bad()
    scope = state["ownership_review"]
    expected_scope = ownership_counts(orders)
    if (
        type(scope) is not dict
        or set(scope) != set(expected_scope)
        or scope["schema"] != expected_scope["schema"]
    ):
        bad()
    for field in ("order_count", "eligible_count", "excluded_count", "held_count"):
        if type(scope[field]) is not int or scope[field] != expected_scope[field]:
            bad()
    for field in ("status_counts", "eligible_split_counts"):
        values = scope[field]
        if (
            type(values) is not dict
            or set(values) != set(expected_scope[field])
            or any(type(value) is not int for value in values.values())
            or values != expected_scope[field]
        ):
            bad()
    triage = state["split_review"]
    if type(triage) is not dict or set(triage) != {
        "schema",
        "as_of",
        "order_count",
        "status_counts",
        "confirmed_split_count",
        "decision_eligible_count",
    }:
        bad()
    if (
        triage["schema"] != "doi-split-review/v1"
        or type(triage["order_count"]) is not int
        or triage["order_count"] != len(orders)
        or type(triage["decision_eligible_count"]) is not int
        or triage["decision_eligible_count"] != 0
        or type(triage["confirmed_split_count"]) is not int
        or triage["confirmed_split_count"] != 0
    ):
        bad()
    as_of = triage["as_of"]
    if as_of is None:
        if orders:
            bad()
    else:
        try:
            if type(as_of) is not str or canonicalize_timestamp(as_of) != as_of:
                bad()
        except (ValueError, TypeError):
            bad()
        instant = parse_timestamp(as_of)
        for order in orders:
            result = order["evidence"]
            capture_time = result["capture_time"]
            if "rep_confirmation" in order:
                proof_time = parse_timestamp(order["rep_confirmation"]["confirmed_at"])
                key = lambda t: (t.epoch_seconds, t.nanosecond)
                if capture_time is None or not key(parse_timestamp(capture_time)) <= key(
                    proof_time
                ) <= key(instant):
                    bad()
            if capture_time is None:
                if (
                    result["snapshot_age_seconds"] is not None
                    or result["snapshot_age_status"] != "UNVERIFIED"
                ):
                    bad()
                continue
            capture = parse_timestamp(capture_time)
            age_ns = (
                (instant.epoch_seconds - capture.epoch_seconds) * 1000000000
                + instant.nanosecond
                - capture.nanosecond
            )
            if age_ns < 0:
                if (
                    result["snapshot_age_seconds"] is not None
                    or result["snapshot_age_status"] != "FUTURE_CAPTURE"
                ):
                    bad()
            elif result["snapshot_age_seconds"] != age_ns // 1000000000 or result[
                "snapshot_age_status"
            ] != ("STALE" if age_ns > 86400 * 1000000000 else "KNOWN"):
                bad()
    for field, keys, observed in (
        (
            "status_counts",
            set(SPLIT_STATUSES),
            Counter(order["split"]["status"] for order in orders),
        ),
    ):
        values = triage[field]
        if (
            type(values) is not dict
            or set(values) != keys
            or any(type(n) is not int or not 0 <= n <= MAX_ORDERS for n in values.values())
        ):
            bad()
        if any(values[key] != observed.get(key, 0) for key in keys):
            bad()
    encoded = json.dumps(state, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode(
        "ascii"
    )
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise DOIReviewError("REVIEW_RESPONSE_LIMIT")
    return encoded
