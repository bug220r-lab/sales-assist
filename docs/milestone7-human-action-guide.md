# Milestone 7 local synthetic human-action guide

The Control Center exposes only actions listed as rendered in the checked-in action-to-service
matrix. Every action is localhost-only, synthetic, explicitly confirmed, request-keyed, and
persisted through an existing application authority. No action modifies source-order facts or
contacts an external system.

## Manager outcome

1. Open a current Sales Credit case that requires manager authority.
2. Review the separate **System classification** and **Manager outcome** sections.
3. Select one closed outcome. `PARTIAL` additionally requires an exact positive amount and currency.
4. Keep the reserved synthetic actor displayed and enter a bounded request key.
5. Select the confirmation describing the exact local synthetic event, then submit.
6. Observe `RECORDED`, `EXACT_REPLAY`, or `REQUEST_CONFLICT` in the live status region.

Reusing the same request key with byte-identical material returns the prior receipt. Reusing it with
changed material returns a conflict and changes nothing. The system classification remains intact.

## DOI overlap scenario selection

1. Open a current DOI overlap case whose aggregate potential is `Unavailable` and whose explanation
   includes the existing unresolved-overlap reason.
2. Review each separate opportunity and its exact line scope.
3. Choose the exact offered scenario option, enter a bounded request key, and explicitly confirm.
4. Submit once. The application records one structured human fact and one selected reevaluation in
   the existing atomic idempotency boundary.
5. Observe the new current projection and immutable timeline. Exact replay returns the original
   receipt; changed material under the key conflicts.

The action does not merge opportunities, guess value, clear unrelated attention, create an
intervention, link a resulting order, or realize value.

## System operations

- **Refresh health** is an ordinary GET.
- **Deep verify database** is an explicitly confirmed local verification operation.
- **Create verified backup** is an explicitly confirmed operation into the existing owned backup
  directory and returns a privacy-safe receipt.
- **View backup receipts** is read-only.

Restore and reset remain separate strongly confirmed CLI workflows. They are never overview
buttons.

## Read-only candidates

An action candidate without an exact service/reducer binding, authority proof, atomicity boundary,
receipt, replay, conflict, projection effect, and executable tests is absent or labeled read-only.
The dashboard does not approximate a missing operation to complete a demo.
