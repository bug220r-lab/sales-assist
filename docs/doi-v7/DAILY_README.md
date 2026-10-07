# DOI v7 daily source

This source adds local DOI CSV review to the reviewed Windows application baseline.
Application version remains 0.2.0. The v7 label identifies the reviewed DOI behavior.
No release, deployment or acceptance of a new distribution is implied.

The DOI page groups eligible, excluded and held records with explicit ownership and
USD provenance. Currency conflicts remain visible for review and excluded from the
default eligible list. Apparent split candidates are observations for human review,
not confirmed fulfillment decisions. Import the summary and component CSV pair
manually. Imported review state stays in memory and expires after 30 minutes;
refresh does not extend expiry. Clear or service shutdown removes the session.

The normal package builders now include the daily policy helper, setup recipe,
required migrations and generic instructions. They generate fresh source identities
and inventories from the requested commit. The private delivery's manifests and
runtime archives are not source inputs. This PR does not build or publish a release.

Read [PRIVATE_CONFIGURATION.md](PRIVATE_CONFIGURATION.md) before any separately
authorized manual launch. START requires an approved external policy. STATUS and
STOP preserve their owned-process checks even if that policy becomes unavailable.
Port 8905 is a candidate with the existing safe loopback fallback behavior.

No CSV, customer data, policy decisions, credentials, receipts or runtime database
belongs in this repository or a distributable archive. The separate Help Scout
closer and its successor are outside this source change.

Manual acceptance on a separately approved disposable installation should confirm:

1. Required configuration rejects missing, invalid, changed or mismatched policy.
2. START opens DOI review and repeated START reopens only its matching owned service.
3. Synthetic CSV ownership scopes, USD provenance and conflicts reconcile correctly.
4. Refresh retains an unexpired session; stale revisions, Clear and expiry behave safely.
5. STATUS/STOP remain available after invalidating policy; STOP affects only its service.

These steps are an acceptance checklist, not a claim they have been completed on
the sanitized package or permission to access private captures.
