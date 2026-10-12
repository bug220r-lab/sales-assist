# ADR 0044: Isolated read-only Help Scout credit evidence

Status: accepted for source implementation; live activation remains disabled.

The later [ADR 0045](0045-cached-read-only-evidence-pilot.md) adds a separately gated,
read-only cached snapshot runner. The core reader's supplied-credential boundary and
the prohibition on token issuance/renewal remain unchanged.

## Context

The user approved development of a read-only Help Scout search/history reader on
2026-10-12 for a small Sales Credit evidence pilot. The existing draft-transfer adapter
does not provide scoped customer discovery and complete paginated history. Its
authentication lifecycle and mutation surface must remain unchanged. The installed daily
DOI app, saved reviews, running cleanup, and original draft-transfer checkout are outside
this implementation's scope.

This explicit request is a bounded exception to the repository's synthetic-only adapter
and localhost-networking boundary. It does not weaken the synthetic data firewall or
authorize company data in the rule engine, tests, fixtures, logs, or Git. It does not
activate credentials or authorize a live test during development.

## Decision

Create a separate evidence-reader package and controlled entry point rather than extending
the draft-transfer adapter or rebuilding the UI. Fix mailbox scope to `166170` and target
author scope to user `897275`. Allow only narrowly scoped GET requests against the exact
Help Scout API origin. Keep customer lookup, conversation discovery, and thread traversal
separate so each stage exposes complete, partial, failed, or ambiguous evidence coverage.

Match exact normalized emails locally after the API's contains search. Retain multiple
matching customer identities without choosing one. Verify mailbox and customer scope on
returned conversations before requesting history. Use separate thread pages, native IDs,
and validated native conversation links. Reject pagination scope changes and HTTP redirects;
apply finite traversal, response, retry, and wait budgets. Preserve completed evidence when
a later request fails, without converting partial coverage into a negative finding.

Return factual thread type/state/source, creator identity, timestamp precision, and
customer associations. Conversation ownership is not authorship. Published outbound
records are candidates rather than proof of personal sending or delivery; imported and
automated records can resemble human contact. Exclude drafts, notes, scheduled or failed
sends and known automation from sent-email candidates, and expose unknown provenance.
Reply associations never independently establish causal replies, two-way pre-order
qualification, relevance, or credit approval.

Live networking defaults off and requires both explicit `enable_live=True` and a
caller-supplied nonrenewing `SuppliedCredential(token, expires_at)`. Do not import an
authentication provider, read environment credentials, decrypt caches, issue/refresh tokens,
or inspect/coordinate the cleanup process. Stop on expired credentials or 401/403. The
external credential owner remains responsible for any future authorized session.

No raw body persistence or logging is added. Diagnostic projection keeps safe status/error
categories and bounded support references, excluding input values and response payloads.
All tests and offline examples use reserved synthetic identities and fake HTTP.

Register the reviewed public API/documentation links and synthetic rejection fixtures in
the repository's existing exact path/category/SHA256 literal inventory. A changed value
or different file path still fails the content gate. Do not add hostname-wide or directory
exemptions, credential-scanner exclusions, or runtime network permissions to the synthetic
engine. This static inventory records the bounded exception; it cannot enable live access.

## Consequences and verification

This design leaves Sales Credit rules, the 14-day operational horizon, DOI behavior,
draft-transfer writes, installed applications, and credential storage unchanged. It does
not integrate with the rules engine, assign credit, send messages, or update sheets/orders.
Phone-only contacts require a source-proven email before the reader can search.

Complete coverage means complete successful traversal of currently accessible scoped API
results. Deleted/inaccessible history, delivery verification, universal automation detection,
and commercial relevance remain outside the available contract. A later live pilot needs
an independent access decision and externally supplied valid credential.

Acceptance uses focused fake-HTTP identity, pagination, chronology, error, authentication,
privacy, and read-only tests plus applicable existing regression checks. No live readiness
is implied. The detailed contract and official API references are in
[Help Scout evidence reader](../helpscout-credit-evidence.md).
