# Windows application scope

This is a launchable local application for the current synthetic workflows. It has no
production credentials, external messaging transport, customer-data ingestion or live
Help Scout connection. The three independent Help Scout scripts and their data are outside
this application's lifecycle.

The private runtime is CPython 3.12.14 for Windows x64, from the pinned
astral-sh/python-build-standalone 20260901 distribution, with tzdata 2026.3 from PyPI.
The runtime and its license notices travel with the extracted package. Runtime inventory
checks precede interpreter execution; missing or changed files cause a closed startup
failure, with no fallback to another Python installation. The package is unsigned;
checksums establish correspondence to the recorded release, not a trusted publisher signature.

The application runs on localhost in a browser. There is no native desktop-shell rewrite,
installer, automatic updater or Chrome Web Store deployment. The optional extension retains
its existing version and localhost permissions. Windows on ARM and other operating systems
have not been qualified for this package.

Human acceptance and testing on a separate clean Windows PC/VM must be recorded separately.
An isolated same-PC test with Python/Codex environment settings removed is useful evidence
of runtime independence, but is not a clean-machine test. Read the release's FINAL_STATUS.

Backups contain separate verified SQLite snapshots and a manifest. The existing order
backup/restore UI still operates on the core database only. Workspace restore requires a
separately verified, stopped-service maintenance procedure; no one-click restore is supplied.
RESET.cmd preserves campaign history and drafts while resetting the order demo. Removal
retains the executing private runtime and unknown/modified files for manual cleanup after exit.

Campaign outreach and reply simulation remain local. Writing-style preparation is provisional;
there is no AI API connection or model training. Previously documented absent DOI GUI actions
remain absent. No package validation establishes production business acceptance.
