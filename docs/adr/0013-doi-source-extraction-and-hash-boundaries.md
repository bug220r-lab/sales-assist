# ADR 0013: DOI source, extraction, provenance, and canonical hashes

- Status: accepted for Milestone 3
- Scope: synthetic in-memory source ingestion and factual extraction

## Decision

Milestone 3 accepts only an in-memory synthetic queue. There is no workbook, file, cloud, browser,
portal, or network adapter. Every raw payload passes the shared prohibited-input and synthetic
identity boundary before normalization or business evaluation.

Source import retains one coherent immutable batch made from a complete bounded row set, exact
schema and mapping versions, structural anchors, finite extent, ordered source references,
before/after revision evidence or a full content fingerprint, and exact privacy-safe counts.
Duplicate target-rep rows merge to one staged order while preserving all permitted source
references. A cross-assignee conflict produces a no-case rejection and zero work/OA effects.

Extraction is factual. Missing or unreadable required data fails extraction; it is never converted
to UNKNOWN. A successful snapshot proves requested/observed order identity, canonical source time,
complete required sections, the complete relevant-line universe, count/manifest parity, line
identity continuity, source coherence, and the shared whole-order completeness proof. DEDUPE
PRESENT requires a constructible timestamp before adapter success.

Every necessary hash-bearing record uses a unique versioned ASCII domain and exactly
`domain || LF || canonical JSON`. Replay authority retains canonical-byte comparison while the
owning graph exists. Hash preimages are independently recomputed in Milestone 3 known-answer tests.
Product-only relationship evidence admits only product namespaces and cannot contain case,
customer, order, contact, VIN, address, name, or arbitrary free text.

## Consequences

No source revision capability is treated as proof of unchanged content. Raw provider-style order
lexemes exist only inside the synthetic source proof and do not become public executable identity.
Milestone 4 may implement a durable adapter, but it must preserve these exact semantic boundaries.
