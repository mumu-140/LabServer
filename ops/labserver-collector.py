#!/usr/bin/env python3
"""LabServer Host Runtime Collector.

A lightweight, zero-dependency read-only script that gathers GPU device metrics
and active GPU compute processes, resolves OS process owners, and reports to
LabServer Core via HTTP POST.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any


def get_process_username(pid: int) -> str:
    try:
        import pwd

        uid = os.stat(f"/proc/{pid}").st_uid
        return pwd.getpwuid(uid).pw_name
    except Exception:
        try:
            res = subprocess.run(
                ["ps", "-p", str(pid), "-o", "user="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                name = res.stdout.strip()
                if name:
                    return name
        except Exception:
            pass
        return "unknown"


def collect_gpus(timeout: float = 5.0) -> list[dict[str, Any]]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []

    cmd_gpus = [
        nvidia_smi,
        "--query-gpu=index,gpu_uuid,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        res = subprocess.run(
            cmd_gpus,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except Exception as exc:
        sys.stderr.write(f"Warning: nvidia-smi device query failed: {exc}\n")
        return []

    gpus_by_uuid: dict[str, dict[str, Any]] = {}
    gpus_list: list[dict[str, Any]] = []

    for line in res.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            idx = int(parts[0])
            uuid = parts[1]
            name = parts[2]
            total_mb = float(parts[3])
            used_mb = float(parts[4])
            util = float(parts[5]) if parts[5] not in ("[N/A]", "N/A", "") else None
            temp = int(parts[6]) if parts[6] not in ("[N/A]", "N/A", "") else None

            gpu_data: dict[str, Any] = {
                "index": idx,
                "name": name,
                "memory_total_mb": total_mb,
                "memory_used_mb": used_mb,
                "utilization_gpu_percent": util,
                "temperature_celsius": temp,
                "processes": [],
            }
            gpus_by_uuid[uuid] = gpu_data
            gpus_list.append(gpu_data)
        except Exception as parse_err:
            sys.stderr.write(f"Warning: failed to parse GPU line {line!r}: {parse_err}\n")

    cmd_apps = [
        nvidia_smi,
        "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        res_apps = subprocess.run(
            cmd_apps,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        for line in res_apps.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            uuid = parts[0]
            try:
                pid = int(parts[1])
                pname = parts[2]
                used_mem = float(parts[3]) if parts[3] not in ("[N/A]", "N/A", "") else None
                uname = get_process_username(pid)

                gpu_item = gpus_by_uuid.get(uuid)
                if gpu_item is not None:
                    gpu_item["processes"].append(
                        {
                            "gpu_id": gpu_item["index"],
                            "pid": pid,
                            "process_name": pname,
                            "username": uname,
                            "used_memory_mb": used_mem,
                        }
                    )
            except Exception as parse_err:
                sys.stderr.write(f"Warning: failed to parse process line {line!r}: {parse_err}\n")
    except Exception as exc:
        sys.stderr.write(f"Warning: nvidia-smi compute-apps query failed: {exc}\n")

    return gpus_list


def build_report(server_key: str, timeout: float = 5.0) -> dict[str, Any]:
    now = datetime.now(UTC)
    gpus = collect_gpus(timeout=timeout)
    return {
        "server_key": server_key,
        "reported_at": now.isoformat(),
        "gpus": gpus,
    }


def send_report(
    core_url: str,
    report: dict[str, Any],
    token: str = "",
    timeout: float = 5.0,
) -> bool:
    endpoint = f"{core_url.rstrip('/')}/api/v1/runtime/report"
    payload = json.dumps(report).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True
            sys.stderr.write(f"Error: Core returned status {resp.status}\n")
            return False
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"HTTP Error {exc.code}: {body}\n")
        return False
    except Exception as exc:
        sys.stderr.write(f"Connection Error: {exc}\n")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect host GPU and process runtime status and report to LabServer."
    )
    parser.add_argument(
        "--server-key",
        default=os.environ.get("LABSERVER_SERVER_KEY", ""),
        help="Host key in LabServer (e.g. fwq57, fwq51)",
    )
    parser.add_argument(
        "--core-url",
        default=os.environ.get("LABSERVER_CORE_URL", "http://127.0.0.1:18281"),
        help="Core service base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("LABSERVER_COLLECTOR_TOKEN", ""),
        help="Shared collector authentication token",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Subprocess and HTTP timeout in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON payload to stdout and exit without posting",
    )

    args = parser.parse_args(argv)

    if not args.server_key:
        sys.stderr.write("Error: --server-key or LABSERVER_SERVER_KEY is required\n")
        return 1

    report = build_report(args.server_key, timeout=args.timeout)

    if args.dry_run:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0

    success = send_report(
        core_url=args.core_url,
        report=report,
        token=args.token,
        timeout=args.timeout,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
