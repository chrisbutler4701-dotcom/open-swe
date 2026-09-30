import base64
import logging
import shlex
import uuid
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

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        if not file_path.startswith("/"):
            file_path = f"/workspace/{file_path}"
        return super().read(file_path, offset=offset, limit=limit)

    def write(self, file_path: str, content: str):
        if not file_path.startswith("/"):
            file_path = f"/workspace/{file_path}"
        return super().write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        if not file_path.startswith("/"):
            file_path = f"/workspace/{file_path}"
        return super().edit(file_path, old_string, new_string, replace_all=replace_all)

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        effective_timeout = timeout or self._default_timeout
        if len(command) <= 7500:
            return self._execute_remote(command, effective_timeout)

        stage_id = uuid.uuid4().hex
        encoded_path = f"/tmp/open-swe-{stage_id}.b64"
        script_path = f"/tmp/open-swe-{stage_id}.sh"
        quoted_encoded_path = shlex.quote(encoded_path)
        quoted_script_path = shlex.quote(script_path)
        encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
        chunks = [encoded[index : index + 3000] for index in range(0, len(encoded), 3000)]
        cleanup = f"rm -f {quoted_encoded_path} {quoted_script_path}"
        try:
            self._require_staging_success(
                self._execute_remote(
                    f"umask 077 && : > {quoted_encoded_path} && rm -f {quoted_script_path}",
                    30,
                ),
                "initialize",
            )
            for chunk in chunks:
                self._require_staging_success(
                    self._execute_remote(
                        f"printf %s {shlex.quote(chunk)} >> {quoted_encoded_path}", 30
                    ),
                    "append",
                )
        except Exception:
            try:
                cleanup_result = self._execute_remote(cleanup, 30)
                if cleanup_result.exit_code != 0:
                    logger.warning(
                        "Lab Manager staging cleanup failed",
                        extra={"run_id": self._run_id, "stage_id": stage_id},
                    )
            except Exception:
                logger.warning(
                    "Lab Manager staging cleanup request failed",
                    extra={"run_id": self._run_id, "stage_id": stage_id},
                    exc_info=True,
                )
            raise

        execute_staged = (
            f"base64 -d {quoted_encoded_path} > {quoted_script_path} && "
            f"chmod 700 {quoted_script_path} && bash {quoted_script_path}; "
            f"rc=$?; {cleanup}; exit $rc"
        )
        return self._execute_remote(execute_staged, effective_timeout)

    def _execute_remote(self, command: str, timeout: int) -> ExecuteResponse:
        url = f"/labs/{self._run_id}/exec"
        try:
            resp = self._client.post(
                url,
                json={"command": command, "timeout_seconds": timeout},
                timeout=float(timeout) + 30.0,
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
        output = stdout + (
            ("\n" if stdout and not stdout.endswith("\n") else "") + stderr if stderr else ""
        )
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=False)

    def _require_staging_success(self, response: ExecuteResponse, operation: str) -> None:
        if response.exit_code != 0:
            raise LabManagerError(
                f"Lab Manager command staging {operation} failed with exit "
                f"{response.exit_code}: {response.output[:200]}"
            )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                b64_content = base64.b64encode(content).decode("ascii")
                program = (
                    "import base64, os, sys; p = sys.argv[1]; "
                    "os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True); "
                    "open(p, 'wb').write(base64.b64decode(sys.argv[2]))"
                )
                script = (
                    f"python3 -c {shlex.quote(program)} {shlex.quote(path)} "
                    f"{shlex.quote(b64_content)}"
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
                program = (
                    "import base64, sys; p = sys.argv[1]; "
                    "sys.stdout.write(base64.b64encode(open(p, 'rb').read()).decode('ascii'))"
                )
                script = f"python3 -c {shlex.quote(program)} {shlex.quote(path)}"
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
    effective_base_url = (base_url or ENV.LAB_MANAGER_BASE_URL.get()).rstrip("/")
    effective_token = token or ENV.LAB_MANAGER_BEARER_TOKEN.get()

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
            logger.info(
                "Reattached to Lab Manager sandbox %s (status=%s)", sandbox_id, state.get("status")
            )
            return LabManagerSandbox(
                run_id=sandbox_id,
                base_url=effective_base_url,
                bearer_token=effective_token,
                transport=transport,
            )
        else:
            target_project = project or ENV.LAB_MANAGER_PROJECT.get()
            if not target_project:
                raise ValueError("Project key is required to create a Lab Manager sandbox")
            target_task = task or ENV.LAB_MANAGER_TASK.get()
            target_model = model or ENV.LAB_MANAGER_MODEL.get()
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
