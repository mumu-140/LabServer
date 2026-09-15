# M1.1 Simple Planning Design

Date: 2026-09-15
Status: Draft for user review

## 1. Purpose

LabServer planning is a lightweight coordination tool, not an approval system or scheduler. A user publishes that they intend to use a server or GPU during a time window so that other lab members can see the plan and coordinate informally.

The product semantics are therefore:

- publish intent;
- show it on a shared schedule;
- highlight overlaps/conflicts;
- allow the owner to edit or cancel the plan;
- never reserve, lock, dispatch, approve, reject, or enforce compute resources.

This supersedes the heavier M1 `TaskRequest -> approval -> Reservation` workflow before production deployment.

## 2. Why M1.1 exists

Milestone 1 implemented separate `TaskRequest` and `Reservation` entities with lifecycle states and admin approval. That model is correct for a reservation/approval product but is unnecessarily heavy for the actual lab workflow.

Because LabServer has not yet been deployed to production, M1.1 should simplify the model now rather than preserve incorrect semantics behind an auto-approval UI.

The goal is a smaller domain that matches what users actually do: "I plan to use this resource at this time."

## 3. Product boundary

### In scope

- Create a plan from the web UI.
- Edit or cancel one's own plan.
- Admin may correct any plan.
- Show plans in a shared Schedule view.
- Filter by server, user, and date/time window.
- Optionally specify GPU count and GPU IDs.
- Optionally specify CPU and memory intent.
- Compute advisory overlap/conflict warnings.
- Preserve audit timestamps and actor identity.

### Explicitly out of scope

- Draft/submitted/approved/rejected workflow.
- Approval queue.
- Resource locking.
- Job dispatch.
- Queue position or priority.
- Automatic placement.
- Process control.
- Automatic cancellation when a user does not run a job.
- Billing or quotas.

## 4. Domain model

Replace `TaskRequest` and `Reservation` as user-facing planning concepts with one object:

```text
PlanEntry
- id: UUID
- owner_id: UUID
- server_id: UUID
- title: string
- project: string nullable
- start_at: datetime UTC
- end_at: datetime UTC
- cpu_cores: int nullable
- memory_gb: float nullable
- gpu_count: int nullable
- gpu_ids: tuple[int, ...] nullable
- note: string nullable
- cancelled_at: datetime nullable
- created_at: datetime UTC
- updated_at: datetime UTC
```

Rules:

- `end_at > start_at`;
- all resource quantities are non-negative;
- explicit GPU IDs are unique;
- if `gpu_ids` are supplied, `gpu_count` must agree with their count;
- known server capacity may be used to warn about impossible values;
- capacity/conflict warnings never block publication in V1;
- a cancelled plan remains available for audit but is excluded from active schedule views by default.

## 5. Status semantics

Do not persist an approval/lifecycle state machine.

Display state is derived:

```text
cancelled       if cancelled_at is set
upcoming        if now < start_at
ongoing         if start_at <= now < end_at
past            if now >= end_at
```

This keeps time-derived display state separate from user-entered intent.

## 6. Authorization

### Member

- view all shared plans;
- create a plan;
- edit own plan;
- cancel own plan.

### Admin

- all member permissions;
- edit/cancel any plan;
- manage users and managed-server metadata.

There is no approval permission because there is no approval workflow.

Human authentication transport remains a separate concern. Production routes must remain default-deny until the chosen login mechanism is configured.

## 7. Conflict semantics

Conflict detection remains advisory only.

A potential conflict exists when:

```text
same server
AND [start_at, end_at) overlaps
AND a constrained resource is oversubscribed
```

Use half-open intervals `[start_at, end_at)` so adjacent plans do not overlap.

GPU handling:

- explicit GPU IDs: warn on exact GPU overlap;
- GPU count only: compare aggregate overlapping count with known server GPU capacity;
- mixed explicit/count-only plans: report uncertainty rather than invent device placement.

CPU and memory handling:

- sum overlapping planned quantities when supplied;
- compare with known server capacity;
- missing quantities mean "not declared", not zero usage.

Warnings are derived data. They do not prevent create/update.

## 8. API surface

Replace request/reservation-oriented public planning endpoints with a small plan API:

```text
GET    /api/v1/plans
POST   /api/v1/plans
GET    /api/v1/plans/{plan_id}
PATCH  /api/v1/plans/{plan_id}
POST   /api/v1/plans/{plan_id}/cancel
GET    /api/v1/plans/{plan_id}/conflicts
```

List filters should include:

```text
server_id
owner_id
start
end
include_cancelled
```

The API returns stable machine-readable error codes for authorization, validation, capacity metadata problems, and missing resources.

## 9. Web surface

M1.1 introduces one intentionally simple coordination page:

```text
/schedule
```

Primary presentation:

- date/day selector;
- server selector;
- simple timeline/list grouped by server;
- owner name;
- task title;
- planned time window;
- GPU count/IDs when declared;
- concise CPU/memory intent when declared;
- conflict badge when overlaps exist;
- edit/cancel controls for owner/admin.

The UI does not present plans as "approved", "reserved", "queued", or "guaranteed".

Recommended wording:

- `Planned use`
- `Schedule`
- `Overlap warning`
- `Who plans to use this server`

Avoid scheduler terminology such as allocation, job, queue, dispatch, reservation lock, or priority unless a future design explicitly introduces those concepts.

## 10. Web technology

Keep the web harness deliberately small:

- FastAPI server-side routes;
- Jinja2 templates;
- HTMX 2.x for lightweight form/list refreshes where useful;
- plain CSS;
- no Node build toolchain in M1.1;
- no React/Next/Vite/Tailwind dependency unless a later UI requirement justifies it.

HTMX assets should be vendored rather than fetched from a CDN at runtime so the internal deployment remains self-contained.

## 11. Persistence migration

M1.1 must use an Alembic migration; do not edit the initial migration in place.

Because M1 has not been deployed to production, the implementation may simplify aggressively, but the migration path must still be testable from the M1 schema.

Preferred approach:

1. create `plan_entries`;
2. if any local development reservations exist, migrate them 1:1 into plan entries where possible;
3. remove request/reservation-only tables and constraints after the migration step;
4. remove obsolete request/approval contracts, services, routes, and tests;
5. retain audit events and server/user identities.

No production-data compatibility promise is required for pre-deployment development records.

## 12. Harness boundaries

### contracts

Own only plan DTOs, enums needed by the API, and shared error/read models.

### core

Own plan validation, authorization, conflict calculation, persistence, and API behavior.

### web

Own form rendering, schedule rendering, filters, and presentation only. Web must not reimplement conflict logic.

### ops

No planning semantics. Ops only deploys/configures services.

## 13. Tests

At minimum:

### Domain/core

- end before start rejected;
- adjacent intervals are not conflicts;
- overlapping explicit GPU IDs produce a warning;
- aggregate GPU oversubscription produces a warning;
- mixed explicit/count-only GPU plans preserve uncertainty;
- CPU/memory advisory conflicts;
- member edits own plan;
- member cannot edit another member's plan;
- admin can edit/cancel any plan;
- cancel is idempotent or has a stable conflict response;
- cancelled plans are excluded by default;
- UTC handling.

### API

- unauthorized;
- forbidden;
- create/get/list/update/cancel;
- not found;
- validation errors;
- filters;
- conflict response shape.

### Web

- create form;
- schedule rendering;
- owner/admin controls;
- conflict badge;
- empty state;
- filtering;
- cancelled plan presentation when explicitly requested.

### Migration

- fresh database -> head;
- M1 schema -> M1.1 head;
- expected tables/constraints present;
- obsolete request/approval schema absent.

## 14. Definition of done

M1.1 is complete when:

- the public planning model is one `PlanEntry` concept;
- users can publish/edit/cancel planned use from the web;
- the schedule is visible to members;
- overlaps are advisory only;
- no approval/rejection workflow remains in the product surface;
- tests and migrations pass;
- no private infrastructure values are committed;
- documentation reflects that LabServer coordinates intent rather than enforcing resource allocation.

## 15. Next milestone boundary

After M1.1 is merged and verified, M2 adds observability without changing planning semantics:

- Docker-first deployment foundation;
- Beszel as the primary infrastructure-monitoring source;
- a minimal read-only Runtime Collector only for user/PID/GPU-process attribution not provided by Beszel;
- Running view combining current monitoring and runtime ownership;
- no scheduler behavior.
