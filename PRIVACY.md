# Privacy

This project is designed to minimize personal data handling.

## What is Collected

- Phone number (for SMS delivery and opt-out handling)
- Scrubbed preference text (user request after PII pattern removal)
- Preference embedding vector (for semantic matching)
- Notification history (which trial IDs were already sent)

## What is Not Intentionally Stored

- Raw inbound SMS body for matching (only scrubbed text is stored)
- Full medical records
- Insurance details

## PII Scrubbing

The service replaces obvious patterns before embedding/storing text:

- Email addresses
- Phone numbers
- SSN-like formats
- Date-of-birth-like formats

This is pattern-based and not a perfect anonymization guarantee.

## User Controls

- `STOP`: unsubscribe and delete stored subscriber data (phone, scrubbed profile, and notification history)
- `HELLO`: start or re-start onboarding
- `HELP`: receive usage and disclosure text

## Data Sharing

- No ad-tech integrations
- No analytics SDKs
- No data resale logic in the codebase

## Recommended Production Controls

- Encrypt database storage and backups
- Restrict DB access by network and role
- Define retention window for inactive subscriber data
- Add formal legal review for local privacy law requirements
