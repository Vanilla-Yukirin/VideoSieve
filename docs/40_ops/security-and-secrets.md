# Security and Secrets

## Rules

- never commit secrets to git
- use environment variables or secret manager
- redact sensitive fields in logs/events

Status markers:
- `implemented`: active in current runtime.
- `planned`: target behavior not yet exposed.

## Secret Types

- provider API keys
- cookie credentials (if needed for source download)
- storage credentials

## Cookie Handling (High Sensitivity)

- `implemented` cookie vault stores encrypted cookie text server-side; plaintext is not returned by API responses
- `implemented` cookie validation requires a concrete video-page URL and rejects site homepage/root URLs
- cookie-related fields must be fully redacted in logs/events/errors
- `implemented` prefer `cookie_id` in API job payloads; resolve cookie material server-side
- `implemented` keep `cookie_file_path` only as migration fallback in controlled local/dev deployments

## API Startup Preconditions

- `implemented` `APP_SECRET_KEY` is mandatory for API startup (fail-fast).
- `implemented` missing or blank `APP_SECRET_KEY` prevents service startup instead of deferring failure to runtime handlers.

## Minimum Deployment Env (API)

- `APP_SECRET_KEY`
- `ENABLE_GUEST_MODE`
- `GUEST_ALLOW_COOKIE_INPUT`
- `GUEST_COOKIE_KEY`
- `GUEST_JOB_COOLDOWN_SECONDS`

Constraint:
- `implemented` if `guest_allow_cookie_input=true` in persisted settings while `GUEST_COOKIE_KEY` is empty, runtime must reject configuration.

## Frontend Public Env Boundary

- `NEXT_PUBLIC_*` variables are public and shipped to browser clients.
- Do not place secrets in `NEXT_PUBLIC_*` values.
- Examples of non-secret public config: `NEXT_PUBLIC_API_ORIGIN`.

## Operational Guardrails

- rotate keys periodically
- least privilege for service accounts
- separate dev/prod credentials
