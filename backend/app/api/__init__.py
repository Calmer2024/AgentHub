from fastapi import APIRouter
from .sessions import router as sessions_router
from .chat import router as chat_router

api_router = APIRouter(prefix="/api")
api_router.include_router(sessions_router)
api_router.include_router(chat_router)

__all__ = ["api_router"]
