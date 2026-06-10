"""SSH Docker runner 的本地包装进程。"""

from __future__ import annotations

import json
import os
import posixpath
import shlex
import stat
import sys
import time
from pathlib import Path
from typing import Any

import paramiko


EXCLUDED_DIRS = {".git", ".venv", "venv", "venv_old", "node_modules", "__pycache__"}


def main() -> int:
    config = json.loads(os.environ.get("AGENTHUB_SSH_DOCKER_CONFIG", "{}"))
    prompt = os.read(sys.stdin.fileno(), int(config.get("promptMaxBytes") or 4 * 1024 * 1024))
    client = _connect(config)
    try:
        sftp = client.open_sftp()
        local_workspace = Path(str(config["localWorkspacePath"]))
        remote_workspace = str(config["remoteWorkspacePath"])
        remote_root = str(config["remoteWorkspaceRoot"])
        _ensure_safe_remote_path(remote_workspace, remote_root)
        _exec_checked(client, f"rm -rf {shlex.quote(remote_workspace)} && mkdir -p {shlex.quote(remote_workspace)}")
        _upload_dir(sftp, local_workspace, remote_workspace)
        env_file = str(config.get("envFilePath") or "")
        env_vars = config.get("envVars") if isinstance(config.get("envVars"), dict) else {}
        if env_file and env_vars:
            _write_env_file(sftp, env_file, env_vars)
        exit_code = _run_docker(client, config, prompt)
        _download_dir(sftp, remote_workspace, local_workspace)
        if env_file:
            _exec_checked(client, f"rm -f {shlex.quote(env_file)}", check=False)
        return exit_code
    finally:
        client.close()


def _connect(config: dict[str, Any]) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=str(config["host"]),
        port=int(config.get("port") or 22),
        username=str(config.get("username") or "root"),
        password=str(config.get("password") or ""),
        timeout=15,
        banner_timeout=15,
        auth_timeout=15,
    )
    return client


def _run_docker(client: paramiko.SSHClient, config: dict[str, Any], prompt: bytes) -> int:
    command = shlex.join(str(item) for item in config["dockerArgs"])
    channel = client.get_transport().open_session()
    channel.exec_command(command)
    if prompt:
        channel.sendall(prompt)
    channel.shutdown_write()
    while True:
        if channel.recv_ready():
            sys.stdout.buffer.write(channel.recv(32768))
            sys.stdout.buffer.flush()
        if channel.recv_stderr_ready():
            sys.stderr.buffer.write(channel.recv_stderr(32768))
            sys.stderr.buffer.flush()
        if channel.exit_status_ready():
            while channel.recv_ready():
                sys.stdout.buffer.write(channel.recv(32768))
            while channel.recv_stderr_ready():
                sys.stderr.buffer.write(channel.recv_stderr(32768))
            sys.stdout.buffer.flush()
            sys.stderr.buffer.flush()
            return int(channel.recv_exit_status())
        time.sleep(0.02)


def _upload_dir(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir: str) -> None:
    _mkdir_p(sftp, remote_dir)
    for item in local_dir.iterdir():
        if item.is_dir() and item.name in EXCLUDED_DIRS:
            continue
        remote_path = posixpath.join(remote_dir, item.name)
        if item.is_dir():
            _upload_dir(sftp, item, remote_path)
        elif item.is_file():
            sftp.put(str(item), remote_path)


def _download_dir(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_dir):
        if entry.filename in EXCLUDED_DIRS:
            continue
        remote_path = posixpath.join(remote_dir, entry.filename)
        local_path = local_dir / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            _download_dir(sftp, remote_path, local_path)
        elif stat.S_ISREG(entry.st_mode):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote_path, str(local_path))


def _write_env_file(sftp: paramiko.SFTPClient, path: str, env_vars: dict[str, Any]) -> None:
    content = "".join(
        f"{key}={str(value).replace(chr(10), r'\\n').replace(chr(13), '')}\n"
        for key, value in sorted(env_vars.items())
        if str(key).strip()
    )
    with sftp.file(path, "w") as handle:
        handle.write(content)
    sftp.chmod(path, 0o600)


def _mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = [part for part in remote_dir.split("/") if part]
    current = "/"
    for part in parts:
        current = posixpath.join(current, part)
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def _exec_checked(client: paramiko.SSHClient, command: str, *, check: bool = True) -> str:
    _stdin, stdout, stderr = client.exec_command(command, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if check and code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"remote command failed: {code}")
    return out


def _ensure_safe_remote_path(remote_path: str, remote_root: str) -> None:
    root = posixpath.normpath(remote_root)
    path = posixpath.normpath(remote_path)
    if path == "/" or not path.startswith(root.rstrip("/") + "/"):
        raise RuntimeError("unsafe remote workspace path")


if __name__ == "__main__":
    raise SystemExit(main())
