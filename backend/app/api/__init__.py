from fastapi import APIRouter
from .sessions import router as sessions_router
from .chat import router as chat_router
from .agents import router as agents_router
from .settings import router as settings_router
from .providers import router as providers_router

api_router = APIRouter(prefix="/api")
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(agents_router)
api_router.include_router(settings_router)
api_router.include_router(providers_router)

__all__ = ["api_router"]
