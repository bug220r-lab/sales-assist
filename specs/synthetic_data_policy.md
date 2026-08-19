
# Synthetic Data Policy

## Reserved identity namespaces

Executable fixtures must use only:

- `SYN-CUSTOMER-*`
- `SYN-ORDER-*`
- `SYN-SKU-*`
- `SYN-INTERACTION-*`
- `SYN-CONVERSATION-*`
- `SYN-SNAPSHOT-*`
- `SYN-EVALUATION-*`
- `SYN-RUN-*`
- `SYN-REP-*`
- `SYN-EVIDENCE-*`

Synthetic email addresses use `example.test`. Synthetic phone values must use an
obviously fictional 555 range.

## Prohibited inputs

Reject before persistence or rule execution:

- identities outside the reserved namespace;
- real-looking customer names, emails, phones, addresses, or VINs;
- ordinary production-looking numeric order IDs unless embedded in a `SYN-ORDER-*` wrapper;
- real product or manufacturer identifiers;
- copied notes, screenshots, HTML dumps, browser storage, credentials, cookies, tokens,
  sessions, or production logs;
- company domains, internal hostnames, cloud-document IDs, and production selectors.

## Network policy

Runtime traffic is limited to loopback:

- `127.0.0.1`
- `localhost`
- `::1`

The Chrome extension host permissions are limited to localhost. A non-loopback runtime
request is a critical safety failure.

## Fixture generation

Synthetic fixtures must be generated from the rule requirements, not by anonymizing real
records. Each fixture must declare:

- scenario ID;
- rule-pack version;
- expected outcome;
- expected reasons;
- expected persistence effects;
- expected human-review state;
- expected safety counters.

## Safety counters

These values must remain zero:

```text
PRODUCTION_SYSTEM_ACCESS_COUNT
PRODUCTION_MUTATION_REQUEST_COUNT
REAL_CUSTOMER_IDENTITY_COUNT
NON_SYNTHETIC_FIXTURE_COUNT
SECRET_MATERIAL_COUNT
```
