import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, AsyncSessionLocal
from .api import api_router
from .api.ws import router as ws_router
from .models import AgentConfig
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
        from sqlalchemy import select
        result = await db.execute(select(AgentConfig).limit(1))
        if not result.scalars().first():
            db.add(AgentConfig(
                id=str(uuid.uuid4()),
                name="默认助手",
                description="通用对话助手，基于 DeepSeek V4 Flash",
                system_prompt="你是一个有帮助的 AI 助手。请用简洁清晰的方式回答用户的问题。",
                provider="deepseek",
                model="deepseek-v4-flash",
            ))
            await db.commit()

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
