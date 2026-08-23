# Pergola milestone verification receipt — 2026-08-24

## Scope

- Branch: `codex/v2-professional-completion`
- Base commit before milestone packaging: `f633d07f0b55ca21124e05e6b6a1a7438286d98e`
- Geometry: `2.3`
- Snapshot Schema: `4.0`
- Standard profile: `CN-2026.7`
- Product boundary: `scheme_estimate`, with professional checks remaining `unverified/incomplete`

## Environment

- Windows host
- Python `3.14.3` for local tests
- Python `3.12` in the backend image
- Node.js `24.14.0`
- npm `11.9.0`
- Docker Engine `25.0.3`
- Docker Compose `2.24.5-desktop.1`

## Verification results

| Check | Command or method | Result |
|---|---|---|
| Backend full suite | `backend/.venv/Scripts/python.exe -m pytest -q` | 479 passed; one Starlette/httpx deprecation warning |
| Frontend lint | `npm run lint` | passed |
| Frontend production build | `npm run build` | passed; 7 static routes generated |
| Clean database migration | container SQLite database, `alembic upgrade head` | upgraded from empty to `20260813_07` |
| Existing database migration | container SQLite database, upgrade to `20260804_03`, then `alembic upgrade head` | upgraded to `20260813_07` |
| Compose PostgreSQL migration | `docker compose exec -T backend alembic current` | `20260813_07 (head)` |
| Docker build and startup | `docker compose --env-file .env up -d --build` | backend and frontend rebuilt; five services running |
| Health endpoint | `GET http://127.0.0.1/health` | `200`, `{"status":"ok","version":"2.0.0"}` |
| Browser regression | Docker base URL, Playwright bundled Chromium, one worker | 20 passed |
| Actual entry | in-app browser, `http://127.0.0.1/` | redirected to login; title and positioning copy rendered; no console error |
| Whitespace audit | `git diff --check` | passed; line-ending conversion warnings only |

## Browser environment note

The machine's installed Chrome timed out when accessing the Docker loopback URL, while Playwright bundled Chromium completed the same suite. This was classified as a browser/network-profile difference rather than a product assertion failure. The reproducible Docker command is documented in the root README.

## Open release gates

This receipt proves reproducible execution, migration and interface regression only. It does not close any professional evidence gate in `PERGOLA_PROFESSIONAL_EVIDENCE.md` and does not authorize changing `verification_status` from `unverified`.
