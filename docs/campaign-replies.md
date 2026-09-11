# Campaign Replies in Sales Assist

Open **Campaign Replies** in the Control Center navigation at
`http://127.0.0.1:8765/campaign-replies`.

This page displays the separately running local draft-review dashboard. Use its
search and filters, select a draft, inspect its context and verification times,
then open the source conversation for editing or sending. The separate-window
link is always available while the companion is enabled.

## Enable on a workstation with the companion installed

1. Start the companion dashboard on `http://127.0.0.1:8770` using that
   dashboard's existing launcher or Windows sign-in task.
2. Before starting Sales Assist, set the process environment variable:

   ```powershell
   $env:SSA_CAMPAIGN_REPLIES = '1'
   .\scripts\start.ps1 -NoBrowser
   ```

   Use the normal configured Python runtime and data directory. If Sales Assist
   is already running, stop it through its normal launcher and restart it with
   the opt-in. The setting belongs to the launched process, not the database.
3. Open the Campaign Replies page. The portal must use exactly
   `http://127.0.0.1:8765`; alternate hosts and ports leave this view disconnected.

For an automatic launcher, set the same environment variable in the process
that starts Sales Assist. Do not store credentials in the launcher.
Unset the variable or use any value other than `1` to disable the companion on
the next start. The synthetic modules work independently of this opt-in.

## Companion requirements

The companion serves `/?embedded=1` and permits only
`http://127.0.0.1:8765` in its Content-Security-Policy `frame-ancestors` directive.
It must keep its own same-origin data checks and read-only controls. No CORS
configuration is needed. If the frame is blank or the service is stopped, start
the companion, use **Open dashboard separately** to verify it, and reload.

Sales Assist does not import customer records, access companion credentials,
query its data API, or start another polling or publishing process. Review
timestamps, saved receipts and warnings come from the companion itself.
The synthetic demo release does not bundle the companion or customer data.
See [ADR 0031](adr/0031-local-campaign-review-companion.md) for the scope and
browser isolation contract.
