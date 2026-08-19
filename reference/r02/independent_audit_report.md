
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI R02 Ingestion, Runs and Replay v1.1 — Independent Audit Report

Audit date: 2026-08-11  
Audit type: independent, read-only authority review  
Target: `doi-authority-remediation-r02-ingestion-run/v1.1`  
Target Drive folder: `1qMlOYSfB0i6iVasS_IcZlaopGtTob-eo`  
Verdict: **FAIL / NOT_READY**

## Executive decision

R02 v1.1 is byte-complete, internally well-formed, private, and mechanically reproducible, and its explicit accepted no-retry finalization design passes. It is not ready for R01/R02 integration because the newly added pre-read systemic-failure route for recheck runs has three independent blocking defects:

1. its work subject is simultaneously required to belong to an exhaustive four-class terminal partition and required to contribute to none of those classes;
2. its run terminalization is not serialized with extraction-occurrence reservation, so both forbidden outcomes can commit under a crossed race; and
3. it persists `RC-084` at `DOIRun` even though the closed reason authority owns `RC-084` at `DOIEvaluation`, without an R02 ownership overlay or affected-artifact delta.

These defects leave B015, B017, and B018 unclosed. They are not repaired in this audit package.

## Scope and controls

The audit read only the target R02 v1.1 package, its R02 predecessor, the v0.1.5.6 baseline package including its immutable corpus, the forward-audit package/blocker register, and an informational R01 normalization candidate for overlap comparison. No source authority, predecessor, baseline, repository, cache, corpus, or workbook was modified. The manager workbook was not accessed. No live Synthetic Order Portal capability was accessed or exercised. The only writes were creation of this private audit-output package.

## Package integrity result

- Target inventory: 27 files, no missing, extra, duplicate, unsafe, or ambiguous path.
- Authority manifest: 25 payload entries. It intentionally excludes itself and `SHA256SUMS.txt`.
- `SHA256SUMS.txt`: 26 entries. It includes the authority manifest and excludes itself.
- Raw Drive readback: 27/27 target files matched exact expected byte length and SHA-256 at audit end.
- Target manifest SHA-256: `1a6e62bb7125cf9fc83e3789f2669f60bb3d32766beb8cb24c89a00bb3407228`.
- Target checksum-file SHA-256: `bcc5189aedd8b1906a44e1638f3198233799914e4be7a4edcca8fa3940746996`.
- Target/predecessor delta: 20 changed, 3 byte-identical, 4 new, 0 removed.
- Target, predecessor, baseline, forward-audit, and nested-corpus listings were identical at audit start and end by file ID, title, size, modified time, and object kind.
- Target folder and all 27 target files exposed only one owner permission at inspection time.
- All JSON parsed under duplicate-key rejection; all raw files were UTF-8, LF-only, terminal-LF, with no BOM, NUL, or CR.

The authoring summary’s `25/26` describes two denominators, not a partial result: 25 manifested payloads and 26 checksum-bound files. `27/27` describes raw readback of every physical object, including `SHA256SUMS.txt`.

## Independent recomputation

The following exact results reproduced:

- 34 canonical records: 11 R02-only hash vectors, 2 fixed enum vectors, 11 deferred event templates, and 10 replay/readback vectors.
- 24 accepted selector cases.
- 95 executable top-level negative cases: 31 run, 36 attempt, and 28 finalization.
- 25 subordinate terminal-event negative selectors and 11 static/replay assertions.
- 77 successor-added accepted/negative cases: 24 + 28 + 25.
- 312 baseline synthetic IDs across 29 families, excluding the two harness identity examples.
- 115 reason codes (`RC-001` through `RC-115`) and 115 raw ownership rows.
- 115 transition IDs (`TR-001` through `TR-114`, plus `TR-045A`).
- 2 run-event literals and 4 source-attempt-event literals.
- 21-member run projections and 36-member source-attempt projections.
- 42 deferred scalar markers: one policy marker and 41 digest/result fields.
- 14/14 shared-artifact delta hashes and 14/14 overlap records.
- TARGET_REP descriptor: 338 bytes; SHA-256 `657f304462a6ca8674322562bc378eee8392abdb59061a4b7f5659932dffd8af`.
- Empty personal-batch source fingerprint: 1,410 canonical bytes; SHA-256 `e3ef4f0b70834ae96063e132ccdc2d62edfdedd82d6949f84c14d149d53bda6d`.
- Failed-finalization key KAT: 161 canonical bytes; SHA-256 `493d55b5a3e6ebc3270f5e4d143cf81a6fe2b4ec5c87903d4f4f7fa510623c46`.

## Blocking discrepancies

### D-R02-001 — terminal-class/count contradiction

`R02_SOURCE_COUNT_EQUATIONS.md` defines `Q(run)` to include every subject in `W(run)` and requires every `q` in `Q(run)` to reduce to exactly one of four `RunOrderTerminalClass` values. The same contract then defines a legal systemic pre-read failure with `work_item_count=1`, every disposition count zero, and the work subject contributing no terminal class. `R02_RUN_TYPE_STATE_MACHINES.md` and `R02_RUN_EVENT_SCHEMAS.json` publish that branch for both recheck RunTypes. The subject is therefore both inside the exhaustive set and unclassified. No implementation can satisfy both rules.

### D-R02-002 — crossed terminalization/reservation race

The extraction contract reserves under an occurrence/work-item lock, reads `run remains IN_PROGRESS`, then commits a STARTED occurrence. The systemic-failure terminalizer checks that no occurrence exists and terminalizes the run, but the package does not require a shared run-control lock, predicate lock, or compare-and-set spanning the check and commit on both sides. Two transactions can each pass its guard and commit a terminal FAILED run plus a STARTED extraction occurrence, violating the package’s own no-orphan invariant. The published vector covers only sequential ordering, not the crossed race.

### D-R02-003 — stale/incompatible `RC-084` ownership

The closed registry and ownership matrix own `RC-084 RULE_VERSION_UNAVAILABLE` at `DOIEvaluation`, with transitions `TR-027,TR-037` and `SYN-EVAL-PROV-001[UNAVAILABLE_RULE_VERSION]`. R02 newly persists it as the sole reason on a run-level FAILED route that explicitly creates no evaluation. The R02 delta map says to preserve reason ownership and omits `DOI_REASON_OWNERSHIP_MATRIX_v0.1.5.3.md`; no machine-checkable R02 owner/governing reference covers the new route.

## Passing substantive areas

Manager-source DTO closure, TARGET_REP normalization, source fingerprinting, invocation and source-attempt identities, ordinary extraction replay/cardinality, explicit failed-source finalization, retry-versus-finalization commit ordering, the 13-effect finalization transaction, retention overlays, event member schemas, event enums, projection reducers, N002 one-order/run-key behavior, resume controls, and conditional R01 integration handling all passed their assigned checks except where directly affected by D-R02-001 through D-R02-003.

## Smallest remediation

1. Redefine the terminal-class subject set to exclude systemic-failure-only work, or add an explicit non-order-disposition partition and update every equation, event vector, and machine oracle consistently.
2. Serialize the RC-084 terminal gate and extraction reservation through one shared run-control boundary or equivalent serializable predicate/CAS, and add both crossed commit-order vectors.
3. Publish a machine-checkable ownership overlay for the run-level RC-084 use, including exact owner, route/transition semantics, deterministic oracle, and governing references; include the affected reason-ownership artifact in the overlap/delta reconciliation while preserving the 115-code inventory.

No code implementation or full DOI freeze is authorized or declared.

`INDEPENDENT_DOI_R02_INGESTION_RUN_AUDIT = FAIL`  
`DOI_R02_INGESTION_RUN_MODULE = NOT_READY`
