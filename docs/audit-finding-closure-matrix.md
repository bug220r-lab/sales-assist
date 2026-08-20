# Audit-finding closure matrix

- Matrix version: `milestone1/v1`
- Scope: Milestone 0 safety foundation plus Milestone 1 Shared Domain Engine
- Status vocabulary: `CLOSED_M1`, `CLOSED_M1_REOPEN_ON_EXTENSION`,
  `PARTIAL_M1_OPEN_M3`, and `DEFERRED_NOT_IN_M1`

`DEFERRED_NOT_IN_M1` is not a waiver. It records the exact future implementation dependency and
keeps the finding release-blocking for that milestone. `CLOSED_M1_REOPEN_ON_EXTENSION` means the
implemented M1 domain inventory is closed, but the finding must be re-audited whenever a new
hash domain or owning record is added.

| Finding | Status | Artifact/version | ADR | Accepted tests | Negative tests | Dependency | Re-audit scope |
|---|---|---|---|---|---|---|---|
| R01-01 | CLOSED_M1 | This matrix, `milestone1/v1` | ADR 0005 | `test_audit_finding_closure_matrix_is_complete` | Missing/duplicate/blank row assertions in the same test | None | Re-audit every milestone and every finding-status change |
| R01-02 | CLOSED_M1_REOPEN_ON_EXTENSION | `docs/milestone1-hash-preimages.md`; 18 M1 bindings | ADR 0004, ADR 0005 | `test_every_envelope_has_a_pinned_hash_preimage_oracle` | Exact fixture-name/domain/digest/preimage/document drift assertions in the same test | New hash-bearing record | Add a KAT row before accepting any new or changed domain |
| R01-03 | CLOSED_M1 | `CanonicalTimestamp`; `WholeOrderCompletenessProof` v1 | ADR 0005 | `test_source_time_coherence_uses_canonical_instant`; `test_completeness_proof_closes_identity_time_counts_manifest_and_state` | Mismatched section/proof/order timestamp vectors in the same tests | None | Re-audit adapter timestamp ownership in M3 |
| R01-04 | CLOSED_M1_REOPEN_ON_EXTENSION | `doi-timestamp/r01-v1`; fixed grammar and digest | ADR 0004 | `test_fixed_known_answer_oracle_reproduces_published_digest`; timestamp boundary tests | Invalid date, offset, fraction, Unicode, storage-alias vectors | New timestamp version | Re-audit any grammar, precision, or hash-domain change |
| R01-05 | CLOSED_M1_REOPEN_ON_EXTENSION | `Quantity.from_source_text`; exact integer lexeme grammar | ADR 0005 | `test_exact_decimal_source_text_normalizes_only_zero_fraction` | Sign, exponent, fractional, alias, and range vectors in `test_domain_numeric` | Owning business-field adapters | Re-audit each adapter's exact-decimal-source flag in M2/M3 |
| R01-06 | DEFERRED_NOT_IN_M1 | No source-import-attempt record exists | None yet | None in M1; absence enforced by milestone boundary | No attempt ID may be accepted or persisted in M1 | M3 DOI ingestion and retention | Owning attempt resolution, bounded ID, retention, replay, purge |
| R01-07 | PARTIAL_M1_OPEN_M3 | Typed synthetic `SourceRef` descriptor and whole-order source resolution | ADR 0005 | Source/order coherence and reverse-parity assertions in `test_completeness_proof_closes_identity_time_counts_manifest_and_state` | Wrong namespace, kind, object type, cross-order, interaction, unused, and arbitrary-content vectors | M3 DOI product-only reusable evidence | Product-only relationship schemas and all prohibited source-object classes |
| R01-08 | PARTIAL_M1_OPEN_M3 | M0 prohibited-input firewall/scanner; closed M1 values | ADR 0002, ADR 0005 | M0 firewall/scanner tests; M1 privacy and non-retention tests | Otherwise-valid identity/contact/credential/source-text canaries in foundation and domain tests | M2/M3 owning adapters and payload schemas | Re-run precedence canaries for every new input class |
| R01-09 | DEFERRED_NOT_IN_M1 | No DEDUPE adapter or business state exists | None yet | None in M1 | Boundary test forbids DOI behavior modules | M3 DOI DEDUPE adapter | Timestamp failure precedence before PRESENT acceptance |
| R01-10 | DEFERRED_NOT_IN_M1 | Order-number normalizer only; no raw-source preservation record | ADR 0004 will govern hash shape | Normalization tests cover canonical value only | No preservation or persistence path exists in M1 | M3 DOI source adapter | Raw-source binding, redaction, retention, canonical hash |
| R01-11 | CLOSED_M1 | Timestamp KAT `ba8fc05dbdbba6fec52a3ed7b0a93a0d8dbb8512e9fe95c56d6d4bd4708d2112` | ADR 0004 | `test_fixed_known_answer_oracle_reproduces_published_digest` | Preimage separator/domain/value mutation assertions | None | Re-audit if timestamp domain or grammar changes |
| R01-12 | CLOSED_M1_REOPEN_ON_EXTENSION | All current shared v1 domains | ADR 0004, ADR 0005, ADR 0006, ADR 0007 | Per-domain canonical, record, numeric, timestamp, observation, and idempotency suites | Version/null/conflict/boundary/missing/extra/noncanonical vectors across those suites | Every future business domain | Reopen for every new record/domain in M2-M4 |
| R01-13 | DEFERRED_NOT_IN_M1 | Public ownership view intentionally excludes planning selectors | ADR 0005 | Registry inventory/parity tests | Public-view tests prove selector/status fields are absent | M3 DOI executable rule/oracle suite | Reconcile every raw selector to collected executable tests |
| R01-14 | DEFERRED_NOT_IN_M1 | Generic evidence reference only; no DOI finding schema | None yet | None in M1 | Boundary test forbids DOI finding implementation | M3 DOI finding/provenance records | Identity, marker, equality, provenance, replay, purge |
| R01-15 | DEFERRED_NOT_IN_M1 | No DOI finding/presence/descriptor hash domains | ADR 0004 will govern | Direct finding-presence v2 scalar tests cover only the shared primitive | Wrapper/alias/wrong-version shared-presence negatives | M3 DOI finding record domains | Exact domains, separators, member closure, KATs |
| R01-16 | DEFERRED_NOT_IN_M1 | No WWC adapter or business partition | None yet | None in M1 | Boundary test forbids DOI behavior modules | M3 DOI WWC rule pack | Exhaustive PRESENT KNOWN/UNKNOWN legal and illegal partitions |
| R02-01 | DEFERRED_NOT_IN_M1 | No DOI work-item/disposition model | None yet | Registry metadata only | Boundary test forbids DOI behavior/persistence | M3 DOI runs plus M4 persistence | Work-item/disposition conservation equations and systemic failure |
| R02-02 | DEFERRED_NOT_IN_M1 | No extraction reservation or terminalization behavior | Concurrency/persistence ADR required later | Registry metadata only | Boundary test forbids business transitions and tables | M3 DOI behavior plus M4 atomic persistence | Race/failure injection and mutually forbidden outcomes |
| R02-03 | DEFERRED_NOT_IN_M1 | RC-084 metadata resolves TR-004, TR-027, TR-037 | ADR 0005 | `test_rc084_has_one_identity_and_all_three_closed_owners`; `test_tr004_contains_exact_two_closed_reconciled_branches` | Recursive schema and protected-parent-run negatives | M3 executable emission sites | Collect both evaluation and pre-extraction oracles before reason emission |

The M1 commit closes no DOI or Sales Credit business outcome. Deferred rows remain binding and
must move to an executable closed state in the milestone named in their dependency column.
