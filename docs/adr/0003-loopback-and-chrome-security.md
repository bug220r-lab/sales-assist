# ADR 0003: Loopback runtime and future Chrome permission security

- Status: accepted for Milestone 0
- Scope: runtime networking and extension permission validation

## Decision

Runtime destinations are accepted only when the parsed host is exactly `127.0.0.1`, `localhost`,
or `::1`. The guard does not resolve DNS and rejects aliases, wildcard hosts, user information,
encoded or numeric host tricks, and non-loopback destinations.

No Chrome extension is created in Milestone 0. A validator is established for a future extension.
Its only permitted host patterns are `http://127.0.0.1/*` and `http://localhost/*`, checked across
all manifest surfaces capable of granting host reach. Privileged write, generic automation, and
external-action capabilities fail closed.

## Consequences

The runtime cannot reach a production or Internet destination through the supported boundary.
Chrome does not receive IPv6 or HTTPS host permissions even though the Python runtime policy can
recognize the exact IPv6 loopback literal. Any future extension capability change requires an ADR
update and executable negative tests.
