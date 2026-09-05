# ADR 0029: Local ECS-inspired presentation tokens

Status: accepted under the user's presentation amendment.

The amendment allows the exact display title and its provenance, while the original
synthetic identity and localhost boundaries stay binding. No local approved logo or exact
brand guide was available. Use the plain-text ECS Sales Assist title with the mandated
synthetic companion on portal, dashboard, and panel. Record chosen colors and pending
exact matching in `docs/m8/THEME_PROVENANCE.md`; do not acquire assets over the network.

Keep one named token definition in `portal/theme.py` and a byte-identical local extension
CSS copy, verified by `tests.test_m8_theme.ThemeTests.test_shared_tokens_and_local_assets`.
All three surfaces use installed system fonts. Existing CSP and extension permissions
remain unchanged; no branding scanner exemption is necessary.

Only presentation, current version/hash contracts, and related packaging documentation
change. App/extension patch versions become 0.1.2; database schema remains 4. The release
builder uses this ordinary successor commit and creates new archives without overwriting
the unbranded evidence. Existing domain tests and HTTP/browser acceptance protect behavior.

Accessible states retain textual labels. Contrast and visible surface labels are covered
by `tests.test_m8_theme.ThemeTests.test_text_and_focus_contrast` and
`tests.test_m8_theme.ThemeTests.test_principal_surfaces_keep_visible_synthetic_labels`.
Native Chrome and screenshot/zoom evidence must keep explicit capability qualifications.
