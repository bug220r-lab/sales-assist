"""SYNTHETIC-SALES-ASSIST-AUTHORED-M5: local alternate-email drafts; no network."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import stat
from urllib.parse import urlsplit, unquote, parse_qsl

from synthetic_sales_assist.persistence.paths import validate_local_path

SCHEMA = "doi-alternate-draft/v1"
STORE_SCHEMA = "doi-alternate-drafts-store/v1"
MAX_REQUEST = 32768
MAX_STORE = 4 * 1024 * 1024
MAX_DRAFTS = 500
CHECKS = {
    "fitment": "Fitment / application",
    "ownership": "Order ownership",
    "quantity": "Required quantity",
    "kit_scope": "Full kit / component scope",
    "allocation": "Allocation",
    "stock": "Current stock / availability",
    "finish_choice": "Finish choice",
    "price": "Price / substitution cost",
}
CTA_TEXT = "Get The Right Tool For The Job Here!"
CTA_URL = "https://www.ecstuning.com/?utm_source=jlewis&utm_medium=email&utm_content=link2cart&salesrep=jlewis"
SIGNATURE = "Thanks,\nJude Lewis - ECS Tuning / Turner Motorsport\nExt. 1234"
HASH = re.compile(r"[0-9a-f]{64}\Z")


class DraftError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def encoded(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _fail(code="DRAFT_INPUT_INVALID"):
    raise DraftError(code)


def _text(value, maximum, *, multiline=False):
    if (
        type(value) is not str
        or len(value) > maximum
        or any(
            ord(c) < 32
            and not (multiline and c in "\n\t")
            or ord(c) == 127
            or 0xD800 <= ord(c) <= 0xDFFF
            or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
            for c in value
        )
    ):
        _fail()
    return value.strip()


def valid_url(value):
    value = _text(value, 1500)
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        decoded = unquote(value)
        if (
            parts.scheme != "https"
            or parts.netloc
            not in {
                "www.ecstuning.com",
                "ecstuning.com",
                "www.turnermotorsport.com",
                "turnermotorsport.com",
            }
            or not parts.path.startswith("/")
            or parts.fragment
            or any(c.isspace() or ord(c) < 32 or c in '<>"\\' for c in decoded)
            or "&amp;" in value
        ):
            _fail("DRAFT_LINK_INVALID")
    except ValueError:
        _fail("DRAFT_LINK_INVALID")
    return value


def empty_fields():
    return dict(
        original_item="",
        alternate_name="",
        selected_line_ids="",
        source_quantities_exact="",
        alternate_id="",
        alternate_quantity="",
        alternate_observed_at="",
        stock_wording="",
        material_differences="",
        technical_conflict=False,
        technical_note="",
        delay_verified=False,
        delay_note="",
        product_url="",
        product_verified=False,
        product_note="",
        product_verifier="",
        product_observed_at="",
        cart_url="",
        cart_verified=False,
        cart_note="",
        cart_verifier="",
        cart_observed_at="",
        checks={key: dict(status="unresolved", note="") for key in CHECKS},
    )


def validate_fields(value):
    if type(value) is not dict or set(value) != set(empty_fields()):
        _fail()
    result = {}
    for name in ("original_item", "alternate_name"):
        result[name] = _text(value[name], 180)
    for name in (
        "delay_note",
        "product_note",
        "cart_note",
        "selected_line_ids",
        "source_quantities_exact",
        "alternate_id",
        "alternate_quantity",
        "alternate_observed_at",
        "stock_wording",
        "material_differences",
        "technical_note",
        "product_observed_at",
        "cart_observed_at",
    ):
        result[name] = _text(value[name], 300)
    for name in ("delay_verified", "product_verified", "cart_verified", "technical_conflict"):
        if type(value[name]) is not bool:
            _fail()
        result[name] = value[name]
    for name in ("product_verifier", "cart_verifier"):
        if value[name] not in ("", "research_tool", "human_review"):
            _fail()
        result[name] = value[name]
    for name in ("product_url", "cart_url"):
        result[name] = valid_url(value[name])
    if type(value["checks"]) is not dict or set(value["checks"]) != set(CHECKS):
        _fail()
    result["checks"] = {}
    for name, check in value["checks"].items():
        if (
            type(check) is not dict
            or set(check) != {"status", "note"}
            or check["status"] not in ("unresolved", "verified", "not_applicable")
        ):
            _fail()
        if check["status"] == "not_applicable" and name not in {
            "kit_scope",
            "allocation",
            "finish_choice",
        }:
            _fail()
        result["checks"][name] = dict(status=check["status"], note=_text(check["note"], 300))
    return result


def cart_matches(fields):
    """Recognize the supplied single-product cart schema; never construct a cart."""
    if not fields["cart_url"]:
        return False
    parts = urlsplit(fields["cart_url"])
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = dict(pairs)
    return (
        parts.hostname in {"www.ecstuning.com", "ecstuning.com"}
        and parts.path == "/Cart/"
        and len(query) == len(pairs)
        and set(query) <= {"add1", "qty1", "utm_source", "utm_medium", "utm_content", "salesrep"}
        and re.fullmatch(r"[1-9][0-9]{0,63}", fields["alternate_id"]) is not None
        and re.fullmatch(r"[1-9][0-9]{0,3}", fields["alternate_quantity"]) is not None
        and query.get("add1") == fields["alternate_id"]
        and query.get("qty1") == fields["alternate_quantity"]
    )


def valid_observed_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def link_verified(fields, prefix):
    return (
        fields[prefix + "_verified"]
        and fields[prefix + "_note"]
        and fields[prefix + "_verifier"] in {"research_tool", "human_review"}
        and valid_observed_time(fields[prefix + "_observed_at"])
    )


def verified_links(fields):
    return [
        fields[prefix + "_url"]
        for prefix in ("product", "cart")
        if link_verified(fields, prefix)
        and fields[prefix + "_url"]
        and (prefix != "cart" or cart_matches(fields))
    ]


def generated_body(fields):
    item = fields["original_item"] or "an item"
    candidate = fields["alternate_name"]
    verified_delay = fields["delay_verified"] and fields["delay_note"]
    intro = f"The {item} is delayed." if verified_delay else f"I’m checking the details for {item}."
    option = (
        f"{candidate} may be an option to consider."
        if candidate
        else "I’m checking whether an alternate option is available."
    )
    if fields["material_differences"]:
        option += " " + fields["material_differences"]
    links = verified_links(fields)
    parts = [
        "Hello!",
        "This is Jude from ECS Tuning / Turner Motorsport reaching out about your order. "
        + intro
        + " "
        + option,
    ]
    if links:
        parts.append("\n".join(links))
    parts.append("If you’d like me to look into this swap, please let me know.")
    return "\n\n".join(parts)


def validate_entry(value):
    if type(value) is not dict or set(value) != {"fields", "body", "body_reviewed"}:
        _fail()
    fields = validate_fields(value["fields"])
    body = _text(value["body"], 5000, multiline=True)
    if type(value["body_reviewed"]) is not bool:
        _fail()
    # Editable prose remains plain text. Only exact reviewer-verified URLs may be exported.
    allowed = set(verified_links(fields)) | {CTA_URL}
    for match in re.findall(r"https?://[^\s<>]+", body):
        if match.rstrip(".,;!()") not in allowed:
            _fail("DRAFT_BODY_LINK_UNVERIFIED")
    if re.search(r"(?:javascript|data|file|vbscript):|www\.", body, re.I):
        stripped = body
        for url in allowed:
            stripped = stripped.replace(url, "")
        if re.search(r"(?:javascript|data|file|vbscript):|www\.", stripped, re.I):
            _fail("DRAFT_BODY_LINK_UNVERIFIED")
    return dict(fields=fields, body=body, body_reviewed=value["body_reviewed"])


def projection(context, entry, *, changed=False):
    entry = validate_entry(entry)
    f = entry["fields"]
    holds = []
    if context["rep_scope"] not in {"OWNER", "UNASSIGNED_WEB"}:
        holds.append("Captured order ownership is unresolved or assigned to another rep.")
    if context["evidence_key"] is None:
        holds.append("The capture identity is ambiguous; saving this candidate is disabled.")
    if changed:
        holds.append(
            (
                'This saved draft belongs to different capture evidence. Recheck '
                'every field and regenerate before saving.'
            )
        )
    if not f["original_item"]:
        holds.append("Identify the delayed purchased item.")
    if not f["alternate_name"]:
        holds.append("Identify the alternate product.")
    for name, label in (
        ("selected_line_ids", "Selected captured line IDs"),
        ("source_quantities_exact", "Exact source quantities and scope"),
        ("alternate_id", "Verified alternate product ID"),
        ("alternate_observed_at", "Alternate observation date/time"),
        ("alternate_quantity", "Reviewed alternate quantity"),
        ("stock_wording", "Exact observed stock wording"),
        ("material_differences", "Brand, material and scope differences (or reviewed none)"),
    ):
        if not f[name]:
            holds.append(label + ": missing.")
    if f["technical_conflict"]:
        holds.append(
            "Technical conflict requires specialist review: "
            + (f["technical_note"] or "record the conflict before proceeding.")
        )
    try:
        observed = datetime.fromisoformat(f["alternate_observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError()
    except ValueError:
        holds.append("Alternate observation needs an ISO date/time with timezone.")
    if (
        f["alternate_quantity"]
        and re.fullmatch(r"[1-9][0-9]{0,3}", f["alternate_quantity"]) is None
    ):
        holds.append("Alternate quantity is unresolved; verify a positive whole quantity.")
    if f["stock_wording"].lower() in {"unknown", "not displayed", "unverified"}:
        holds.append("The recorded stock observation remains unknown.")
    if not (f["delay_verified"] and f["delay_note"]):
        holds.append("Verify the delay and record its source.")
    if not (f["product_url"] and link_verified(f, "product")):
        holds.append(
            (
                'Product link contents need recorded verification, source and '
                'observation time (tool or human evidence).'
            )
        )
    if f["cart_url"] and not link_verified(f, "cart"):
        holds.append(
            (
                'Cart contents need recorded verification, source and observation '
                'time, or remove the cart link.'
            )
        )
    if f["cart_url"] and not cart_matches(f):
        holds.append(
            (
                'Cart contents do not match the reviewed product ID and quantity, or '
                'the cart format is unsupported. The link is withheld.'
            )
        )
    for key, check in f["checks"].items():
        if check["status"] == "unresolved" or not check["note"]:
            holds.append(CHECKS[key] + ": unresolved; record a reviewed result.")
    if not entry["body"]:
        holds.append("Generate or enter the customer body.")
    if entry["body"] != generated_body(f) and not entry["body_reviewed"]:
        holds.append("Review the edited customer body against the evidence.")
    subject = f"ORDER #{context['order_id']} DELAY - ECS TUNING - JUDE LEWIS"
    email_text = entry["body"] + "\n\n" + SIGNATURE + "\n" + CTA_TEXT + "\n" + CTA_URL
    body_html = html.escape(entry["body"])
    for url in sorted(verified_links(f), key=len, reverse=True):
        escaped = html.escape(url, quote=True)
        body_html = body_html.replace(
            escaped, f'<a href="{escaped}" rel="noopener noreferrer">{escaped}</a>'
        )
    email_html = (
        '<div style="white-space:pre-wrap">'
        + body_html
        + "</div><p>"
        + html.escape(SIGNATURE).replace("\n", "<br>")
        + '<br><a href="'
        + html.escape(CTA_URL, quote=True)
        + '">'
        + CTA_TEXT
        + "</a></p>"
    )
    if context.get("hard_conflicts"):
        holds.append(
            "Conflicting capture facts require technical review: "
            + "; ".join(context["hard_conflicts"])
        )
    status = (
        "HELD_TECHNICAL_REVIEW"
        if f["technical_conflict"] or context.get("hard_conflicts")
        else "HELD_CANDIDATE"
        if holds
        else "READY_FOR_HUMAN_REVIEW"
    )
    notices = [
        "Split eligibility is unknown. This draft makes no claim that the order cannot be split.",
        "Human review only. No email is sent and no order is changed.",
        (
            'Link verification can use recorded research-tool or human evidence. '
            'It does not approve customer-specific fitment, quantity or price.'
        ),
        (
            'This app does not contact product or cart pages; existing verified '
            'research does not require another manual link check.'
        ),
    ]
    source_holds = context["source_holds"]
    packet = status.replace("_", " ") + " — INTERNAL REVIEW\n" + "\n".join(holds + notices)
    if source_holds:
        packet += "\nCapture checks: " + "; ".join(source_holds)
    packet += "\n\nCUSTOMER EMAIL\nSubject: " + subject + "\n\n" + email_text
    review_html = (
        '<!doctype html><meta charset="utf-8"><title>Alternate email review</title><h1>'
        + status.replace("_", " ")
        + "</h1><section><h2>Internal review — outside the customer email</h2><ul>"
        + "".join("<li>" + html.escape(note) + "</li>" for note in holds + notices + source_holds)
        + "</ul></section><hr><section><h2>Customer email</h2><p>Subject: "
        + html.escape(subject)
        + "</p>"
        + email_html
        + "</section>"
    )
    return dict(
        status=status,
        send_ready=False,
        recipient_email=None,
        holds=holds,
        notices=notices,
        subject=subject,
        email_text=email_text,
        template_body=generated_body(f),
        cart_status="VERIFIED_CONTENTS"
        if f["cart_url"] in verified_links(f)
        else "UNVERIFIED"
        if f["cart_url"]
        else "NOT_PROVIDED",
        email_html=email_html,
        review_text=packet,
        review_html=review_html,
        entry=entry,
    )


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def parse_request(raw):
    if type(raw) is not bytes or len(raw) > MAX_REQUEST:
        _fail("DRAFT_REQUEST_TOO_LARGE")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda _: _fail()
        )
    except (UnicodeError, ValueError, RecursionError):
        _fail()
    if type(value) is not dict:
        _fail()
    return value


class DraftStore:
    """Separate bounded, atomic, revisioned file under the owned local data directory."""

    def __init__(self, path: Path):
        self.path = path

    def _path(self):
        try:
            path = self.path
            if (
                not path.is_absolute()
                or ".." in path.parts
                or path.name != "doi-alternate-drafts.json"
            ):
                raise ValueError()
            for node in (*reversed(path.parents), path):
                try:
                    info = node.lstat()
                except FileNotFoundError:
                    if node != path:
                        raise ValueError()
                    continue
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError()
                if node == path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError()
            return validate_local_path(path)
        except (OSError, ValueError, RuntimeError):
            _fail("DRAFT_STORAGE_UNAVAILABLE")

    def read(self):
        try:
            path = self._path()
            try:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_STORE + 1)
            except FileNotFoundError:
                return 0, {}
            if len(raw) > MAX_STORE:
                raise ValueError()
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
            if (
                type(value) is not dict
                or set(value) != {"schema", "revision", "records"}
                or value["schema"] != STORE_SCHEMA
                or type(value["revision"]) is not int
                or not 0 <= value["revision"] < 2**53 - 1
                or type(value["records"]) is not dict
                or len(value["records"]) > MAX_DRAFTS
            ):
                raise ValueError()
            for key, record in value["records"].items():
                if (
                    not HASH.fullmatch(key)
                    or type(record) is not dict
                    or set(record) != {"evidence_key", "entry", "updated_at"}
                    or type(record["evidence_key"]) is not str
                    or not HASH.fullmatch(record["evidence_key"])
                    or type(record["updated_at"]) is not str
                    or len(record["updated_at"]) > 40
                ):
                    raise ValueError()
                validate_entry(record["entry"])
            return value["revision"], value["records"]
        except (OSError, ValueError, UnicodeError, RecursionError, TypeError):
            _fail("DRAFT_STORAGE_UNAVAILABLE")

    def set(self, key, record, expected):
        if type(expected) is not int or not 0 <= expected < 2**53 - 1 or not HASH.fullmatch(key):
            _fail()
        revision, records = self.read()
        if revision != expected:
            _fail("DRAFT_REVISION_MISMATCH")
        updated = copy.deepcopy(records)
        if record is None:
            updated.pop(key, None)
        else:
            validate_entry(record["entry"])
            if key in records and all(
                records[key][k] == record[k] for k in ("evidence_key", "entry")
            ):
                return revision
            updated[key] = record
        if updated == records:
            return revision
        raw = encoded(dict(schema=STORE_SCHEMA, revision=revision + 1, records=updated))
        if len(updated) > MAX_DRAFTS or len(raw) > MAX_STORE:
            _fail("DRAFT_STORAGE_FULL")
        temporary = None
        try:
            path = self._path()
            temporary = path.with_name(".doi-draft-" + secrets.token_hex(12) + ".tmp")
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self.read() != (revision, records):
                _fail("DRAFT_REVISION_MISMATCH")
            self._path()
            os.replace(temporary, path)
            temporary = None
            return revision + 1
        except OSError:
            _fail("DRAFT_STORAGE_UNAVAILABLE")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


class AlternateDraftService:
    def __init__(self, session, store=None):
        self.session, self.store = session, store

    def act(self, value):
        base = {"action", "revision", "order_id"}
        action = value.get("action")
        extra = {
            "generate": {"fields"},
            "preview": {"entry"},
            "save": {"entry", "storage_revision", "evidence_key"},
            "delete": {"storage_revision", "evidence_key"},
            "load": set(),
        }
        if (
            type(action) is not str
            or action not in extra
            or set(value) != base | extra[action]
            or type(value["order_id"]) is not str
        ):
            _fail()
        context = self.session.alternate_draft_context(value["order_id"], value["revision"])
        available, revision, records = False, None, {}
        if self.store is not None:
            try:
                revision, records = self.store.read()
                available = True
            except DraftError:
                if action in {"save", "delete"}:
                    raise
        key = hashlib.sha256(("doi-alternate-order/v1:" + value["order_id"]).encode()).hexdigest()
        saved = records.get(key)
        prior_body = None
        changed = saved is not None and saved["evidence_key"] != context["evidence_key"]
        if action == "load":
            entry = (
                copy.deepcopy(saved["entry"])
                if saved
                else dict(fields=empty_fields(), body="", body_reviewed=False)
            )
            if changed:
                prior_body = entry["body"]
                # Product/cart content evidence is product-level; order approvals do not carry.
                entry["fields"]["delay_verified"] = False
                for check in entry["fields"]["checks"].values():
                    check["status"] = "unresolved"
                entry["body_reviewed"] = False
                # Keep edited prose exactly; the changed-evidence hold remains outside the body.
        elif action == "generate":
            fields = validate_fields(value["fields"])
            entry = dict(fields=fields, body=generated_body(fields), body_reviewed=False)
            changed = False
        elif action in {"preview", "save"}:
            entry = validate_entry(value["entry"])
            changed = False
        else:
            entry = dict(fields=empty_fields(), body="", body_reviewed=False)
        if action in {"save", "delete"}:
            if not available:
                _fail("DRAFT_STORAGE_UNAVAILABLE")
            if context["evidence_key"] is None or value["evidence_key"] != context["evidence_key"]:
                _fail("DRAFT_EVIDENCE_MISMATCH")
            record = (
                None
                if action == "delete"
                else dict(
                    evidence_key=context["evidence_key"],
                    entry=entry,
                    updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
            )
            if (
                record is not None
                and saved is not None
                and all(record[k] == saved[k] for k in ("evidence_key", "entry"))
            ):
                # Repeated saves retain the stored update time, bytes and revision.
                record = saved
            revision = self.store.set(key, record, value["storage_revision"])
            saved = record
        result = projection(context, entry, changed=changed)
        return dict(
            schema=SCHEMA,
            revision=value["revision"],
            order_id=value["order_id"],
            context=context,
            evidence_key=context["evidence_key"],
            storage_available=available,
            storage_revision=revision,
            saved=saved is not None,
            updated_at=saved["updated_at"] if saved else None,
            changed_evidence=changed,
            prior_body=prior_body,
            draft=result,
        )
