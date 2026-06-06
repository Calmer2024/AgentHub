from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, AsyncSessionLocal
from .api import api_router
from .api.ws import router as ws_router
from .event_bus import InMemoryEventBus

_event_bus = InMemoryEventBus()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
        from migrations.migration_runner import run as run_migrations
        await run_migrations(conn)

    await _event_bus.start()

    async with AsyncSessionLocal() as db:
        from .services.project_service import ProjectService
        from .services.agent_seed import seed_default_cli_agents
        await ProjectService(db, event_bus=_event_bus).attach_legacy_sessions_to_default_project()
        await seed_default_cli_agents(db)

    yield

    await _event_bus.stop()


app = FastAPI(title="AgentHub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"message": "AgentHub API is running"}
