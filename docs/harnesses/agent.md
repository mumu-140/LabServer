# Agent Harness Guide

Scope: `services/agent/`

## Owns

- Local host heartbeat/identity observation.
- Safe process observations via `psutil`.
- NVIDIA GPU/device/process observations via `nvitop`/NVML.
- Normalization into shared observation contracts.
- Bounded delivery/pull responses with timestamps and health metadata.

## Hard safety boundary

The agent is read-only.

Forbidden in V1:
- remote command execution;
- arbitrary shell invocation requested by core;
- process kill/renice;
- job submission;
- package installation;
- arbitrary filesystem browsing;
- returning full command lines by default.

Any future relaxation of this boundary requires a new design review and ADR.

## Collection rules

- Treat `AccessDenied`, disappearing PIDs, missing NVML, and unsupported GPUs as expected states.
- Collection must have a configurable cadence and bounded runtime.
- Do not poll faster merely to make the UI feel realtime; 10-30 seconds is the initial design range.
- Never block one device/process failure from producing the rest of a snapshot.
- Do not log secrets or complete process arguments.
- Avoid privilege escalation solely for richer metrics.

## Contracts

The agent emits only shared DTOs from `packages/contracts`. It does not import request/reservation/domain modules from core.

A snapshot must include:
- logical server key;
- observation timestamp;
- freshness/health metadata;
- normalized process/resource activity;
- capability/unsupported indicators where needed.

## Testing

Tests use fakes/fixtures and cover:
- no NVIDIA GPU;
- multiple GPUs;
- multiple processes on one GPU;
- one PID on multiple GPUs where reported;
- process exits between list/read operations;
- access denied;
- malformed/partial upstream readings;
- timeout/bounded snapshot behavior;
- omission of full command lines/secrets.
