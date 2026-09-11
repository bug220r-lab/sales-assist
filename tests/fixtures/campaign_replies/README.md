# Campaign and reply reference fixtures

These three files preserve exact bytes from the user-supplied handoff so a clean
checkout can run the Campaigns/Replies regression tests without the private local
`SalesAssist_Handoff/` directory. The original handoff files remain unchanged and
are not Git dependencies.

| Tracked copy | Original source | SHA-256 |
| --- | --- | --- |
| `companion-reference/replies-core.js` | `SalesAssist_Handoff/companion-reference/replies-core.js` | `0c2107f51084c547721d168eac0055a61e53b34e3eacbefd8d239ab8b32cd577` |
| `companion-reference/drafts-core.js` | `SalesAssist_Handoff/companion-reference/drafts-core.js` | `15fa6e90a0475f95d85c46cfd9c3b50896096af2a0c8f91029eb4ae2c9cda4e1` |
| `scenarios.json` | `SalesAssist_Handoff/fixtures/campaign/scenarios.json` | `ea7e1e0dce745f46d089d1141c11017add4cce053c310dd78e0b75afa59d411c` |

The JavaScript modules are test-only references for the Python lifecycle and
source-evidence port. `test_campaign_replies.py` passes generated reserved SYN
identities and example.test contacts to Node; the parity check performs no remote
operations. The JSON enumerates twelve synthetic send-state scenarios; its
contents describe expected behavior, not executed test results.

The repository scanner admits these two JS references only at these exact fixture
paths with the recorded SHA-256 bytes and a bounded size. Modified or relocated
copies retain normal rejection, and the separate credential scan still applies.

The original 91 companion checks remain optional checks of the local handoff and
historical evidence in `MORNING_HANDOFF.md`. Their complete dependency closure
includes legacy identity fixtures, PowerShell network-capable worker modules and
the standalone companion UI. Those files are deliberately not copied into this
synthetic application or required for its clean-checkout regression suite. Run
original companion checks only with their documented mocks and isolated temporary
copies: `drafts.test.js` writes a sibling `writer-fixture.json`.

Copying these references does not authorize a live worker, customer message,
remote draft, production snapshot import or change to the handoff's scripts.
