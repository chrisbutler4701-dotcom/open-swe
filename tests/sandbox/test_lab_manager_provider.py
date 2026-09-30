import base64
import json
import re
import shlex
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from deepagents.backends.protocol import ExecuteResponse

from agent.sandboxes.providers.lab_manager import (
    LabManagerError,
    LabManagerSandbox,
    create_lab_manager_sandbox,
)
from agent.sandboxes.providers.registry import SandboxGoneError


def _mock_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_lab_manager_exec_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/labs/run-123/exec"
        assert request.headers["Authorization"] == "Bearer test-token"
        body = json.loads(request.content)
        assert body["command"] == "echo hello"
        assert body["timeout_seconds"] == 100
        return httpx.Response(
            200,
            json={
                "exit_code": 0,
                "stdout": "hello\n",
                "stderr": "",
                "duration_ms": 15,
            },
        )

    sb = LabManagerSandbox(
        run_id="run-123",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        default_timeout=100,
        transport=_mock_transport(handler),
    )
    assert sb.id == "run-123"
    result = sb.execute("echo hello", timeout=100)
    assert isinstance(result, ExecuteResponse)
    assert result.exit_code == 0
    assert result.output == "hello\n"
    assert result.truncated is False


def test_lab_manager_exec_404_raises_sandbox_gone():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown run_id"})

    sb = LabManagerSandbox(
        run_id="run-dead",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )
    with pytest.raises(SandboxGoneError, match="not found"):
        sb.execute("ls")


def test_lab_manager_exec_410_raises_sandbox_gone():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={"detail": "lab destroyed"})

    sb = LabManagerSandbox(
        run_id="run-destroyed",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )
    with pytest.raises(SandboxGoneError, match="destroyed"):
        sb.execute("ls")


def test_lab_manager_exec_nonzero_exit_code_preserved():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "exit_code": 42,
                "stdout": "",
                "stderr": "custom failure",
                "duration_ms": 50,
            },
        )

    sb = LabManagerSandbox(
        run_id="run-err",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )
    result = sb.execute("false")
    assert result.exit_code == 42
    assert "custom failure" in result.output


def test_lab_manager_reattach_missing_lab_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown run_id"})

    with pytest.raises(SandboxGoneError, match="was not found"):
        create_lab_manager_sandbox(
            sandbox_id="missing-lab",
            base_url="http://test-server/v1",
            token="test-token",
            transport=_mock_transport(handler),
        )


def test_lab_manager_reattach_ready_lab_succeeds():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/labs/existing-lab":
            return httpx.Response(
                200,
                json={
                    "run_id": "existing-lab",
                    "project": "smoke-hello",
                    "task": "smoke",
                    "model": "open-swe",
                    "ref_requested": "master",
                    "ref_resolved_sha": "abc12345",
                    "workspace_name": "lab--smoke",
                    "volume": "vol",
                    "container": "cont",
                    "status": "ready",
                    "created_at": "2026-09-29T20:00:00Z",
                    "last_activity": "2026-09-29T20:01:00Z",
                },
            )
        return httpx.Response(404)

    sb = create_lab_manager_sandbox(
        sandbox_id="existing-lab",
        base_url="http://test-server/v1",
        token="test-token",
        transport=_mock_transport(handler),
    )
    assert sb.id == "existing-lab"


def test_lab_manager_diff_and_destroy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/labs/lab-1/diff":
            return httpx.Response(
                200,
                json={
                    "run_id": "lab-1",
                    "diff": "diff --git a/foo b/foo\n+bar",
                    "modified": ["foo"],
                    "untracked": [],
                },
            )
        if request.method == "DELETE" and request.url.path == "/v1/labs/lab-1":
            return httpx.Response(200, json={"run_id": "lab-1", "status": "destroyed"})
        return httpx.Response(404)

    sb = LabManagerSandbox(
        run_id="lab-1",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )
    diff = sb.get_diff()
    assert diff["diff"] == "diff --git a/foo b/foo\n+bar"
    assert diff["modified"] == ["foo"]

    destroy = sb.destroy()
    assert destroy["status"] == "destroyed"


@pytest.mark.parametrize(
    "path",
    [
        "ordinary.txt",
        "/workspace/dir/a b'\"$;&.txt",
    ],
)
def test_lab_manager_file_transfer_quotes_paths(path: str):
    content = b"payload\x00with-bytes"
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        argv = shlex.split(body["command"])
        assert argv[:2] == ["python3", "-c"]
        observed_paths.append(argv[3])
        if "base64.b64encode" in argv[2]:
            return httpx.Response(
                200,
                json={
                    "exit_code": 0,
                    "stdout": base64.b64encode(content).decode("ascii"),
                    "stderr": "",
                },
            )
        assert base64.b64decode(argv[4]) == content
        return httpx.Response(200, json={"exit_code": 0, "stdout": "", "stderr": ""})

    sandbox = LabManagerSandbox(
        run_id="lab-files",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )

    upload = sandbox.upload_files([(path, content)])
    download = sandbox.download_files([path])

    assert upload[0].error is None
    assert download[0].error is None
    assert download[0].content == content
    assert observed_paths == [path, path]


def test_lab_manager_long_command_staging_failure_stops_execution():
    commands: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        command = json.loads(request.content)["command"]
        commands.append(command)
        exit_code = 19 if command.startswith("printf %s ") else 0
        return httpx.Response(
            200,
            json={"exit_code": exit_code, "stdout": "", "stderr": "stage failed"},
        )

    sandbox = LabManagerSandbox(
        run_id="lab-stage-fail",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )

    with pytest.raises(LabManagerError, match="staging append failed"):
        sandbox.execute("echo x\n" * 2000)

    assert any(command.startswith("rm -f ") for command in commands)
    assert not any(command.startswith("base64 -d ") for command in commands)


def test_overlapping_long_commands_use_distinct_staging_paths():
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    staging_paths: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        command = json.loads(request.content)["command"]
        if command.startswith("umask 077"):
            match = re.search(r"/tmp/open-swe-[a-f0-9]+\.b64", command)
            assert match is not None
            with lock:
                staging_paths.add(match.group(0))
            barrier.wait(timeout=5)
        return httpx.Response(200, json={"exit_code": 0, "stdout": "", "stderr": ""})

    sandbox = LabManagerSandbox(
        run_id="lab-overlap",
        base_url="http://test-server/v1",
        bearer_token="test-token",
        transport=_mock_transport(handler),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(sandbox.execute, ["echo a\n" * 2000, "echo b\n" * 2000]))

    assert [result.exit_code for result in results] == [0, 0]
    assert len(staging_paths) == 2
