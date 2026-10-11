# CSV review and Help Scout draft transfer

Open `/doi-draft-transfer` from the DOI review page in the new build. Existing split
checks and alternate drafts use their original stores. The new workflow does not
load, clear, migrate or replace them. Do not point a test instance at a live data
directory, or restart a working review to try this build without the owner's approval.

1. Download the header template, then choose a UTF-8 CSV and **Preview import**.
   Fix row/field errors. Preview and Cancel never persist imported rows.
2. **Import new rows; keep local conflicts** explicitly commits the preview. Rows
   join by exact order ID. Existing edits and approval history survive; conflicting
   imports are reported and retained locally rather than silently replaced.
3. Review the exact recipient, subject, selected copy, separate cart choices, original
   history, and all unresolved checks. Record recipient verification and its source.
   No customer/contact lookup is performed by the app. Imported claims are not approval.
4. Save review evidence, including separate customer approval and exact cart contents.
   Reconcile any prior Help Scout reference or draft ID. Those imported fields are
   claims only; an existing draft blocks creation of another. Body/recipient edits
   clear affected verification. Every edit invalidates approval.
5. Approve the exact displayed version for **ECS Sales (166170), Jude (897275)**.
   Then, in a separately configured environment, explicitly create the approved draft.
   There is no bulk transfer or customer-send action.
6. Read the per-row result and returned Help Scout link. An unknown write is locked;
   do not delete its journal or retry blindly. A known created ID can be rechecked with
   the read-only verification action. Auth/rate-limit rejection permits explicit retry.

## CSV contract

Schema: `doi-review-csv/v1`. Producer transport is RFC 4180, UTF-8 with BOM, CRLF
records and every cell quoted, preserving embedded newlines and Unicode. The importer
also accepts UTF-8 without a BOM. All 34 headers are required; their order may vary.
The template uses this order:

```text
schema_version,order_id,subject,selected_body_text,selected_body_sha256,preserved_original_body_text,preserved_original_rich_text_runs_json,withheld_selected_body_text,pre_cart_requirement_body_text,copy_version,source_body_sha256,recipient_email,recipient_verified,draft_status,review_approval,send_ready,source_days_json,current_rep,current_rep_eligibility,current_order_status,observed_at_utc,review_holds_json,review_gate_state_json,source_order_lines_json,alternates_json,alternate_relationship,source_alternate_relationship,complete_recipe_json,cart_links_json,cart_validation_status,source_provenance_json,reviewer_notes,existing_help_scout_reference,help_scout_draft_id
```

JSON columns contain arrays/objects or `null` for unknowns. Nullable scalars are
empty. CSV booleans use lowercase `true`/`false`; JSON uses real booleans. Input is
bounded to 32 MiB, 500 unique orders, 1 MiB per JSON cell, 64 KiB per other cell
and 4 MiB per logical row. The CSV parser allows 1 MiB characters; the stricter
UTF-8 byte bounds still apply. This accepts provenance beyond the parser's default
128 KiB limit, including a 262,905-character source cell, without truncation.
Pretty-printed multiline JSON is preserved exactly. The dedicated HTTP route is
bounded to 64 MiB requests and 8 MiB responses; other routes retain their limits.
Duplicate headers, duplicate order IDs, malformed quoting/JSON, duplicate JSON keys,
invalid UTF-8 or mismatched body hashes block the import with logical row/field errors.
Error messages omit field contents. Imported approval/verification flags are retained
as claims only; local review starts unresolved and `send_ready` remains false.

`source_body_sha256` hashes the exact UTF-8 bytes of `preserved_original_body_text`.
`selected_body_sha256` hashes exact `selected_body_text` bytes. Neither calculation
trims, changes line endings, normalizes Unicode nor expands links. A missing original
has a blank source hash. The selected hash always covers the selected string, including
SHA-256 of an empty string. The selected copy is the only approval body; blank stays
blank even when original, withheld or pre-cart history exists. Original rich text is retained
as JSON history, never interpreted as executable markup.

The subject must be `ORDER #[number] DELAY - ECS TUNING - JUDE LEWIS`. Copy retains:

```text
Thanks,
Jude Lewis - ECS Tuning / Turner Motorsport
Ext. 1234
Get The Right Tool For The Job Here!
```

The CTA links to `https://www.ecstuning.com/?utm_source=jlewis&utm_medium=email&utm_content=link2cart&salesrep=jlewis`.
Copy is preserved as text and rendered as escaped HTML with links, including the CTA.
The exact text and rendered payload both participate in approval binding.

## Options, recipes and holds

`alternates_json` is an array of `{option_id,label,cart_url,components,mapping_status,
content_status,validated_at_utc}`. Components contain `{es,sale_quantity}`; optional
SKU fields and additional source evidence remain preserved.
`cart_links_json` is an array of `{option_id,url,components,content_status}`.
Quantities are positive whole sale quantities; captured quantities stay separately
in `source_order_lines_json`. Only explicit ES identifiers are compared; variant
IDs are never inferred. Numeric cart `addN` IDs and contiguous `qtyN` fields must
match the recorded components exactly. Repeated/conflicting parameters are rejected.

- `SINGLE_OPTION`: one option and its matching cart.
- `MUTUALLY_EXCLUSIVE_OPTIONS`: a separate cart for each choice; never combine them.
- `JOINT_COMPLETE_RECIPE`: one cart containing the whole required sale recipe.
  `complete_recipe_json` contains `{kind,options,scope_basis,holds}`, where each option
  has `{option_id,components}`. All recipe options must exactly match the alternates;
  their quantities combine in one cart. Missing scope evidence, missing components,
  or hard recipe holds block transfer. Explicit quantity/allocation unknowns still
  require reviewer evidence and acknowledgment. Recipe kind is metadata; full purchased
  kit scope, including retained parts, must be reviewed against the source lines.
- `NO_SELECTED_ALTERNATE`: retained for review, with creation held.

Cart URLs are pasted, never generated or fetched by this app. They use ECS HTTPS
`/Cart/`, exact numeric `addN`/`qtyN` pairs, and the four CTA tracking parameters above.
`UNVERIFIED_SCHEMA_MAPPED_CART` remains visibly unverified; schema matching is not
browser validation. The reviewer must record exact content evidence and an observed
timestamp for each cart. Product-only rows, missing required carts, incomplete recipes,
blocked ownership, blank/held copy, shipped/canceled/DS Pending Cancel orders and
unresolved identity remain held. `customer-web`, `jlewis`, and `jlewis_web` are eligible
rep values. Other fitment/stock/quantity/allocation findings require explicit evidence
or acknowledgment; no check is inferred from imported flags.

## API semantics verified against official documentation

Reviewed 2026-10-11:

- [Create Conversation](https://developer.helpscout.com/mailbox-api/endpoints/conversations/create/)
  documents a draft conversation using a `reply` thread with `draft: true`. The new
  conversation uses mailbox 166170, user/assignee 897275, `type: email`, required
  `status: active`, and `autoReply: false`. No customer thread is created.
- [Create Reply](https://developer.helpscout.com/mailbox-api/endpoints/conversations/threads/reply/)
  distinguishes a draft from a published reply. This adapter never invokes the
  existing-conversation reply endpoint, which can otherwise reopen conversations.
- [Get Conversation](https://developer.helpscout.com/mailbox-api/endpoints/conversations/get/)
  and [List Threads](https://developer.helpscout.com/mailbox-api/endpoints/conversations/threads/list/)
  document draft state and thread content used for readback.
- [Rate limits](https://developer.helpscout.com/mailbox-api/overview/rate-limiting/)
  specifies 429 and `X-RateLimit-Retry-After`; the UI requires an explicit retry after
  that delay. [Authentication](https://developer.helpscout.com/mailbox-api/overview/authentication/)
  documents server-side bearer tokens and 401 expiry. This change creates no grant.

Creating a conversation with an email may also create that customer record when it
does not exist. Therefore draft creation itself is an external write and requires
the explicit reviewed action. No real create was used for development verification.

## Secure setup and operation

API transfer is off by default. An operator may enable `SSA_HELPSCOUT_DRAFT_TRANSFER=1`
and supply `SSA_HELPSCOUT_ACCESS_TOKEN` through an already-approved server-side secret
manager/injector. These are process environment inputs only; the app neither persists
them nor accepts them from CSV or browser requests. Do not put a token in a command
argument, source file, CSV, log, Git, or frontend. Any new persistent credential/grant
requires action-time approval and separate secure setup. No credentials are shipped.

The **Check configured API access** control makes only GET requests for the fixed
mailbox and user, without customer discovery. It is optional setup verification,
not a grant or draft creation. The only outbound write is the closed draft creation
operation. The browser remains localhost-only; OAuth exchanges, sends, publishes,
cleanup status changes, proxy URLs and automatic retries are absent.

Private storage: `data/doi-draft-transfer.sqlite3` under the chosen owned data root.
Preserve it with its SQLite journal during operation; do not copy an open database
as a backup. It contains recipient/copy history and must never enter Git or a package.
Use the same store for duplicate protection across restarts. Uncertain operations
require human reconciliation; no automatic reset or forced-retry path is provided.

For isolated checks, run the existing package lifecycle against a **new** absolute
data directory and a free localhost port. Leave transfer disabled. Do not change the
active installation, live cleanup script, its journal/locks, or private configurations.
The source tests and frontend harness use obvious synthetic fixtures and mocked API
responses. They do not establish production credentials or real API acceptance.

```powershell
python -B tools/run_tests.py tests.test_doi_draft_transfer tests.test_doi_draft_transfer_http
python -B tools/run_draft_transfer_frontend.py --node node --output-dir C:\Temp\ssa-draft-qa
python -B tools/run_tests.py
```
