import uuid
import json
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app, lifespan
from app.database import get_db, AsyncSessionLocal
from app.models import AgentConfig, Project

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"

@pytest_asyncio.fixture(loop_scope="session")
async def _lifespan():
    """触发一次 FastAPI lifespan —— create_all + 迁移 + EventBus + 默认种子。"""
    async with lifespan(app):
        # 启用 WAL 模式以避免多连接写锁冲突
        from app.database import engine
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.commit()
        yield
    from app.database import engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def _cleanup_db():
    """每个测试结束后删除所有用户数据，确保隔离。"""
    yield
    from app.database import engine
    from sqlalchemy import text
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        for t in (
            "audit_logs",
            "workspace_restores",
            "workspace_imports",
            "workspace_snapshots",
            "build_logs",
            "context_pack_snapshots",
            "orchestrator_plans",
            "build_runs",
            "approval_checkpoints",
            "runtime_logs",
            "deployment_logs",
            "deployment_releases",
            "runtime_runs",
            "deployments",
            "deployment_targets",
            "preview_sessions",
            "run_processes",
            "run_tasks",
            "runs",
            "quota_usages",
            "sandboxes",
            "cli_credential_configs",
            "secrets",
            "comments",
            "attachments",
            "artifact_references",
            "notifications",
            "agent_template_sessions",
            "git_sync_jobs",
            "auth_sessions",
            "auth_identities",
            "workspace_volumes",
            "runner_nodes",
        ):
            try:
                await conn.execute(text(f"DELETE FROM {t}"))
            except Exception:
                pass
        for t in (
            "engine_sessions",
            "session_members",
            "artifacts",
            "messages",
            "sessions",
            "agent_configs",
            "projects",
            "workspaces",
            "team_members",
            "teams",
            "users",
        ):
            try:
                await conn.execute(text(f"DELETE FROM {t}"))
            except Exception:
                pass
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    # 重新种子默认 Agent（lifespan 只在 session 级别运行一次）
    async with AsyncSessionLocal() as s:
        from app.services.agent_seed import seed_default_cli_agents
        await seed_default_cli_agents(s)


@pytest_asyncio.fixture(loop_scope="function")
async def test_client(_lifespan, _cleanup_db):
    """主测试客户端 —— 文件 DB + 真实应用路由。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        from app.database import engine

        async with engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)

            async def override_get_db():
                yield session

            app.dependency_overrides[get_db] = override_get_db

            yield client

            app.dependency_overrides.clear()
            await session.close()


@pytest_asyncio.fixture(loop_scope="function")
async def db_session(test_client):
    """独立 DB session，用于 fixture 工厂 (test_agent, test_session)。"""
    from app.database import engine

    async with engine.connect() as conn:
        s = AsyncSession(bind=conn, expire_on_commit=False)
        yield s
        await s.close()


@pytest_asyncio.fixture
async def test_agent(db_session):
    cli = _ensure_fixture_cli()
    agent = AgentConfig(
        id=str(uuid.uuid4()),
        name="测试 Agent",
        description="测试",
        system_prompt="你是一个测试助手。",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps([str(cli)]),
        env_vars="{}",
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest_asyncio.fixture
async def test_session(test_client, db_session, test_agent):
    from app.models.session import Session

    project = Project(
        id=str(uuid.uuid4()),
        name="测试项目",
        workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
        status="ready",
    )
    Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
    sid = str(uuid.uuid4())
    sess = Session(
        id=sid,
        title="测试会话",
        project_id=project.id,
        agent_config_id=test_agent.id,
    )
    db_session.add(project)
    db_session.add(sess)
    await db_session.commit()
    return sid


def _ensure_fixture_cli() -> Path:
    script = BACKEND_ROOT / ".test-bin" / "fixture_cli.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "with open('.agenthub-cli-stdin.txt', 'w', encoding='utf-8') as f:\n"
        "    f.write(data)\n"
        "if 'WRITE_HTML_ARTIFACT' in data:\n"
        "    with open('index.html', 'w', encoding='utf-8') as f:\n"
        "        f.write('<!doctype html><html><body><main>Fixture Bridge</main></body></html>')\n"
        "    sys.stdout.write('created index.html')\n"
        "    sys.exit(0)\n"
        "if 'WRITE_FRONTEND_TREE' in data:\n"
        "    os.makedirs('src', exist_ok=True)\n"
        "    with open('package.json', 'w', encoding='utf-8') as f:\n"
        "        f.write('{\"scripts\":{\"dev\":\"vite\"},\"dependencies\":{\"@vitejs/plugin-react\":\"latest\"}}')\n"
        "    with open('src/App.tsx', 'w', encoding='utf-8') as f:\n"
        "        f.write('export default function App() { return <main>Tree</main>; }')\n"
        "    sys.stdout.write('created frontend tree')\n"
        "    sys.exit(0)\n"
        "if 'EMIT_HTML_BLOCK' in data:\n"
        "    sys.stdout.write('```html\\n<html><body><main>Group Artifact</main></body></html>\\n```')\n"
        "    sys.exit(0)\n"
        "sys.stdout.write('\\x1b[32mHello\\x1b[0m, World!')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script
