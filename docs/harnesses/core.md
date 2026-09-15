# Core Harness Guide

Scope: `services/core/`

## Owns

- Domain entities and state machines.
- Request/reservation lifecycle.
- Resource conflict evaluation.
- User/role authorization.
- Managed-server logical registry.
- Observation ingestion boundary.
- Plan-vs-actual reconciliation.
- Usage aggregation/reporting semantics.
- Persistence interfaces and migrations.

## Must not own

- Browser presentation.
- psutil/nvitop collection details.
- Beszel-specific payload types.
- Deployment/service-manager configuration.

## Design rules

- Domain logic is framework-independent wherever practical.
- External integrations enter through explicit adapters/interfaces.
- Transactions protect approval -> reservation creation and other multi-write invariants.
- Repeated approval must be idempotent.
- Use half-open time intervals `[start, end)` for scheduling/conflict calculations.
- Derived reconciliation never silently mutates declared reservations.
- Store timestamps in UTC.
- Persist stable server IDs/logical keys, not IP addresses as identity.

## Error model

Return stable machine-readable error codes for invalid transitions, authorization failures, capacity violations, and missing resources. Operational adapter failures must map to availability/freshness states rather than unhandled exceptions.

## Testing priorities

Unit-test at minimum:
- request state machine;
- approval idempotency;
- adjacent vs overlapping intervals;
- CPU/memory capacity conflicts;
- explicit GPU-ID conflicts;
- GPU-count-only conflicts/uncertainty;
- ambiguous reconciliation;
- overrun classification;
- admin/member permissions;
- SQLite migration path.

Core tests must run without network access, Beszel, Linux process access, or a GPU.
