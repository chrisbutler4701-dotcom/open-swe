import base64
import json
import pytest
import httpx
from deepagents.backends.protocol import ExecuteResponse
from agent.sandboxes.providers.registry import SandboxGoneError, create_sandbox
from agent.sandboxes.providers.lab_manager import (
    LabManagerSandbox,
    LabManagerError,
    create_lab_manager_sandbox,
)


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
