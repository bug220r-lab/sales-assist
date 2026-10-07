"""Local owner evidence: exact captured-case exclusions and ECS USD provenance."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from synthetic_sales_assist.domain.timestamps import canonicalize_timestamp, parse_timestamp
from .staging import StagedOrder, ascii_four_trim


class OwnerConfirmationError(ValueError):
    code = 'OWNER_CONFIRMATIONS_INVALID'

    def __init__(self):
        super().__init__(self.code)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def record_digest(fields: dict[str, str]) -> str:
    return text_digest(json.dumps(fields, sort_keys=True, ensure_ascii=True, separators=(',', ':')))


@dataclass(frozen=True)
class ConfirmedOtherRep:
    order_id: str
    summary_ordinal: int
    record_sha256: str
    confirmed_at: str
    evidence_reference: str

    def __post_init__(self):
        if (type(self.order_id) is not str or re.fullmatch(r'[1-9][0-9]{0,127}', self.order_id) is None
            or type(self.summary_ordinal) is not int or not 2 <= self.summary_ordinal <= 5001
            or type(self.record_sha256) is not str or re.fullmatch(r'[a-f0-9]{64}', self.record_sha256) is None
            or type(self.evidence_reference) is not str or re.fullmatch(r'(?:Sentinel_[a-f0-9]{32}|SYN-[A-Z0-9_-]{1,64})', self.evidence_reference) is None):
            raise OwnerConfirmationError()
        try:
            if type(self.confirmed_at) is not str or canonicalize_timestamp(self.confirmed_at) != self.confirmed_at:
                raise OwnerConfirmationError()
        except (ValueError, TypeError):
            raise OwnerConfirmationError() from None


@dataclass(frozen=True)
class OwnerConfirmations:
    summary_text_sha256: str = ''
    lines_text_sha256: str = ''
    decisions: tuple[ConfirmedOtherRep, ...] = ()

    def __post_init__(self):
        if type(self.decisions) is not tuple or len(self.decisions) > 10 or any(type(x) is not ConfirmedOtherRep for x in self.decisions):
            raise OwnerConfirmationError()
        if len({x.order_id for x in self.decisions}) != len(self.decisions):
            raise OwnerConfirmationError()
        for value in (self.summary_text_sha256, self.lines_text_sha256):
            if type(value) is not str or (value == '' and self.decisions) or (value != '' and re.fullmatch(r'[a-f0-9]{64}', value) is None):
                raise OwnerConfirmationError()

    def match(self, order: StagedOrder, *, scope: str, summary_hash: str, lines_hash: str, as_of: str):
        # A private decision can only exclude an otherwise trusted unmapped rep.
        if scope != 'REP_UNMAPPED' or len(order.summary_occurrences) != 1 or summary_hash != self.summary_text_sha256 or lines_hash != self.lines_text_sha256:
            return None
        row = order.summary_occurrences[0]
        fields = dict(row.raw_fields)
        for decision in self.decisions:
            if decision.order_id == order.canonical_order_id and decision.summary_ordinal == row.row_number and decision.record_sha256 == record_digest(fields):
                try:
                    captured = parse_timestamp(fields['captured_at_america_new_york'])
                    confirmed = parse_timestamp(decision.confirmed_at)
                    current = parse_timestamp(as_of)
                    key = lambda t: (t.epoch_seconds, t.nanosecond)
                    if not key(captured) <= key(confirmed) <= key(current):
                        return None
                except (KeyError, ValueError, TypeError):
                    return None
                return {'confirmed_at': decision.confirmed_at, 'evidence_reference': decision.evidence_reference}
        return None


EMPTY_CONFIRMATIONS = OwnerConfirmations()


def parse_owner_confirmations(text: str) -> OwnerConfirmations:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OwnerConfirmationError()
            result[key] = value
        return result
    try:
        if type(text) is not str or len(text.encode('utf-8')) > 32768:
            raise OwnerConfirmationError()
        value = json.loads(text, object_pairs_hook=pairs)
        if type(value) is not dict or set(value) != {'schema', 'summary_text_sha256', 'lines_text_sha256', 'decisions'} or value['schema'] != 'doi-owner-confirmations/v1' or type(value['decisions']) is not list:
            raise OwnerConfirmationError()
        decisions = []
        for item in value['decisions']:
            if type(item) is not dict or set(item) != {'order_id', 'summary_ordinal', 'record_sha256', 'confirmed_at', 'evidence_reference'}:
                raise OwnerConfirmationError()
            decisions.append(ConfirmedOtherRep(**item))
        return OwnerConfirmations(value['summary_text_sha256'], value['lines_text_sha256'], tuple(decisions))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise OwnerConfirmationError() from None


def load_owner_confirmations(path: Path | None) -> OwnerConfirmations:
    if path is None:
        return EMPTY_CONFIRMATIONS
    try:
        with path.open('rb') as stream:
            data = stream.read(32769)
        if len(data) > 32768:
            raise OwnerConfirmationError()
        return parse_owner_confirmations(data.decode('utf-8-sig'))
    except (OSError, UnicodeError, ValueError):
        raise OwnerConfirmationError() from None


def currency_projection(code: str, symbol: str) -> list[str | None]:
    # Preserve safe raw tokens; unsafe malformed source strings stay in the CSV.
    def missing(value):
        return ascii_four_trim(value).lower() in {'', 'unknown', 'unknown - not displayed', 'not displayed'}
    safe_code = code if len(code) <= 40 and (missing(code) or re.fullmatch(r'[A-Z]{3}', code) is not None) else None
    safe_symbol = symbol if len(symbol) <= 40 and (missing(symbol) or symbol in {'$', '\u20ac', '\u00a3', '\u00a5'}) else None
    if safe_code is None or safe_symbol is None or (not missing(code) and code != 'USD') or (not missing(symbol) and symbol != '$'):
        source = 'CONFLICT'
    else:
        source = 'OBSERVED_USD' if code == 'USD' else 'OWNER_USD'
    return [safe_code, safe_symbol, source]


def validate_currency(value: object) -> None:
    if type(value) is not list or len(value) != 3 or value[2] not in {'OWNER_USD', 'OBSERVED_USD', 'CONFLICT'}:
        raise ValueError('CURRENCY_PROJECTION_INVALID')
    if any(x is not None and type(x) is not str for x in value[:2]):
        raise ValueError('CURRENCY_PROJECTION_INVALID')
    expected = currency_projection(value[0] if value[0] is not None else 'INVALID', value[1] if value[1] is not None else 'INVALID')
    if expected != value:
        raise ValueError('CURRENCY_PROJECTION_INVALID')
