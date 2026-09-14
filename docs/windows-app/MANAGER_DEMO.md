# Ten-minute Sales Assist walkthrough

Use the extracted application identified in its external FINAL_STATUS report.

| Time | Action and expected result |
|---|---|
| 0-1 min | Double-click START.cmd. Overview opens in your browser. Open System to inspect actual local health. |
| 1-3 min | Open Campaigns and select SYN-RUN-CAMPAIGN-DEMO. Inspect the audience, exclusions and exact payload preview. Select Launch and Simulate next outreach. The receipt records synthetic acceptance. |
| 3-4 min | Select Simulate customer replies, then open Replies. Inspect attention priority and cart sorting. |
| 4-6 min | Open synthetic-customer-1@example.test. Inspect the conversation evidence, attachment metadata and draft. Edit and save the draft; review the current revision. Reload and confirm the text remains. |
| 6-7 min | Open Writing history. Inspect candidate inclusion/hold reasons, template references and the provisional style version. No model training or remote API is involved. |
| 7-8 min | Return to Overview and inspect the supplied Sales Credit and DOI sample cases. Existing classifications and human decisions remain separate. |
| 8-9 min | Run BACKUP.cmd. Inspect the returned verified manifest: both order and campaign database backups have hashes. |
| 9-10 min | Run STOP.cmd, then START.cmd. Reopen the saved draft and confirm it persists. STATUS.cmd identifies the owned local service. |

All outreach and reply events in this walkthrough are simulated. Unknown send outcomes
remain held; a saved or reviewed local draft is not a remotely created draft or a sent email.
The existing order backup page covers Sales Credit/DOI; use BACKUP.cmd for both databases.
