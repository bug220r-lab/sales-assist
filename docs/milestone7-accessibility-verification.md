# Milestone 7 accessibility verification

Automated checks are release gates; zoom, screen-reader announcement quality, and complete keyboard
operation remain explicit manual checks.

## Required page contract

- one visible `h1` and logical heading order;
- skip link targeting the unique `main` landmark;
- labeled primary navigation plus filter/status landmarks where present;
- semantic table caption, `thead`, `tbody`, and scoped column headers;
- persistent visible labels and associated validation messages;
- keyboard-reachable links, controls, confirmation, and submission;
- visible `:focus-visible` outline and no positive `tabindex`;
- no keyboard trap or hover-only/tooltip-only evidence;
- action result and processing state in a polite live region;
- errors name recovery steps without exposing unsafe detail;
- state labels in text, never color alone;
- responsive wrapping for long synthetic identifiers;
- narrow layout at a 320 CSS-pixel viewport and usable browser zoom at 200%;
- `prefers-reduced-motion` disables nonessential transition and animation;
- no flashing or nondeterministic animation;
- every visual metric representation has an adjacent accessible table, explicit unit, currency,
  denominator, and unavailable-versus-zero label.

## Keyboard manager-demo sequence

Starting from the address bar, a user can reach `/system`, `/overview`, both domain queues/details,
the Sales Credit outcome form, DOI overlap form, `/review`, the immutable audit timeline,
`/system/telemetry`, and `/system/backups` using only Tab, Shift+Tab, Space, Enter, arrow keys for
native controls, and browser navigation. Focus returns to the submitted form status and no modal is
required.

## Manual evidence checklist

- [ ] At 200% zoom, no required content or action is lost in horizontal clipping.
- [ ] At 320 CSS pixels, navigation and tables remain usable with intentional table scrolling.
- [ ] Keyboard-only manager sequence completes with visible focus throughout.
- [ ] A screen reader announces page title, headings, table captions, validation, processing, replay,
      conflict, fail-closed, and human-review states.
- [ ] Windows reduced-motion preference removes nonessential motion.
- [ ] High-contrast or grayscale inspection preserves all status distinctions through text.

The complete user-visible checklist remains pending until performed; automated PASS is not a claim
that a person completed these observations.
