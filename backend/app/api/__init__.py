from fastapi import APIRouter
from .sessions import router as sessions_router
from .chat import router as chat_router
from .agents import router as agents_router
from .artifacts import router as artifacts_router
from .messages import router as messages_router
from .projects import router as projects_router
from .skills import router as skills_router
from .debug import router as debug_router
from .orchestrator import router as orchestrator_router
from .runs import router as runs_router
from .approvals import router as approvals_router
from .context import router as context_router
from .system import router as system_router

api_router = APIRouter(prefix="/api")
api_router.include_router(projects_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(agents_router)
api_router.include_router(skills_router)
api_router.include_router(artifacts_router)
api_router.include_router(messages_router)
api_router.include_router(debug_router)
api_router.include_router(orchestrator_router)
api_router.include_router(runs_router)
api_router.include_router(approvals_router)
api_router.include_router(context_router)
api_router.include_router(system_router)

__all__ = ["api_router"]
