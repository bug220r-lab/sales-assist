"""Lossless import contract and fail-closed review projections. No network or writes."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

SCHEMA = "doi-review-csv/v1"
HEADERS = tuple(
    (
        "schema_version,order_id,subject,selected_body_text,selected_body_sha256,"
        "preserved_original_body_text,preserved_original_rich_text_runs_json,"
        "withheld_selected_body_text,pre_cart_requirement_body_text,copy_version,"
        "source_body_sha256,recipient_email,recipient_verified,draft_status,review_approval,"
        "send_ready,source_days_json,current_rep,current_rep_eligibility,current_order_status,"
        "observed_at_utc,review_holds_json,review_gate_state_json,source_order_lines_json,"
        "alternates_json,alternate_relationship,source_alternate_relationship,"
        "complete_recipe_json,cart_links_json,cart_validation_status,source_provenance_json,"
        "reviewer_notes,existing_help_scout_reference,help_scout_draft_id"
    ).split(",")
)
JSON_FIELDS = frozenset(name for name in HEADERS if name.endswith("_json"))
JSON_OBJECT_FIELDS = {
    "review_gate_state_json",
    "complete_recipe_json",
    "source_provenance_json",
}
BODY_FIELDS = frozenset(
    {
        "selected_body_text",
        "preserved_original_body_text",
        "withheld_selected_body_text",
        "pre_cart_requirement_body_text",
    }
)
CHECKS = (
    "fitment",
    "ownership",
    "quantity",
    "kit_scope",
    "allocation",
    "stock",
    "finish_choice",
    "price",
    "customer_approval",
    "identity",
)
MAX_CSV = 32 * 1024 * 1024
MAX_ROWS = 500
MAX_CELL = 1024 * 1024
MAX_BODY = 65536
MAX_ROW = 4 * 1024 * 1024
# csv's default 128 KiB character limit rejects valid source provenance. The
# byte limits below remain authoritative, including for multibyte Unicode.
csv.field_size_limit(max(csv.field_size_limit(), MAX_CELL))
MAILBOX_ID = 166170
USER_ID = 897275
CTA_TEXT = "Get The Right Tool For The Job Here!"
CTA_URL = (
    "https://www.ecstuning.com/?utm_source=jlewis&utm_medium=email"
    "&utm_content=link2cart&salesrep=jlewis"
)
SIGNATURE = "Thanks,\nJude Lewis - ECS Tuning / Turner Motorsport\nExt. 1234"
HASH = re.compile(r"[0-9a-f]{64}\Z")
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
URL = re.compile(r"https?://[^\s<>\"\[\]()]+")
BODY_LINK = re.compile(
    r"(?<!!)(?<!\\)\[([^\[\]\r\n]+)\]\((https://[^\s<>\"\[\]()]+)\)"
    + "|" + URL.pattern + "|" + re.escape(CTA_TEXT)
)


class TransferError(ValueError):
    """Only closed error codes cross the HTTP/logging boundary."""

    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
    )


def text(value, limit=MAX_CELL, multiline=False):
    if (
        type(value) is not str
        or len(value.encode("utf-8")) > limit
        or any(
            ord(c) < 32
            and not (multiline and c in "\r\n\t")
            or ord(c) == 127
            or 0xD800 <= ord(c) <= 0xDFFF
            or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
            for c in value
        )
    ):
        raise TransferError("INVALID_TEXT")
    return value  # Never trim, normalize Unicode, or rewrite body line endings.


def order_id(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,16}", value):
        raise TransferError("INVALID_ORDER_ID")
    return value


def subject_for(value):
    return f"ORDER #{order_id(value)} DELAY - ECS TUNING - JUDE LEWIS"


def valid_email(value):
    return (
        type(value) is str
        and 3 <= len(value) <= 254
        and EMAIL.fullmatch(value)
        and ".." not in value
        and not value.startswith(".")
        and all(
            p and not p.startswith("-") and not p.endswith("-")
            for p in value.split("@")[-1].split(".")
        )
    )


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def parse_csv(csv_text):
    """Return useful row/field errors without echoing sensitive field contents."""
    if type(csv_text) is not str:
        raise TransferError("CSV_TYPE_INVALID")
    try:
        size = len(csv_text.encode("utf-8"))
    except UnicodeError:
        raise TransferError("CSV_UTF8_INVALID") from None
    if size > MAX_CSV:
        raise TransferError("CSV_TOO_LARGE", 413)
    rows, errors, seen = [], [], set()
    reader = csv.reader(io.StringIO(csv_text.removeprefix("\ufeff"), newline=""), strict=True)
    try:
        header = next(reader, [])
        if len(header) != len(HEADERS) or set(header) != set(HEADERS):
            return [], [{"row": 1, "field": "header", "code": "EXACT_HEADER_REQUIRED"}]
        for number, cells in enumerate(reader, start=2):
            if number > MAX_ROWS + 1:
                errors.append({"row": number, "field": "file", "code": "ROW_LIMIT"})
                break
            if len(cells) != len(HEADERS):
                errors.append({"row": number, "field": "row", "code": "COLUMN_COUNT"})
                continue
            value = dict(zip(header, cells, strict=True))
            issues = validate_row(value)
            oid = value["order_id"]
            if oid in seen:
                issues.append(("order_id", "DUPLICATE_ORDER_ID"))
            seen.add(oid)
            errors.extend({"row": number, "field": field, "code": code} for field, code in issues)
            if not issues:
                rows.append(value)
    except (csv.Error, UnicodeError):
        errors.append({"row": reader.line_num, "field": "row", "code": "MALFORMED_CSV"})
    if not rows and not errors:
        errors.append({"row": 1, "field": "file", "code": "EMPTY_IMPORT"})
    return rows, errors


def validate_row(row):
    issues = []
    if type(row) is not dict or set(row) != set(HEADERS):
        return [("row", "EXACT_FIELDS_REQUIRED")]
    for key, value in row.items():
        try:
            text(
                value,
                MAX_CELL if key in JSON_FIELDS else MAX_BODY,
                multiline=key in BODY_FIELDS or key in JSON_FIELDS or key == "reviewer_notes",
            )
        except (TransferError, UnicodeError):
            issues.append((key, "INVALID_TEXT"))
    if issues:
        return issues
    if len(encoded(row)) > MAX_ROW:
        issues.append(("row", "ROW_TOO_LARGE"))
    try:
        order_id(row["order_id"])
    except TransferError:
        issues.append(("order_id", "INVALID_ORDER_ID"))
    if not row["schema_version"]:
        issues.append(("schema_version", "SCHEMA_REQUIRED"))
    for key in JSON_FIELDS:
        try:
            value = unique_json(row[key])
            expected_type = dict if key in JSON_OBJECT_FIELDS else list
            if value is not None and type(value) is not expected_type:
                raise ValueError()
        except (ValueError, RecursionError):
            issues.append((key, "JSON_ARRAY_OR_OBJECT_REQUIRED"))
    for hash_field, body_field in (
        ("source_body_sha256", "preserved_original_body_text"),
        ("selected_body_sha256", "selected_body_text"),
    ):
        expected = (
            text_hash(row[body_field])
            if row[body_field] or hash_field == "selected_body_sha256"
            else ""
        )
        if row[hash_field] != expected:
            issues.append((hash_field, "EXACT_BODY_SHA256_MISMATCH"))
    if not row["copy_version"]:
        issues.append(("copy_version", "COPY_VERSION_REQUIRED"))
    for key in ("recipient_verified", "send_ready"):
        if row[key] not in {"", "true", "false"}:
            issues.append((key, "BOOLEAN_REQUIRED"))
    if row["recipient_email"] and not valid_email(row["recipient_email"]):
        issues.append(("recipient_email", "RECIPIENT_EMAIL_INVALID"))
    if row["observed_at_utc"] and not timestamp(row["observed_at_utc"]):
        issues.append(("observed_at_utc", "OFFSET_TIMESTAMP_REQUIRED"))
    return issues


def template_csv():
    out = io.StringIO(newline="")
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerow(HEADERS)
    return "\ufeff" + out.getvalue()


def product_id(value):
    if type(value) not in {str, int} or type(value) is bool:
        raise ValueError()
    token = str(value)
    if token.startswith("ES"):
        token = token[2:]
    if not re.fullmatch(r"[1-9][0-9]{0,15}", token):
        raise ValueError()
    return token


def component_map(components):
    if type(components) is not list or not 1 <= len(components) <= 30:
        raise ValueError()
    result = {}
    for item in components:
        if type(item) is not dict:
            raise ValueError()
        pid = product_id(item.get("es", item.get("product_id")))
        qty = item.get("sale_quantity")
        if type(qty) is str and re.fullmatch(r"[1-9][0-9]{0,3}", qty):
            qty = int(qty)
        if type(qty) is not int or not 1 <= qty <= 9999 or pid in result:
            raise ValueError()
        result[pid] = qty
    return result


def cart_components(url):
    """Validate pasted URLs. Never construct carts or accept redirect destinations."""
    text(url, 4096)
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc not in {"www.ecstuning.com", "ecstuning.com"}
        or parts.path != "/Cart/"
        or parts.fragment
        or any(c.isspace() for c in url)
        or "&amp;" in url
    ):
        raise ValueError()
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    params = dict(pairs)
    if len(params) != len(pairs):
        raise ValueError()
    tags = {
        "utm_source": "jlewis",
        "utm_medium": "email",
        "utm_content": "link2cart",
        "salesrep": "jlewis",
    }
    if any(params.pop(k, None) != v for k, v in tags.items()):
        raise ValueError()
    result, index = {}, 1
    while params:
        token = params.pop(f"add{index}", None)
        if type(token) is not str or not re.fullmatch(r"[1-9][0-9]{0,15}", token):
            raise ValueError()
        pid = product_id(token)
        qty = params.pop(f"qty{index}", None)
        if not qty or not re.fullmatch(r"[1-9][0-9]{0,3}", qty) or pid in result:
            raise ValueError()
        result[pid] = int(qty)
        index += 1
        if index > 31:
            raise ValueError()
    if not result:
        raise ValueError()
    return result


def cart_holds(row):
    """Only the documented structured option/recipe shape can clear scope holds."""
    if row["alternate_relationship"] == "NO_SELECTED_ALTERNATE":
        return ["NO_SELECTED_ALTERNATE"]
    holds = []
    try:
        carts = unique_json(row["cart_links_json"])
        alternatives = unique_json(row["alternates_json"])
        recipe = unique_json(row["complete_recipe_json"])
        if not isinstance(carts, list) or not carts:
            return ["NO_VERIFIED_CART"]
        if not isinstance(alternatives, list) or not alternatives:
            return ["ALTERNATE_SCOPE_UNKNOWN"]
        expected = {}
        for option in alternatives:
            oid = option["option_id"]
            if not isinstance(oid, str) or not oid or oid in expected:
                raise ValueError()
            expected[oid] = component_map(option["components"])
        relation = row["alternate_relationship"]
        if relation == "MUTUALLY_EXCLUSIVE_OPTIONS":
            targets = expected
            if len(expected) < 2:
                holds.append("OPTION_RELATIONSHIP_MISMATCH")
        elif relation == "JOINT_COMPLETE_RECIPE":
            if (
                not isinstance(recipe, dict)
                or not isinstance(recipe.get("scope_basis"), str)
                or not recipe["scope_basis"].strip()
                or not isinstance(recipe.get("kind"), str)
                or not recipe["kind"].strip()
                or not isinstance(recipe.get("holds"), list)
                or any(
                    h not in {"UNKNOWN_REMAINING_QUANTITY", "UNKNOWN_ALLOCATION"}
                    for h in recipe["holds"]
                    if isinstance(h, str)
                )
                or any(not isinstance(h, str) for h in recipe["holds"])
                or not isinstance(recipe.get("options"), list)
                or not recipe["options"]
            ):
                return ["INCOMPLETE_RECIPE"]
            if len(carts) != 1:
                return ["JOINT_RECIPE_REQUIRES_ONE_CART"]
            recipe_options = {}
            for option in recipe["options"]:
                oid = option["option_id"]
                if type(oid) is not str or not oid or oid in recipe_options:
                    raise ValueError()
                recipe_options[oid] = component_map(option["components"])
            if recipe_options != expected:
                holds.append("RECIPE_COMPONENT_MISMATCH")
            combined = {}
            for values in recipe_options.values():
                for pid, qty in values.items():
                    combined[pid] = combined.get(pid, 0) + qty
            targets = {carts[0]["option_id"]: combined}
        elif relation == "SINGLE_OPTION" and len(expected) == 1:
            targets = expected
        else:
            return ["OPTION_RELATIONSHIP_UNKNOWN"]
        found = set()
        for cart in carts:
            target = cart["option_id"]
            if target in found or target not in targets:
                raise ValueError()
            found.add(target)
            mapped = component_map(cart["components"])
            if mapped != targets[target] or cart_components(cart["url"]) != mapped:
                holds.append("CART_COMPONENT_MISMATCH")
            options = [o for o in alternatives if o["option_id"] == target]
            if relation != "JOINT_COMPLETE_RECIPE" and (
                len(options) != 1 or options[0].get("cart_url") != cart["url"]
            ):
                holds.append("ALTERNATE_CART_MAPPING_MISMATCH")
        if found != set(targets):
            holds.append("CART_OPTION_MISSING")
    except (ValueError, KeyError, TypeError, TransferError, RecursionError):
        holds.append("CART_OR_SCOPE_SCHEMA_INVALID")
    return sorted(set(holds))


def row_holds(row):
    holds = []
    if row["schema_version"] != SCHEMA:
        holds.append("SCHEMA_VERSION_REVIEW_REQUIRED")
    if not row["selected_body_text"].strip():
        holds.append("NO_SELECTED_COPY")
    if any(word in row["draft_status"].lower() for word in ("held", "withheld")):
        holds.append("SOURCE_COPY_HELD")
    if row["subject"] != subject_for(row["order_id"]):
        holds.append("SUBJECT_MISMATCH")
    if row["current_rep"] not in {"jlewis", "jlewis_web", "customer-web"}:
        holds.append("REP_ELIGIBILITY_HELD")
    if row["current_order_status"].strip().lower() in {
        "closed",
        "cancelled",
        "canceled",
        "shipped",
        "ds pending cancel",
    }:
        holds.append("ORDER_STATUS_HELD")
    if not row["current_order_status"].strip() or not timestamp(row["observed_at_utc"]):
        holds.append("CURRENT_ORDER_OBSERVATION_REQUIRED")
    if not unique_json(row["source_order_lines_json"]):
        holds.append("SOURCE_LINE_SCOPE_UNKNOWN")
    original_hash = (
        text_hash(row["preserved_original_body_text"])
        if row["preserved_original_body_text"]
        else ""
    )
    if original_hash != row["source_body_sha256"]:
        holds.append("SOURCE_BODY_HASH_MISMATCH")
    body = row["selected_body_text"]
    plain = body.replace("\r\n", "\n")
    if SIGNATURE not in plain or CTA_TEXT not in plain or CTA_URL not in body:
        holds.append("SIGNATURE_CTA_REQUIRED")
    holds.extend(cart_holds(row))
    try:
        carts = unique_json(row["cart_links_json"])
        allowed = {CTA_URL} | {c["url"] for c in carts if isinstance(c, dict) and "url" in c}
        body_urls = set(URL.findall(body))
        if not body_urls <= allowed:
            holds.append("UNREVIEWED_BODY_LINK")
        if not (allowed - {CTA_URL}) <= body_urls:
            holds.append("CART_MISSING_FROM_COPY")
    except (TypeError, ValueError):
        holds.append("CART_OR_SCOPE_SCHEMA_INVALID")
    return sorted(set(holds))


def body_segments(body):
    """Shared text/link segments for the safe UI preview and outbound HTML."""
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    parts, offset = [], 0
    for match in BODY_LINK.finditer(body):
        if match.start() > offset:
            parts.append({"text": body[offset : match.start()]})
        label, url = match.group(1), match.group(2)
        if label is None:
            label = match.group()
            url = CTA_URL if label == CTA_TEXT else label
        parts.append({"text": label, "url": url})
        offset = match.end()
    if offset < len(body):
        parts.append({"text": body[offset:]})
    return parts


def rendered_body(body):
    """Render plain labels/HTTPS links without changing stored copy or URL bytes."""
    parts = []
    for item in body_segments(body):
        label = html.escape(item["text"])
        if "url" in item:
            label = f'<a href="{html.escape(item["url"], quote=True)}">{label}</a>'
        parts.append(label)
    result = "".join(parts)
    return "<div>" + result.replace("\n", "<br>") + "</div>"


def approval_binding(row, version, review):
    return digest(
        {
            "schema": "draft-transfer-approval/v1",
            "version": version,
            "row": row,
            "review": review,
            "mailbox_id": MAILBOX_ID,
            "user_id": USER_ID,
            "html": rendered_body(row["selected_body_text"]),
        }
    )


def fresh_review():
    checks = {key: {"resolved": False, "evidence": ""} for key in CHECKS}
    checks["customer_approval"] = {
        "decision": "unreviewed",
        "conditional_copy_reviewed": False,
        "evidence": "",
    }
    return {
        "recipient_provenance": "",
        "recipient_verified": False,
        "checks": checks,
        "holds_reviewed": False,
        "holds_review_note": "",
        "carts": {},
        "duplicate_status": "unresolved",
        "duplicate_evidence": "",
    }


def validate_review(value):
    if type(value) is not dict or set(value) != set(fresh_review()):
        raise TransferError("REVIEW_FIELDS_INVALID")
    if type(value["recipient_verified"]) is not bool or type(value["holds_reviewed"]) is not bool:
        raise TransferError("REVIEW_FIELDS_INVALID")
    text(value["recipient_provenance"], 2000, multiline=True)
    text(value["holds_review_note"], 4000, multiline=True)
    if type(value["duplicate_status"]) is not str or value["duplicate_status"] not in {
        "unresolved",
        "no_existing_draft",
        "existing_draft_found",
    }:
        raise TransferError("DUPLICATE_REVIEW_INVALID")
    text(value["duplicate_evidence"], 2000, multiline=True)
    if type(value["checks"]) is not dict or set(value["checks"]) != set(CHECKS):
        raise TransferError("REVIEW_CHECKS_INVALID")
    for key, check in value["checks"].items():
        if key == "customer_approval":
            if (
                type(check) is not dict
                or set(check) != {"decision", "conditional_copy_reviewed", "evidence"}
                or type(check["decision"]) is not str
                or check["decision"]
                not in {"unreviewed", "pending_conditional_outreach", "approval_recorded"}
                or type(check["conditional_copy_reviewed"]) is not bool
            ):
                raise TransferError("CUSTOMER_DECISION_REVIEW_INVALID")
            text(check["evidence"], 2000, multiline=True)
            continue
        if (
            type(check) is not dict
            or set(check) != {"resolved", "evidence"}
            or type(check["resolved"]) is not bool
        ):
            raise TransferError("REVIEW_CHECKS_INVALID")
        text(check["evidence"], 2000, multiline=True)
    if type(value["carts"]) is not dict or len(value["carts"]) > 30:
        raise TransferError("REVIEW_CARTS_INVALID")
    for key, cart in value["carts"].items():
        text(key, 100)
        if (
            type(cart) is not dict
            or set(cart) != {"verified", "evidence", "observed_at_utc"}
            or type(cart["verified"]) is not bool
        ):
            raise TransferError("REVIEW_CARTS_INVALID")
        text(cart["evidence"], 2000, multiline=True)
        text(cart["observed_at_utc"], 80)
    return value


def review_holds(row, review):
    holds = row_holds(row)
    if not valid_email(row["recipient_email"]):
        holds.append("RECIPIENT_REQUIRED")
    if not review["recipient_verified"] or not review["recipient_provenance"].strip():
        holds.append("RECIPIENT_REVIEW_REQUIRED")
    holds.extend(
        "REVIEW_" + key.upper()
        for key, check in review["checks"].items()
        if key != "customer_approval" and (not check["resolved"] or not check["evidence"].strip())
    )
    # Old resolved/evidence reviews do not imply recorded customer consent.
    customer = review["checks"].get("customer_approval", {})
    decision = customer.get("decision", "unreviewed")
    if decision not in {"pending_conditional_outreach", "approval_recorded"}:
        holds.append("REVIEW_CUSTOMER_DECISION_REQUIRED")
    elif not customer.get("evidence", "").strip():
        holds.append("CUSTOMER_DECISION_EVIDENCE_REQUIRED")
    elif decision == "pending_conditional_outreach" and not customer.get(
        "conditional_copy_reviewed", False
    ):
        holds.append("CONDITIONAL_OUTREACH_COPY_REVIEW_REQUIRED")
    if not review["holds_reviewed"] or not review["holds_review_note"].strip():
        holds.append("IMPORTED_HOLDS_REVIEW_REQUIRED")
    if (
        review["duplicate_status"] != "no_existing_draft"
        or not review["duplicate_evidence"].strip()
    ):
        holds.append("DUPLICATE_RECONCILIATION_REQUIRED")
    carts = unique_json(row["cart_links_json"])
    if isinstance(carts, list):
        for cart in carts:
            if not isinstance(cart, dict):
                continue
            option_id = cart.get("option_id")
            checked = review["carts"].get(option_id, {}) if isinstance(option_id, str) else {}
            if (
                checked.get("verified") is not True
                or not checked.get("evidence", "").strip()
                or not timestamp(checked.get("observed_at_utc"))
            ):
                holds.append("CART_CONTENT_REVIEW_REQUIRED")
    return sorted(set(holds))
