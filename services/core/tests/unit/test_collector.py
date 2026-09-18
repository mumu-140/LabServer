import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

from labserver_contracts.runtime import HostRuntimeReport

COLLECTOR_PATH = Path(__file__).resolve().parents[4] / "ops" / "labserver-collector.py"
spec = importlib.util.spec_from_file_location("labserver_collector", COLLECTOR_PATH)
assert spec is not None and spec.loader is not None
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_collect_gpus_fallback_when_nvidia_smi_missing() -> None:
    with patch.object(collector.shutil, "which", return_value=None):
        gpus = collector.collect_gpus()
        assert gpus == []


def test_collect_gpus_parses_devices_and_processes() -> None:
    mock_gpu_output = (
        "0, GPU-aaaa, NVIDIA A100-SXM4-40GB, 40960, 10240, 50, 48\n"
        "1, GPU-bbbb, NVIDIA A100-SXM4-40GB, 40960, 2048, 10, 45\n"
    )
    mock_apps_output = (
        "GPU-aaaa, 1234, python train.py, 8000\n"
        "GPU-aaaa, 5678, python eval.py, 2000\n"
    )

    def fake_subprocess_run(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        if "--query-gpu=" in cmd_str:
            mock_res.stdout = mock_gpu_output
        elif "--query-compute-apps=" in cmd_str:
            mock_res.stdout = mock_apps_output
        else:
            mock_res.stdout = ""
        return mock_res

    with (
        patch.object(collector.shutil, "which", return_value="/usr/bin/nvidia-smi"),
        patch.object(collector.subprocess, "run", side_effect=fake_subprocess_run),
        patch.object(collector, "get_process_username", return_value="testuser"),
    ):
        gpus = collector.collect_gpus()

        assert len(gpus) == 2
        gpu0 = gpus[0]
        assert gpu0["index"] == 0
        assert gpu0["name"] == "NVIDIA A100-SXM4-40GB"
        assert gpu0["memory_total_mb"] == 40960.0
        assert gpu0["memory_used_mb"] == 10240.0
        assert gpu0["temperature_celsius"] == 48

        assert len(gpu0["processes"]) == 2
        p0 = gpu0["processes"][0]
        assert p0["pid"] == 1234
        assert p0["process_name"] == "python train.py"
        assert p0["used_memory_mb"] == 8000.0
        assert p0["username"] == "testuser"

        gpu1 = gpus[1]
        assert gpu1["index"] == 1
        assert len(gpu1["processes"]) == 0


def test_build_report_generates_valid_host_runtime_report() -> None:
    with (
        patch.object(collector, "collect_gpus", return_value=[]),
    ):
        report_dict = collector.build_report("fwq10")
        assert report_dict["server_key"] == "fwq10"
        assert "reported_at" in report_dict
        # Validate against contracts Pydantic model
        validated = HostRuntimeReport.model_validate(report_dict)
        assert validated.server_key == "fwq10"
        assert validated.gpus == []
