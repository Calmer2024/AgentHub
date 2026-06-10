#!/usr/bin/env python3
"""AgentHub 云端 CLI Runtime 入口。

容器以 root 启动，用于修正挂载 workspace 权限；真实 CLI 进程会降权到
agenthub 用户执行，避免 Claude Code 拒绝 root + dangerous flags 的组合。
"""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        return

    target_user = os.environ.get("AGENTHUB_RUNTIME_USER", "agenthub")
    if os.geteuid() == 0:
        try:
            user = pwd.getpwnam(target_user)
        except KeyError:
            os.execvp(sys.argv[1], sys.argv[1:])

        home = Path(user.pw_dir)
        workspace = Path(os.environ.get("AGENTHUB_WORKDIR", "/workspace"))
        _ensure_owned(home, user.pw_uid, user.pw_gid)
        _ensure_owned(workspace, user.pw_uid, user.pw_gid)

        os.environ["HOME"] = str(home)
        os.environ["USER"] = target_user
        os.environ["LOGNAME"] = target_user
        if workspace.exists():
            os.chdir(workspace)

        os.initgroups(target_user, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)

    os.execvp(sys.argv[1], sys.argv[1:])


def _ensure_owned(path: Path, uid: int, gid: int) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    _chown(path, uid, gid)
    if not path.is_dir():
        return
    for root, dirs, files in os.walk(path):
        for name in [*dirs, *files]:
            _chown(Path(root) / name, uid, gid)


def _chown(path: Path, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except OSError:
        pass


if __name__ == "__main__":
    main()
