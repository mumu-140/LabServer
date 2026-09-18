# Project Knowledge

This file records stable project facts and durable decisions. Do not use it for transient task notes.

## Purpose

LabServer is a lightweight internal research-lab server coordination system. It combines:

1. infrastructure visibility;
2. current user workload visibility;
3. human-entered plans (published intent);
4. plan-vs-actual reconciliation;
5. simple usage/availability reporting.

It is intentionally not a batch scheduler or general infrastructure-management platform.

## Initial environment

- Initial managed hosts: logical names `fwq10`, `fwq51`, `fwq56`, `fwq57`.
- Hosts are reachable on the same private network.
- Runtime association may use private IP addresses, but real addresses are deployment configuration and must not be committed.
- Initial scale is small: optimize for clarity and operational simplicity rather than distributed-system scale.

## Delivery discipline

- Lesson from M1.1 (2026-09-16 audit): scope that was planned but not delivered must be listed explicitly as deferred items in `CURRENT_STATE.md` at delivery time. Unrecorded deferrals made the gap discoverable only by a post-hoc audit.
- Same rule applies to any deviation from an approved plan: record it where the status is written, not in the implementer's memory.

## Durable architecture decisions

### Monitoring

Use mature upstream monitoring/telemetry components where practical. Beszel is the preferred baseline for host-level CPU, memory, disk, network, load, temperature, GPU totals, history, and alerts.

LabServer must not fork or duplicate a full monitoring stack unless a later requirement proves the adapter approach insufficient.

### Runtime user activity

Host-level monitoring alone is insufficient for answering which user/process is consuming GPU/CPU resources. A small read-only Lab Agent will collect normalized runtime observations.

Preferred libraries:
- `psutil` for Linux process/system information;
- `nvitop`/NVML for NVIDIA GPU and GPU-process information.

Do not parse human-formatted `ps`, `top`, or `nvidia-smi` output when a stable library/API is available.

### Task planning

Users publish plan entries with fields such as title, server, start and end (UTC window), CPU, memory, GPU count and optional GPU IDs, project, and notes. Publishing is not gated.

A plan entry is the single published planning concept. It is never gated, queued, or converted into another artifact.

V1 provides conflict detection and warnings but is not responsible for dispatching, blocking, killing, or enforcing workloads.

### Plan vs actual

A core differentiator is reconciling declared plans with observed runtime activity. The system should identify:
- planned activity that appears to be running;
- planned activity that has not started;
- observed activity with no matching plan;
- resource/time overruns.

Reconciliation must be explainable and must not silently mutate plans.

### Persistence

SQLite is the preferred initial database. The initial scale does not justify PostgreSQL, Redis, Kafka, or a distributed cache.

Real-time observations should primarily remain ephemeral/current-state data. Persist only the history needed for reporting and audit, rather than high-frequency raw telemetry.

### Security and privacy

- Repository contains no real private IPs, tokens, credentials, SSH keys, or personal secrets.
- Full process command lines are not exposed to ordinary users by default.
- Agent is read-only and narrowly scoped.
- All agent-to-core traffic must be authenticated and bounded by timeouts.

## Product surfaces

Initial user-facing surfaces:
- Dashboard
- Servers
- Running
- Schedule
- Statistics

Initial roles:
- `admin`: manages servers, members, and plan corrections.
- `member`: views the shared schedule, publishes plans, and manages own plans.

## Non-goals for V1

- Slurm-like queueing and dispatch.
- Remote shell.
- Process killing or priority changes.
- Automated package/software management.
- Kubernetes/container orchestration.
- Full accounting/billing.
- Internet-facing multi-tenant SaaS.
