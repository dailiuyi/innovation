# Repository Guidelines

## Start here

- Read the [knowledge index](docs/index.md) for current implementation, historical candidates, decisions and task handoffs.
- Use [resource ingestion](docs/12-resource-ingestion.md) for current business behavior and [development workflow](docs/development-workflow.md) for local processes, Docker and acceptance commands.
- Use [harness instructions](docs/13-harness.md) to choose checks and interpret evidence. A passing quick check is not end-to-end acceptance.
- For work spanning sessions, copy the [task template](docs/tasks/template.md) and follow the [handoff rules](docs/tasks/README.md).
- For review requests, follow the [review defaults](docs/14-code-review.md). A short request naming the changes is sufficient; review only unless the user also requests fixes.

## Review defaults

Review actual changes against the user's intent and accepted project constraints. For "current uncommitted changes", include staged, unstaged and relevant untracked files; the named feature is the focus, not permission to silently omit other changes. Let the reviewer choose investigation and necessary verification. Report actionable defects with location, trigger and impact; distinguish uncertainty, avoid style-only findings and do not invent issues to meet a quota. Do not edit source, tracked reports or task records during review, or deploy, unless separately requested. State the reviewed scope and verification limits; see the linked defaults for evidence and changing-worktree handling.

## V0.1 boundaries

One Spring Boot service, intranet local ArtifactStorage, manual content production, and separate accounts with equal administrator privileges. Private ingestion implements scene-linked drafts, multiple file records, upload/verification, retry, startup reconciliation and administrator audit.

Draft file deletion is physical: remove stored payloads and the row, retain audit and minimal idempotency receipts, and recover unfinished deletions at startup. Preserve the separation of scenes, content versions and deliverable files.

Administrator publication is one published draft pointer per scene: files freeze, description stays editable, and replacing the pointer returns the previous draft to an unpublished state. Preview, unpublish-without-replace and client download/loading are unimplemented pending a real Addressables sample and client contract. Shared dependencies, day/night variants, coordinates and catalog parsing remain provisional. Do not introduce task queues, Worker services, tenant isolation or approval roles without a new requirement.

## Repository map

- `backend/`: pinned RuoYi Spring Boot 3, MyBatis, Bearer authentication, fixed-role accounts and ruoyi-ar. Only `classpath:db/demo` migrations initialize the application.
- `frontend/`: pinned RuoYi Vue3; use `scripts/agent_check.py --profile frontend` for task-local dependency/build reuse. It installs with `npm ci` when needed; preserve the lockfile and do not repeat installs/builds outside the entrypoint.
- `database/migrations/`: historical candidate SQL, not current application migrations.
- `contracts/`: generated OpenAPI and historical candidate manifest examples. Edit `scripts/generate_contracts.py`, then regenerate; never fix drift only in generated files.
- `scripts/`: development, contract and acceptance tooling; `harness.py` is the common check entrypoint.
- `compose.yaml`, `deploy/`: single-host containers; container tests must use isolated `innovation-infra-check` resources.
- `.local/`: ignored runtime, logs, harness evidence and secrets. Never commit or print credentials.
- Root images and notes are user references; preserve unrelated files and worktree changes.

## Development and validation

Run the shortest requirement-specific business check first; trace actual callers before changing shared rules. Java changes must execute affected-module tests via `scripts/check_java.py` with nonzero executed tests. Then choose quick/frontend/ingestion by risk; account changes do not automatically require unrelated artifact-ingestion regression. See [fast review workflow](docs/16-fast-review.md).

For PR review use `scripts/review.py` to prepare a commit-scoped checkout, validate, and (after independent review) serve a loopback-only human acceptance instance. Include verified URL, SHA, credential-file location and stop command. This authorizes isolated local acceptance tooling, not merge or daily Demo/LAN deployment.

Work locally first. Use Vite on `127.0.0.1:43174` and the local backend on `127.0.0.1:18080`. LAN Compose uses `192.168.0.12:43174` and a separate database/account set. No remote server deployment has been performed by this repository workflow.

Do not rebuild images, copy into containers or recreate Compose services for copy/button/layout edits. Update the corresponding browser selectors and documentation; use full login/click checks for behavior changes. Do not re-enable retired LAN bootstrap accounts or mint sessions to make checks pass. Report login blockers honestly.

Read the development workflow before starting/stopping processes: this agent's Windows Job Object can kill descendants when a starter command exits. Confirm health endpoints after startup; a printed `started` is insufficient. Never stop the daily Demo just to validate a change. Harness ingestion builds a separate backend copy.

Run `python scripts/harness.py doctor --profile quick`, then `python scripts/harness.py check --profile quick` for repository rules and contracts. Choose `frontend` for frontend behavior/build checks or `ingestion` for the isolated current-source backend/HTTP/browser flow. Inspect the report's scope, source fingerprint and skipped/blocked checks before claiming completion.

Optional Symphony development-task orchestration is configured in `WORKFLOW.md`; see [its runbook](docs/15-symphony.md). Only explicitly labeled issues are eligible, and delivery stops at a draft PR for human review. No automatic merge, deployment or unscoped repair loop is enabled. A failed check must be understood; do not weaken a test or edit a report to make it green. Promote reviewed acceptance evidence to docs explicitly; routine checks keep reports under `.local/harness/`.

When preparing a Symphony issue, follow the runbook's model-selection procedure: inspect the container's model catalog (GPT plus the configured DeepSeek provider), respect the user's explicit choice, record the selection reason, validate the model/effort pair, set the two routing labels, and add `symphony:ready` last. Missing routing labels default independently to `gpt-6-astra` and `low`; do not infer execution parameters from issue prose or silently replace an unavailable model. DeepSeek uses the official `deepseek-flash` ID and a separately mounted API key; catalog/label validation alone does not prove authenticated inference.

## Conventions and security

Use four-space Python indentation, SQL/Python `snake_case`, API `camelCase`, UUIDs and UTC timestamps. Keep Chinese documentation concise. No global formatter/linter is configured. Update SQL, generated contracts and documentation together when their behavior changes.

Use descriptive incremental Flyway migrations for subsequent changes; keep empty-database initialization reproducible. Use real isolated PostgreSQL for changed data invariants; PostgreSQL 18 results do not establish PostgreSQL 17 compatibility. Verify applicable concurrency, audit, storage and authentication behavior. Day/night publication and client-loading invariants belong to candidate design checks until implemented.

Record commands, tested versions, results and limitations in [validation records](docs/06-validation.md). SQL checks do not establish HTTP, cloud storage or client behavior. No percentage coverage threshold exists.

Use imperative commit subjects, optionally `docs:`, `db:` or `contracts:`. PRs explain changed behavior, reason, validation commands, database version and remaining assumptions. Never commit production connection strings; keep examples synthetic and unresolved client/server contracts explicit.
