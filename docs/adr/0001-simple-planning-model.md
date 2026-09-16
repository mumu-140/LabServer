# ADR 0001 — Simple published-intent planning

Date: 2026-09-16
Status: Accepted

## Context

M1 originally modeled lab coordination as `TaskRequest -> approval -> Reservation`. The actual workflow is lighter: a member only needs to tell the group that they intend to use a logical server, GPU, CPU, or memory during a time window. LabServer must coordinate intent without becoming a scheduler, approval queue, allocation system, or workload controller.

This decision crosses the contracts, core, persistence, API, and web harnesses, so it is recorded explicitly under the repository cross-harness change protocol.

## Decision

Use one public planning object, `PlanEntry`.

A `PlanEntry` means only:

> I intend to use this server/resource during this time window.

The planning model therefore has these properties:

- publication is immediate; there is no submit/approve/reject lifecycle;
- there is no queue, priority, resource lock, placement, dispatch, or enforcement;
- `start_at` / `end_at` use half-open interval semantics `[start_at, end_at)`;
- CPU, memory, GPU count, and GPU IDs are optional declarations;
- missing resource declarations mean "not declared", never zero usage;
- `cancelled_at` is retained for audit/history, while `upcoming` / `ongoing` / `past` are derived display states rather than persisted lifecycle states;
- overlap and capacity results are advisory warnings and never block create/update;
- members own their plans; admins may correct any plan;
- Core remains the authorization and planning source of truth; Web only renders and submits through Core APIs.

The M1 request/reservation tables are replaced by `plan_entries` through Alembic migration `0002_simple_planning`. Pre-production reservations are migrated where possible; request-only development records are intentionally not preserved.

## Consequences

Positive:

- the domain matches the actual lab coordination workflow;
- the Web surface can remain a simple shared schedule;
- planning data stays independent from runtime observation and monitoring;
- future Beszel/Runtime Collector integration can compare observed use with published intent without turning plans into enforced allocations.

Trade-offs:

- a published plan does not guarantee resource availability;
- conflicts require social coordination rather than scheduler enforcement;
- human authentication still needs a separate transport adapter before production deployment;
- the Web must clearly distinguish intent from actual runtime state.

## Compatibility

- Public request/reservation APIs are retired before first production deployment.
- Historical M1 design/plan documents may retain old terminology for provenance.
- Active source, active API documentation, and product copy must use `PlanEntry` / planned-use terminology only.

## Follow-up hardening

Post-merge review identified a small M1.1H hardening milestone before M2:

- correct Web timezone semantics;
- add missing user filter and owner/admin edit controls;
- remove unconditional mutation controls when no authenticated Web viewer exists;
- harden Web validation/error handling;
- ensure a single plan that exceeds known capacity still produces an advisory warning;
- make the planning user directory readable by active members while keeping user mutation admin-only;
- correct current-state and API documentation drift.

M1.1H does not add Docker, Beszel, Runtime Collector, production authentication, or deployment.