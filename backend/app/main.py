import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, AsyncSessionLocal
from .api import api_router
from .api.ws import router as ws_router
from .models import AgentConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：已有数据库添加缺失列
        for sql in [
            "ALTER TABLE sessions ADD COLUMN agent_config_id VARCHAR",
            "ALTER TABLE sessions ADD COLUMN model_name VARCHAR",
            "ALTER TABLE sessions ADD COLUMN mode VARCHAR DEFAULT 'single'",
            "ALTER TABLE sessions ADD COLUMN is_active VARCHAR DEFAULT '1'",
            "ALTER TABLE messages ADD COLUMN agent_name VARCHAR",
        ]:
            try:
                await conn.run_sync(lambda c, s=sql: c.exec_driver_sql(s))
            except Exception:
                pass

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
