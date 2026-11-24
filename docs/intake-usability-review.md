# Intake usability pass — November 24, 2026

This pass covers the Classic and Guided client demos plus the signed-in staff request form. Existing identity, date-override authorization, native storage and notification boundaries are retained.

## Corrections

- Category text and row padding select/deselect their option. Explicit label associations and focus handling prevent a dropdown from closing before its label activates. Direct checkbox clicks retain native behavior without double toggling.
- Printing and poster quantities have distinct labels. Guided service notes identify the service rather than repeating an ambiguous generic prompt.
- Draft reference files can be cleared locally. Clearing selection does not delete original files, saved references or attachments. Classic lists selected file names; Guided retains its list across Back/Continue.
- Guided validates unsupported/empty/oversized/too-many files before Review. File/reference errors stay on the Timing and references step rather than returning users to Details.
- The staff form uses the shared additional-services controls and optional event date. Its payload uses the same selected-service serializer and ignores hidden retained draft values. The staff-only lead-time override remains separate from the request fields and server verified.
- Service-group validation in the staff form reports an inline error and focuses a usable control rather than treating a checkbox group as a single text input.

## Verification scope

Browser checks covered category text select/deselect, direct keyboard selection through filtered search, Escape, single-select text selection and optional Clear, service-tile text, distinct quantities, Back/Continue retention, unsupported files, valid draft files, file clearing, and end-to-end synthetic form completion. Classic and Guided were checked at a narrow viewport without horizontal overflow. These are browser viewport checks, not real-device certification.

The shared staff service payload is checked by the eight-test staff intake rule group, including native serialization with an authenticated override. Existing thirty JavaScript checks and syntax/brand/secret checks passed. Live deployment evidence and any marked DEV save/readback remain private under ignored artifacts.

The two client comparison demos remain non-active. Microsoft employee rollout and the approved operational ORNL closure calendar remain pending. This update changes browser assets only; no backend restart, source-schema change, invite expansion or notification integration is required. Prior source commit `5eb652e` remains available for rollback.
