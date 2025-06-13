from fastapi import APIRouter

from app.api.v1.endpoints import clips, health, analysis, tasks

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    clips.router, 
    prefix="/clips", 
    tags=["clips"],
    responses={
        500: {"description": "Internal server error"},
        400: {"description": "Bad request"}
    }
)

api_router.include_router(
    health.router, 
    prefix="/health", 
    tags=["health"],
    responses={
        500: {"description": "Internal server error"}
    }
)

api_router.include_router(
    analysis.router, 
    prefix="/analysis", 
    tags=["analysis"],
    responses={
        500: {"description": "Internal server error"},
        400: {"description": "Bad request"}
    }
)

api_router.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["tasks"],
    responses={
        500: {"description": "Internal server error"},
        404: {"description": "Task not found"}
    }
) 