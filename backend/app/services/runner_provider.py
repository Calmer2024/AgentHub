"""Phase 15 RunnerProvider：隔离运行时的可替换后端。"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.process_utils import hidden_subprocess_kwargs
from ..core.timezone import china_now
from ..models import RunnerNode, Sandbox, WorkspaceVolume
from .cloud_storage import cloud_workspace_path, ensure_cloud_workspace
from .phase10_schemas import RuntimeImageListRead, RuntimeImageRead, RunnerNodeListRead, RunnerNodeRead
from .quota_service import parse_resource_limits


class RunnerProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxRequest:
    sandbox_id: str
    workspace_id: str
    image: str
    resource_limits: dict[str, Any]
    region: str


@dataclass(frozen=True)
class RunnerSandboxHandle:
    provider: str
    external_id: str
    runner_node_id: str
    workspace_path: str
    container_workspace_path: str
    region: str


@dataclass(frozen=True)
class RunnerProcessSpec:
    agent: Any
    workspace_path: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class WorkspaceSyncResult:
    changed_files: list[dict[str, Any]]
    disk_bytes: int


class RunnerProvider(Protocol):
    name: str
    requires_fresh_sandbox: bool

    async def create_sandbox(self, request: SandboxRequest) -> RunnerSandboxHandle:
        ...

    async def prepare_process(
        self,
        *,
        sandbox: Sandbox,
        agent: Any,
        run_id: str,
        workspace_path: str,
    ) -> RunnerProcessSpec:
        ...

    async def cancel(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        ...

    async def dispose(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        ...

    async def health(self) -> dict[str, Any]:
        ...


class LocalDevRunnerProvider:
    name = "local_dev"
    requires_fresh_sandbox = False

    async def create_sandbox(self, request: SandboxRequest) -> RunnerSandboxHandle:
        workspace_path = ensure_cloud_workspace(request.workspace_id, {"phase": "phase15-local-dev"})
        return RunnerSandboxHandle(
            provider=self.name,
            external_id=f"local-dev-{request.sandbox_id}",
            runner_node_id=settings.agenthub_cloud_runner_node_id,
            workspace_path=str(workspace_path),
            container_workspace_path=str(workspace_path),
            region=settings.agenthub_runner_region,
        )

    async def prepare_process(
        self,
        *,
        sandbox: Sandbox,
        agent: Any,
        run_id: str,
        workspace_path: str,
    ) -> RunnerProcessSpec:
        del sandbox, run_id
        return RunnerProcessSpec(
            agent=agent,
            workspace_path=workspace_path,
            metadata={"provider": self.name, "workspaceMount": "local_dev"},
        )

    async def cancel(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del sandbox, run_id, reason

    async def dispose(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del sandbox, run_id, reason

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": self.name}


class DockerRunnerProvider:
    name = "docker"
    requires_fresh_sandbox = True
    container_workspace_path = "/workspace"

    async def create_sandbox(self, request: SandboxRequest) -> RunnerSandboxHandle:
        await self._check_docker()
        workspace_path = ensure_cloud_workspace(request.workspace_id, {"phase": "phase15-docker"})
        return RunnerSandboxHandle(
            provider=self.name,
            external_id=f"agenthub-sbx-{request.sandbox_id}",
            runner_node_id=settings.agenthub_cloud_runner_node_id,
            workspace_path=str(workspace_path),
            container_workspace_path=self.container_workspace_path,
            region=settings.agenthub_runner_region,
        )

    async def prepare_process(
        self,
        *,
        sandbox: Sandbox,
        agent: Any,
        run_id: str,
        workspace_path: str,
    ) -> RunnerProcessSpec:
        container_name = self._container_name(sandbox, run_id)
        container_env = _json_dict(getattr(agent, "env_vars", "{}"))
        original_args = _json_list(getattr(agent, "init_args", "[]"))
        executable = self._container_executable(getattr(agent, "executable", "") or "")
        limits = parse_resource_limits(sandbox.resource_limits_json)
        env_file_path = _write_runner_env_file(run_id, container_env) if container_env else None
        docker_args = [
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "--label",
            f"agenthub.sandbox_id={sandbox.id}",
            "--label",
            f"agenthub.run_id={run_id}",
            "--network",
            _network_policy(),
            "--memory",
            f"{int(limits.get('memoryMb') or settings.agenthub_cloud_memory_mb)}m",
            "--cpus",
            str(float(settings.agenthub_runner_cpu or 1.0)),
            "--pids-limit",
            "128",
            "--workdir",
            self.container_workspace_path,
            "--mount",
            f"type=bind,source={Path(workspace_path).resolve()},target={self.container_workspace_path}",
            "--mount",
            f"type=bind,source={Path(workspace_path).resolve()},target=/tmp/opencode",
        ]
        if env_file_path:
            docker_args.extend(["--env-file", env_file_path])
        docker_args.extend([sandbox.image, executable])
        docker_args.extend(original_args)

        docker_env = {}
        if settings.agenthub_runner_docker_host.strip():
            docker_env["DOCKER_HOST"] = settings.agenthub_runner_docker_host.strip()

        return RunnerProcessSpec(
            agent=_copy_agent(
                agent,
                cli_tool=getattr(agent, "cli_tool", "custom"),
                executable=settings.agenthub_runner_docker_binary,
                init_args=json.dumps(docker_args, ensure_ascii=False),
                env_vars=json.dumps(docker_env, ensure_ascii=False),
                close_stdin_after_prompt=True,
                prepared_invocation=True,
            ),
            workspace_path=workspace_path,
            metadata={
                "provider": self.name,
                "containerName": container_name,
                "containerWorkspacePath": self.container_workspace_path,
                "network": _network_policy(),
                "resourceLimits": limits,
            },
        )

    async def cancel(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del reason
        try:
            await self._docker_rm(sandbox, run_id)
        finally:
            _remove_runner_env_file(run_id)

    async def dispose(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del reason
        try:
            await self._docker_rm(sandbox, run_id)
        finally:
            _remove_runner_env_file(run_id)

    async def health(self) -> dict[str, Any]:
        try:
            version = await self._docker_output("version", "--format", "{{.Server.Version}}")
            return {"status": "healthy", "provider": self.name, "version": version.strip()}
        except RunnerProviderError as exc:
            return {"status": "unavailable", "provider": self.name, "error": str(exc)}

    async def _check_docker(self) -> None:
        await self._docker_output("version", "--format", "{{.Server.Version}}")

    async def _docker_rm(self, sandbox: Sandbox, run_id: str | None) -> None:
        names = [self._container_name(sandbox, run_id)] if run_id else []
        if not names and sandbox.external_id:
            names.append(str(sandbox.external_id))
        for name in names:
            await self._docker_output("rm", "-f", name, check=False)

    async def _docker_output(self, *args: str, check: bool = True) -> str:
        env = None
        if settings.agenthub_runner_docker_host.strip():
            env = os.environ.copy()
            env["DOCKER_HOST"] = settings.agenthub_runner_docker_host.strip()
        proc = await asyncio.create_subprocess_exec(
            settings.agenthub_runner_docker_binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            **hidden_subprocess_kwargs(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if check and proc.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip() or "docker command failed"
            raise RunnerProviderError(detail)
        return stdout.decode("utf-8", errors="replace")

    def _container_name(self, sandbox: Sandbox, run_id: str | None) -> str:
        suffix = (run_id or "manual")[:12]
        return f"agenthub-{sandbox.id[:12]}-{suffix}"

    def _container_executable(self, executable: str) -> str:
        name = Path(executable).name.lower()
        if name in {"python.exe", "python3.exe", "python"}:
            return "python"
        if name in {"python3"}:
            return "python3"
        return executable.strip() or "sh"


class SshDockerRunnerProvider(DockerRunnerProvider):
    name = "ssh_docker"

    async def create_sandbox(self, request: SandboxRequest) -> RunnerSandboxHandle:
        await self._check_remote_docker()
        workspace_path = ensure_cloud_workspace(request.workspace_id, {"phase": "phase15-ssh-docker"})
        remote_workspace = self._remote_workspace_path(request.workspace_id)
        await self._ssh_output(f"mkdir -p {shlex.quote(remote_workspace)}")
        return RunnerSandboxHandle(
            provider=self.name,
            external_id=f"agenthub-sbx-{request.sandbox_id}",
            runner_node_id=settings.agenthub_cloud_runner_node_id,
            workspace_path=str(workspace_path),
            container_workspace_path=self.container_workspace_path,
            region=settings.agenthub_runner_region,
        )

    async def prepare_process(
        self,
        *,
        sandbox: Sandbox,
        agent: Any,
        run_id: str,
        workspace_path: str,
    ) -> RunnerProcessSpec:
        container_name = self._container_name(sandbox, run_id)
        container_env = _json_dict(getattr(agent, "env_vars", "{}"))
        original_args = _json_list(getattr(agent, "init_args", "[]"))
        executable = self._container_executable(getattr(agent, "executable", "") or "")
        limits = parse_resource_limits(sandbox.resource_limits_json)
        remote_workspace = self._remote_workspace_path(sandbox.workspace_id)
        env_file_path = f"/tmp/agenthub-env-{run_id}.env"
        docker_args = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "--label",
            f"agenthub.sandbox_id={sandbox.id}",
            "--label",
            f"agenthub.run_id={run_id}",
            "--network",
            _network_policy(),
            "--memory",
            f"{int(limits.get('memoryMb') or settings.agenthub_cloud_memory_mb)}m",
            "--cpus",
            str(float(settings.agenthub_runner_cpu or 1.0)),
            "--pids-limit",
            "128",
            "--workdir",
            self.container_workspace_path,
            "--mount",
            f"type=bind,source={remote_workspace},target={self.container_workspace_path}",
            "--mount",
            f"type=bind,source={remote_workspace},target=/tmp/opencode",
        ]
        if container_env:
            docker_args.extend(["--env-file", env_file_path])
        docker_args.extend([sandbox.image, executable])
        docker_args.extend(original_args)

        config = {
            "host": settings.agenthub_runner_ssh_host.strip(),
            "port": settings.agenthub_runner_ssh_port,
            "username": settings.agenthub_runner_ssh_user.strip() or "root",
            "password": settings.agenthub_runner_ssh_password,
            "localWorkspacePath": workspace_path,
            "remoteWorkspaceRoot": settings.agenthub_runner_ssh_workspace_root,
            "remoteWorkspacePath": remote_workspace,
            "envFilePath": env_file_path,
            "envVars": container_env,
            "dockerArgs": docker_args,
            "promptMaxBytes": 4 * 1024 * 1024,
        }
        entry = Path(__file__).with_name("ssh_docker_runner_entry.py").resolve()
        return RunnerProcessSpec(
            agent=_copy_agent(
                agent,
                cli_tool=getattr(agent, "cli_tool", "custom"),
                executable=sys.executable,
                init_args=json.dumps([str(entry)], ensure_ascii=False),
                env_vars=json.dumps({"AGENTHUB_SSH_DOCKER_CONFIG": json.dumps(config, ensure_ascii=False)}, ensure_ascii=False),
                close_stdin_after_prompt=True,
                prepared_invocation=True,
            ),
            workspace_path=workspace_path,
            metadata={
                "provider": self.name,
                "containerName": container_name,
                "containerWorkspacePath": self.container_workspace_path,
                "remoteHost": config["host"],
                "remoteWorkspacePath": f"cloud-volume://agenthub/{self.name}/{sandbox.workspace_id}",
                "network": _network_policy(),
                "resourceLimits": limits,
            },
        )

    async def cancel(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del reason
        await self._remote_docker_rm(sandbox, run_id)

    async def dispose(self, sandbox: Sandbox, *, run_id: str | None = None, reason: str | None = None) -> None:
        del reason
        await self._remote_docker_rm(sandbox, run_id)

    async def health(self) -> dict[str, Any]:
        try:
            version = await self._ssh_output("docker version --format '{{.Server.Version}}'")
            return {"status": "healthy", "provider": self.name, "version": version.strip()}
        except RunnerProviderError as exc:
            return {"status": "unavailable", "provider": self.name, "error": str(exc)}

    async def _check_remote_docker(self) -> None:
        await self._ssh_output("docker version --format '{{.Server.Version}}'")

    async def _remote_docker_rm(self, sandbox: Sandbox, run_id: str | None) -> None:
        names = [self._container_name(sandbox, run_id)] if run_id else []
        if not names and sandbox.external_id:
            names.append(str(sandbox.external_id))
        for name in names:
            await self._ssh_output(f"docker rm -f {shlex.quote(name)}", check=False)

    async def _ssh_output(self, command: str, *, check: bool = True, timeout: int = 30) -> str:
        return await asyncio.to_thread(self._ssh_output_sync, command, check=check, timeout=timeout)

    def _ssh_output_sync(self, command: str, *, check: bool, timeout: int) -> str:
        host = settings.agenthub_runner_ssh_host.strip()
        if not host:
            raise RunnerProviderError("AGENTHUB_RUNNER_SSH_HOST is required")
        try:
            import paramiko

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=host,
                port=int(settings.agenthub_runner_ssh_port or 22),
                username=settings.agenthub_runner_ssh_user.strip() or "root",
                password=settings.agenthub_runner_ssh_password,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
            client.close()
        except Exception as exc:
            raise RunnerProviderError(f"ssh docker runner unavailable: {type(exc).__name__}: {exc}") from exc
        if check and code != 0:
            raise RunnerProviderError(err.strip() or out.strip() or "remote docker command failed")
        return out

    def _remote_workspace_path(self, workspace_id: str) -> str:
        safe_workspace = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in workspace_id)
        root = settings.agenthub_runner_ssh_workspace_root.rstrip("/") or "/tmp/agenthub/workspaces"
        return f"{root}/{safe_workspace}"


def get_runner_provider() -> RunnerProvider:
    provider = settings.agenthub_runner_provider.strip().lower()
    if provider in {"ssh_docker", "remote_docker"}:
        return SshDockerRunnerProvider()
    if provider == "docker":
        return DockerRunnerProvider()
    return LocalDevRunnerProvider()


async def ensure_runner_node(db: AsyncSession, provider: RunnerProvider | None = None) -> RunnerNode:
    provider = provider or get_runner_provider()
    node_id = settings.agenthub_cloud_runner_node_id
    node = await db.get(RunnerNode, node_id)
    now = china_now()
    capacity = {
        "concurrentRuns": settings.agenthub_cloud_concurrent_runs,
        "runtimeSeconds": settings.agenthub_cloud_runtime_seconds,
        "memoryMb": settings.agenthub_cloud_memory_mb,
        "diskMb": settings.agenthub_cloud_disk_mb,
        "network": _network_policy(),
    }
    health = await provider.health()
    if not node:
        node = RunnerNode(
            id=node_id,
            provider=provider.name,
            region=settings.agenthub_runner_region,
            status=str(health.get("status") or "unknown"),
            capacity_json=json.dumps(capacity, ensure_ascii=False),
            last_heartbeat_at=now,
            created_at=now,
        )
        db.add(node)
    else:
        node.provider = provider.name
        node.region = settings.agenthub_runner_region
        node.status = str(health.get("status") or "unknown")
        node.capacity_json = json.dumps(capacity, ensure_ascii=False)
        node.last_heartbeat_at = now
    await db.commit()
    await db.refresh(node)
    return node


async def ensure_workspace_volume(db: AsyncSession, workspace_id: str, *, provider: str) -> WorkspaceVolume:
    result = await db.execute(
        select(WorkspaceVolume).where(
            WorkspaceVolume.workspace_id == workspace_id,
            WorkspaceVolume.storage_provider == provider,
        )
    )
    volume = result.scalars().first()
    now = china_now()
    storage_uri = f"cloud-volume://agenthub/{provider}/{workspace_id}"
    if provider == "local_dev":
        storage_uri = str(cloud_workspace_path(workspace_id))
    if not volume:
        volume = WorkspaceVolume(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            storage_provider=provider,
            storage_uri=storage_uri,
            status="ready",
            last_synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(volume)
    else:
        volume.status = "ready"
        volume.storage_uri = storage_uri
        volume.last_synced_at = now
        volume.updated_at = now
    await db.commit()
    await db.refresh(volume)
    return volume


async def list_runner_nodes(db: AsyncSession) -> RunnerNodeListRead:
    await ensure_runner_node(db)
    result = await db.execute(select(RunnerNode).order_by(RunnerNode.created_at.desc()))
    return RunnerNodeListRead(items=[_runner_node_to_read(node) for node in result.scalars().all()])


def list_runtime_images() -> RuntimeImageListRead:
    configured = [
        item.strip()
        for item in (settings.agenthub_runtime_images or "").split(",")
        if item.strip()
    ]
    images = configured or [settings.agenthub_runtime_image]
    return RuntimeImageListRead(items=[
        RuntimeImageRead(
            id=f"runtime-image-{index + 1}",
            label="默认 CLI Runtime" if index == 0 else f"CLI Runtime {index + 1}",
            image=image,
            provider=get_runner_provider().name,
            default=index == 0,
            tools=_image_tools(image),
        )
        for index, image in enumerate(images)
    ])


def collect_workspace_sync(workspace_path: str, changed_files: list[dict[str, Any]]) -> WorkspaceSyncResult:
    return WorkspaceSyncResult(
        changed_files=changed_files,
        disk_bytes=_safe_disk_bytes(workspace_path),
    )


def workspace_path_for_sandbox(sandbox: Sandbox) -> str:
    return str(ensure_cloud_workspace(sandbox.workspace_id, {
        "phase": "phase15",
        "sandboxId": sandbox.id,
    }))


def _safe_disk_bytes(workspace_path: str) -> int:
    try:
        return sum(
            path.stat().st_size
            for path in Path(workspace_path).rglob("*")
            if path.is_file()
        )
    except OSError:
        return 0


def _runner_node_to_read(node: RunnerNode) -> RunnerNodeRead:
    try:
        capacity = json.loads(node.capacity_json or "{}")
    except json.JSONDecodeError:
        capacity = {}
    return RunnerNodeRead(
        id=node.id,
        provider=node.provider,
        region=node.region,
        status=node.status,
        capacity=capacity if isinstance(capacity, dict) else {},
        last_heartbeat_at=node.last_heartbeat_at,
        created_at=node.created_at,
    )


def _copy_agent(agent: Any, **overrides: Any) -> Any:
    values = {
        "id": getattr(agent, "id", ""),
        "name": getattr(agent, "name", ""),
        "description": getattr(agent, "description", None),
        "system_prompt": getattr(agent, "system_prompt", ""),
        "rules": getattr(agent, "rules", ""),
        "agent_type": getattr(agent, "agent_type", "cli_wrapper"),
        "cli_tool": getattr(agent, "cli_tool", "custom"),
        "executable": getattr(agent, "executable", ""),
        "init_args": getattr(agent, "init_args", "[]"),
        "env_vars": getattr(agent, "env_vars", "{}"),
        "primary_skill": getattr(agent, "primary_skill", None),
        "auxiliary_skills": getattr(agent, "auxiliary_skills", "[]"),
        "toolset": getattr(agent, "toolset", "[]"),
        "context_policy": getattr(agent, "context_policy", "workspace_coding"),
        "close_stdin_after_prompt": getattr(agent, "close_stdin_after_prompt", False),
        "prepared_invocation": getattr(agent, "prepared_invocation", False),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_dict(raw: str | None) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key)}


def _write_runner_env_file(run_id: str, env_vars: dict[str, str]) -> str:
    root = Path(tempfile.gettempdir()) / "agenthub-runner-env"
    root.mkdir(parents=True, exist_ok=True)
    path = _runner_env_file_path(run_id)
    lines = [
        f"{key}={_sanitize_env_file_value(value)}"
        for key, value in sorted(env_vars.items())
        if _is_valid_env_key(key) and value
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


def _runner_env_file_path(run_id: str | None) -> Path:
    safe_run_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in (run_id or "manual"))
    return Path(tempfile.gettempdir()) / "agenthub-runner-env" / f"{safe_run_id}.env"


def _remove_runner_env_file(run_id: str | None) -> None:
    if not run_id:
        return
    try:
        _runner_env_file_path(run_id).unlink(missing_ok=True)
    except OSError:
        pass


def _is_valid_env_key(key: str) -> bool:
    if not key:
        return False
    first = key[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)


def _sanitize_env_file_value(value: str) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _network_policy() -> str:
    value = settings.agenthub_runner_network_policy.strip().lower()
    return "bridge" if value == "bridge" else "none"


def _image_tools(image: str) -> list[str]:
    lower = image.lower()
    tools = []
    for name in ("claude", "codex", "opencode", "python", "node"):
        if name in lower:
            tools.append(name)
    return tools or ["custom-cli"]
