"""Synthetic proof that HTML attribute decoding cannot repair literal source URLs."""

import copy
import html
import json
from urllib.parse import parse_qsl, urlsplit

import pytest

from doi_draft_transfer import contract
from doi_draft_transfer.helpscout import body_links, body_text
from sales_credit_evidence.approved_draft import ApprovedDraftError, make_approved_bundle
from tests.test_doi_draft_transfer import verified_review
from tests.test_doi_draft_transfer_links import labeled_row


def cart_url(row):
    return json.loads(row["cart_links_json"])[0]["url"]


def literal_entity_row(*, cart, cta):
    row = labeled_row()
    if cart:
        original = cart_url(row)
        literal = original.replace("&", "&amp;")
        row["selected_body_text"] = row["selected_body_text"].replace(original, literal)
        for field, key in (("cart_links_json", "url"), ("alternates_json", "cart_url")):
            values = json.loads(row[field])
            values[0][key] = literal
            row[field] = json.dumps(values)
    if cta:
        row["selected_body_text"] = row["selected_body_text"].replace(
            contract.CTA_URL, contract.CTA_URL.replace("&", "&amp;")
        )
    row["selected_body_sha256"] = contract.text_hash(row["selected_body_text"])
    return row


@pytest.mark.parametrize("entity", ["&amp;", "&#38;", "&#x26;"])
def test_html_attribute_entities_decode_once_to_the_valid_reviewed_url(entity):
    row = labeled_row()
    raw_url = cart_url(row)
    markup = '<a href="' + raw_url.replace("&", entity) + '">SYN cart</a>'
    assert body_links(markup) == [[[raw_url], 0, len("SYN cart")]]
    assert contract.cart_components(body_links(markup)[0][0][0]) == {"99000001": 2}
    before = copy.deepcopy(row)
    review = verified_review()
    assert contract.review_holds(row, review) == []
    bundle = make_approved_bundle(row, review, version=2, source_approval_ref="SYN-ENTITY-001")
    assert bundle["row"] == before
    assert row == before


def test_literal_html_ampersands_change_query_names_and_remain_invalid_carts():
    raw_url = cart_url(labeled_row())
    literal_url = raw_url.replace("&", "&amp;")
    valid_query = dict(parse_qsl(urlsplit(raw_url).query, strict_parsing=True))
    literal_query = dict(parse_qsl(urlsplit(literal_url).query, strict_parsing=True))
    assert valid_query["qty1"] == "2"
    assert "qty1" not in literal_query
    assert literal_query["amp;qty1"] == "2"
    assert "utm_source" not in literal_query
    assert literal_query["amp;utm_source"] == "jlewis"
    with pytest.raises(ValueError):
        contract.cart_components(literal_url)


@pytest.mark.parametrize("entity", ["&amp;", "&#38;", "&#x26;"])
def test_plaintext_entity_bytes_are_preserved_without_a_second_html_decode(entity):
    raw_url = cart_url(labeled_row())
    literal_url = raw_url.replace("&", entity)
    source = f"[SYN cart]({literal_url})"
    rendered = contract.rendered_body(source)
    assert f'href="{html.escape(literal_url, quote=True)}"' in rendered
    assert body_text(rendered) == "SYN cart"
    assert body_links(rendered) == [[[literal_url], 0, len("SYN cart")]]
    assert body_links(rendered)[0][0][0] != raw_url
    assert contract.body_segments(source) == [{"text": "SYN cart", "url": literal_url}]
    with pytest.raises(ValueError):
        contract.cart_components(body_links(rendered)[0][0][0])


@pytest.mark.parametrize(("cart", "cta"), [(True, False), (False, True), (True, True)])
def test_literal_entity_source_cannot_clear_genuine_approved_bundle_holds(cart, cta):
    row = literal_entity_row(cart=cart, cta=cta)
    review = verified_review()
    before_row, before_review = copy.deepcopy(row), copy.deepcopy(review)
    assert contract.validate_row(row) == []
    holds = contract.review_holds(row, review)
    if cart:
        assert "CART_OR_SCOPE_SCHEMA_INVALID" in holds
    if cta:
        assert "SIGNATURE_CTA_REQUIRED" in holds
        assert "UNREVIEWED_BODY_LINK" in holds
    with pytest.raises(ApprovedDraftError, match=r"^APPROVED_REVIEW_HOLDS$"):
        make_approved_bundle(row, review, version=2, source_approval_ref="SYN-ENTITY-002")
    assert row == before_row
    assert review == before_review


def test_replacing_literal_entities_changes_copy_rendering_and_approval_binding():
    correct = labeled_row()
    literal = literal_entity_row(cart=True, cta=True)
    review = verified_review()
    assert correct["selected_body_sha256"] != literal["selected_body_sha256"]
    assert contract.rendered_body(correct["selected_body_text"]) != contract.rendered_body(
        literal["selected_body_text"]
    )
    assert contract.approval_binding(correct, 2, review) != contract.approval_binding(
        literal, 2, review
    )
