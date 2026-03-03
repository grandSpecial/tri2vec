# Security

## Current Controls

- API endpoints are protected by bearer token (`API_AUTH_TOKEN`)
- Twilio webhook signature validation is enforced when Twilio is configured
- Runtime secrets are loaded from environment variables
- Internal exceptions are not returned to users
- Trial notifications are deduplicated to reduce repeated sends

## Threat Model (High Level)

- Unauthenticated access to protected endpoints
- Forged webhook requests pretending to be Twilio
- Secret leakage through source control
- Abuse/spam via high-volume inbound requests

## Hardening Checklist

- Rotate all credentials before production launch
- Use a secret manager (not plaintext env files on servers)
- Rate-limit webhook endpoint by sender/IP
- Add structured audit logging for admin endpoints
- Add monitoring/alerts for SMS send failures and error spikes
- Run dependency vulnerability scans in CI

## Reporting

If you discover a security issue, report it privately to the maintainer before public disclosure.
