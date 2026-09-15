# AGENTS.md

This file is the repository-wide entrypoint for Codex, Claude Code, Gemini/Antigravity, and other coding agents. Keep it short. Detailed rules live under `docs/` and inside each harness.

## 1. Read order

Before changing code:

1. Read `docs/PROJECT_KNOWLEDGE.md`.
2. Read `docs/CURRENT_STATE.md`.
3. Read the relevant harness guide under `docs/harnesses/`.
4. Read the current design/spec and implementation plan referenced by `docs/CURRENT_STATE.md`.

Do not load unrelated harness documentation unless the change crosses a documented interface.

## 2. Repository boundaries

LabServer is split into four harnesses:

- `web` — presentation, forms, dashboards, schedule UI.
- `core` — domain model, requests, plans, reconciliation, reporting APIs.
- `agent` — read-only collection of host/process/GPU observations from managed servers.
- `ops` — deployment, configuration templates, service definitions, backup/restore.

Cross-harness dependencies must follow the interfaces in `docs/HARNESS_ARCHITECTURE.md`. Never bypass an interface by importing another harness's internals.

## 3. Non-negotiable rules

- Never commit real server IPs, credentials, SSH material, API tokens, usernames, or private command lines.
- Runtime secrets and IP mappings belong in ignored local/deployment configuration.
- The agent is read-only by default. No remote shell, process kill, job submission, package installation, or filesystem mutation without an explicit future design change.
- Do not turn LabServer into a scheduler. V1 observes, plans, reconciles, and reports; it does not dispatch workloads.
- Prefer mature libraries and upstream APIs over custom parsers or reimplementations.
- Business/domain logic belongs in `core`, not in HTTP handlers, templates, monitoring adapters, or persistence models.
- Monitoring integrations are adapters. Beszel/nvitop/psutil-specific types must not leak into core domain interfaces.
- Schema changes require migrations and tests.
- New dependencies require a stated reason in the PR and must be scoped to one harness when possible.
- Every behavior change requires tests at the narrowest useful layer.

## 4. Change discipline

- Keep commits small and single-purpose.
- Do not mix refactors with behavior changes unless the refactor is required by the change.
- Update `docs/CURRENT_STATE.md` when a milestone or architectural decision changes.
- Update `docs/PROJECT_KNOWLEDGE.md` only for stable facts or durable decisions.
- Create/update an ADR when changing a cross-harness contract, data ownership, security boundary, or major dependency.

## 5. Deployment safety

Production-like hosts are group compute servers. Treat observation code as potentially disruptive:

- collection must be bounded in CPU, memory, file descriptors, and polling frequency;
- timeouts are mandatory for network calls;
- one unreachable server must not block the dashboard;
- failures must degrade to `stale`/`unavailable`, never crash the whole service;
- local development configuration must never target real hosts by default.

## 6. Definition of done

A change is complete only when:

- tests for the changed behavior pass;
- public/internal interfaces are documented where needed;
- no secrets or private infrastructure details are present in the diff;
- relevant harness documentation remains accurate;
- `docs/CURRENT_STATE.md` reflects milestone-level changes.
