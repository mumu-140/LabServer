# Core Harness Guide

Scope: `services/core/`

## Owns

- Domain entities and derived display state.
- Published plan entries (Planning = published intent).
- Resource conflict evaluation (advisory only).
- User/role authorization.
- Managed-server logical registry.
- Observation ingestion boundary.
- Plan-vs-actual reconciliation (future milestone).
- Usage aggregation/reporting semantics (future milestone).
- Persistence interfaces and migrations.

## Must not own

- Browser presentation.
- psutil/nvitop collection details.
- Beszel-specific payload types.
- Deployment/service-manager configuration.

## Design rules

- Domain logic is framework-independent wherever practical.
- External integrations enter through explicit adapters/interfaces.
- Transactions protect multi-write invariants such as plan + audit creation.
- Repeated cancel is idempotent and keeps the first timestamp.
- Use half-open time intervals `[start, end)` for scheduling/conflict calculations.
- Display states and conflicts are computed, never persisted as lifecycle columns.
- Store timestamps in UTC.
- Persist stable server IDs/logical keys, not IP addresses as identity.

## Error model

Return stable machine-readable error codes for authorization failures, disabled servers, capacity warnings surfaced as advisory conflicts, and missing resources. Operational adapter failures must map to availability/freshness states rather than unhandled exceptions.

## Testing priorities

Unit-test at minimum:
- plan create/update/cancel authorization;
- cancel idempotency;
- adjacent vs overlapping intervals;
- CPU/memory capacity conflicts;
- explicit GPU-ID conflicts;
- GPU-count-only conflicts/uncertainty;
- display-state derivation;
- admin/member permissions;
- SQLite migration path (fresh and M1 → M1.1 upgrade).

Core tests must run without network access, Beszel, Linux process access, or a GPU.
