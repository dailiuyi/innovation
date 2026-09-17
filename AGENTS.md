# Repository Guidelines

## V0.1 Scope

V0.1 targets one Spring Boot service, local artifact storage on an intranet, manual content production, simple version rollback, and separate accounts with equal administrator privileges. The current implementation stage is infrastructure only: Docker Compose and a local ArtifactStorage component; artifact upload/publication/download APIs remain unimplemented until a real deliverable and client loading contract are available. The old seven-table/object-storage design is historical candidate material. Preserve the separation of scenes, content versions, and deliverable files. Confirm the delivery format before finalizing file granularity; multi-file associations, day/night variants, coordinates, and dependency handling are provisional, not implementation requirements. Do not introduce task queues, Worker services, tenant isolation, or approval roles without a new requirement.

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
