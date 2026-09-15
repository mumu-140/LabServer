# LabServer

Lightweight lab server management for a small research group.

LabServer is designed around four concerns:

- **Observe** — host, GPU, storage, and current user workload visibility.
- **Plan** — human-entered resource requests and reservations.
- **Reconcile** — compare planned work with observed runtime activity.
- **Report** — simple usage and availability statistics.

The initial target is a small set of Linux compute servers on the same private network. Servers are identified by a stable logical name (for example `fwq10`) and an internal IP supplied at deployment time. Real IP addresses, credentials, tokens, and user secrets must never be committed to this repository.

## Project status

**Architecture approved; Milestone 1 central planning core is under implementation. No production deployment yet.**

The design baseline is maintained under `docs/`. Start with:

- `AGENTS.md` — repository-wide guardrails and harness routing.
- `docs/PROJECT_KNOWLEDGE.md` — stable project context and decisions.
- `docs/CURRENT_STATE.md` — current implementation state and next step.
- `docs/superpowers/specs/2026-09-15-labserver-design.md` — approved architecture baseline.
- `docs/superpowers/plans/2026-09-15-m1-foundation-core.md` — Milestone 1 execution plan.
- `docs/api/core-v1.md` — current Core v1 HTTP/authorization semantics.

## Design principle

Prefer mature components over reimplementing infrastructure. LabServer should remain a thin coordination layer rather than becoming a scheduler, monitoring stack, or cluster orchestrator.
