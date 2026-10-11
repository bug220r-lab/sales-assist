"""Small structured editor embedded in the existing DOI review page."""

from pathlib import Path

from doi_csv_staging.alternate_drafts import CHECKS


def _input(name, label, maximum=300, kind="text"):
    return (
        f'<label class="dashboard-field"><span>{label}</span>'
        f'<input id="alt-{name}" type="{kind}" maxlength="{maximum}"></label>'
    )


ALTERNATE_DRAFT_PANEL = (
    '<section id="alternate-editor" class="dashboard-panel" hidden aria-labelledby="alt-heading">'
    '<h2 id="alt-heading">Alternate email draft</h2>'
    "<p>Draft only. Review the product and order facts; nothing is sent or changed.</p>"
    '<p>Save keeps this draft on this computer across refresh and '
        'restart. It is separate from Reviewed for split. '
    'Do not enter customer names, email addresses, payment information '
        'or other personal details.</p>'
    '<p id="alt-message" role="status" aria-live="polite"></p>'
    '<fieldset id="alt-fields"><legend>Reviewed alternate details</legend>'
    + _input("original_item", "Delayed purchased item", 180)
    + _input("alternate_name", "Alternate product name / identifier", 180)
    + _input("selected_line_ids", "Selected captured line IDs (exact)")
    + _input("source_quantities_exact", "Exact source quantity wording and column / scope")
    + _input("alternate_id", "Verified alternate product ID")
    + _input("alternate_quantity", "Reviewed alternate quantity (positive whole quantity)")
    + _input("alternate_observed_at", "Alternate observation date/time and timezone")
    + _input("stock_wording", "Exact observed stock wording")
    + _input(
        "material_differences",
        "Customer-facing brand, material or scope differences (state reviewed none if none)",
    )
    + '<label><input id="alt-technical_conflict" type="checkbox"> A '
        'technical / fitment conflict remains</label>'
    + _input("technical_note", "Internal technical conflict details")
    + '<label><input id="alt-delay_verified" type="checkbox"> I verified '
        'the delay for this purchased item</label>'
    + _input("delay_note", "Delay check — source and date")
    + _input(
        "product_url", "Exact product URL (HTTPS ECS Tuning or Turner Motorsport)", 1500, "url"
    )
    + '<label><input id="alt-product_verified" type="checkbox"> Exact '
        'product link contents verified in the recorded evidence</label>'
    + '<label class="dashboard-field"><span>Product '
        'verification</span><select id="alt-product_verifier"><option '
        'value="">No recorded verification</option><option '
        'value="research_tool">Supported research tool</option><option '
        'value="human_review">Human review</option></select></label>'
    + _input("product_note", "Verification source/reference (existing tool evidence is sufficient)")
    + _input(
        "product_observed_at", "Product verification observation time (ISO date/time with timezone)"
    )
    + "<details><summary>Optional verified populated cart</summary>"
    + _input(
        "cart_url", "Verified populated-cart URL (optional; paste the actual link)", 1500, "url"
    )
    + '<label><input id="alt-cart_verified" type="checkbox"> Exact cart '
        'contents verified in the recorded evidence</label>'
    + '<label class="dashboard-field"><span>Cart '
        'verification</span><select id="alt-cart_verifier"><option '
        'value="">No recorded verification</option><option '
        'value="research_tool">Supported research tool</option><option '
        'value="human_review">Human review</option></select></label>'
    + _input("cart_note", "Cart verification source/reference and exact contents")
    + _input("cart_observed_at", "Cart verification observation time (ISO date/time with timezone)")
    + "</details><details><summary>Order checks — internal, outside the customer body</summary>"
    + "".join(
        '<label class="dashboard-field"><span>'
        + label
        + '</span><select id="alt-check-'
        + key
        + '">'
        '<option value="unresolved">Unresolved</option><option value="verified">Verified</option>'
        + (
            '<option value="not_applicable">Not applicable — explain</option>'
            if key in {"kit_scope", "allocation", "finish_choice"}
            else ""
        )
        + "</select></label>"
        + _input("note-" + key, label + " — evidence / explanation")
        for key, label in CHECKS.items()
    )
    + '</details></fieldset><div class="dashboard-actions"><button '
        'type="button" id="alt-generate">Generate concise '
        'draft</button></div>'
    '<section aria-labelledby="alt-review-heading"><h3 '
        'id="alt-review-heading">Internal review status</h3>'
    '<p id="alt-status" class="dashboard-state"></p><ul '
        'id="alt-holds"></ul><ul id="alt-notices"></ul>'
    '<details><summary>Capture checks</summary><ul id="alt-source-holds"></ul></details></section>'
    '<section aria-labelledby="alt-customer-heading"><h3 '
        'id="alt-customer-heading">Customer email</h3>'
    '<label class="dashboard-field"><span>Subject</span><input id="alt-subject" readonly></label>'
    '<label class="dashboard-field"><span>Customer body — signature is added below</span>'
    '<textarea id="alt-body" rows="8" maxlength="5000"></textarea></label>'
    '<label><input id="alt-body-reviewed" type="checkbox"> Wording '
        'reviewed (optional; does not send)</label>'
    '<p id="alt-signature">Thanks,<br>Jude Lewis - ECS Tuning / Turner Motorsport<br>Ext. 1234<br>'
    '<a href="https://www.ecstuning.com/?utm_source=jlewis&amp;utm_medium=email&amp;utm_content=link2cart&amp;salesrep=jlewis" '
    'target="_blank" rel="noopener noreferrer">Get The Right Tool For The Job Here!</a></p>'
    '<details id="alt-prior" hidden><summary>Previous saved wording '
        '(different capture; reference only)</summary><pre '
        'id="alt-prior-body"></pre></details>'
    '</section><div class="dashboard-actions">'
    '<button type="button" id="alt-preview">Preview '
        'edits</button><button type="button" id="alt-save">Save draft '
        'locally</button>'
    '<button type="button" id="alt-copy-subject">Copy '
        'subject</button><button type="button" id="alt-copy-email">Copy '
        'draft for review</button>'
    '<button type="button" id="alt-copy-review">Copy review '
        'packet</button><button type="button" id="alt-export">Export review '
        'HTML</button>'
    '<button type="button" id="alt-delete">Delete saved '
        'draft</button><button type="button" id="alt-close">Close '
        'editor</button></div>'
    '<p>Held and ready drafts can be copied for Jude’s review. '
        'Copy/export is never send approval. Review packets include '
    'internal checks outside the customer email. Existing tool-verified '
        'links do not require another manual link check.</p></section>'
    '<script src="/static/doi-alternate-draft.js" defer></script>'
)

ALTERNATE_DRAFT_JS = Path(__file__).with_name("alternate-draft.js").read_text(encoding="utf-8")
