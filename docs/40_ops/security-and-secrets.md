# Security and Secrets

## Rules

- never commit secrets to git
- use environment variables or secret manager
- redact sensitive fields in logs/events

## Secret Types

- provider API keys
- cookie credentials (if needed for source download)
- storage credentials

## Cookie Handling (High Sensitivity)

- cookie must be injected via file mount or secret manager; do not store/paste raw cookie in Web UI (MVP policy)
- cookie-related fields must be fully redacted in logs/events/errors

## Operational Guardrails

- rotate keys periodically
- least privilege for service accounts
- separate dev/prod credentials
