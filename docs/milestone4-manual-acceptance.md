# Milestone 4 manual acceptance

Use a new absolute local test directory and run:

```powershell
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test db init
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test doctor
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test db verify --deep
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo list
```

Run every alias once, then replay one with the same request key:

```powershell
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run sales-credit-target-rep --request-key MANUAL-REPLAY-1
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run sales-credit-human-review
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run doi-fulfillment-split
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run doi-full-ds
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run doi-manual-review
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run doi-overlap
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run malformed-input
python -m synthetic_sales_assist.cli --data-dir C:\safe\ssa-m4-test demo run sales-credit-target-rep --request-key MANUAL-REPLAY-1
```

Inspect the returned synthetic order/run identifiers with `order show`, `case history`, and
`run show`; inspect `metrics summary`; create a backup; add another demo; restore the backup with
`--confirm`; and verify that the restored request key still replays exactly. Repeat important
commands with `--json` and confirm that one closed JSON object is emitted.

Acceptance requires zero safety counters, zero runtime network calls, zero extension manifests,
a clean deep database verification, and no runtime database or backup artifact tracked by Git.
