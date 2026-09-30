
import base64
import logging
import shlex
from typing import Any

import httpx
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    SandboxBackendProtocol,
)
from deepagents.backends.sandbox import BaseSandbox

from agent.config import ENV
from agent.sandboxes.providers.registry import SandboxGoneError

logger = logging.getLogger(__name__)


class LabManagerError(RuntimeError):
    pass


class LabManagerSandbox(BaseSandbox):
    """Sandbox provider delegating execution to the Lab Manager REST API."""

    def __init__(
        self,
        run_id: str,
        base_url: str,
        bearer_token: str,
        *,
        default_timeout: int = 600,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._run_id = run_id
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._default_timeout = default_timeout
        self._transport = transport
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._bearer_token}"},
            timeout=float(default_timeout) + 30.0,
            transport=self._transport,
        )

    @property
    def id(self) -> str:
        return self._run_id

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        effective_timeout = timeout or self._default_timeout
        url = f"/labs/{self._run_id}/exec"

        if len(command) > 7500:
            import base64
            b64 = base64.b64encode(command.encode("utf-8")).decode("ascii")
            chunk_size = 3000
            chunks = [b64[i : i + chunk_size] for i in range(0, len(b64), chunk_size)]
            try:
                self._client.post(
                    url,
                    json={"command": "rm -f /tmp/_lm_b64 /tmp/_lm_cmd.sh"},
                    timeout=30.0,
                )
                for chunk in chunks:
                    self._client.post(
                        url,
                        json={"command": f"printf '%s' '{chunk}' >> /tmp/_lm_b64"},
                        timeout=30.0,
                    )
                exec_cmd = (
                    "base64 -d /tmp/_lm_b64 > /tmp/_lm_cmd.sh && chmod +x /tmp/_lm_cmd.sh && "
                    "bash /tmp/_lm_cmd.sh; rc=$?; rm -f /tmp/_lm_b64 /tmp/_lm_cmd.sh; exit $rc"
                )
                payload = {
                    "command": exec_cmd,
                    "timeout_seconds": effective_timeout,
                }
            except httpx.RequestError as exc:
                raise LabManagerError(f"Lab Manager request failed: {exc}") from exc
        else:
            payload = {
                "command": command,
                "timeout_seconds": effective_timeout,
            }

        try:
            resp = self._client.post(
                url,
                json=payload,
                timeout=float(effective_timeout) + 30.0,
            )
        except httpx.RequestError as exc:
            raise LabManagerError(f"Lab Manager request failed: {exc}") from exc

        if resp.status_code == 404:
            raise SandboxGoneError(f"Lab {self._run_id} not found on Lab Manager (404)")
        if resp.status_code == 410:
            raise SandboxGoneError(f"Lab {self._run_id} has been destroyed (410)")
        if resp.status_code != 200:
            raise LabManagerError(
                f"Lab Manager exec returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        exit_code = int(data.get("exit_code", 1))
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        output = stdout + (("\n" if stdout and not stdout.endswith("\n") else "") + stderr if stderr else "")
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                b64_content = base64.b64encode(content).decode("ascii")
                script = (
                    f"python3 -c \"import base64, os, sys; "
                    f"p = {shlex.quote(path)}; "
                    f"os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True); "
                    f"open(p, \x27wb\x27).write(base64.b64decode({shlex.quote(b64_content)}))\""
                )
                res = self.execute(script)
                if res.exit_code == 0:
                    responses.append(FileUploadResponse(path=path, error=None))
                else:
                    responses.append(
                        FileUploadResponse(
                            path=path,
                            error=f"Write failed: {res.output[:200]}",
                        )
                    )
            except Exception as exc:
                responses.append(FileUploadResponse(path=path, error=str(exc)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                script = (
                    f"python3 -c \"import base64, sys, os; "
                    f"p = {shlex.quote(path)}; "
                    f"sys.stdout.write(base64.b64encode(open(p, \x27rb\x27).read()).decode(\x27ascii\x27))\""
                )
                res = self.execute(script)
                if res.exit_code == 0:
                    raw_bytes = base64.b64decode(res.output.strip())
                    responses.append(FileDownloadResponse(path=path, content=raw_bytes, error=None))
                else:
                    responses.append(
                        FileDownloadResponse(
                            path=path,
                            content=None,
                            error=f"Read failed: {res.output[:200]}",
                        )
                    )
            except Exception as exc:
                responses.append(FileDownloadResponse(path=path, content=None, error=str(exc)))
        return responses

    def get_diff(self) -> dict[str, Any]:
        resp = self._client.get(f"/labs/{self._run_id}/diff")
        if resp.status_code != 200:
            raise LabManagerError(f"Failed to fetch diff: HTTP {resp.status_code}")
        return resp.json()

    def get_status(self) -> dict[str, Any]:
        resp = self._client.get(f"/labs/{self._run_id}")
        if resp.status_code == 404:
            raise SandboxGoneError(f"Lab {self._run_id} not found")
        if resp.status_code != 200:
            raise LabManagerError(f"Failed to fetch lab status: HTTP {resp.status_code}")
        return resp.json()

    def destroy(self) -> dict[str, Any]:
        resp = self._client.delete(f"/labs/{self._run_id}")
        if resp.status_code not in (200, 404):
            raise LabManagerError(f"Failed to destroy lab: HTTP {resp.status_code}")
        return resp.json() if resp.status_code == 200 else {"status": "destroyed"}

    def close(self) -> None:
        self._client.close()


def create_lab_manager_sandbox(
    sandbox_id: str | None = None,
    *,
    base_url: str | None = None,
    token: str | None = None,
    project: str | None = None,
    task: str | None = None,
    model: str | None = None,
    ref: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> SandboxBackendProtocol:
    effective_base_url = (
        base_url
        or ENV.get("LAB_MANAGER_BASE_URL", "http://172.18.0.1:8090/v1")
    ).rstrip("/")
    effective_token = (
        token
        or ENV.get("LAB_MANAGER_BEARER_TOKEN", "")
    )

    if not effective_token:
        raise ValueError("LAB_MANAGER_BEARER_TOKEN is required for lab_manager provider")

    client = httpx.Client(
        base_url=effective_base_url,
        headers={"Authorization": f"Bearer {effective_token}"},
        timeout=30.0,
        transport=transport,
    )

    try:
        if sandbox_id:
            resp = client.get(f"/labs/{sandbox_id}")
            if resp.status_code == 404:
                raise SandboxGoneError(f"Lab {sandbox_id} was not found on Lab Manager")
            if resp.status_code != 200:
                raise LabManagerError(
                    f"Lab Manager returned HTTP {resp.status_code} while checking lab {sandbox_id}"
                )
            state = resp.json()
            if state.get("status") == "destroyed":
                raise SandboxGoneError(f"Lab {sandbox_id} has been destroyed")
            logger.info("Reattached to Lab Manager sandbox %s (status=%s)", sandbox_id, state.get("status"))
            return LabManagerSandbox(
                run_id=sandbox_id,
                base_url=effective_base_url,
                bearer_token=effective_token,
                transport=transport,
            )
        else:
            target_project = project or ENV.get("LAB_MANAGER_PROJECT", "")
            if not target_project:
                raise ValueError("Project key is required to create a Lab Manager sandbox")
            target_task = task or ENV.get("LAB_MANAGER_TASK", "oswe-0-trial")
            target_model = model or ENV.get("LAB_MANAGER_MODEL", "open-swe-worker")
            create_payload: dict[str, Any] = {
                "project": target_project,
                "task": target_task,
                "model": target_model,
            }
            if ref:
                create_payload["ref"] = ref

            resp = client.post("/labs", json=create_payload)
            if resp.status_code != 200:
                raise LabManagerError(
                    f"Failed to create lab on Lab Manager: HTTP {resp.status_code}: {resp.text[:300]}"
                )
            state = resp.json()
            run_id = state["run_id"]
            logger.info("Created Lab Manager sandbox %s for project %s", run_id, target_project)
            return LabManagerSandbox(
                run_id=run_id,
                base_url=effective_base_url,
                bearer_token=effective_token,
                transport=transport,
            )
    finally:
        client.close()
