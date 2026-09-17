# Repository Guidelines

## V0.1 Scope

V0.1 targets one Spring Boot service, local artifact storage on an intranet, manual content production, simple version rollback, and separate accounts with equal administrator privileges. The current implementation includes private resource ingestion: scene-linked drafts, multiple file records, local ArtifactStorage upload/verification, retry, startup reconciliation and administrator audit. Draft file deletion is physical: remove stored payloads and the file row, retain audit and minimal idempotency receipts, and recover unfinished deletions at startup. Publication, rollback, preview and client download/loading remain unimplemented until a real Addressables sample and client contract are available. See docs/12-resource-ingestion.md. The old seven-table/object-storage design is historical candidate material. Preserve the separation of scenes, content versions, and deliverable files. Confirm the delivery format before finalizing file granularity; draft-to-file associations are implemented for private ingestion; shared dependencies, day/night variants, coordinates and catalog parsing remain provisional. Do not introduce task queues, Worker services, tenant isolation, or approval roles without a new requirement.

## Project Structure & Module Organization

This repository includes a local RuoYi Spring Boot 3 / Vue3 Demo with PostgreSQL 17, plus candidate resource/version designs. Nothing has been deployed to a server. See docs/08-demo-runbook.md for implemented scope.

- `backend/`: pinned RuoYi Spring Boot 3 with MyBatis, Bearer authentication, fixed-role accounts and ruoyi-ar scene/audit module. Only classpath:db/demo migrations initialize the app.
- `frontend/`: pinned RuoYi Vue3 with package-lock.json; use npm ci.
- `.local/`: ignored runtime, logs and local secrets; never commit or print credentials.
- `compose.yaml`, `deploy/`: single-host Linux containers on Windows Docker Desktop or Linux; named volumes and an internal service network. Use an isolated `innovation-infra-check` project for container tests.
- `docs/`: architecture, database, workflows, operations, review checklist, and validation reports.
- `database/migrations/`: Flyway migrations for tables, constraints, version sealing, and publication switching.
- `contracts/`: generated OpenAPI, runtime-manifest schema, and examples.
- `scripts/`: contract generator and executable validation checks.
- Root images and notes are user-provided references; preserve unrelated files.

## Development loop

Work locally. Docker is a packaging step after the change is settled, not part of the edit cycle.

1. Inner loop: edit source, run the Windows Demo, check the result, repeat.
2. Package Docker only when the UI and APIs are stable, the LAN demo must show the new build, or a container-shaped acceptance is required.
3. Do not rebuild images, `docker cp` into a container, or recreate Compose services for copy, button, layout, or other small edits.

Frontend inner loop is Vite (`npm --prefix frontend run dev`). Backend inner loop is the local jar (`python scripts/local_demo.py backend`); Java changes still need a package and process restart, which is faster than rebuilding the backend image.

```powershell
python scripts/local_demo.py infra
python scripts/local_demo.py backend
npm --prefix frontend run dev
```

Open `http://127.0.0.1:43174`. Local API is `http://127.0.0.1:18080`. Vue saves hot-reload; do not rebuild the gateway to see them.

A human terminal can run those start commands and walk away: Postgres, Redis, and Java keep running after `local_demo.py` exits. This agent's shell does not. It puts each command in a Windows Job Object that kills every descendant when the command returns. So `python scripts/local_demo.py infra` or `backend` as a one-shot looks successful, then Postgres/Java die with no shutdown log, and `127.0.0.1:15432` / `:18080` go silent. Vite survives only if it was launched `background: true` (the npm process never exits).

From this agent, start infra and backend in one long-lived background command that does not return, then wait until the ports still accept connections:

```powershell
python scripts/local_demo.py infra
python scripts/local_demo.py backend
python -c "import time; time.sleep(10**9)"
```

Do not report the local demo as up merely because `local_demo.py` printed `started`. Confirm `http://127.0.0.1:18080/captchaImage` and `http://127.0.0.1:43174/` after the starter is still running. `python scripts/local_demo.py stop` remains the stop path.

The LAN demo is the Compose gateway at `http://192.168.0.12:43174`. It bakes `frontend/` at image build time. Compose already binds `192.168.0.12:43174`; Vite listens on `127.0.0.1:43174`, so they can run together. Do not run `python scripts/local_demo.py frontend` while Compose is up — that script binds `AR_FRONTEND_HOST` with `--strictPort` and will fail. Compose and the Windows Demo use separate databases and accounts. Redis in Compose is tmpfs; recreating backend or gateway drops logins.

For copy, button, or layout-only changes: edit `frontend/src` and any Playwright selector that clicks the old control (`scripts/verify_browser.py`, `scripts/verify_ingestion.py`). Update the matching sentence in `docs/` if it names that control. A removed label is done when the source and selectors no longer name it. Full login-and-click checks are for behavior changes. `bootstrap` is retired on the LAN demo; do not enable it or mint sessions to satisfy a browser check. If you cannot log in, say so and stop.

When the user asks to publish a settled change to the LAN demo, rebuild only what changed. Frontend-only:

```powershell
docker compose --env-file config/compose.env build gateway
docker compose --env-file config/compose.env up -d gateway
```

Do not `up --build gateway` in a way that recreates `backend`.

## Build, Test, and Development Commands

Run from the repository root in a Python environment:

```powershell
python -m pip install -r scripts/requirements-review.txt
python scripts/generate_contracts.py
python scripts/verify_design.py
python scripts/verify_database.py --pg-bin 'C:/Program Files/PostgreSQL/17/bin'
```

Edit `scripts/generate_contracts.py`, then regenerate contracts. Design validation checks schemas, examples, authentication declarations, and links. Database validation starts and stops its own temporary Windows PostgreSQL instance. Adjust the binary path and record the tested version; PostgreSQL 18.4 results do not establish PostgreSQL 17 compatibility.

## Coding Style & Naming Conventions

Use four-space Python indentation, SQL/Python `snake_case`, API `camelCase`, UUIDs, and UTC timestamps. Keep Chinese design documentation concise. Update SQL, contracts, and documentation together. No formatter or linter is configured.

The V0.1 scripts initialize an empty database. Use descriptive Flyway names such as `V003__add_scene_field.sql` for subsequent changes. Keep initialization reproducible.

## Testing Guidelines

Use JSON Schema/OpenAPI validators and psycopg with real PostgreSQL. Add descriptive checks for changed invariants: immutable versions, verified assets, day/night separation, publication conflicts, rollback, and audit history. No percentage coverage threshold exists. Record results and limitations in `docs/06-validation.md`; SQL tests do not verify HTTP, cloud storage, or client behavior.

## Commit & Pull Request Guidelines

Git history was unavailable. Use imperative subjects, optionally prefixed `docs:`, `db:`, or `contracts:`. PRs should explain changed behavior, the reason for the change, validation commands, database version, and remaining assumptions.

## Security & Configuration

Never commit credentials or production connection strings. Keep examples synthetic and validate only against isolated databases. Treat unresolved client formats and server settings as explicit assumptions.
